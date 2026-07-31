"""Organ 10 + 42: MissionAuthority journals through RecoveryResumptionAuthority."""

from __future__ import annotations

from pathlib import Path

from aios.application.missions.mission_service import MissionAuthority
from aios.application.recovery.authority import RecoveryResumptionAuthority
from aios.domain.missions.mission_contract import MissionContract
from aios.infrastructure.missions.sqlite_mission_repository import SqliteMissionRepository
from aios.infrastructure.missions.transition_journal_store import MissionTransitionJournal


def _authority(tmp_path: Path) -> tuple[MissionAuthority, RecoveryResumptionAuthority]:
    journal = MissionTransitionJournal(tmp_path / "journal.db")
    recovery = RecoveryResumptionAuthority(journal)
    mission = MissionAuthority(
        SqliteMissionRepository(tmp_path / "missions.db"),
        export_dir=tmp_path / "exports",
        recovery_authority=recovery,
    )
    return mission, recovery


def _contract(mission_id: str) -> MissionContract:
    return MissionContract(
        mission_id=mission_id,
        operator_id="operator-1",
        goal="repair defect",
        worker_type="local-clerk",
        created_by="tests",
    )


def test_mission_authority_journals_mission_created_when_recovery_is_wired(
    tmp_path: Path,
) -> None:
    mission, recovery = _authority(tmp_path)

    record = mission.create(_contract("mission-journal-1"))

    assert recovery.last_transition(record.mission_id) == "MISSION_CREATED"
    assert recovery.verify_journal().verified == 1


def test_maintenance_mission_service_shares_recovery_journal() -> None:
    from aios.api.deps import get_maintenance_convergence_service, get_recovery_resumption_authority

    service = get_maintenance_convergence_service()
    recovery = get_recovery_resumption_authority()

    assert service.mission_service.recovery_authority is recovery
    assert service.mission_journal is recovery.journal
