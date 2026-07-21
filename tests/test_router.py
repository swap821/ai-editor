"""Unit tests for aios.core.router."""

import pytest

from aios.core.router import (
    COST_FREE,
    COST_HIGH,
    LOCAL_FIRST,
    Policy,
    Provider,
    PRIVACY_CLOUD,
    PRIVACY_LOCAL,
    PROVIDER_BEDROCK,
    PROVIDER_GEMINI,
    PROVIDER_OLLAMA,
    candidates,
    parse_pick,
    pick_from,
    picker_prompt,
    policy_allows,
    route,
    route_model_id,
)


def test_policy_allows_local():
    local_prov = Provider(
        name=PROVIDER_OLLAMA,
        privacy=PRIVACY_LOCAL,
        cost=COST_FREE,
        available=True,
        models=("qwen2.5-coder:7b",),
    )
    assert policy_allows(LOCAL_FIRST, "coding", local_prov) is True


def test_policy_blocks_cloud_when_not_in_cloud_tasks():
    cloud_prov = Provider(
        name=PROVIDER_GEMINI,
        privacy=PRIVACY_CLOUD,
        cost=COST_HIGH,
        available=True,
        models=("gemini-2.5-flash",),
    )
    assert policy_allows(LOCAL_FIRST, "coding", cloud_prov) is False

    cloud_policy = Policy(cloud_tasks=frozenset({"coding"}), max_cost=COST_HIGH)
    assert policy_allows(cloud_policy, "coding", cloud_prov) is True
    assert policy_allows(cloud_policy, "general", cloud_prov) is False


def test_policy_blocks_unavailable_provider():
    prov = Provider(
        name=PROVIDER_OLLAMA,
        privacy=PRIVACY_LOCAL,
        cost=COST_FREE,
        available=False,
        models=("qwen2.5-coder:7b",),
    )
    assert policy_allows(LOCAL_FIRST, "coding", prov) is False


def test_candidates_ranking():
    local_prov = Provider(
        name=PROVIDER_OLLAMA,
        privacy=PRIVACY_LOCAL,
        cost=COST_FREE,
        available=True,
        models=("qwen2.5-coder:7b",),
    )
    cloud_prov = Provider(
        name=PROVIDER_BEDROCK,
        privacy=PRIVACY_CLOUD,
        cost=COST_HIGH,
        available=True,
        models=("claude-3-5-sonnet",),
    )

    policy = Policy(cloud_tasks=frozenset({"reasoning"}), prefer_local=True)

    # For reasoning, both are allowed
    cands = candidates("reasoning", [local_prov, cloud_prov], policy=policy)
    assert len(cands) == 2
    # Bedrock has cap 300 vs Local 100+60=160, so Bedrock ranks #1
    assert cands[0].provider == PROVIDER_BEDROCK
    assert cands[0].model == "claude-3-5-sonnet"


def test_route_with_picker():
    local_prov = Provider(
        name=PROVIDER_OLLAMA,
        privacy=PRIVACY_LOCAL,
        cost=COST_FREE,
        available=True,
        models=("qwen2.5-coder:7b", "llama3.1:8b"),
    )

    # Custom picker choosing llama3.1:8b
    def custom_picker(routes):
        return "ollama.llama3.1:8b"

    chosen = route("general", [local_prov], policy=LOCAL_FIRST, picker=custom_picker)
    assert chosen is not None
    assert route_model_id(chosen) in ("ollama.llama3.1:8b", "ollama.qwen2.5-coder:7b")


def test_picker_prompt_and_parse_pick():
    local_prov = Provider(
        name=PROVIDER_OLLAMA,
        privacy=PRIVACY_LOCAL,
        cost=COST_FREE,
        available=True,
        models=("qwen2.5-coder:7b",),
    )
    cands = candidates("coding", [local_prov], policy=LOCAL_FIRST)
    prompt = picker_prompt("coding", cands)
    assert "Task type: coding" in prompt
    assert "ollama.qwen2.5-coder:7b" in prompt

    parsed = parse_pick("I choose ollama.qwen2.5-coder:7b for this task", cands)
    assert parsed == "ollama.qwen2.5-coder:7b"
