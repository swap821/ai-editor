"""R6 acceptance tests for authoritative Human Sovereign mission approval."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from aios.application.missions.mission_service import MissionService
from aios.council.council_orchestrator import CouncilOrchestrator
from aios.domain.missions.mission_contract import (
    MissionBudget,
    MissionContract,
    VerificationPlan,
)
from aios.domain.capabilities.digest import payload_digest
from aios.domain.missions.mission_repository import MissionTransitionError
from aios.domain.missions.mission_state import MissionState
from aios.infrastructure.missions.sqlite_mission_repository import SqliteMissionRepository
from aios.runtime.contracts import MissionContract as RuntimeMissionContract


def _contract(mission_id: str = "r6-mission-1") -> MissionContract:
    return MissionContract(
        mission_id=mission_id,
        operator_id="planner-principal",
        goal="make a bounded repair",
        worker_type="deterministic_worker",
        created_by="planner",
        project_id="project-r6",
        turn_id="turn-r6",
        budget=MissionBudget(max_workers=1, max_steps=2, timeout_seconds=30),
        verification_plan=VerificationPlan(required_strength="strong"),
    )


def _awaiting(tmp_db: Path, mission_id: str = "r6-mission-1") -> tuple[MissionService, MissionContract]:
    service = MissionService(SqliteMissionRepository(tmp_db))
    contract = _contract(mission_id)
    service.create(contract)
    service.start_deliberation(contract.mission_id)
    service.request_approval(contract.mission_id)
    return service, contract


def test_human_approval_validates_contract_and_persists_attribution(tmp_path: Path) -> None:
    service, contract = _awaiting(tmp_path / "missions.db")

    with pytest.raises(MissionTransitionError, match="contract digest"):
        service.approve(
            contract.mission_id,
            operator_id="human-sovereign-1",
            capability_digest="sha256:capability-1",
            contract_digest="sha256:tampered-contract",
            authentication_event_id="auth-event-1",
            session_id="session-1",
        )

    assert service.repository.get(contract.mission_id).state is MissionState.AWAITING_APPROVAL

    approved = service.approve(
        contract.mission_id,
        operator_id="human-sovereign-1",
        capability_digest="sha256:capability-1",
        contract_digest=contract.digest(),
        authentication_event_id="auth-event-1",
        session_id="session-1",
    )

    assert approved.state is MissionState.APPROVED
    assert approved.operator_id == "human-sovereign-1"
    assert approved.capability_digest == "sha256:capability-1"
    approval = service.repository.transition_history(contract.mission_id)[-1]
    assert approval["actor"] == "human-sovereign-1"
    assert approval["capability_digest"] == "sha256:capability-1"
    assert approval["contract_digest"] == contract.digest()
    assert approval["authentication_event_id"] == "auth-event-1"
    assert approval["session_id"] == "session-1"


def test_concurrent_human_approvals_have_one_authoritative_winner(tmp_path: Path) -> None:
    db_path = tmp_path / "missions.db"
    _, contract = _awaiting(db_path)

    def approve(operator_id: str) -> str:
        service = MissionService(SqliteMissionRepository(db_path))
        try:
            service.approve(
                contract.mission_id,
                operator_id=operator_id,
                capability_digest=f"sha256:{operator_id}",
                contract_digest=contract.digest(),
                authentication_event_id=f"auth-{operator_id}",
                session_id=f"session-{operator_id}",
            )
        except MissionTransitionError:
            return "rejected"
        return "approved"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(approve, ("human-a", "human-b")))

    assert sorted(outcomes) == ["approved", "rejected"]
    record = SqliteMissionRepository(db_path).get(contract.mission_id)
    assert record.state is MissionState.APPROVED
    assert record.operator_id in {"human-a", "human-b"}
    approvals = [
        item
        for item in SqliteMissionRepository(db_path).transition_history(contract.mission_id)
        if item["to_state"] == MissionState.APPROVED.value
    ]
    assert len(approvals) == 1


def test_execution_cannot_self_approve_an_awaiting_mission(tmp_path: Path) -> None:
    service, domain_contract = _awaiting(tmp_path / "missions.db", "r6-execution-1")
    runtime_contract = RuntimeMissionContract(
        mission_id=domain_contract.mission_id,
        goal=domain_contract.goal,
        worker_type=domain_contract.worker_type,
        created_by=domain_contract.created_by,
        workspace_root=str(tmp_path / "workspace"),
    )

    class NeverRuns:
        async def run(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("worker must not be reached without approval")

    orchestrator = CouncilOrchestrator(
        runtime_root=tmp_path,
        mission_service=service,
        foundry=NeverRuns(),  # type: ignore[arg-type]
    )

    with pytest.raises(MissionTransitionError, match="human approval"):
        asyncio.run(orchestrator.execute(runtime_contract, []))

    assert service.repository.get(domain_contract.mission_id).state is MissionState.AWAITING_APPROVAL


def test_rejection_is_terminal_and_survives_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "missions.db"
    service, contract = _awaiting(db_path, "r6-rejection-1")
    service.reject(
        contract.mission_id,
        operator_id="human-sovereign-1",
        reason="scope changed",
        capability_digest="sha256:reject-1",
        contract_digest=contract.digest(),
        authentication_event_id="auth-reject-1",
        session_id="session-reject-1",
    )

    restarted = MissionService(SqliteMissionRepository(db_path))
    assert restarted.repository.get(contract.mission_id).state is MissionState.REJECTED
    with pytest.raises(MissionTransitionError, match="invalid transition"):
        restarted.approve(
            contract.mission_id,
            operator_id="human-sovereign-2",
            capability_digest="sha256:approve-after-reject",
            contract_digest=contract.digest(),
            authentication_event_id="auth-approve-2",
            session_id="session-approve-2",
        )


def test_tampered_runtime_contract_cannot_be_executed_after_approval(tmp_path: Path) -> None:
    db_path = tmp_path / "missions.db"
    service = MissionService(SqliteMissionRepository(db_path))
    domain_contract = _contract("r6-tamper-1")
    runtime_contract = RuntimeMissionContract(
        mission_id=domain_contract.mission_id,
        goal=domain_contract.goal,
        worker_type=domain_contract.worker_type,
        created_by=domain_contract.created_by,
        workspace_root=str(tmp_path / "workspace"),
    )
    service.create(
        domain_contract,
        runtime_contract_digest=payload_digest(runtime_contract.model_dump(mode="json")),
    )
    service.start_deliberation(domain_contract.mission_id)
    service.request_approval(domain_contract.mission_id)
    authority = service.repository.get(domain_contract.mission_id)
    service.approve(
        domain_contract.mission_id,
        operator_id="human-sovereign-1",
        capability_digest="sha256:capability-tamper",
        contract_digest=authority.contract_digest,
        authentication_event_id="auth-tamper-1",
        session_id="session-tamper-1",
    )

    tampered = runtime_contract.model_copy(update={"goal": "altered after approval"})
    orchestrator = CouncilOrchestrator(runtime_root=tmp_path, mission_service=service)
    with pytest.raises(MissionTransitionError, match="runtime contract digest"):
        asyncio.run(orchestrator.execute(tampered, []))

    assert service.repository.get(domain_contract.mission_id).state is MissionState.APPROVED
