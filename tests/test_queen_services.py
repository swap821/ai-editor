from __future__ import annotations

import asyncio
from pathlib import Path

from aios.council.queen_service import (
    QUEEN_SERVICES,
    clear_queen_services,
    init_queen_services,
)
from aios.council.queens import (
    CouncilMissionRequest,
    ProjectUnderstandingQueen,
    ReflectionQueen,
    RoutingQueen,
)
from aios.runtime.contracts import MissionContract


def _contract(**overrides: object) -> MissionContract:
    data: dict[str, object] = {
        "mission_id": "m-1",
        "goal": "Improve login.",
        "worker_type": "hybrid_plan_worker",
        "created_by": "test",
        "workspace_root": "/tmp/ws",
        "allowed_files": ["frontend/src/pages/Login.jsx"],
        "metadata": {},
    }
    data.update(overrides)
    return MissionContract(**data)  # type: ignore[arg-type]


def test_init_queen_services_populates_registry() -> None:
    clear_queen_services()
    registry = init_queen_services()

    assert set(registry) == {
        "planner",
        "security",
        "memory",
        "testing",
        "critique",
        "routing",
        "reflection",
        "project_understanding",
    }
    assert registry is QUEEN_SERVICES


def test_init_queen_services_is_idempotent() -> None:
    clear_queen_services()
    first = init_queen_services()
    second = init_queen_services()

    assert first is second


def test_routing_queen_service_recommendation() -> None:
    clear_queen_services()
    init_queen_services()
    svc = QUEEN_SERVICES["routing"]

    async def _run() -> None:
        await svc.start()
        try:
            return await svc.submit(_contract())
        finally:
            await svc.stop()

    verdict = asyncio.run(_run())
    assert verdict.queen == "routing"
    assert verdict.verdict == "allow"
    assert verdict.recommended_worker_strategy == "hybrid_plan_worker"


def test_reflection_queen_service_escalates_on_prior_failures() -> None:
    clear_queen_services()
    init_queen_services()
    svc = QUEEN_SERVICES["reflection"]

    async def _run() -> None:
        await svc.start()
        try:
            return await svc.submit(
                _contract(metadata={"prior_failure_count": 2, "prior_failure_patterns": ["scope_creep"]})
            )
        finally:
            await svc.stop()

    verdict = asyncio.run(_run())
    assert verdict.queen == "reflection"
    assert any("scope creep" in c.lower() for c in verdict.constraints)


def test_project_understanding_queen_service_asks_questions_without_project() -> None:
    clear_queen_services()
    init_queen_services()
    svc = QUEEN_SERVICES["project_understanding"]

    async def _run() -> None:
        await svc.start()
        try:
            return await svc.submit(_contract())
        finally:
            await svc.stop()

    verdict = asyncio.run(_run())
    assert verdict.queen == "project_understanding"
    assert any("project context" in q.lower() for q in verdict.unresolved_questions)


def test_routing_queen_selects_strategy_by_worker_type() -> None:
    queen = RoutingQueen()

    assert queen.review(_contract(worker_type="swarm_worker")).recommended_worker_strategy == "swarm_strategy"
    assert queen.review(_contract(worker_type="role_pass_worker")).recommended_worker_strategy == "role_pass_strategy"
    assert (
        queen.review(_contract(worker_type="deterministic_worker")).recommended_worker_strategy
        == "deterministic_worker_strategy"
    )


def test_reflection_queen_strengthen_only() -> None:
    queen = ReflectionQueen()

    green_no_failures = queen.review(_contract(risk_level="GREEN"))
    assert green_no_failures.risk == "GREEN"

    yellow_with_failures = queen.review(
        _contract(risk_level="YELLOW", metadata={"prior_failure_count": 1})
    )
    assert yellow_with_failures.verdict == "allow_with_approval"
    assert "prior failure" in " ".join(yellow_with_failures.constraints).lower()


def test_project_understanding_queen_adds_constraints() -> None:
    queen = ProjectUnderstandingQueen()
    contract = _contract(metadata={"project_id": "p-1", "complex_task": True})

    verdict = queen.review(contract)

    assert any("project 'p-1'" in c for c in verdict.constraints)
    assert any("milestone" in c.lower() for c in verdict.constraints)


def test_clear_queen_services_empties_registry() -> None:
    init_queen_services()
    clear_queen_services()

    assert QUEEN_SERVICES == {}
