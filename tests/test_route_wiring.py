"""Integration tests for the cross-provider router WIRED into the API's model
selection (``_select_chat_client`` with ``auto``).

The pure routing policy is unit-tested in ``test_router.py``; here we pin the live
wiring — that ``auto`` builds providers from the live clients, routes through the
operator policy, and (critically) that the **privacy boundary holds even on the
fail-soft fallback path**: a task the operator hasn't opted into cloud is NEVER
sent to a cloud client, even when no local model exists. Fakes only; no network.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from aios import config
from aios.api.deps import get_policy_kernel
from aios.api.main import _build_providers, _provider_name, _select_chat_client
from aios.core.catalog import clear_catalog_cache
from aios.runtime import profiles


@pytest.fixture(autouse=True)
def _clear_catalog():
    # The cloud catalog is process-cached; isolate every test (fake clients that
    # can't list models fall back to the configured default, uncached).
    clear_catalog_cache()
    yield
    clear_catalog_cache()


@pytest.fixture(autouse=True)
def _reset_runtime_profile():
    """Keep the process-wide PolicyKernel in the local-first profile unless a test overrides it."""
    kernel = get_policy_kernel()
    kernel._active_profile = profiles.get_profile("local-first")
    yield
    kernel._active_profile = profiles.get_profile("local-first")


def _set_cloud_policy(monkeypatch, *, cloud_tasks=(), prefer_local=True, max_cost="high"):
    """Drive the router through the kernel's active profile while mirroring legacy config knobs."""
    base = profiles.get_profile("local-first")
    profile = replace(
        base,
        router_cloud_tasks=tuple(str(t).lower() for t in cloud_tasks),
        router_prefer_local=prefer_local,
        router_max_cost=max_cost,
    )
    get_policy_kernel()._active_profile = profile
    monkeypatch.setattr(config, "ROUTER_CLOUD_TASKS", tuple(cloud_tasks))
    monkeypatch.setattr(config, "ROUTER_PREFER_LOCAL", prefer_local)
    monkeypatch.setattr(config, "ROUTER_MAX_COST", max_cost)


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
    _set_cloud_policy(monkeypatch, cloud_tasks=())  # default: cloud off
    ollama = FakeOllama(["llama3.1:8b", "qwen2.5-coder:7b"])
    client, model = _select_chat_client(
        "auto", ollama, bedrock=object(), gemini=object(), task="coding"
    )
    assert client is ollama
    assert model == "qwen2.5-coder:7b"  # the coder wins for a coding task


def test_auto_never_falls_back_to_cloud_for_unopted_task(monkeypatch) -> None:
    # No local model AND cloud not opted in -> must NOT use Bedrock/Gemini. The
    # privacy boundary holds on the fallback path; we drop to the local default.
    _set_cloud_policy(monkeypatch, cloud_tasks=())
    ollama = FakeOllama([])
    bedrock, gemini = object(), object()
    client, model = _select_chat_client("auto", ollama, bedrock=bedrock, gemini=gemini, task="coding")
    assert client is ollama  # stayed local, did not silently egress to cloud
    assert client is not bedrock and client is not gemini
    assert model == config.LLM_MODEL


# --- Opted-in task: auto may escalate to an available cloud provider --------
def test_auto_routes_to_cloud_when_task_opted_in_and_no_local(monkeypatch) -> None:
    _set_cloud_policy(monkeypatch, cloud_tasks=("reasoning",))
    gemini = object()
    client, model = _select_chat_client(
        "auto", FakeOllama([]), bedrock=None, gemini=gemini, task="reasoning"
    )
    assert client is gemini
    assert model == config.GEMINI_MODEL


def test_auto_keeps_local_for_a_task_not_opted_in(monkeypatch) -> None:
    # Only 'reasoning' may go to cloud; a coding turn with a local model present
    # stays local even though cloud providers are available.
    _set_cloud_policy(monkeypatch, cloud_tasks=("reasoning",))
    ollama = FakeOllama(["qwen2.5-coder:7b"])
    client, model = _select_chat_client(
        "auto", ollama, bedrock=object(), gemini=object(), task="coding"
    )
    assert client is ollama
    assert model == "qwen2.5-coder:7b"


# --- Explicit picks are unchanged by the router wiring ----------------------
def test_explicit_ollama_pick_still_local(monkeypatch) -> None:
    _set_cloud_policy(monkeypatch, cloud_tasks=("coding",))  # even with cloud opted in
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
    _set_cloud_policy(monkeypatch, cloud_tasks=("reasoning",))
    monkeypatch.setattr(config, "ROUTER_LLM_PICK", True)  # pin (the dev .env may disable it)
    # For a reasoning task the local candidate is the general model (llama3.1:8b
    # beats the coder), so the local model picks that allowed id.
    ollama = FakeOllama(["qwen2.5-coder:7b", "llama3.1:8b"],
                        chat_reply={"content": "ollama.llama3.1:8b"})
    client, model = _select_chat_client("auto", ollama, None, gemini=object(), task="reasoning")
    assert ollama.chat_called  # the hybrid pick ran (there was a real choice)
    # 2 candidates -> a failover wrapper whose PRIMARY is the picked local model.
    assert client.active_provider == "ollama" and model == "llama3.1:8b"


def test_hybrid_picker_garbage_reply_falls_back_to_deterministic(monkeypatch) -> None:
    # The local model returns nonsense -> the deterministic winner (gemini) stands.
    _set_cloud_policy(monkeypatch, cloud_tasks=("reasoning",))
    monkeypatch.setattr(config, "ROUTER_LLM_PICK", True)  # pin (the dev .env may disable it)
    gemini = object()
    ollama = FakeOllama(["qwen2.5-coder:7b"], chat_reply={"content": "uhh not sure"})
    client, model = _select_chat_client("auto", ollama, None, gemini=gemini, task="reasoning")
    assert ollama.chat_called
    assert client.active_provider == "gemini" and model == config.GEMINI_MODEL


def test_hybrid_picker_not_invoked_when_single_candidate(monkeypatch) -> None:
    # Default policy (cloud off) -> only the local candidate -> no real choice, so
    # the local model is NOT consulted (zero added latency on the common path).
    _set_cloud_policy(monkeypatch, cloud_tasks=())
    ollama = FakeOllama(["qwen2.5-coder:7b"], chat_reply={"content": "should not be read"})
    client, model = _select_chat_client("auto", ollama, bedrock=object(), gemini=object(), task="reasoning")
    assert not ollama.chat_called
    assert client is ollama and model == "qwen2.5-coder:7b"


def test_hybrid_picker_disabled_by_config_stays_deterministic(monkeypatch) -> None:
    _set_cloud_policy(monkeypatch, cloud_tasks=("reasoning",))
    monkeypatch.setattr(config, "ROUTER_LLM_PICK", False)
    gemini = object()
    ollama = FakeOllama(["qwen2.5-coder:7b"], chat_reply={"content": "ollama.qwen2.5-coder:7b"})
    client, model = _select_chat_client("auto", ollama, None, gemini=gemini, task="reasoning")
    assert not ollama.chat_called  # picker disabled
    assert client.active_provider == "gemini" and model == config.GEMINI_MODEL  # deterministic winner


# --- P3: evidence calibration re-ranks the auto route ----------------------
def test_calibration_reorders_auto_route(monkeypatch) -> None:
    # Two cloud providers opted in, local-first off, no local model (so the hybrid
    # picker can't run). Deterministic tie-break picks the cheaper Gemini; measured
    # evidence that Bedrock verifies far more often re-ranks it to win once calibrated.
    _set_cloud_policy(monkeypatch, cloud_tasks=("reasoning",), prefer_local=False)
    bedrock, gemini = object(), object()
    metrics = {
        ("bedrock", config.BEDROCK_MODEL, "reasoning"): 0.95,
        ("gemini", config.GEMINI_MODEL, "reasoning"): 0.05,
    }
    # No calibration -> deterministic cheaper-cloud (Gemini) wins (failover primary).
    c0, _ = _select_chat_client("auto", FakeOllama([]), bedrock, gemini=gemini, task="reasoning")
    assert c0.active_provider == "gemini"
    # Strong calibration + Bedrock's measured success -> Bedrock wins.
    c1, m1 = _select_chat_client(
        "auto", FakeOllama([]), bedrock, gemini=gemini, task="reasoning",
        metrics=metrics, calibration_weight=0.8,
    )
    assert c1.active_provider == "bedrock" and m1 == config.BEDROCK_MODEL


# --- Failover cascade: auto wraps the ranked candidates -----------------------
def test_auto_returns_failover_cascade_with_fallbacks(monkeypatch) -> None:
    # reasoning opted in + a local model + both clouds -> the primary is the picked
    # route and the cascade carries the rest as fallbacks (one outage never blocks).
    _set_cloud_policy(monkeypatch, cloud_tasks=("reasoning",))
    monkeypatch.setattr(config, "ROUTER_LLM_PICK", False)  # deterministic primary
    client, _ = _select_chat_client(
        "auto", FakeOllama(["qwen2.5-coder:7b", "llama3.1:8b"]),
        bedrock=object(), gemini=object(), task="reasoning",
    )
    provs = [p for (_c, _m, p) in client.candidates]
    assert client.active_provider == "gemini"          # frontier primary for reasoning
    assert provs[0] == "gemini"                          # primary first
    assert "bedrock" in provs and "ollama" in provs      # both fallbacks present
    assert len(provs) == 3


# --- Breadth: auto spans the provider's model catalog ------------------------
class FakeBedrock:
    def __init__(self, ids: list[str]) -> None:
        self._ids = ids

    def list_models(self):
        return [{"id": i, "name": i} for i in self._ids]


def test_build_providers_spans_the_cloud_catalog() -> None:
    bed = FakeBedrock(["amazon.nova-lite-v1:0", "us.anthropic.claude-3-5-sonnet-20241022-v2:0"])
    provs = _build_providers(FakeOllama(["qwen2.5-coder:7b"]), bed, None)
    bedrock_models = [p.models[0] for p in provs if p.name == "bedrock"]
    # one candidate per discovered model + the configured default (forced in).
    assert "amazon.nova-lite-v1:0" in bedrock_models
    assert "us.anthropic.claude-3-5-sonnet-20241022-v2:0" in bedrock_models
    assert config.BEDROCK_MODEL in bedrock_models
    # the frontier (Claude/sonnet) outranks a light model by the capability heuristic.
    caps = {p.models[0]: p.capability for p in provs if p.name == "bedrock"}
    assert caps["us.anthropic.claude-3-5-sonnet-20241022-v2:0"] > caps["amazon.nova-lite-v1:0"]


def test_auto_failover_cascade_spans_catalog_models(monkeypatch) -> None:
    # coding opted into cloud + a multi-model Bedrock catalog -> the failover cascade
    # carries several specific cloud models (not just one per provider).
    _set_cloud_policy(monkeypatch, cloud_tasks=("coding",))
    monkeypatch.setattr(config, "ROUTER_LLM_PICK", False)
    bed = FakeBedrock(["amazon.nova-pro-v1:0", "us.anthropic.claude-3-5-sonnet-20241022-v2:0"])
    client, _ = _select_chat_client("auto", FakeOllama(["qwen2.5-coder:7b"]), bed, task="coding")
    bedrock_in_cascade = [m for (_c, m, p) in client.candidates if p == "bedrock"]
    assert len(bedrock_in_cascade) >= 2  # multiple Bedrock models are failover candidates


def test_provider_name_maps_client_to_provider() -> None:
    bed, gem, oll = object(), object(), object()
    assert _provider_name(bed, bed, gem) == "bedrock"
    assert _provider_name(gem, bed, gem) == "gemini"
    assert _provider_name(oll, bed, gem) == "ollama"
    assert _provider_name(oll, None, None) == "ollama"


# --- OpenAI-compat and Anthropic-direct provider wiring -----------------------
def test_explicit_openai_pick_routes_and_strips_prefix() -> None:
    oai = object()
    client, model = _select_chat_client("openai.gpt-4o", FakeOllama([]), None, openai=oai)
    assert client is oai and model == "gpt-4o"


def test_explicit_openai_unconfigured_raises_503() -> None:
    with pytest.raises(Exception) as exc_info:
        _select_chat_client("openai.gpt-4o", FakeOllama([]), None, openai=None)
    assert exc_info.value.status_code == 503


def test_explicit_anthropic_pick_routes_and_strips_prefix() -> None:
    anth = object()
    client, model = _select_chat_client(
        "anthropic.claude-sonnet-4-20250514", FakeOllama([]), None, anthropic=anth
    )
    assert client is anth and model == "claude-sonnet-4-20250514"


def test_explicit_anthropic_unconfigured_raises_503() -> None:
    with pytest.raises(Exception) as exc_info:
        _select_chat_client("anthropic.claude-sonnet-4-20250514", FakeOllama([]), None, anthropic=None)
    assert exc_info.value.status_code == 503


def test_provider_name_detects_openai_and_anthropic() -> None:
    oai, anth, bed, gem = object(), object(), object(), object()
    assert _provider_name(oai, bed, gem, openai=oai) == "openai"
    assert _provider_name(anth, bed, gem, anthropic=anth) == "anthropic"
    assert _provider_name(oai, bed, gem, openai=oai, anthropic=anth) == "openai"


def test_build_providers_includes_openai_and_anthropic() -> None:
    oai, anth = object(), object()
    provs = _build_providers(FakeOllama([]), None, None, openai=oai, anthropic=anth)
    oai_provs = [p for p in provs if p.name == "openai"]
    anth_provs = [p for p in provs if p.name == "anthropic"]
    assert len(oai_provs) == 1
    assert len(anth_provs) == 1
    assert oai_provs[0].privacy == "cloud"
    assert anth_provs[0].privacy == "cloud"
    assert config.OPENAI_MODEL in oai_provs[0].models
    assert config.ANTHROPIC_MODEL in anth_provs[0].models


def test_auto_routes_to_openai_when_task_opted_in(monkeypatch) -> None:
    _set_cloud_policy(monkeypatch, cloud_tasks=("coding",))
    monkeypatch.setattr(config, "ROUTER_LLM_PICK", False)
    oai = object()
    client, model = _select_chat_client(
        "auto", FakeOllama([]), None, openai=oai, task="coding"
    )
    assert model == config.OPENAI_MODEL


def test_auto_never_routes_to_openai_for_unopted_task(monkeypatch) -> None:
    _set_cloud_policy(monkeypatch, cloud_tasks=())
    oai = object()
    client, model = _select_chat_client(
        "auto", FakeOllama(["qwen2.5-coder:7b"]), None, openai=oai, task="coding"
    )
    assert client is not oai
    assert model == "qwen2.5-coder:7b"
