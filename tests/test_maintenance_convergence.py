from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from types import SimpleNamespace

from aios.application.evidence.verification import VerificationAuthority
from aios.application.evidence.verifier_registry import VerifierRegistry
from aios.application.executor.service import ExecutorService
from aios.application.missions.mission_service import MissionService
from aios.application.maintenance.service import MaintenanceConvergenceService
from aios.application.promotion.authority import PromotionAuthority
from aios.application.workspaces import StagedWorkspaceManager
from aios.domain.executor import ExecutorResult
from aios.domain.maintenance.contracts import MaintenanceFinding
from aios.domain.maintenance.lifecycle import MaintenanceLifecycleEngine
from aios.domain.maintenance.repository import MaintenanceFindingRepository
from aios.domain.maintenance.scan_contracts import BoundedScanContract
from aios.domain.maintenance.scan_repository import MaintenanceScanRepository
from aios.domain.missions.mission_state import MissionState
from aios.infrastructure.missions.sqlite_mission_repository import (
    SqliteMissionRepository,
)


def _contract(*, root: Path, max_files: int = 4) -> BoundedScanContract:
    return BoundedScanContract(
        allowed_root=str(root),
        max_files=max_files,
        max_total_bytes=4096,
        max_file_bytes=1024,
        deadline=10,
        max_findings=4,
        git_history_allowed=False,
    )


def _finding(*, target_digest: str, source_digest: str) -> MaintenanceFinding:
    return MaintenanceFinding(
        finding_id="finding-controlled-defect",
        fingerprint="controlled-defect",
        scanner_id="controlled-scanner",
        scanner_version="1",
        kind="controlled_defect",
        severity="medium",
        confidence=1.0,
        evidence_quality="deterministic",
        target_id="bug.txt",
        target_digest=target_digest,
        source_digest=source_digest,
        first_seen="2026-07-18T00:00:00Z",
        last_seen="2026-07-18T00:00:00Z",
        occurrence_count=1,
        status="OPEN",
        deterministic_evidence="controlled defect marker is present",
    )


class _WorkerFoundry:
    def __init__(self, *, repair: bool = True) -> None:
        self.repair = repair
        self.calls = 0
        self.workspace_manager = None

    async def run(self, contract, **_kwargs):  # noqa: ANN001
        self.calls += 1
        if (
            self.workspace_manager is not None
            and self.workspace_manager.for_mission(contract.mission_id) is None
        ):
            self.workspace_manager.stage(contract.mission_id, contract.workspace_root)
        lease = self.workspace_manager.for_mission(contract.mission_id)
        if self.repair:
            Path(lease.workspace_path, "bug.txt").write_text(
                "fixed\n", encoding="utf-8"
            )
        return SimpleNamespace(worker_id="worker-maintenance-1", status="completed")


class _Executor:
    def __init__(self, *, exit_code: int = 0) -> None:
        self.exit_code = exit_code
        self.jobs = []

    def execute(self, job):  # noqa: ANN001
        self.jobs.append(job)
        return ExecutorResult(
            job_id=job.job_id,
            status="completed" if self.exit_code == 0 else "failed",
            exit_code=self.exit_code,
            stdout="rescan clean"
            if self.exit_code == 0
            else "repair verification failed",
            isolation_verified=True,
            environment_digest="environment-maintenance-1",
        )


def _service(
    tmp_path: Path, *, worker, executor
) -> tuple[MaintenanceConvergenceService, Path]:
    project = tmp_path / "project"
    project.mkdir()
    (project / "bug.txt").write_text("CONTROLLED_DEFECT\n", encoding="utf-8")
    workspace = StagedWorkspaceManager(tmp_path / "staged", enrolled_roots=(project,))
    missions = SqliteMissionRepository(tmp_path / "missions.db")
    mission_service = MissionService(missions, workspace_manager=workspace)
    finding_repository = MaintenanceFindingRepository(tmp_path / "operational.db")
    scan_repository = MaintenanceScanRepository(tmp_path / "operational.db")
    service = MaintenanceConvergenceService(
        finding_repository=finding_repository,
        scan_repository=scan_repository,
        mission_service=mission_service,
        worker_foundry=worker,
        executor_service=ExecutorService(
            profile="test",
            runner=executor.execute,
            backend_name="private_service",
        ),
        verifier_registry=VerifierRegistry(
            scanner_adapters={"controlled-scanner": _scanner}
        ),
        verification_authority=VerificationAuthority(),
        promotion_authority=PromotionAuthority(workspace),
        workspace_manager=workspace,
        lifecycle_engine=MaintenanceLifecycleEngine(),
    )
    worker.workspace_manager = workspace
    return service, project


def _scanner(context):  # noqa: ANN001
    payload = context.read_text("bug.txt")
    if "CONTROLLED_DEFECT" not in payload:
        return ()
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return (_finding(target_digest=digest, source_digest=digest),)


def test_bounded_context_enforces_file_and_total_limits_before_returning_findings(
    tmp_path: Path,
) -> None:
    service, project = _service(
        tmp_path,
        worker=_WorkerFoundry(),
        executor=_Executor(),
    )
    (project / "too-large.txt").write_text("x" * 2048, encoding="utf-8")
    result = service.run_scan(
        _contract(root=project),
        lambda context: context.read_text("too-large.txt") and (),
        scanner_id="bounded",
        scanner_version="1",
        target_id="too-large.txt",
        source_digest="source-1",
    )
    assert result.scan.status == "incomplete"
    assert "max_file_bytes" in (result.scan.failure_reason or "")


def test_maintenance_repair_uses_canonical_mission_executor_verifier_promotion_and_rescan(
    tmp_path: Path,
) -> None:
    worker = _WorkerFoundry()
    executor = _Executor()
    service, project = _service(tmp_path, worker=worker, executor=executor)

    initial = service.run_scan(
        _contract(root=project),
        _scanner,
        scanner_id="controlled-scanner",
        scanner_version="1",
        target_id="bug.txt",
        source_digest="source-before",
    )
    assert initial.scan.status == "completed"
    assert initial.findings[0].status == "OPEN"

    mission = service.create_repair_mission(
        initial.findings[0].fingerprint,
        operator_id="operator-1",
        workspace_root=str(project),
    )
    service.mission_service.start_deliberation(mission.mission_id)
    service.mission_service.request_approval(mission.mission_id)
    service.mission_service.approve(
        mission.mission_id,
        operator_id="operator-1",
        capability_digest="operator-capability-1",
        contract_digest=mission.contract_digest,
        authentication_event_id="auth-1",
        session_id="session-1",
    )

    result = asyncio.run(
        service.run_approved_repair(
            mission.mission_id,
            scanner=_scanner,
            rescan_contract=_contract(root=project),
            capability_consumer=lambda _request: True,
            create_checkpoint=lambda _request: "checkpoint-1",
            restore_checkpoint=lambda _checkpoint, _request: True,
            smoke_test=lambda _request: (project / "bug.txt").read_text() == "fixed\n",
        )
    )

    assert result.status == "VERIFIED_RESOLVED", result.reason
    assert worker.calls == 1
    assert len(executor.jobs) == 1
    assert project.joinpath("bug.txt").read_text() == "fixed\n"
    assert (
        service.finding_repository.get("controlled-defect").status
        == "VERIFIED_RESOLVED"
    )
    assert (
        service.mission_service.repository.get(mission.mission_id).state
        is MissionState.COMPLETED
    )


def test_failed_repair_never_resolves_finding(tmp_path: Path) -> None:
    worker = _WorkerFoundry(repair=False)
    executor = _Executor(exit_code=1)
    service, project = _service(tmp_path, worker=worker, executor=executor)
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
        capability_digest="operator-capability-1",
        contract_digest=mission.contract_digest,
        authentication_event_id="auth-1",
        session_id="session-1",
    )

    result = asyncio.run(
        service.run_approved_repair(
            mission.mission_id,
            scanner=_scanner,
            rescan_contract=_contract(root=project),
            capability_consumer=lambda _request: True,
            create_checkpoint=lambda _request: "checkpoint-1",
            restore_checkpoint=lambda _checkpoint, _request: True,
            smoke_test=lambda _request: False,
        )
    )

    assert result.status == "VERIFICATION_FAILED"
    assert (
        service.finding_repository.get("controlled-defect").status
        == "VERIFICATION_FAILED"
    )
    assert (
        service.mission_service.repository.get(mission.mission_id).state
        is MissionState.FAILED
    )


def test_rescan_incomplete_does_not_resolve_and_reappearance_reopens(
    tmp_path: Path,
) -> None:
    service, project = _service(
        tmp_path,
        worker=_WorkerFoundry(),
        executor=_Executor(),
    )
    finding = service.run_scan(
        _contract(root=project),
        _scanner,
        scanner_id="controlled-scanner",
        scanner_version="1",
        target_id="bug.txt",
        source_digest="source-before",
    ).findings[0]
    incomplete = service.run_scan(
        _contract(root=project, max_files=0),
        lambda context: tuple(context.iter_files()),
        scanner_id="controlled-scanner",
        scanner_version="1",
        target_id="bug.txt",
        source_digest="source-incomplete",
        rescan_of=finding.fingerprint,
    )
    assert incomplete.scan.status == "incomplete"
    assert service.finding_repository.get(finding.fingerprint).status == "OPEN"

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
        capability_digest="operator-capability-1",
        contract_digest=mission.contract_digest,
        authentication_event_id="auth-1",
        session_id="session-1",
    )
    resolved = asyncio.run(
        service.run_approved_repair(
            mission.mission_id,
            scanner=_scanner,
            rescan_contract=_contract(root=project),
            capability_consumer=lambda _request: True,
            create_checkpoint=lambda _request: "checkpoint-1",
            restore_checkpoint=lambda _checkpoint, _request: True,
            smoke_test=lambda _request: (project / "bug.txt").read_text() == "fixed\n",
        )
    )
    assert resolved.status == "VERIFIED_RESOLVED"

    (project / "bug.txt").write_text("CONTROLLED_DEFECT\n", encoding="utf-8")
    reopened = service.run_scan(
        _contract(root=project),
        _scanner,
        scanner_id="controlled-scanner",
        scanner_version="1",
        target_id="bug.txt",
        source_digest="source-reintroduced",
        rescan_of=finding.fingerprint,
    )
    assert reopened.findings[0].status == "REOPENED"
