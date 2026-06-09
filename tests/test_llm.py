"""Contract tests for the local Ollama HTTP client; no network is used."""
from __future__ import annotations

import io
import json
import urllib.error

import pytest

from aios.core.llm import LLMError, OllamaClient


class FakeResponse:
    def __init__(self, body: bytes = b"", *, lines: list[bytes] | None = None, status: int = 200):
        self.body = body
        self.lines = lines or []
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return self.body

    def __iter__(self):
        return iter(self.lines)


def _payload(request) -> dict:
    return json.loads(request.data.decode("utf-8"))


def test_complete_sends_options_and_system(monkeypatch) -> None:
    seen = {}

    def urlopen(request, timeout):
        seen.update(request=request, timeout=timeout)
        return FakeResponse(b'{"response":"done"}')

    monkeypatch.setattr("aios.core.llm.urllib.request.urlopen", urlopen)
    client = OllamaClient("qwen", host="http://ollama/", timeout_s=9, temperature=0.2, num_ctx=4096)

    assert client.complete("build it", system="be precise") == "done"
    assert seen["request"].full_url == "http://ollama/api/generate"
    assert seen["timeout"] == 9
    assert _payload(seen["request"]) == {
        "model": "qwen",
        "prompt": "build it",
        "stream": False,
        "options": {"temperature": 0.2, "num_ctx": 4096},
        "system": "be precise",
    }


def test_complete_surfaces_http_transport_and_decode_errors(monkeypatch) -> None:
    client = OllamaClient("qwen", host="http://ollama")

    error = urllib.error.HTTPError(
        "http://ollama/api/generate", 500, "server error", None, io.BytesIO(b"out of memory")
    )
    monkeypatch.setattr("aios.core.llm.urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(error))
    with pytest.raises(LLMError, match="out of memory"):
        client.complete("x")

    monkeypatch.setattr(
        "aios.core.llm.urllib.request.urlopen",
        lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )
    with pytest.raises(LLMError, match="request.*failed"):
        client.complete("x")

    monkeypatch.setattr(
        "aios.core.llm.urllib.request.urlopen", lambda *a, **k: FakeResponse(b"not-json")
    )
    with pytest.raises(LLMError, match="non-JSON"):
        client.complete("x")


def test_chat_sends_tools_and_model_override(monkeypatch) -> None:
    seen = {}
    reply = {"message": {"role": "assistant", "content": "", "tool_calls": [{"id": "x"}]}}

    def urlopen(request, timeout):
        seen["request"] = request
        return FakeResponse(json.dumps(reply).encode("utf-8"))

    monkeypatch.setattr("aios.core.llm.urllib.request.urlopen", urlopen)
    client = OllamaClient("default", host="http://ollama")
    tools = [{"type": "function", "function": {"name": "read_file"}}]

    assert client.chat([{"role": "user", "content": "read"}], tools=tools, model="tool-model") == reply["message"]
    assert _payload(seen["request"])["model"] == "tool-model"
    assert _payload(seen["request"])["tools"] == tools


def test_chat_returns_safe_empty_message_for_malformed_response(monkeypatch) -> None:
    monkeypatch.setattr(
        "aios.core.llm.urllib.request.urlopen",
        lambda *a, **k: FakeResponse(b'{"message":"not-an-object"}'),
    )
    assert OllamaClient().chat([]) == {"role": "assistant", "content": ""}


def test_chat_surfaces_http_transport_and_decode_errors(monkeypatch) -> None:
    client = OllamaClient("qwen")
    error = urllib.error.HTTPError(
        "http://ollama/api/chat", 404, "not found", None, io.BytesIO(b"unknown model")
    )
    monkeypatch.setattr("aios.core.llm.urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(error))
    with pytest.raises(LLMError, match="unknown model"):
        client.chat([])

    monkeypatch.setattr(
        "aios.core.llm.urllib.request.urlopen",
        lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )
    with pytest.raises(LLMError, match="chat.*failed"):
        client.chat([])

    monkeypatch.setattr(
        "aios.core.llm.urllib.request.urlopen", lambda *a, **k: FakeResponse(b"not-json")
    )
    with pytest.raises(LLMError, match="non-JSON"):
        client.chat([])


def test_stream_complete_skips_invalid_lines_and_stops_at_done(monkeypatch) -> None:
    seen = {}

    def urlopen(request, timeout):
        seen["request"] = request
        return FakeResponse(lines=[
            b"\n",
            b"not-json\n",
            b'{"response":"one"}\n',
            b'{"response":"two","done":true}\n',
            b'{"response":"ignored"}\n',
        ])

    monkeypatch.setattr("aios.core.llm.urllib.request.urlopen", urlopen)
    client = OllamaClient("default", host="http://ollama")

    assert list(client.stream_complete("go", system="rules", model="selected")) == ["one", "two"]
    payload = _payload(seen["request"])
    assert payload["model"] == "selected"
    assert payload["stream"] is True
    assert payload["system"] == "rules"


def test_stream_complete_surfaces_transport_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "aios.core.llm.urllib.request.urlopen",
        lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )
    with pytest.raises(LLMError, match="stream.*failed"):
        list(OllamaClient().stream_complete("go"))


def test_stream_complete_surfaces_http_error_detail(monkeypatch) -> None:
    error = urllib.error.HTTPError(
        "http://ollama/api/generate", 500, "server error", None, io.BytesIO(b"model crashed")
    )
    monkeypatch.setattr("aios.core.llm.urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(error))
    with pytest.raises(LLMError, match="model crashed"):
        list(OllamaClient("qwen").stream_complete("go"))


def test_model_discovery_and_availability_fail_soft(monkeypatch) -> None:
    monkeypatch.setattr(
        "aios.core.llm.urllib.request.urlopen",
        lambda *a, **k: FakeResponse(b'{"models":[{"name":"qwen"},{"name":""},{"other":1}]}'),
    )
    client = OllamaClient()
    assert client.list_models() == {"available": True, "models": ["qwen"]}
    assert client.is_available() is True

    monkeypatch.setattr(
        "aios.core.llm.urllib.request.urlopen",
        lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )
    assert client.list_models() == {"available": False, "models": []}
    assert client.is_available() is False
