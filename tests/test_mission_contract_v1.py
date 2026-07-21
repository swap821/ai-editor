from __future__ import annotations

import json
from pathlib import Path

import pytest

from aios.domain.missions.mission_contract import (
    MissionBudget,
    MissionContract,
    VerificationPlan,
)
from aios.domain.missions.mission_repository import (
    MissionNotFoundError,
    MissionRecord,
    MissionTransitionError,
)
from aios.domain.missions.mission_state import MissionState, MissionTransition
from aios.infrastructure.missions.sqlite_mission_repository import (
    SqliteMissionRepository,
)
from aios.application.missions.mission_service import MissionService
from aios.application.workspaces import StagedWorkspaceManager


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "missions.db"


@pytest.fixture
def repository(tmp_db: Path) -> SqliteMissionRepository:
    return SqliteMissionRepository(tmp_db)


@pytest.fixture
def service(repository: SqliteMissionRepository) -> MissionService:
    return MissionService(repository)


def _contract(**overrides: object) -> MissionContract:
    data: dict[str, object] = {
        "mission_id": "mission-1",
        "operator_id": "operator-1",
        "goal": "append a harmless comment",
        "worker_type": "deterministic_worker",
        "created_by": "planner",
        "project_id": "project-1",
        "turn_id": "turn-1",
        "budget": MissionBudget(max_workers=1, max_steps=5, timeout_seconds=300),
        "verification_plan": VerificationPlan(required_strength="strong"),
    }
    data.update(overrides)
    return MissionContract(**data)


def test_contract_version_and_digest() -> None:
    contract = _contract()
    assert contract.version == "v1"
    digest = contract.digest()
    assert len(digest) == 64
    assert contract.digest() == digest


def test_contract_digest_changes_with_field() -> None:
    a = _contract()
    b = _contract(goal="different goal")
    assert a.digest() != b.digest()


def test_repository_creates_mission_in_draft_state(
    repository: SqliteMissionRepository,
) -> None:
    contract = _contract()
    record = repository.create(contract)
    assert isinstance(record, MissionRecord)
    assert record.state == MissionState.DRAFT
    assert record.contract_digest == contract.digest()


def test_repository_get_missing_mission_raises(
    repository: SqliteMissionRepository,
) -> None:
    with pytest.raises(MissionNotFoundError):
        repository.get("missing")


def test_valid_state_transitions(repository: SqliteMissionRepository) -> None:
    contract = _contract()
    repository.create(contract, state=MissionState.DRAFT)
    record = repository.apply_transition(
        contract.mission_id, MissionState.DELIBERATING, actor="system"
    )
    assert record.state == MissionState.DELIBERATING
    record = repository.apply_transition(
        contract.mission_id, MissionState.AWAITING_APPROVAL, actor="council"
    )
    assert record.state == MissionState.AWAITING_APPROVAL
    record = repository.apply_transition(
        contract.mission_id,
        MissionState.APPROVED,
        actor="operator-1",
        capability_digest="cap-1",
        contract_digest=contract.digest(),
        authentication_event_id="auth-1",
        session_id="session-1",
    )
    assert record.state == MissionState.APPROVED
    record = repository.apply_transition(
        contract.mission_id, MissionState.RUNNING, actor="system"
    )
    assert record.state == MissionState.RUNNING


def test_invalid_transition_is_rejected(repository: SqliteMissionRepository) -> None:
    contract = _contract()
    repository.create(contract, state=MissionState.DRAFT)
    with pytest.raises(MissionTransitionError):
        repository.apply_transition(
            contract.mission_id, MissionState.RUNNING, actor="system"
        )


def test_service_double_approve_guard(service: MissionService) -> None:
    contract = _contract()
    service.create(contract)
    service.start_deliberation(contract.mission_id)
    service.request_approval(contract.mission_id)
    service.double_approve_guard(
        contract.mission_id,
        operator_id="operator-1",
        capability_digest="cap-1",
        contract_digest=contract.digest(),
        authentication_event_id="auth-1",
        session_id="session-1",
    )
    with pytest.raises(MissionTransitionError, match="capability already consumed"):
        service.double_approve_guard(
            contract.mission_id,
            operator_id="operator-1",
            capability_digest="cap-1",
            contract_digest=contract.digest(),
            authentication_event_id="auth-1",
            session_id="session-1",
        )


def test_mission_survives_restart(tmp_db: Path) -> None:
    contract = _contract()
    repo = SqliteMissionRepository(tmp_db)
    repo.create(contract, state=MissionState.AWAITING_APPROVAL)

    repo2 = SqliteMissionRepository(tmp_db)
    record = repo2.get(contract.mission_id)
    assert record.state == MissionState.AWAITING_APPROVAL
    assert record.contract.mission_id == contract.mission_id


def test_query_by_project_and_turn(repository: SqliteMissionRepository) -> None:
    a = _contract(mission_id="a", project_id="p1", turn_id="t1")
    b = _contract(mission_id="b", project_id="p1", turn_id="t2")
    c = _contract(mission_id="c", project_id="p2", turn_id="t1")
    repository.create(a)
    repository.create(b)
    repository.create(c)
    assert {r.mission_id for r in repository.list_by_project("p1")} == {"b", "a"}
    assert {r.mission_id for r in repository.list_by_turn("t1")} == {"c", "a"}


def test_file_tampering_does_not_affect_authoritative_state(
    repository: SqliteMissionRepository, service: MissionService, tmp_path: Path
) -> None:
    contract = _contract()
    service.create(contract)
    service.start_deliberation(contract.mission_id)
    service.request_approval(contract.mission_id)
    export_path = service.export(contract.mission_id)

    tampered = json.loads(export_path.read_text())
    tampered["state"] = "approved"
    export_path.write_text(json.dumps(tampered), encoding="utf-8")

    record = repository.get(contract.mission_id)
    assert record.state == MissionState.AWAITING_APPROVAL


def test_migrate_legacy_artifact(repository: SqliteMissionRepository) -> None:
    contract = _contract()
    record = repository.migrate_from_legacy(
        contract.mission_id,
        contract,
        MissionState.COMPLETED,
        exported_path="missions/mission-1/run_ledger.json",
    )
    assert record.state == MissionState.COMPLETED
    assert record.exported_path == "missions/mission-1/run_ledger.json"
    history = repository.transition_history(contract.mission_id)
    assert len(history) == 0


def test_all_defined_transitions_are_allowed() -> None:
    for transition in MissionTransition:
        assert MissionTransition.is_allowed(transition.from_state, transition.to_state)


def test_transition_history_is_recorded(service: MissionService) -> None:
    contract = _contract()
    service.create(contract)
    service.start_deliberation(contract.mission_id)
    service.request_approval(contract.mission_id)
    history = service.repository.transition_history(contract.mission_id)
    states = [h["to_state"] for h in history]
    assert states == ["deliberating", "awaiting_approval"]
    assert all(h["actor"] for h in history)


def test_service_cleans_staged_workspace_after_terminal_completion(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("print('ok')\n", encoding="utf-8")
    manager = StagedWorkspaceManager(tmp_path / "staged", enrolled_roots=(project,))
    repository = SqliteMissionRepository(tmp_path / "missions.db")
    service = MissionService(repository, workspace_manager=manager)
    contract = _contract(workspace_root=str(project))

    service.create(contract)
    lease = manager.stage(contract.mission_id, project)
    service.start_deliberation(contract.mission_id)
    service.request_approval(contract.mission_id)
    service.approve(
        contract.mission_id,
        operator_id="operator-1",
        capability_digest="cap-1",
        contract_digest=contract.digest(),
        authentication_event_id="auth-1",
        session_id="session-1",
    )
    service.start_execution(contract.mission_id)
    service.start_verification(contract.mission_id)
    service.complete(contract.mission_id)

    assert not Path(lease.workspace_path).exists()
    assert manager.for_mission(contract.mission_id) is None
