"""Phase 4 — Production proof for Real WorkerFoundry and Private Executor integration.

Tests:
1. WorkerFoundry contract staging & lifecycle tracking with CortexBus event emissions.
2. ExecutorService job construction with ExecutorCapability and ResourceLimits.
3. MaintenanceConvergenceService governed repair execution using real WorkerFoundry and ExecutorService.
4. Fail-closed lifecycle state handling when worker execution fails.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from typing import Any
from pathlib import Path
from types import SimpleNamespace

import pytest

from aios.application.evidence.verification import VerificationAuthority
from aios.application.evidence.verifier_registry import VerifierRegistry
from aios.application.executor.service import ExecutorService
from aios.application.governance import EmergencyStopController, EmergencyStopHooks
from aios.application.maintenance.service import MaintenanceConvergenceService
from aios.application.missions.mission_service import MissionService
from aios.application.promotion.authority import PromotionAuthority
from aios.application.workers.foundry import WorkerFoundry
from aios.application.workspaces import StagedWorkspaceManager
from aios.core.events import CanonicalEventType
from aios.domain.executor import ExecutorJob, ExecutorResult
from aios.domain.maintenance.contracts import MaintenanceFinding
from aios.domain.maintenance.lifecycle import MaintenanceLifecycleEngine
from aios.domain.maintenance.repository import MaintenanceFindingRepository
from aios.domain.maintenance.scan_contracts import BoundedScanContract
from aios.domain.maintenance.scan_repository import MaintenanceScanRepository
from aios.domain.workers.worker_contract import WorkerState, WorkerStrategyName
from aios.infrastructure.missions.sqlite_mission_repository import (
    SqliteMissionRepository,
)
from aios.runtime.cortex_bus import CortexBus


def _finding(*, target_id: str = "bug.txt", target_digest: str, source_digest: str) -> MaintenanceFinding:
    return MaintenanceFinding(
        finding_id="finding-real-foundry-test",
        fingerprint="real-foundry-fingerprint",
        scanner_id="admitted-scanner",
        scanner_version="1",
        kind="real_foundry_defect",
        severity="high",
        confidence=1.0,
        evidence_quality="deterministic",
        target_id=target_id,
        target_digest=target_digest,
        source_digest=source_digest,
        first_seen="2026-07-19T00:00:00Z",
        last_seen="2026-07-19T00:00:00Z",
        occurrence_count=1,
        status="OPEN",
        deterministic_evidence="real foundry defect present",
    )


def _scanner(context):  # noqa: ANN001
    payload = context.read_text("bug.txt")
    if "DEFECT_MARKER" not in payload:
        return ()
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return (_finding(target_digest=digest, source_digest=digest),)


@pytest.fixture()
def foundry_env(tmp_path: Path) -> Iterator[
    tuple[MaintenanceConvergenceService, WorkerFoundry, ExecutorService, StagedWorkspaceManager, CortexBus, Path]
]:
    project = tmp_path / "project"
    project.mkdir()
    (project / "bug.txt").write_text("DEFECT_MARKER\n", encoding="utf-8")

    workspace = StagedWorkspaceManager(tmp_path / "staged", enrolled_roots=(project,))
    missions = SqliteMissionRepository(tmp_path / "missions.db")
    mission_service = MissionService(missions, workspace_manager=workspace)
    finding_repository = MaintenanceFindingRepository(tmp_path / "operational.db")
    scan_repository = MaintenanceScanRepository(tmp_path / "operational.db")
    bus = CortexBus(db_path=tmp_path / "cortex_bus.db")
    emergency_stop = EmergencyStopController(
        hooks=EmergencyStopHooks(
            revoke_capabilities=lambda: None,
            cancel_queued_missions=lambda _reason="": 0,
            kill_active_workers=lambda: None,
            disable_autonomy=lambda: None,
            preserve_evidence=lambda _reason="": None,
        )
    )

    class _RepairStrategy:
        name = WorkerStrategyName.DETERMINISTIC

        async def run(self, request) -> Any:  # noqa: ANN001
            staged = request.context.get("staged_workspace", {})
            workspace_path = Path(staged.get("workspace_path", request.spec.scope.get("workspace_root", "")))
            if workspace_path.exists():
                (workspace_path / "bug.txt").write_text("REPAIRED_CLEAN\n", encoding="utf-8")
            return SimpleNamespace(worker_id=request.spec.worker_id, status="completed")

    foundry = WorkerFoundry(
        workspace_manager=workspace,
        bus=bus,
        strategies={WorkerStrategyName.DETERMINISTIC.value: _RepairStrategy()},
        emergency_stop=emergency_stop,
    )

    executor_runner = lambda job: ExecutorResult(  # noqa: E731
        job_id=job.job_id,
        status="completed",
        exit_code=0,
        stdout="clean execution",
        isolation_verified=True,
        environment_digest="env-real-1",
    )
    executor_service = ExecutorService(
        profile="test",
        runner=executor_runner,
        backend_name="private_service",
    )

    service = MaintenanceConvergenceService(
        finding_repository=finding_repository,
        scan_repository=scan_repository,
        mission_service=mission_service,
        worker_foundry=foundry,
        executor_service=executor_service,
        verifier_registry=VerifierRegistry(scanner_adapters={"admitted-scanner": _scanner}),
        verification_authority=VerificationAuthority(),
        promotion_authority=PromotionAuthority(workspace, emergency_stop=emergency_stop),
        workspace_manager=workspace,
        lifecycle_engine=MaintenanceLifecycleEngine(),
    )

    yield service, foundry, executor_service, workspace, bus, project


# ---------------------------------------------------------------------------
# Test 1: WorkerFoundry contract staging & lifecycle tracking
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_worker_foundry_contract_staging_and_events(foundry_env) -> None:
    service, foundry, _executor, workspace, bus, project = foundry_env

    # 1. Run initial scan
    scan_contract = BoundedScanContract(
        allowed_root=str(project),
        max_files=10,
        max_total_bytes=100_000,
        max_file_bytes=10_000,
        deadline=10,
        max_findings=10,
        git_history_allowed=False,
    )
    scan_result = service.run_scan(
        scan_contract,
        _scanner,
        scanner_id="admitted-scanner",
        scanner_version="1",
        target_id="bug.txt",
        source_digest=str(project),
    )
    assert scan_result.scan.status == "completed"
    assert len(scan_result.findings) == 1
    finding = scan_result.findings[0]

    # 2. Create & approve repair mission
    record = service.create_repair_mission(
        finding.fingerprint,
        operator_id="op-real-1",
        workspace_root=str(project),
    )
    mission_id = record.mission_id
    service.mission_service.start_deliberation(mission_id)
    service.mission_service.request_approval(mission_id)
    service.mission_service.approve(
        mission_id,
        operator_id="op-real-1",
        capability_digest="cap-real-1",
        contract_digest=record.contract_digest,
        authentication_event_id="auth-real-1",
        session_id="session-real-1",
    )

    # 3. Run approved repair using real WorkerFoundry
    rescan_contract = BoundedScanContract(
        allowed_root=str(project),
        max_files=10,
        max_total_bytes=100_000,
        max_file_bytes=10_000,
        deadline=10,
        max_findings=10,
        git_history_allowed=False,
    )
    repair_result = await service.run_approved_repair(
        mission_id,
        scanner=_scanner,
        rescan_contract=rescan_contract,
        capability_consumer=lambda _r: True,
        create_checkpoint=lambda _r: "cp-1",
        restore_checkpoint=lambda _c, _r: True,
        smoke_test=lambda _r: True,
    )

    assert repair_result.status == "VERIFIED_RESOLVED"
    assert repair_result.mission_id == mission_id

    # 4. Verify WorkerFoundry lifecycle states and bus events
    assert len(foundry._lifecycles) == 1
    worker_id = next(iter(foundry._lifecycles.keys()))
    lifecycle = foundry.lifecycle(worker_id)
    assert lifecycle is not None
    assert lifecycle.state == WorkerState.DISSOLVED

    principal = foundry.principal(worker_id)
    assert principal is not None
    assert principal.mission_id == mission_id

    bus_events = bus.fetch_since(0)
    event_types = [e.event_type for e in bus_events]
    assert CanonicalEventType.WORKER_REQUESTED.value in event_types
    assert CanonicalEventType.WORKER_ADMITTED.value in event_types
    assert CanonicalEventType.WORKER_STARTED.value in event_types
    assert CanonicalEventType.WORKER_COMPLETED.value in event_types
    assert CanonicalEventType.WORKER_DISSOLVED.value in event_types


# ---------------------------------------------------------------------------
# Test 2: ExecutorService job building and capabilities
# ---------------------------------------------------------------------------


def test_executor_service_command_job_building(foundry_env) -> None:
    _service, _foundry, executor, _workspace, _bus, _project = foundry_env

    job = executor.build_command_job(
        mission_contract_digest="digest-12345",
        command="python -m pytest",
        workspace_snapshot="/tmp/staged_workspace",
        timeout_seconds=30,
        job_id="job-custom-123",
    )

    assert isinstance(job, ExecutorJob)
    assert job.job_id == "job-custom-123"
    assert job.mission_contract_digest == "digest-12345"
    assert job.argv == ("python", "-m", "pytest")
    assert job.capability.action_digest != ""
    assert job.capability.mission_contract_digest == "digest-12345"
    assert job.resource_limits.timeout_seconds == 30

    result = executor.execute(job)
    assert result.job_id == "job-custom-123"
    assert result.status == "completed"
    assert result.isolation_verified is True


# ---------------------------------------------------------------------------
# Test 3: Worker execution failure fail-closed behavior
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_worker_foundry_failed_worker_fails_closed(foundry_env) -> None:
    service, _foundry, executor, workspace, bus, project = foundry_env

    class _FailingStrategy:
        name = WorkerStrategyName.DETERMINISTIC

        async def run(self, request) -> Any:  # noqa: ANN001
            return SimpleNamespace(worker_id=request.spec.worker_id, status="failed")

    emergency_stop = EmergencyStopController(
        hooks=EmergencyStopHooks(
            revoke_capabilities=lambda: None,
            cancel_queued_missions=lambda _reason="": 0,
            kill_active_workers=lambda: None,
            disable_autonomy=lambda: None,
            preserve_evidence=lambda _reason="": None,
        )
    )

    failing_foundry = WorkerFoundry(
        workspace_manager=workspace,
        bus=bus,
        strategies={WorkerStrategyName.DETERMINISTIC.value: _FailingStrategy()},
        emergency_stop=emergency_stop,
    )

    service.worker_foundry = failing_foundry

    # 1. Scan & setup mission
    scan_contract = BoundedScanContract(
        allowed_root=str(project),
        max_files=10,
        max_total_bytes=100_000,
        max_file_bytes=10_000,
        deadline=10,
        max_findings=10,
        git_history_allowed=False,
    )
    scan_result = service.run_scan(
        scan_contract,
        _scanner,
        scanner_id="admitted-scanner",
        scanner_version="1",
        target_id="bug.txt",
        source_digest=str(project),
    )
    finding = scan_result.findings[0]

    record = service.create_repair_mission(
        finding.fingerprint,
        operator_id="op-fail-1",
        workspace_root=str(project),
    )
    mission_id = record.mission_id
    service.mission_service.start_deliberation(mission_id)
    service.mission_service.request_approval(mission_id)
    service.mission_service.approve(
        mission_id,
        operator_id="op-fail-1",
        capability_digest="cap-fail-1",
        contract_digest=record.contract_digest,
        authentication_event_id="auth-fail-1",
        session_id="session-fail-1",
    )

    # 2. Execute failing repair → returns WORKER_FAILED repair result
    rescan_contract = BoundedScanContract(
        allowed_root=str(project),
        max_files=10,
        max_total_bytes=100_000,
        max_file_bytes=10_000,
        deadline=10,
        max_findings=10,
        git_history_allowed=False,
    )
    failed_repair = await service.run_approved_repair(
        mission_id,
        scanner=_scanner,
        rescan_contract=rescan_contract,
        capability_consumer=lambda _r: True,
        create_checkpoint=lambda _r: "cp-1",
        restore_checkpoint=lambda _c, _r: True,
        smoke_test=lambda _r: True,
    )

    print("FAILED_REPAIR_REASON:", failed_repair.reason)
    assert failed_repair.status == "WORKER_FAILED"
    assert "worker status: failed" in failed_repair.reason

    # Target file in project must remain UNCHANGED (fail closed)
    assert (project / "bug.txt").read_text(encoding="utf-8") == "DEFECT_MARKER\n"
