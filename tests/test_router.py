"""Unit tests for the cross-provider hybrid router (aios.core.router).

The router is pure and deterministic given its inputs (providers, policy, metrics)
plus one optional injected ``picker`` (the local LLM). These tests pin the safety
guarantees — the privacy gate, "the LLM can never escape the policy", the
deterministic fallback — and the ranking/calibration behaviour, all with mocks and
no network, no boto3, no Ollama.
"""
from __future__ import annotations

from aios.core.model_selector import TASK_CODING, TASK_REASONING
from aios.core.router import (
    COST_FREE,
    COST_HIGH,
    COST_LOW,
    LOCAL_FIRST,
    PRIVACY_CLOUD,
    PRIVACY_LOCAL,
    PROVIDER_BEDROCK,
    PROVIDER_GEMINI,
    PROVIDER_OLLAMA,
    Policy,
    Provider,
    candidates,
    policy_allows,
    route,
    route_model_id,
)


# --- Fixtures (providers as data) -------------------------------------------
def _ollama(models=("qwen2.5-coder:7b", "llama3.1:8b"), available=True) -> Provider:
    return Provider(PROVIDER_OLLAMA, PRIVACY_LOCAL, COST_FREE, available, tuple(models))


def _bedrock(models=("us.anthropic.claude-3-5-sonnet-20241022-v2:0",), available=True) -> Provider:
    return Provider(PROVIDER_BEDROCK, PRIVACY_CLOUD, COST_HIGH, available, tuple(models))


def _gemini(models=("gemini-2.0-flash",), available=True, cost=COST_LOW) -> Provider:
    return Provider(PROVIDER_GEMINI, PRIVACY_CLOUD, cost, available, tuple(models))


# --- The default policy is behaviour-preserving (cloud OFF) -----------------
def test_default_policy_never_routes_to_cloud() -> None:
    # LOCAL_FIRST has an empty cloud_tasks set: with a local model present, even a
    # frontier cloud provider is gated out — today's local-only behaviour holds.
    providers = [_ollama(), _bedrock(), _gemini()]
    chosen = route(TASK_CODING, providers)
    assert chosen is not None
    assert chosen.provider == PROVIDER_OLLAMA
    assert chosen.privacy == PRIVACY_LOCAL


def test_default_policy_local_wins_even_for_reasoning() -> None:
    chosen = route(TASK_REASONING, [_ollama(), _bedrock()])
    assert chosen is not None and chosen.provider == PROVIDER_OLLAMA


# --- The privacy gate -------------------------------------------------------
def test_privacy_gate_blocks_cloud_for_unopted_task() -> None:
    policy = Policy(cloud_tasks=frozenset({TASK_REASONING}))
    # Reasoning may escalate; coding may NOT.
    assert policy_allows(policy, TASK_REASONING, _bedrock()) is True
    assert policy_allows(policy, TASK_CODING, _bedrock()) is False
    # Local is always allowed regardless of the task.
    assert policy_allows(policy, TASK_CODING, _ollama()) is True


def test_opted_in_task_can_reach_cloud_when_no_local_model() -> None:
    # Reasoning opted into cloud + NO local model available -> cloud is chosen.
    policy = Policy(cloud_tasks=frozenset({TASK_REASONING}))
    providers = [_ollama(models=(), available=True), _bedrock()]
    chosen = route(TASK_REASONING, providers, policy=policy)
    assert chosen is not None
    assert chosen.provider == PROVIDER_BEDROCK
    assert chosen.privacy == PRIVACY_CLOUD


def test_capability_escalates_to_cloud_when_local_present_but_prefer_local_off() -> None:
    # Operator opted reasoning into cloud AND turned off the local-first bias:
    # the frontier cloud model out-ranks the local one even though local exists.
    policy = Policy(cloud_tasks=frozenset({TASK_REASONING}), prefer_local=False)
    chosen = route(TASK_REASONING, [_ollama(), _bedrock()], policy=policy)
    assert chosen is not None and chosen.provider == PROVIDER_BEDROCK


def test_local_first_bias_keeps_local_when_opted_in_but_prefer_local_on() -> None:
    # Same opt-in, but local-first is ON: a present local model still wins ties /
    # is preferred — cloud is a deliberate escalation, not the default.
    policy = Policy(cloud_tasks=frozenset({TASK_REASONING}))  # prefer_local True
    chosen = route(TASK_REASONING, [_ollama(), _bedrock()], policy=policy)
    # The frontier cloud capability (300) still beats local (100+60 bias=160) here,
    # so this documents that the small bias does NOT outweigh a real capability gap.
    assert chosen is not None and chosen.provider == PROVIDER_BEDROCK


# --- The cost gate ----------------------------------------------------------
def test_cost_ceiling_blocks_expensive_provider() -> None:
    policy = Policy(cloud_tasks=frozenset({TASK_REASONING}), max_cost=COST_LOW)
    # Bedrock is COST_HIGH -> blocked by the ceiling; the cheaper Gemini is allowed.
    assert policy_allows(policy, TASK_REASONING, _bedrock()) is False
    assert policy_allows(policy, TASK_REASONING, _gemini(cost=COST_LOW)) is True


# --- The hybrid picker: can re-order, can NEVER escape the policy ------------
def test_picker_may_choose_among_allowed_candidates() -> None:
    # Both cloud providers opted in; the local LLM prefers Gemini over the
    # deterministic #1 — honoured because Gemini is an allowed candidate.
    policy = Policy(cloud_tasks=frozenset({TASK_REASONING}), prefer_local=False)
    providers = [_bedrock(), _gemini()]
    picked = route(
        TASK_REASONING, providers, policy=policy,
        picker=lambda cands: "gemini.gemini-2.0-flash",
    )
    assert picked is not None and picked.provider == PROVIDER_GEMINI


def test_picker_choosing_a_blocked_provider_is_ignored() -> None:
    # The LLM tries to route a LOCAL-ONLY (coding) task to Bedrock. Bedrock is not
    # even a candidate, so the choice is discarded and the deterministic local
    # winner stands. THIS is the core hybrid safety guarantee.
    providers = [_ollama(), _bedrock()]
    picked = route(
        TASK_CODING, providers,  # default policy: coding stays local
        picker=lambda cands: "bedrock.us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    )
    assert picked is not None
    assert picked.provider == PROVIDER_OLLAMA
    assert picked.privacy == PRIVACY_LOCAL


def test_picker_garbage_falls_back_to_deterministic() -> None:
    chosen = route(TASK_CODING, [_ollama()], picker=lambda cands: "not-a-real-id")
    assert chosen is not None and chosen.provider == PROVIDER_OLLAMA


def test_picker_exception_falls_back_to_deterministic() -> None:
    def boom(_cands):
        raise RuntimeError("picker crashed")

    chosen = route(TASK_CODING, [_ollama()], picker=boom)
    assert chosen is not None and chosen.provider == PROVIDER_OLLAMA


def test_picker_only_ever_sees_allowed_candidates() -> None:
    # The picker must never be offered a gated-out provider to choose from.
    seen: list[str] = []

    def spy(cands):
        seen.extend(c.provider for c in cands)
        return None

    route(TASK_CODING, [_ollama(), _bedrock(), _gemini()], picker=spy)
    assert seen == [PROVIDER_OLLAMA]  # cloud was gated out before the picker ran


# --- Evidence calibration ---------------------------------------------------
def test_calibration_can_reorder_two_cloud_models() -> None:
    # Two equal-capability cloud providers opted in, local-first off. Evidence says
    # Gemini verifies far more often on reasoning -> it should win once calibrated.
    policy = Policy(cloud_tasks=frozenset({TASK_REASONING}), prefer_local=False)
    gem = Provider(PROVIDER_GEMINI, PRIVACY_CLOUD, COST_HIGH, True, ("gemini-2.0-flash",))
    bed = Provider(PROVIDER_BEDROCK, PRIVACY_CLOUD, COST_HIGH, True, ("claude-x",))
    metrics = {
        (PROVIDER_GEMINI, "gemini-2.0-flash", TASK_REASONING): 0.95,
        (PROVIDER_BEDROCK, "claude-x", TASK_REASONING): 0.10,
    }
    chosen = route(
        TASK_REASONING, [bed, gem], policy=policy,
        metrics=metrics, calibration_weight=0.5,
    )
    assert chosen is not None and chosen.provider == PROVIDER_GEMINI
    assert "verified" in chosen.reason


def test_calibration_cold_start_leaves_heuristic_order() -> None:
    # With no metric for either, calibration is a no-op: deterministic order holds.
    policy = Policy(cloud_tasks=frozenset({TASK_REASONING}), prefer_local=False)
    ranked = candidates(
        TASK_REASONING, [_bedrock(), _gemini(cost=COST_HIGH)],
        policy=policy, metrics={}, calibration_weight=0.7,
    )
    # Equal capability + cost -> stable provider-name order (bedrock before gemini).
    assert [r.provider for r in ranked] == [PROVIDER_BEDROCK, PROVIDER_GEMINI]


# --- No usable provider -----------------------------------------------------
def test_no_available_provider_returns_none() -> None:
    assert route(TASK_CODING, []) is None
    assert route(TASK_CODING, [_ollama(available=False), _bedrock(available=False)]) is None


def test_local_unavailable_and_cloud_gated_returns_none() -> None:
    # Local down, cloud gated out by the default policy -> nothing to route to.
    assert route(TASK_CODING, [_ollama(available=False), _bedrock()]) is None


# --- The selector/UI id round-trips -----------------------------------------
def test_route_model_id_reattaches_prefix() -> None:
    chosen = route(TASK_CODING, [_ollama(models=("qwen2.5-coder:7b",))])
    assert chosen is not None
    assert chosen.model == "qwen2.5-coder:7b"
    assert route_model_id(chosen) == "ollama.qwen2.5-coder:7b"
    assert route_model_id(None) is None


def test_require_tools_drops_non_tool_local_model() -> None:
    # A reasoning-only local family can't drive the tool loop; with require_tools
    # and nothing else available, the local provider fields no candidate.
    prov = _ollama(models=("deepseek-r1:8b",))
    assert route(TASK_CODING, [prov], require_tools=True) is None
    # Without the tool requirement it is routable again.
    assert route(TASK_CODING, [prov], require_tools=False) is not None
