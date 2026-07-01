"""Unit tests for the Google Gemini chat client (Vertex mapping + parsing) and
its routing wiring.

A fake google-genai client is injected, so the suite never imports the SDK, makes
a network call, or needs gcloud/ADC — the conversion + routing logic is what's
under test, not Vertex itself.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from aios.api.main import _select_chat_client, models_gemini
from aios.core.gemini import (
    CURATED_MODELS,
    GeminiClient,
    _parse_output,
    _to_gemini,
    _to_tools,
)
from aios.core.llm import LLMError

pytestmark = [pytest.mark.cloud]


# --- Fakes that mimic the google-genai response/object shape ----------------
class _FnCall:
    def __init__(self, name: str, args: dict) -> None:
        self.name = name
        self.args = args


class _Part:
    def __init__(self, *, text=None, function_call=None) -> None:
        self.text = text
        self.function_call = function_call


class _Content:
    def __init__(self, parts: list) -> None:
        self.parts = parts


class _Candidate:
    def __init__(self, content: _Content) -> None:
        self.content = content


class _Response:
    def __init__(self, candidates: list) -> None:
        self.candidates = candidates


class _Model:
    def __init__(self, name: str, display_name=None) -> None:
        self.name = name
        self.display_name = display_name


class _FakeModels:
    """Stub ``client.models``: records generate_content kwargs, returns canned replies."""

    def __init__(self, response, listing, stream=None) -> None:
        self._response = response
        self._listing = listing
        self._stream = stream or []
        self.last: dict | None = None
        self.stream_last: dict | None = None

    def generate_content(self, **kwargs):
        self.last = kwargs
        return self._response

    def generate_content_stream(self, **kwargs):
        self.stream_last = kwargs
        return self._stream

    def list(self):
        return self._listing


class FakeGemini:
    def __init__(self, response, listing=None, stream=None) -> None:
        self.models = _FakeModels(response, listing or [], stream=stream)


# --- Message conversion -----------------------------------------------------
def test_to_gemini_splits_system_and_pairs_tools_by_name() -> None:
    system, contents = _to_gemini([
        {"role": "system", "content": "you are an agent"},
        {"role": "user", "content": "list files"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "execute_terminal", "arguments": {"command": "ls"}}}]},
        {"role": "tool", "content": "ran: ls"},
    ])
    assert system == "you are an agent"
    assert contents[0] == {"role": "user", "parts": [{"text": "list files"}]}
    model_msg = contents[1]
    assert model_msg["role"] == "model"
    fc = model_msg["parts"][-1]["function_call"]
    assert fc["name"] == "execute_terminal"
    assert fc["args"] == {"command": "ls"}
    fr = contents[2]["parts"][0]["function_response"]
    assert contents[2]["role"] == "user"
    assert fr["name"] == "execute_terminal"          # result paired to its call by NAME
    assert fr["response"] == {"result": "ran: ls"}


def test_to_gemini_coerces_stringified_arguments() -> None:
    _, contents = _to_gemini([
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "read_file", "arguments": '{"filepath": "a.py"}'}}]},
    ])
    assert contents[0]["parts"][0]["function_call"]["args"] == {"filepath": "a.py"}


def test_to_tools_maps_function_specs() -> None:
    decls = _to_tools([
        {"type": "function", "function": {
            "name": "read_file", "description": "read it",
            "parameters": {"type": "object", "properties": {"filepath": {"type": "string"}},
                           "required": ["filepath"]},
        }}
    ])
    fd = decls[0]["function_declarations"][0]
    assert fd["name"] == "read_file"
    assert fd["description"] == "read it"
    assert fd["parameters"]["properties"]["filepath"]["type"] == "string"


def test_to_tools_none_when_empty() -> None:
    assert _to_tools(None) is None
    assert _to_tools([]) is None


# --- Response parsing -------------------------------------------------------
def test_parse_output_extracts_text_and_tool_calls() -> None:
    resp = _Response([_Candidate(_Content([
        _Part(text="On it."),
        _Part(function_call=_FnCall("execute_terminal", {"command": "pip install flask"})),
    ]))])
    parsed = _parse_output(resp)
    assert parsed["content"] == "On it."
    assert parsed["tool_calls"][0]["function"]["name"] == "execute_terminal"
    assert parsed["tool_calls"][0]["function"]["arguments"] == {"command": "pip install flask"}


def test_parse_output_text_only_has_no_tool_calls() -> None:
    resp = _Response([_Candidate(_Content([_Part(text="just words")]))])
    assert _parse_output(resp) == {"role": "assistant", "content": "just words"}


def test_parse_output_empty_candidates_is_empty_assistant() -> None:
    assert _parse_output(_Response([])) == {"role": "assistant", "content": ""}


# --- chat() round trip ------------------------------------------------------
def test_chat_calls_generate_content_and_returns_agent_shape() -> None:
    resp = _Response([_Candidate(_Content([
        _Part(function_call=_FnCall("execute_terminal", {"command": "pip install flask"})),
    ]))])
    fake = FakeGemini(resp)
    client = GeminiClient(model="gemini-x", project="p", location="us-central1", client=fake)
    out = client.chat(
        [{"role": "user", "content": "install flask"}],
        tools=[{"function": {"name": "execute_terminal", "description": "", "parameters": {}}}],
    )
    assert out["tool_calls"][0]["function"]["arguments"] == {"command": "pip install flask"}
    # generate_content was handed the model id, a tools config, and an output cap.
    assert fake.models.last["model"] == "gemini-x"
    assert "tools" in fake.models.last["config"]
    assert fake.models.last["config"]["max_output_tokens"] >= 1


def test_stream_chat_calls_generate_content_stream_and_yields_text_chunks() -> None:
    fake = FakeGemini(
        None,
        stream=[
            _Response([_Candidate(_Content([_Part(text="hel")]))]),
            _Response([_Candidate(_Content([_Part(text="lo")]))]),
        ],
    )
    client = GeminiClient(model="gemini-x", project="p", location="us-central1", client=fake)
    chunks = list(client.stream_chat(
        [{"role": "user", "content": "say hello"}],
        tools=[{"function": {"name": "read_file", "description": "", "parameters": {}}}],
    ))
    assert chunks == ["hel", "lo"]
    assert fake.models.stream_last["model"] == "gemini-x"
    assert "tools" in fake.models.stream_last["config"]
    assert fake.models.stream_last["config"]["thinking_config"] == {"thinking_budget": 0}


def test_stream_chat_applies_privacy_filter_before_generate_content_stream() -> None:
    raw_path = r"C:\Users\kumar\ai-editor\secrets.txt"
    fake = FakeGemini(None, stream=[])
    client = GeminiClient(model="m", project="p", client=fake)
    list(client.stream_chat([{"role": "user", "content": f"read {raw_path}"}]))
    sent = fake.models.stream_last["contents"][0]["parts"][0]["text"]
    assert raw_path not in sent
    assert "[PATH REDACTED]" in sent


def test_chat_passes_system_instruction_separately() -> None:
    fake = FakeGemini(_Response([_Candidate(_Content([_Part(text="ok")]))]))
    client = GeminiClient(project="p", client=fake)
    client.chat([{"role": "system", "content": "be terse"}, {"role": "user", "content": "hi"}])
    assert fake.models.last["config"]["system_instruction"] == "be terse"


def test_chat_disables_thinking_by_default() -> None:
    # 2.5-era models think by default and can spend the whole output budget on it;
    # the client caps that to a predictable 0 so a turn always returns text.
    fake = FakeGemini(_Response([_Candidate(_Content([_Part(text="ok")]))]))
    GeminiClient(project="p", client=fake).chat([{"role": "user", "content": "hi"}])
    assert fake.models.last["config"]["thinking_config"] == {"thinking_budget": 0}


def test_chat_thinking_budget_negative_omits_config() -> None:
    # -1 means "leave the model's own dynamic thinking on" -> no thinking_config sent.
    fake = FakeGemini(_Response([_Candidate(_Content([_Part(text="ok")]))]))
    GeminiClient(project="p", thinking_budget=-1, client=fake).chat([{"role": "user", "content": "hi"}])
    assert "thinking_config" not in fake.models.last["config"]


def test_chat_wraps_failures_as_llmerror() -> None:
    class _BoomModels:
        def generate_content(self, **kwargs):
            raise RuntimeError("PermissionDenied")

    class _BoomClient:
        def __init__(self) -> None:
            self.models = _BoomModels()

    client = GeminiClient(model="m", project="p", client=_BoomClient())
    with pytest.raises(LLMError):
        client.chat([{"role": "user", "content": "hi"}])


# --- list_models: discovery + curated fallback ------------------------------
def test_list_models_discovers_gemini_and_strips_prefix() -> None:
    listing = [
        _Model("publishers/google/models/gemini-2.0-flash", "Gemini 2.0 Flash"),
        _Model("publishers/google/models/text-embedding-004", "Embedder"),  # not gemini -> dropped
    ]
    client = GeminiClient(project="p", client=FakeGemini(None, listing=listing))
    ids = [m["id"] for m in client.list_models()]
    assert "gemini-2.0-flash" in ids
    assert "text-embedding-004" not in ids


def test_list_models_falls_back_to_curated_when_discovery_empty() -> None:
    client = GeminiClient(project="p", client=FakeGemini(None, listing=[]))
    assert client.list_models() == CURATED_MODELS


def test_list_models_falls_back_to_curated_on_discovery_error() -> None:
    class _BoomModels:
        def list(self):
            raise RuntimeError("AccessDenied")

    class _BoomClient:
        def __init__(self) -> None:
            self.models = _BoomModels()

    client = GeminiClient(project="p", client=_BoomClient())
    assert client.list_models() == CURATED_MODELS


# --- Routing: explicit gemini.* pick + the models endpoint ------------------
def test_select_chat_client_routes_gemini_prefix_and_strips_it() -> None:
    fake_gemini = object()
    chat_client, model = _select_chat_client(
        "gemini.gemini-2.5-pro", object(), None, gemini=fake_gemini
    )
    assert chat_client is fake_gemini
    assert model == "gemini-2.5-pro"


def test_select_chat_client_gemini_unconfigured_is_503_not_silent_fallback() -> None:
    # A gemini pick with Gemini unavailable must fail clearly, never fall through
    # to Bedrock or local (no silent provider change).
    with pytest.raises(HTTPException) as exc:
        _select_chat_client("gemini.gemini-2.5-pro", object(), object(), gemini=None)
    assert exc.value.status_code == 503


def test_models_gemini_endpoint_reports_configured_and_lists() -> None:
    fake = FakeGemini(None, listing=[_Model("models/gemini-2.5-flash", "Gemini 2.5 Flash")])
    out = models_gemini(gemini=GeminiClient(project="p", client=fake))
    assert out["configured"] is True
    assert out["available"] is True
    assert any(m["id"] == "gemini-2.5-flash" for m in out["models"])


def test_models_gemini_endpoint_unconfigured_is_empty() -> None:
    assert models_gemini(gemini=None) == {"configured": False, "available": False, "models": []}
