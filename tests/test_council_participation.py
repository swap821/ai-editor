from __future__ import annotations

import pytest

from aios.council.participation import CouncilParticipationPolicy
from aios.council.queens import CouncilMissionRequest


def _contract(**overrides: object) -> CouncilMissionRequest:
    data: dict[str, object] = {
        "mission_id": "m-1",
        "goal": "Improve the login page.",
        "workspace_root": "/tmp/ws",
        "allowed_files": ["frontend/src/pages/Login.jsx"],
        "forbidden_files": ["backend/"],
        "worker_type": "hybrid_plan_worker",
        "risk_level": "GREEN",
        "metadata": {},
    }
    data.update(overrides)
    return CouncilMissionRequest(**data)  # type: ignore[arg-type]


def test_default_participation_is_minimal() -> None:
    policy = CouncilParticipationPolicy()
    contract = _contract()
    participation = policy.decide(contract)

    assert participation.required == ("planner", "security", "memory", "testing")
    assert participation.optional == ()
    assert "minimal Council" in participation.reason


def test_routing_joins_when_many_files() -> None:
    policy = CouncilParticipationPolicy()
    contract = _contract(
        allowed_files=["a", "b", "c", "d"],
    )
    participation = policy.decide(contract)

    assert "routing" in participation.optional


def test_routing_joins_for_swarm_or_role_pass() -> None:
    policy = CouncilParticipationPolicy()
    swarm = _contract(worker_type="swarm_worker")
    role_pass = _contract(worker_type="role_pass_worker")

    assert "routing" in policy.decide(swarm).optional
    assert "routing" in policy.decide(role_pass).optional


def test_reflection_joins_for_red_risk() -> None:
    policy = CouncilParticipationPolicy()
    contract = _contract(risk_level="RED")
    participation = policy.decide(contract)

    assert "reflection" in participation.optional


def test_reflection_joins_for_prior_failures() -> None:
    policy = CouncilParticipationPolicy()
    contract = _contract(metadata={"prior_failure_count": 1})
    participation = policy.decide(contract)

    assert "reflection" in participation.optional


def test_project_understanding_joins_for_project_id() -> None:
    policy = CouncilParticipationPolicy()
    contract = _contract(metadata={"project_id": "proj-42"})
    participation = policy.decide(contract)

    assert "project_understanding" in participation.optional


def test_project_understanding_joins_for_long_goal() -> None:
    policy = CouncilParticipationPolicy()
    contract = _contract(goal="x" * 201)
    participation = policy.decide(contract)

    assert "project_understanding" in participation.optional


def test_critique_joins_for_yellow_risk() -> None:
    policy = CouncilParticipationPolicy()
    contract = _contract(risk_level="YELLOW")
    participation = policy.decide(contract)

    assert "critique" in participation.optional


def test_explain_includes_full_council_flag() -> None:
    policy = CouncilParticipationPolicy()
    explanation = policy.explain(_contract(risk_level="RED", metadata={"project_id": "p"}))

    assert "required" in explanation
    assert "optional" in explanation
    assert isinstance(explanation["full_council"], bool)
