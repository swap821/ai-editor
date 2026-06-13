"""Integration tests for the cross-provider router WIRED into the API's model
selection (``_select_chat_client`` with ``auto``).

The pure routing policy is unit-tested in ``test_router.py``; here we pin the live
wiring — that ``auto`` builds providers from the live clients, routes through the
operator policy, and (critically) that the **privacy boundary holds even on the
fail-soft fallback path**: a task the operator hasn't opted into cloud is NEVER
sent to a cloud client, even when no local model exists. Fakes only; no network.
"""
from __future__ import annotations

from aios import config
from aios.api.main import _select_chat_client


class FakeOllama:
    """Stub local client: ``list_models()`` returns the installed tags; ``chat()``
    records that it ran (so tests can assert the hybrid picker did/didn't fire) and
    returns a canned reply (the local model's route choice)."""

    def __init__(self, models: list[str], chat_reply: dict | None = None) -> None:
        self._models = models
        self._chat_reply = chat_reply or {"content": ""}
        self.chat_called = False
        self.chat_model = None

    def list_models(self) -> dict:
        return {"models": self._models}

    def chat(self, messages, *, tools=None, model=None) -> dict:
        self.chat_called = True
        self.chat_model = model
        return self._chat_reply


# --- Default policy (cloud OFF): auto stays local, exactly as before --------
def test_auto_picks_best_local_under_default_policy(monkeypatch) -> None:
    monkeypatch.setattr(config, "ROUTER_CLOUD_TASKS", ())  # default: cloud off
    ollama = FakeOllama(["llama3.1:8b", "qwen2.5-coder:7b"])
    client, model = _select_chat_client(
        "auto", ollama, bedrock=object(), gemini=object(), task="coding"
    )
    assert client is ollama
    assert model == "qwen2.5-coder:7b"  # the coder wins for a coding task


def test_auto_never_falls_back_to_cloud_for_unopted_task(monkeypatch) -> None:
    # No local model AND cloud not opted in -> must NOT use Bedrock/Gemini. The
    # privacy boundary holds on the fallback path; we drop to the local default.
    monkeypatch.setattr(config, "ROUTER_CLOUD_TASKS", ())
    ollama = FakeOllama([])
    bedrock, gemini = object(), object()
    client, model = _select_chat_client("auto", ollama, bedrock=bedrock, gemini=gemini, task="coding")
    assert client is ollama  # stayed local, did not silently egress to cloud
    assert client is not bedrock and client is not gemini
    assert model == config.LLM_MODEL


# --- Opted-in task: auto may escalate to an available cloud provider --------
def test_auto_routes_to_cloud_when_task_opted_in_and_no_local(monkeypatch) -> None:
    monkeypatch.setattr(config, "ROUTER_CLOUD_TASKS", ("reasoning",))
    gemini = object()
    client, model = _select_chat_client(
        "auto", FakeOllama([]), bedrock=None, gemini=gemini, task="reasoning"
    )
    assert client is gemini
    assert model == config.GEMINI_MODEL


def test_auto_keeps_local_for_a_task_not_opted_in(monkeypatch) -> None:
    # Only 'reasoning' may go to cloud; a coding turn with a local model present
    # stays local even though cloud providers are available.
    monkeypatch.setattr(config, "ROUTER_CLOUD_TASKS", ("reasoning",))
    ollama = FakeOllama(["qwen2.5-coder:7b"])
    client, model = _select_chat_client(
        "auto", ollama, bedrock=object(), gemini=object(), task="coding"
    )
    assert client is ollama
    assert model == "qwen2.5-coder:7b"


# --- Explicit picks are unchanged by the router wiring ----------------------
def test_explicit_ollama_pick_still_local(monkeypatch) -> None:
    monkeypatch.setattr(config, "ROUTER_CLOUD_TASKS", ("coding",))  # even with cloud opted in
    ollama = FakeOllama(["qwen2.5-coder:7b"])
    client, model = _select_chat_client("ollama.qwen2.5-coder:7b", ollama, bedrock=object())
    assert client is ollama and model == "qwen2.5-coder:7b"


def test_explicit_gemini_pick_still_routes_to_gemini() -> None:
    gemini = object()
    client, model = _select_chat_client("gemini.gemini-2.5-pro", FakeOllama([]), None, gemini=gemini)
    assert client is gemini and model == "gemini-2.5-pro"


# --- The HYBRID layer: the local model picks among policy-allowed candidates -
def test_hybrid_picker_honours_local_model_choice(monkeypatch) -> None:
    # reasoning opted into cloud + a local model present -> 2 candidates (local +
    # gemini). Deterministic #1 is gemini (higher capability), but the local model
    # picks the local one; its choice is honoured (it IS an allowed candidate).
    monkeypatch.setattr(config, "ROUTER_CLOUD_TASKS", ("reasoning",))
    # For a reasoning task the local candidate is the general model (llama3.1:8b
    # beats the coder), so the local model picks that allowed id.
    ollama = FakeOllama(["qwen2.5-coder:7b", "llama3.1:8b"],
                        chat_reply={"content": "ollama.llama3.1:8b"})
    client, model = _select_chat_client("auto", ollama, None, gemini=object(), task="reasoning")
    assert ollama.chat_called  # the hybrid pick ran (there was a real choice)
    assert client is ollama and model == "llama3.1:8b"


def test_hybrid_picker_garbage_reply_falls_back_to_deterministic(monkeypatch) -> None:
    # The local model returns nonsense -> the deterministic winner (gemini) stands.
    monkeypatch.setattr(config, "ROUTER_CLOUD_TASKS", ("reasoning",))
    gemini = object()
    ollama = FakeOllama(["qwen2.5-coder:7b"], chat_reply={"content": "uhh not sure"})
    client, model = _select_chat_client("auto", ollama, None, gemini=gemini, task="reasoning")
    assert ollama.chat_called
    assert client is gemini and model == config.GEMINI_MODEL


def test_hybrid_picker_not_invoked_when_single_candidate(monkeypatch) -> None:
    # Default policy (cloud off) -> only the local candidate -> no real choice, so
    # the local model is NOT consulted (zero added latency on the common path).
    monkeypatch.setattr(config, "ROUTER_CLOUD_TASKS", ())
    ollama = FakeOllama(["qwen2.5-coder:7b"], chat_reply={"content": "should not be read"})
    client, model = _select_chat_client("auto", ollama, bedrock=object(), gemini=object(), task="reasoning")
    assert not ollama.chat_called
    assert client is ollama and model == "qwen2.5-coder:7b"


def test_hybrid_picker_disabled_by_config_stays_deterministic(monkeypatch) -> None:
    monkeypatch.setattr(config, "ROUTER_CLOUD_TASKS", ("reasoning",))
    monkeypatch.setattr(config, "ROUTER_LLM_PICK", False)
    gemini = object()
    ollama = FakeOllama(["qwen2.5-coder:7b"], chat_reply={"content": "ollama.qwen2.5-coder:7b"})
    client, model = _select_chat_client("auto", ollama, None, gemini=gemini, task="reasoning")
    assert not ollama.chat_called  # picker disabled
    assert client is gemini and model == config.GEMINI_MODEL  # deterministic winner
