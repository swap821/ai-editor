"""API routes for managing the Maintenance Center."""

from __future__ import annotations

import inspect
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from aios import config
from aios.api.action_guard import enforce_action_boundary
from aios.api.deps import (
    get_checkpoint_creator,
    get_checkpoint_restorer,
    get_emergency_stop,
    get_maintenance_convergence_service,
    get_maintenance_finding_repository,
    get_maintenance_scan_repository,
    get_promotion_capability_consumer,
    get_promotion_smoke_verifier,
    require_privileged_operator,
)
from aios.application.governance import EmergencyStopController, EmergencyStopError
from aios.application.maintenance.service import (
    MaintenanceConvergenceError,
    MaintenanceConvergenceService,
)
from aios.domain.identity.models import Principal
from aios.domain.maintenance.repository import MaintenanceFindingRepository
from aios.domain.maintenance.scan_contracts import BoundedScanContract
from aios.domain.maintenance.scan_repository import MaintenanceScanRepository
from aios.domain.missions.mission_repository import (
    MissionNotFoundError,
    MissionTransitionError,
)
from aios.domain.missions.mission_state import MissionState

from aios.application.workspaces.staged import tree_digest

router = APIRouter(
    tags=["maintenance-center"], dependencies=[Depends(enforce_action_boundary)]
)


class StartScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scanner_id: str = Field(
        min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"
    )
    target_id: str = Field(min_length=1, max_length=512)
    scanner_version: str = Field(default="1", min_length=1, max_length=64)
    max_files: int = Field(default=100, ge=1, le=1000)
    max_total_bytes: int = Field(default=10_000_000, ge=1, le=100_000_000)
    max_file_bytes: int = Field(default=1_000_000, ge=1, le=10_000_000)
    deadline_seconds: int = Field(default=30, ge=1, le=300)


class CreateRepairMissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    finding_fingerprint: str = Field(min_length=1, max_length=128)
    operator_id: str | None = Field(default=None, max_length=128)
    workspace_root: str | None = Field(default=None, max_length=4096)


class ApproveRepairMissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_digest: str = Field(min_length=1, max_length=128)


class RunApprovedRepairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mission_id: str = Field(min_length=1, max_length=128)


def _get_mission_or_404(service: MaintenanceConvergenceService, mission_id: str) -> Any:
    """`SqliteMissionRepository.get()` raises `MissionNotFoundError` rather
    than returning `None` -- the three routes below previously checked `if
    record is None`, a comparison that could never be true, leaving an
    unknown mission_id an uncaught 500 instead of a 404."""
    try:
        return service.mission_service.repository.get(mission_id)
    except MissionNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail=f"Mission {mission_id!r} not found"
        ) from exc


def _validate_target_bounded(target_id: str, allowed_root: Path) -> Path:
    """Ensure target path is relative and within allowed enrolled root."""
    if any(char in target_id for char in ";&|<>`\r\n\x00"):
        raise HTTPException(
            status_code=400, detail="target path contains forbidden shell characters"
        )
    if target_id.startswith(("/", "\\")) or ":" in target_id[:3]:
        raise HTTPException(status_code=400, detail="target path must be relative")
    root_text = str(allowed_root.resolve())
    candidate = os.path.normpath(os.path.join(root_text, target_id))
    if candidate != root_text and not candidate.startswith(root_text + os.sep):
        raise HTTPException(status_code=400, detail="target path escapes enrolled root")
    return Path(candidate)


@router.get("/api/v1/maintenance/findings")
def list_maintenance_findings(
    repository: MaintenanceFindingRepository = Depends(
        get_maintenance_finding_repository
    ),
) -> dict[str, Any]:
    """List durable scanner findings without inventing operational state."""
    items = [finding.model_dump(mode="json") for finding in repository.list_findings()]
    return {
        "items": items,
        "status": "available" if items else "empty",
        "source": "durable_repository",
    }


@router.get("/api/v1/maintenance/scans")
def list_maintenance_scans(
    repository: MaintenanceScanRepository = Depends(get_maintenance_scan_repository),
) -> dict[str, Any]:
    """List persisted bounded-scan metadata only."""
    items = [scan.model_dump(mode="json") for scan in repository.list_scans()]
    return {
        "items": items,
        "status": "available" if items else "empty",
        "source": "durable_repository",
    }


@router.post("/api/v1/maintenance/scans")
def start_bounded_scan(
    payload: StartScanRequest,
    service: MaintenanceConvergenceService = Depends(
        get_maintenance_convergence_service
    ),
    emergency_stop: EmergencyStopController = Depends(get_emergency_stop),
) -> dict[str, Any]:
    """Start one bounded scan through injected scanner adapters."""
    try:
        emergency_stop.assert_operational()
    except EmergencyStopError as exc:
        raise HTTPException(
            status_code=503, detail=f"Emergency stop engaged: {exc}"
        ) from exc

    scanner_fn = service.verifier_registry.scanner_adapters.get(payload.scanner_id)
    if scanner_fn is None:
        raise HTTPException(
            status_code=400,
            detail=f"Scanner {payload.scanner_id!r} is not an admitted scanner adapter",
        )

    enrolled_roots = getattr(service.workspace_manager, "enrolled_roots", ())
    primary_root = enrolled_roots[0] if enrolled_roots else config.PROJECT_ROOT
    target_path = _validate_target_bounded(payload.target_id, primary_root)
    allowed_root = target_path if target_path.is_dir() else target_path.parent

    contract = BoundedScanContract(
        allowed_root=str(allowed_root),
        max_files=payload.max_files,
        max_total_bytes=payload.max_total_bytes,
        max_file_bytes=payload.max_file_bytes,
        deadline=payload.deadline_seconds,
        max_findings=100,
        git_history_allowed=False,
    )

    digest_val = tree_digest(allowed_root)

    result = service.run_scan(
        contract,
        scanner_fn,
        scanner_id=payload.scanner_id,
        scanner_version=payload.scanner_version,
        target_id=payload.target_id,
        source_digest=digest_val,
    )

    return {
        "scan": result.scan.model_dump(mode="json"),
        "finding_count": len(result.findings),
        "status": result.scan.status,
    }


@router.post("/api/v1/maintenance/repairs/missions")
def create_repair_mission(
    payload: CreateRepairMissionRequest,
    request: Request,
    service: MaintenanceConvergenceService = Depends(
        get_maintenance_convergence_service
    ),
    emergency_stop: EmergencyStopController = Depends(get_emergency_stop),
) -> dict[str, Any]:
    """Create a draft repair mission bound to a durable finding."""
    try:
        emergency_stop.assert_operational()
    except EmergencyStopError as exc:
        raise HTTPException(
            status_code=503, detail=f"Emergency stop engaged: {exc}"
        ) from exc

    guard = getattr(request.state, "action_guard", None)
    operator_id = getattr(getattr(guard, "envelope", None), "operator_id", None)
    if not operator_id:
        raise HTTPException(status_code=401, detail="authenticated operator required")

    enrolled_roots = getattr(service.workspace_manager, "enrolled_roots", ())
    default_root = (
        str(enrolled_roots[0]) if enrolled_roots else str(config.PROJECT_ROOT)
    )
    workspace_root = payload.workspace_root or default_root
    try:
        record = service.create_repair_mission(
            payload.finding_fingerprint,
            operator_id=operator_id,
            workspace_root=workspace_root,
        )
    except MaintenanceConvergenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "mission_id": record.mission_id,
        "state": record.state.value,
        "contract_digest": record.contract_digest,
    }


@router.post("/api/v1/maintenance/repairs/{mission_id}/approve")
def approve_repair_mission(
    mission_id: str,
    payload: ApproveRepairMissionRequest,
    request: Request,
    service: MaintenanceConvergenceService = Depends(
        get_maintenance_convergence_service
    ),
    principal: Principal = Depends(require_privileged_operator),
    emergency_stop: EmergencyStopController = Depends(get_emergency_stop),
) -> dict[str, Any]:
    """Move an already-created repair mission to APPROVED through a real
    HTTP route -- organ 42's own named gap: the state machine already
    defines DIRECT_REQUEST_APPROVAL (DRAFT -> AWAITING_APPROVAL) for exactly
    this Council-free path, but no production caller ever used it, so
    ``run_approved_repair()`` could never receive a mission that had
    genuinely reached APPROVED outside a test bypassing HTTP entirely.

    Requires a privileged Human Sovereign session (matching
    ``council_approve``'s own reasoning: this is the gate where a human
    authorizes the repair to run, not a system default). The consumed exact
    capability and the caller-supplied ``contract_digest`` are threaded
    through to ``MissionService.approve()`` exactly as ``council_approve``
    already does -- no new authorization semantics invented here.
    """
    try:
        emergency_stop.assert_operational()
    except EmergencyStopError as exc:
        raise HTTPException(
            status_code=503, detail=f"Emergency stop engaged: {exc}"
        ) from exc

    record = _get_mission_or_404(service, mission_id)
    if payload.contract_digest != record.contract_digest:
        raise HTTPException(
            status_code=403,
            detail="contract digest does not match authoritative mission",
        )

    guard = getattr(request.state, "action_guard", None)
    capability_digest = getattr(guard, "capability_digest", None)
    if not capability_digest:
        raise HTTPException(
            status_code=403,
            detail="consumed exact capability is required for mission approval",
        )

    try:
        if record.state is MissionState.DRAFT:
            service.mission_service.request_approval_direct(mission_id)
        approved = service.mission_service.approve(
            mission_id,
            operator_id=principal.principal_id,
            capability_digest=capability_digest,
            contract_digest=payload.contract_digest,
            authentication_event_id=principal.authentication_event_id,
            session_id=principal.session_id,
        )
    except MissionTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "mission_id": approved.mission_id,
        "state": approved.state.value,
        "contract_digest": approved.contract_digest,
    }


@router.post("/api/v1/maintenance/repairs/run")
async def run_approved_repair(
    payload: RunApprovedRepairRequest,
    http_request: Request,
    service: MaintenanceConvergenceService = Depends(
        get_maintenance_convergence_service
    ),
    emergency_stop: EmergencyStopController = Depends(get_emergency_stop),
    capability_consumer: Any = Depends(get_promotion_capability_consumer),
    create_checkpoint: Any = Depends(get_checkpoint_creator),
    restore_checkpoint: Any = Depends(get_checkpoint_restorer),
    smoke_test: Any = Depends(get_promotion_smoke_verifier),
) -> dict[str, Any]:
    """Execute one already-approved repair mission through canonical organs."""
    try:
        emergency_stop.assert_operational()
    except EmergencyStopError as exc:
        raise HTTPException(
            status_code=503, detail=f"Emergency stop engaged: {exc}"
        ) from exc

    record = _get_mission_or_404(service, payload.mission_id)
    if record.state is not MissionState.APPROVED:
        raise HTTPException(
            status_code=400,
            detail=f"Mission must be APPROVED before execution, got {record.state.value}",
        )

    fingerprint = str(record.contract.metadata.get("finding_fingerprint", ""))
    finding = service.finding_repository.get(fingerprint)
    if finding is None:
        raise HTTPException(status_code=400, detail="Finding not found for mission")

    scanner_fn = service.verifier_registry.scanner_adapters.get(finding.scanner_id)
    if scanner_fn is None:
        raise HTTPException(
            status_code=400,
            detail=f"Scanner adapter {finding.scanner_id!r} is not registered",
        )

    workspace_root = record.contract.workspace_root or str(config.PROJECT_ROOT)
    target_path = (Path(workspace_root) / finding.target_id).resolve()
    allowed_root = target_path if target_path.is_dir() else target_path.parent

    rescan_contract = BoundedScanContract(
        allowed_root=str(allowed_root),
        max_files=100,
        max_total_bytes=10_000_000,
        max_file_bytes=1_000_000,
        deadline=30,
        max_findings=100,
        git_history_allowed=False,
    )

    try:
        result = service.run_approved_repair(
            payload.mission_id,
            scanner=scanner_fn,
            rescan_contract=rescan_contract,
            capability_consumer=capability_consumer,
            create_checkpoint=create_checkpoint,
            restore_checkpoint=restore_checkpoint,
            smoke_test=smoke_test,
            consumed_capability_proof=getattr(
                http_request.state, "consumed_capability_proof", None
            ),
        )
        if inspect.isawaitable(result):
            result = await result
    except MaintenanceConvergenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "status": result.status,
        "mission_id": result.mission_id,
        "finding_id": result.finding.finding_id,
        "reason": result.reason,
    }


@router.get("/api/v1/maintenance/repairs/{mission_id}/status")
def get_repair_status(
    mission_id: str,
    service: MaintenanceConvergenceService = Depends(
        get_maintenance_convergence_service
    ),
) -> dict[str, Any]:
    """Inspect repair mission lifecycle and rescan status."""
    record = _get_mission_or_404(service, mission_id)

    return {
        "mission_id": record.mission_id,
        "state": record.state.value,
        "contract_digest": record.contract_digest,
        "created_at": record.created_at,
    }
