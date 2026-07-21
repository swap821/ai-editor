"""Phase 2 — Maintenance mission completion ordering.

Red-first tests documenting the required lifecycle:

    repair worker completes
    → structured verification (VerificationAuthority)
    → promotion (WorkspaceManager.apply + smoke_test)
    → exact post-promotion rescan (run_scan)
    → authoritative rescan proof (reconcile_rescan)
    → COMPLETED (MissionService.complete)

The mission MUST NOT reach MissionState.COMPLETED before the rescan proof is
established.  A RESCAN_INCOMPLETE result must leave the mission in a non-COMPLETED
state so the operator can diagnose and re-attempt.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from types import SimpleNamespace


from aios.application.evidence.verification import VerificationAuthority
from aios.application.evidence.verifier_registry import VerifierRegistry
from aios.application.executor.service import ExecutorService
from aios.application.maintenance.service import (
    MaintenanceConvergenceService,
)
from aios.application.missions.mission_service import MissionService
from aios.application.promotion.authority import PromotionAuthority
from aios.application.workspaces import StagedWorkspaceManager
from aios.domain.maintenance.contracts import MaintenanceFinding
from aios.domain.maintenance.lifecycle import MaintenanceLifecycleEngine
from aios.domain.maintenance.repository import MaintenanceFindingRepository
from aios.domain.maintenance.scan_contracts import BoundedScanContract
from aios.domain.maintenance.scan_repository import MaintenanceScanRepository
from aios.domain.missions.mission_state import MissionState
from aios.infrastructure.missions.sqlite_mission_repository import (
    SqliteMissionRepository,
)
from tests.helpers import consume_real_capability_proof, executor_repair_result


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
        finding_id="finding-ordering-test",
        fingerprint="ordering-defect",
        scanner_id="ordering-scanner",
        scanner_version="1",
        kind="ordering_defect",
        severity="medium",
        confidence=1.0,
        evidence_quality="deterministic",
        target_id="bug.txt",
        target_digest=target_digest,
        source_digest=source_digest,
        first_seen="2026-07-19T00:00:00Z",
        last_seen="2026-07-19T00:00:00Z",
        occurrence_count=1,
        status="OPEN",
        deterministic_evidence="ordering defect marker present",
    )


class _WorkerFoundry:
    def __init__(self, *, repair: bool = True) -> None:
        self.repair = repair
        self.workspace_manager: StagedWorkspaceManager | None = None

    async def run(self, contract, **_kwargs):  # noqa: ANN001
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
        return SimpleNamespace(worker_id="worker-ordering-1", status="completed")


class _Executor:
    def __init__(self, *, exit_code: int = 0) -> None:
        self.exit_code = exit_code

    def execute(self, job):  # noqa: ANN001
        return executor_repair_result(
            job,
            status="completed" if self.exit_code == 0 else "failed",
            exit_code=self.exit_code,
        )


def _scanner(context):  # noqa: ANN001
    payload = context.read_text("bug.txt")
    if "ORDERING_DEFECT" not in payload:
        return ()
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return (_finding(target_digest=digest, source_digest=digest),)


def _build_service(
    tmp_path: Path,
) -> tuple[MaintenanceConvergenceService, Path, _WorkerFoundry]:
    project = tmp_path / "project"
    project.mkdir()
    (project / "bug.txt").write_text("ORDERING_DEFECT\n", encoding="utf-8")
    workspace = StagedWorkspaceManager(tmp_path / "staged", enrolled_roots=(project,))
    missions = SqliteMissionRepository(tmp_path / "missions.db")
    mission_service = MissionService(missions, workspace_manager=workspace)
    finding_repository = MaintenanceFindingRepository(tmp_path / "operational.db")
    scan_repository = MaintenanceScanRepository(tmp_path / "operational.db")
    worker = _WorkerFoundry()
    executor = _Executor()
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
            scanner_adapters={"ordering-scanner": _scanner}
        ),
        verification_authority=VerificationAuthority(),
        promotion_authority=PromotionAuthority(workspace),
        workspace_manager=workspace,
        lifecycle_engine=MaintenanceLifecycleEngine(),
    )
    worker.workspace_manager = workspace
    return service, project, worker


def _approve_mission(
    service: MaintenanceConvergenceService, mission_id: str, mission
) -> None:
    service.mission_service.start_deliberation(mission_id)
    service.mission_service.request_approval(mission_id)
    service.mission_service.approve(
        mission_id,
        operator_id="operator-ordering",
        capability_digest="operator-capability-ordering",
        contract_digest=mission.contract_digest,
        authentication_event_id="auth-ordering",
        session_id="session-ordering",
    )


def test_mission_is_not_completed_before_rescan_proof(tmp_path: Path) -> None:
    """ORDERING: mission must not reach COMPLETED before rescan proves resolution."""
    service, project, _worker = _build_service(tmp_path)

    initial = service.run_scan(
        _contract(root=project),
        _scanner,
        scanner_id="ordering-scanner",
        scanner_version="1",
        target_id="bug.txt",
        source_digest="source-before",
    )
    assert initial.scan.status == "completed"

    mission = service.create_repair_mission(
        initial.findings[0].fingerprint,
        operator_id="operator-ordering",
        workspace_root=str(project),
    )
    _approve_mission(service, mission.mission_id, mission)

    # Intercept run_scan ONLY during repair to capture mission state BEFORE rescan completes
    rescan_states: list[MissionState] = []
    original_run_scan = service.run_scan

    def _intercepting_run_scan(*args, **kwargs):
        if kwargs.get("rescan_of"):
            state = service.mission_service.repository.get(mission.mission_id).state
            rescan_states.append(state)
        return original_run_scan(*args, **kwargs)

    service.run_scan = _intercepting_run_scan  # type: ignore[method-assign]

    result = asyncio.run(
        service.run_approved_repair(
            mission.mission_id,
            scanner=_scanner,
            rescan_contract=_contract(root=project),
            capability_consumer=lambda _request: True,
            consumed_capability_proof=consume_real_capability_proof(
                tmp_path / "proof-caps.db",
                mission_id=mission.mission_id,
                contract_digest=mission.contract_digest,
            ),
            create_checkpoint=lambda _request: "checkpoint-ordering",
            restore_checkpoint=lambda _checkpoint, _request: True,
            smoke_test=lambda _request: (project / "bug.txt").read_text() == "fixed\n",
        )
    )

    assert len(rescan_states) == 1, "rescan run_scan must be called exactly once"
    assert rescan_states[0] is not MissionState.COMPLETED, (
        f"Mission must not be COMPLETED before rescan proof. "
        f"Got {rescan_states[0].value} (should be VERIFYING). "
        f"This means mark_completed was called inside promote() before the rescan."
    )
    assert result.status == "VERIFIED_RESOLVED", result.reason


def test_rescan_incomplete_does_not_complete_mission(tmp_path: Path) -> None:
    """ORDERING: a RESCAN_INCOMPLETE result must NOT leave the mission COMPLETED."""
    service, project, _worker = _build_service(tmp_path)

    initial = service.run_scan(
        _contract(root=project),
        _scanner,
        scanner_id="ordering-scanner",
        scanner_version="1",
        target_id="bug.txt",
        source_digest="source-before",
    )
    assert initial.scan.status == "completed"

    mission = service.create_repair_mission(
        initial.findings[0].fingerprint,
        operator_id="operator-ordering",
        workspace_root=str(project),
    )
    _approve_mission(service, mission.mission_id, mission)

    original_run_scan = service.run_scan

    def _incomplete_rescan(contract, scan_fn, **kwargs):
        if kwargs.get("rescan_of"):
            incomplete_contract = _contract(root=project, max_files=0)
            return original_run_scan(
                incomplete_contract, lambda ctx: tuple(ctx.iter_files()), **kwargs
            )
        return original_run_scan(contract, scan_fn, **kwargs)

    service.run_scan = _incomplete_rescan  # type: ignore[method-assign]

    result = asyncio.run(
        service.run_approved_repair(
            mission.mission_id,
            scanner=_scanner,
            rescan_contract=_contract(root=project),
            capability_consumer=lambda _request: True,
            consumed_capability_proof=consume_real_capability_proof(
                tmp_path / "proof-caps.db",
                mission_id=mission.mission_id,
                contract_digest=mission.contract_digest,
            ),
            create_checkpoint=lambda _request: "checkpoint-ordering-incomplete",
            restore_checkpoint=lambda _checkpoint, _request: True,
            smoke_test=lambda _request: (project / "bug.txt").read_text() == "fixed\n",
        )
    )

    assert result.status == "RESCAN_INCOMPLETE", (
        f"Expected RESCAN_INCOMPLETE, got {result.status}"
    )

    mission_state = service.mission_service.repository.get(mission.mission_id).state
    assert mission_state is not MissionState.COMPLETED, (
        f"Mission must NOT be COMPLETED when rescan is INCOMPLETE. "
        f"Got {mission_state.value}."
    )
