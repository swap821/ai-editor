"""One law for cloud egress: the constitution is the ceiling.

Operator decision, 2026-10-11. Found by the sovereignty drills: chat routing
obeyed the runtime profile alone, while the constitution (``AIOS_ROUTER_CLOUD_
TASKS``, the documented opt-in) was obeyed by nothing live -- a persisted
profile switch could open cloud egress the constitution never allowed.

Pinned, both directions: the effective policy is the constitution narrowed by
the profile -- never widened; the kernel, its summary and the dormant enforcer
check all answer from the one derivation (aios/policy/egress.py).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from aios.core import router
from aios.policy.constitution import build_constitution
from aios.policy.egress import effective_router_policy, stricter_cost
from aios.policy.kernel import PolicyKernel
from aios.runtime import profiles


def _law(tasks=(), *, prefer_local=True, max_cost="high"):
    from dataclasses import replace

    return replace(
        build_constitution(router_cloud_tasks=tasks, router_max_cost=max_cost),
        router_prefer_local=prefer_local,
    )


def _kernel(law, profile_name: str) -> PolicyKernel:
    kernel = PolicyKernel(constitution=law)
    kernel._active_profile = profiles.get_profile(profile_name)
    return kernel


# --------------------------------------------------------------------------- #
# The rule
# --------------------------------------------------------------------------- #


def test_cloud_tasks_are_the_intersection() -> None:
    law = SimpleNamespace(
        router_cloud_tasks=("reasoning", "coding"),
        router_prefer_local=True,
        router_max_cost="high",
    )
    profile = SimpleNamespace(
        router_cloud_tasks=("coding", "browse"),
        router_prefer_local=True,
        router_max_cost="high",
    )
    assert effective_router_policy(law, profile).cloud_tasks == frozenset({"coding"})


def test_a_profile_can_never_widen_the_law() -> None:
    law = SimpleNamespace(
        router_cloud_tasks=(), router_prefer_local=True, router_max_cost="low"
    )
    wide = SimpleNamespace(
        router_cloud_tasks=("reasoning", "coding", "browse", "swarm"),
        router_prefer_local=False,
        router_max_cost="high",
    )
    policy = effective_router_policy(law, wide)
    assert policy.cloud_tasks == frozenset()
    assert policy.prefer_local is True
    assert policy.max_cost == "low"


def test_a_profile_can_narrow_the_law() -> None:
    law = SimpleNamespace(
        router_cloud_tasks=("reasoning", "coding"),
        router_prefer_local=False,
        router_max_cost="high",
    )
    narrow = SimpleNamespace(
        router_cloud_tasks=(), router_prefer_local=True, router_max_cost="free"
    )
    policy = effective_router_policy(law, narrow)
    assert policy.cloud_tasks == frozenset()
    assert policy.prefer_local is True
    assert policy.max_cost == "free"


@pytest.mark.parametrize(
    "a, b, expected",
    [
        ("high", "low", "low"),
        ("free", "high", "free"),
        ("low", "low", "low"),
        ("bogus", "high", "free"),
    ],
)
def test_the_stricter_cost_wins_and_unknown_is_strictest(a, b, expected) -> None:
    assert stricter_cost(a, b) == expected


def test_without_a_profile_the_law_alone_applies() -> None:
    law = SimpleNamespace(
        router_cloud_tasks=("Coding ",),
        router_prefer_local=False,
        router_max_cost="low",
    )
    policy = effective_router_policy(law, None)
    assert policy.cloud_tasks == frozenset({"coding"}) and policy.max_cost == "low"
    assert policy.prefer_local is False


# --------------------------------------------------------------------------- #
# The kernel answers from it
# --------------------------------------------------------------------------- #


def test_the_operator_profile_is_local_only_until_the_law_allows_cloud() -> None:
    """The consequence the operator accepted: under `operator` with
    AIOS_ROUTER_CLOUD_TASKS unset, auto never leaves the machine."""
    assert _kernel(_law(), "operator").router_policy().cloud_tasks == frozenset()
    allowed = _kernel(_law(("reasoning", "coding")), "operator").router_policy()
    assert allowed.cloud_tasks == frozenset({"reasoning", "coding"})


def test_autonomous_cannot_open_more_than_the_law() -> None:
    policy = _kernel(_law(("coding",), prefer_local=True), "autonomous").router_policy()
    assert policy.cloud_tasks == frozenset({"coding"})
    assert policy.prefer_local is True, (
        "the profile cannot make cloud preferred past the law"
    )
    open_law = _kernel(
        _law(("coding",), prefer_local=False), "autonomous"
    ).router_policy()
    assert open_law.prefer_local is False


def test_local_first_stays_local_whatever_the_law() -> None:
    policy = _kernel(
        _law(("reasoning", "coding", "browse")), "local-first"
    ).router_policy()
    assert policy.cloud_tasks == frozenset()


def test_the_summary_and_the_question_tell_the_truth() -> None:
    kernel = _kernel(_law(("coding",)), "operator")
    summary = kernel.runtime_profile_decisions()
    assert summary["router_cloud_tasks"] == ["reasoning", "coding"], (
        "the profile's own setting"
    )
    assert summary["constitution_router_cloud_tasks"] == ["coding"]
    assert summary["effective_router_cloud_tasks"] == ["coding"]
    assert summary["cloud_tasks_allowed"] == {
        "reasoning": False,
        "coding": True,
        "browse": False,
        "swarm": False,
    }
    assert kernel.cloud_tasks_allowed("coding") is True
    assert kernel.cloud_tasks_allowed("reasoning") is False


def test_auto_routing_asks_the_kernel(monkeypatch) -> None:
    """The live route reads the same policy -- not the profile directly."""
    from aios.api import deps
    from aios.core import router_wiring

    kernel = _kernel(_law(), "operator")
    monkeypatch.setattr(deps, "get_policy_kernel", lambda: kernel)
    assert router_wiring._router_policy().cloud_tasks == frozenset()


def test_the_dormant_enforcer_check_applies_the_same_ceiling() -> None:
    from aios.policy.constitution_enforcer import ConstitutionEnforcer

    contract = SimpleNamespace(mission_id="m", budget=None)
    denied = ConstitutionEnforcer(constitution=_law()).check_cloud_request(
        contract, task="coding", estimated_tokens=10
    )
    assert denied.allowed is False and denied.source == "router_policy"


def test_the_policy_type_is_the_routers() -> None:
    assert isinstance(_kernel(_law(), "operator").router_policy(), router.Policy)
