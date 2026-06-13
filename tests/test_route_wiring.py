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
    """Stub local client: ``list_models()`` returns the installed tag list."""

    def __init__(self, models: list[str]) -> None:
        self._models = models

    def list_models(self) -> dict:
        return {"models": self._models}


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
