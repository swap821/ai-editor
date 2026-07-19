from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from aios.application.evidence.verification import VerificationAuthority
from aios.application.maintenance.service import (
    MaintenanceConvergenceError,
    MaintenanceConvergenceService,
)
from aios.domain.evidence import VerificationObservation, VerificationPlanV1
from aios.domain.maintenance.contracts import (
    MaintenanceFinding,
    MaintenanceResolutionEvidence,
)
from aios.domain.maintenance.lifecycle import SecurityViolationError
from aios.domain.maintenance.scan_repository import MaintenanceScan
from aios.domain.missions.mission_state import MissionState
from aios.domain.promotion import PromotionResult, PromotionStatus

from tests.test_maintenance_convergence import _contract, _scanner, _service


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _prepared(
    tmp_path: Path,
    *,
    finding_status: str = "VERIFYING",
    mission_state: MissionState = MissionState.COMPLETED,
) -> tuple[MaintenanceConvergenceService, MaintenanceFinding, MaintenanceResolutionEvidence]:
    service, project = _service(
        tmp_path,
        worker=type("Worker", (), {"workspace_manager": None})(),
        executor=type("Executor", (), {"execute": lambda _self, _job: None})(),
    )
    finding = service.run_scan(
        _contract(root=project),
        _scanner,
        scanner_id="controlled-scanner",
        scanner_version="1",
        target_id="bug.txt",
        source_digest="source-before",
    ).findings[0]
    mission = service.create_repair_mission(
        finding.fingerprint,
        operator_id="operator-1",
        workspace_root=str(project),
    )
    service.mission_service.start_deliberation(mission.mission_id)
    service.mission_service.request_approval(mission.mission_id)
    service.mission_service.approve(
        mission.mission_id,
        operator_id="operator-1",
        capability_digest="capability-1",
        contract_digest=mission.contract_digest,
        authentication_event_id="auth-1",
        session_id="session-1",
    )
    service.mission_service.start_execution(mission.mission_id)
    if mission_state in (MissionState.VERIFYING, MissionState.COMPLETED):
        service.mission_service.start_verification(mission.mission_id)
    if mission_state is MissionState.COMPLETED:
        service.mission_service.complete(mission.mission_id, evidence_digest="bundle-1")

    finding = finding.model_copy(
        update={"mission_id": mission.mission_id, "status": finding_status}
    )
    service.finding_repository.save(finding)

    action_id = f"maintenance-action:{mission.mission_id}"
    verification = service.verification_authority.verify(
        mission_id=mission.mission_id,
        action_id=action_id,
        worker_id="worker-1",
        target=finding.target_id,
        plan=VerificationPlanV1(
            intended_behavior="controlled repair",
            targets=(finding.target_id,),
            minimum_strength=1,
        ),
        workspace_digest="workspace-1",
        diff_digest="diff-1",
        environment_digest="environment-1",
        observation=VerificationObservation(
            command="registered-verifier",
            exit_code=0,
            stdout="verified",
            passed_count=1,
            tool_version="test-verifier",
        ),
    )
    promotion = PromotionResult(
        mission_id=mission.mission_id,
        action_id=action_id,
        status=PromotionStatus.PROMOTED,
        diff_digest="diff-1",
        evidence_ids=verification.evidence_ids,
    )
    scan = MaintenanceScan(
        scan_id="rescan-1",
        scanner_id=finding.scanner_id,
        scanner_version=finding.scanner_version,
        target_id=finding.target_id,
        source_digest="source-after",
        contract=_contract(root=project),
        status="completed",
        started_at=_utc_now(),
        completed_at=_utc_now(),
        finding_count=0,
        finding_fingerprints=(),
        rescan_of=finding.fingerprint,
    )
    service.scan_repository.save(scan)
    evidence = MaintenanceResolutionEvidence(
        mission_id=mission.mission_id,
        mission_contract_digest=mission.contract_digest,
        action_id=action_id,
        promotion=promotion,
        verification_results=(verification,),
        workspace_digest="workspace-1",
        diff_digest="diff-1",
        rescan_id=scan.scan_id,
        scanner_id=finding.scanner_id,
        scanner_version=finding.scanner_version,
        target_id=finding.target_id,
        source_digest=scan.source_digest,
    )
    return service, finding, evidence


def _reject(service: MaintenanceConvergenceService, evidence: MaintenanceResolutionEvidence) -> None:
    with pytest.raises((MaintenanceConvergenceError, SecurityViolationError)):
        service.reconcile_rescan(evidence)


def test_open_finding_cannot_resolve(tmp_path: Path) -> None:
    service, _, evidence = _prepared(tmp_path, finding_status="OPEN")
    _reject(service, evidence)


def test_manually_bound_open_finding_cannot_resolve(tmp_path: Path) -> None:
    service, _, evidence = _prepared(tmp_path, finding_status="OPEN")
    _reject(service, evidence)


def test_missing_mission_cannot_resolve(tmp_path: Path) -> None:
    service, finding, evidence = _prepared(tmp_path)
    service.finding_repository.save(finding.model_copy(update={"mission_id": "missing"}))
    _reject(service, evidence.model_copy(update={"mission_id": "missing"}))


def test_incomplete_mission_cannot_resolve(tmp_path: Path) -> None:
    service, _, evidence = _prepared(tmp_path, mission_state=MissionState.RUNNING)
    _reject(service, evidence)


def test_mission_contract_digest_mismatch_cannot_resolve(tmp_path: Path) -> None:
    service, _, evidence = _prepared(tmp_path)
    _reject(
        service,
        evidence.model_copy(update={"mission_contract_digest": "other-contract"}),
    )


def test_action_binding_mismatch_cannot_resolve(tmp_path: Path) -> None:
    service, _, evidence = _prepared(tmp_path)
    _reject(service, evidence.model_copy(update={"action_id": "other-action"}))


def test_failed_promotion_cannot_resolve(tmp_path: Path) -> None:
    service, _, evidence = _prepared(tmp_path)
    _reject(
        service,
        evidence.model_copy(
            update={
                "promotion": evidence.promotion.model_copy(
                    update={"status": PromotionStatus.FAILED}
                )
            }
        ),
    )


def test_promotion_from_another_mission_cannot_resolve(tmp_path: Path) -> None:
    service, _, evidence = _prepared(tmp_path)
    _reject(
        service,
        evidence.model_copy(
            update={
                "promotion": evidence.promotion.model_copy(
                    update={"mission_id": "another-mission"}
                )
            }
        ),
    )


def test_fabricated_verification_cannot_resolve(tmp_path: Path) -> None:
    service, _, evidence = _prepared(tmp_path)
    _reject(
        service,
        evidence.model_copy(
            update={
                "verification_results": (
                    evidence.verification_results[0].model_copy(
                        update={"verification_id": "fabricated"}
                    ),
                )
            }
        ),
    )


def test_verification_from_another_mission_cannot_resolve(tmp_path: Path) -> None:
    service, _, evidence = _prepared(tmp_path)
    other = VerificationAuthority().verify(
        mission_id="another-mission",
        action_id=evidence.action_id,
        worker_id="worker-2",
        target="bug.txt",
        plan=VerificationPlanV1(intended_behavior="other", minimum_strength=1),
        workspace_digest=evidence.workspace_digest,
        diff_digest=evidence.diff_digest,
        environment_digest="environment-2",
        observation=VerificationObservation(command="registered-verifier", exit_code=0),
    )
    _reject(service, evidence.model_copy(update={"verification_results": (other,)}))


def test_stale_verification_cannot_resolve(tmp_path: Path) -> None:
    service, _, evidence = _prepared(tmp_path)
    _reject(
        service,
        evidence.model_copy(
            update={
                "verification_results": (
                    evidence.verification_results[0].model_copy(
                        update={"observed_at": "2000-01-01T00:00:00+00:00"}
                    ),
                )
            }
        ),
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [("workspace_digest", "other-workspace"), ("diff_digest", "other-diff")],
)
def test_digest_mismatch_cannot_resolve(
    tmp_path: Path, field: str, value: str
) -> None:
    service, _, evidence = _prepared(tmp_path)
    _reject(service, evidence.model_copy(update={field: value}))


def test_insufficient_verification_strength_cannot_resolve(tmp_path: Path) -> None:
    service, _, evidence = _prepared(tmp_path)
    _reject(
        service,
        evidence.model_copy(
            update={
                "verification_results": (
                    evidence.verification_results[0].model_copy(
                        update={"strength": 0, "required_strength": 1}
                    ),
                )
            }
        ),
    )


@pytest.mark.parametrize("status", ["incomplete", "failed"])
def test_noncompleted_rescan_cannot_resolve(tmp_path: Path, status: str) -> None:
    service, _, evidence = _prepared(tmp_path)
    scan = service.scan_repository.get(evidence.rescan_id)
    assert scan is not None
    service.scan_repository.save(scan.model_copy(update={"status": status}))
    _reject(service, evidence)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("rescan_of", "other-fingerprint"),
        ("scanner_id", "other-scanner"),
        ("scanner_version", "other-version"),
        ("target_id", "other-target"),
        ("source_digest", "other-source"),
    ],
)
def test_rescan_provenance_mismatch_cannot_resolve(
    tmp_path: Path, field: str, value: str
) -> None:
    service, _, evidence = _prepared(tmp_path)
    scan = service.scan_repository.get(evidence.rescan_id)
    assert scan is not None
    if field == "rescan_of":
        service.scan_repository.save(scan.model_copy(update={field: value}))
    else:
        service.scan_repository.save(scan.model_copy(update={field: value}))
    _reject(service, evidence)


def test_reappearing_finding_does_not_resolve(tmp_path: Path) -> None:
    service, finding, evidence = _prepared(tmp_path)
    service.finding_repository.save(finding.model_copy(update={"status": "REOPENED"}))
    scan = service.scan_repository.get(evidence.rescan_id)
    assert scan is not None
    service.scan_repository.save(
        scan.model_copy(update={"finding_count": 1, "finding_fingerprints": (finding.fingerprint,)})
    )
    assert service.reconcile_rescan(evidence).status == "REOPENED"


def test_current_verification_without_promotion_cannot_resolve(tmp_path: Path) -> None:
    service, _, evidence = _prepared(tmp_path)
    _reject(
        service,
        evidence.model_copy(
            update={
                "promotion": evidence.promotion.model_copy(
                    update={"status": PromotionStatus.REJECTED}
                )
            }
        ),
    )


def test_resolution_requires_complete_governed_evidence(tmp_path: Path) -> None:
    service, _, evidence = _prepared(tmp_path)
    resolved = service.reconcile_rescan(evidence)
    assert resolved.status == "VERIFIED_RESOLVED"
