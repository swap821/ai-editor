"""Policy engine tests — versioned chain, queen voting, additive-only gate."""
from __future__ import annotations

import pytest

from aios.policy.engine import Policy, PolicyEngine, PolicyStatus


@pytest.fixture()
def engine(tmp_path) -> PolicyEngine:
    return PolicyEngine(db_path=tmp_path / "policy.db")


def test_propose_and_get(engine: PolicyEngine) -> None:
    policy_id = engine.propose("agents must always verify output", "queen-planner")
    policy = engine.get(policy_id)
    assert policy is not None
    assert policy.policy_id == policy_id
    assert policy.constraint == "agents must always verify output"
    assert policy.status == PolicyStatus.PROPOSED
    assert policy.proposed_by == "queen-planner"
    assert policy.votes == []


def test_propose_generates_unique_id(engine: PolicyEngine) -> None:
    id1 = engine.propose("agents must always verify output", "queen-planner")
    id2 = engine.propose("agents must never skip approval", "queen-security")
    assert id1 != id2


def test_vote_records_correctly(engine: PolicyEngine) -> None:
    policy_id = engine.propose("agents must always verify output", "queen-planner")
    engine.vote(policy_id, "queen-security", True, "aligns with fail-closed posture")
    policy = engine.get(policy_id)
    assert len(policy.votes) == 1
    assert policy.votes[0].queen == "queen-security"
    assert policy.votes[0].approve is True
    assert policy.votes[0].reason == "aligns with fail-closed posture"


def test_vote_rejects_duplicate_queen(engine: PolicyEngine) -> None:
    policy_id = engine.propose("agents must always verify output", "queen-planner")
    engine.vote(policy_id, "queen-security", True, "ok")
    with pytest.raises(ValueError):
        engine.vote(policy_id, "queen-security", True, "again")


def test_enact_with_enough_votes(engine: PolicyEngine) -> None:
    policy_id = engine.propose("agents must always verify output", "queen-planner")
    engine.vote(policy_id, "queen-security", True, "ok")
    engine.vote(policy_id, "queen-testing", True, "ok")
    engine.vote(policy_id, "queen-memory", True, "ok")
    policy = engine.enact(policy_id, required_approvals=3)
    assert policy.status == PolicyStatus.ENACTED
    assert policy.enacted_at is not None


def test_enact_fails_without_votes(engine: PolicyEngine) -> None:
    policy_id = engine.propose("agents must always verify output", "queen-planner")
    engine.vote(policy_id, "queen-security", True, "ok")
    with pytest.raises(ValueError):
        engine.enact(policy_id, required_approvals=3)


def test_suspend_policy(engine: PolicyEngine) -> None:
    policy_id = engine.propose("agents must always verify output", "queen-planner")
    engine.vote(policy_id, "queen-security", True, "ok")
    engine.vote(policy_id, "queen-testing", True, "ok")
    engine.vote(policy_id, "queen-memory", True, "ok")
    engine.enact(policy_id, required_approvals=3)

    suspended = engine.suspend(policy_id, "queen-security")
    assert suspended.status == PolicyStatus.SUSPENDED

    chain = engine.policy_chain()
    suspension_records = [
        p for p in chain if p.constraint == f"SUSPEND: {policy_id}"
    ]
    assert len(suspension_records) == 1
    assert suspension_records[0].status == PolicyStatus.ENACTED


def test_current_policies_excludes_suspended(engine: PolicyEngine) -> None:
    policy_id = engine.propose("agents must always verify output", "queen-planner")
    engine.vote(policy_id, "queen-security", True, "ok")
    engine.vote(policy_id, "queen-testing", True, "ok")
    engine.vote(policy_id, "queen-memory", True, "ok")
    engine.enact(policy_id, required_approvals=3)

    engine.suspend(policy_id, "queen-security")

    current = engine.current_policies()
    assert all(p.policy_id != policy_id for p in current)


def test_policy_chain_includes_all(engine: PolicyEngine) -> None:
    policy_id = engine.propose("agents must always verify output", "queen-planner")
    engine.vote(policy_id, "queen-security", True, "ok")
    engine.vote(policy_id, "queen-testing", True, "ok")
    engine.vote(policy_id, "queen-memory", True, "ok")
    engine.enact(policy_id, required_approvals=3)
    engine.suspend(policy_id, "queen-security")

    chain = engine.policy_chain()
    statuses = {p.policy_id: p.status for p in chain}
    assert statuses[policy_id] == PolicyStatus.SUSPENDED
    assert len(chain) == 2


def test_validate_additive_accepts(engine: PolicyEngine) -> None:
    assert engine.validate_additive("agents must always verify output") is True


def test_validate_additive_rejects(engine: PolicyEngine) -> None:
    assert engine.validate_additive("allow unverified output") is False


def test_empty_engine(engine: PolicyEngine) -> None:
    assert engine.current_policies() == []
