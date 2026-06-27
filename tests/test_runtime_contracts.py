from __future__ import annotations

import pytest
from pydantic import ValidationError

from aios.runtime.contracts import (
    KingReport,
    MissionContract,
    QueenVerdict,
    RunLedger,
    WorkerResult,
)


def _mission(**overrides: object) -> MissionContract:
    data: dict[str, object] = {
        "mission_id": "mission-1",
        "goal": "append a harmless comment",
        "worker_type": "deterministic_worker",
        "created_by": "planner",
        "workspace_root": "C:/workspace",
    }
    data.update(overrides)
    return MissionContract(**data)


def test_phase0_contracts_import_and_validate_minimal_shapes() -> None:
    mission = _mission()
    verdict = QueenVerdict(
        queen="security",
        verdict="allow_with_approval",
        risk="YELLOW",
        reason="write requires human approval",
    )
    worker = WorkerResult(
        mission_id=mission.mission_id,
        worker_id="worker-1",
        status="completed",
        risk_after="GREEN",
        started_at="2026-06-27T00:00:00Z",
        ended_at="2026-06-27T00:00:01Z",
    )
    ledger = RunLedger(
        mission_id=mission.mission_id,
        mission=mission.goal,
        risk_before="YELLOW",
        risk_after=worker.risk_after,
        contract=mission,
        council_verdicts=[verdict],
        status="completed",
        created_at="2026-06-27T00:00:00Z",
        completed_at="2026-06-27T00:00:01Z",
    )
    report = KingReport(
        mission_id=mission.mission_id,
        mission=mission.goal,
        status="completed",
        recommendation="approve",
        risk="GREEN",
        approval_needed=False,
        rollback_available=False,
        human_summary="Worker completed the mission under contract.",
    )

    assert mission.version == "v0.1"
    assert ledger.contract == mission
    assert ledger.council_verdicts == [verdict]
    assert report.recommendation == "approve"


def test_contract_lists_and_dicts_do_not_share_mutable_defaults() -> None:
    first = _mission()
    second = _mission(mission_id="mission-2")

    first.allowed_files.append("frontend/src/workbench/GagosChrome.jsx")
    first.metadata["model_policy"] = {"mode": "local"}

    assert second.allowed_files == []
    assert second.metadata == {}


def test_invalid_contract_values_fail_validation() -> None:
    with pytest.raises(ValidationError):
        _mission(risk_level="ORANGE")

    with pytest.raises(ValidationError):
        WorkerResult(
            mission_id="mission-1",
            worker_id="worker-1",
            status="escaped",
            risk_after="GREEN",
            started_at="2026-06-27T00:00:00Z",
            ended_at="2026-06-27T00:00:01Z",
        )


def test_contracts_reject_unknown_fields_for_v01_schema_lock() -> None:
    with pytest.raises(ValidationError):
        MissionContract(
            mission_id="mission-1",
            goal="do work",
            worker_type="deterministic_worker",
            created_by="planner",
            workspace_root="C:/workspace",
            surprise_field=True,
        )
