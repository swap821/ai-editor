"""Council mission routes — origination, dashboard, rollback, and King decisions.

Extracted from ``aios/api/main.py`` into its own APIRouter module. Council-only
helpers (mission-id validation, dashboard summaries, background deliberation/
execution, rollback bookkeeping) are re-defined here so this module has no
runtime dependency on ``main.py``. A few genuinely cross-cutting helpers that
other (non-council) routes in ``main.py`` also depend on — session resolution,
the approval store, the conversation rate limiter, and prompt-injection
classification — are imported from ``main`` rather than duplicated.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from aios import config
from aios.logging_config import get_logger
from aios.application.action_broker import ActionBroker, PolicyBrokerError
from aios.application.missions.mission_service import MissionService
from aios.domain.actions.envelope import (
    ActionEnvelope,
    ActionType,
    Principal as EnvelopePrincipal,
)
from aios.domain.capabilities.contracts import CapabilityBinding
from aios.domain.capabilities.digest import payload_digest, resource_digest
from aios.domain.missions.mission_repository import (
    MissionNotFoundError,
    MissionTransitionError,
)
from aios.infrastructure.missions.sqlite_mission_repository import (
    SqliteMissionRepository,
)
from aios.agents.rollback_engine import RollbackError
from aios.runtime.contracts import KingReport, RunLedger
from aios.runtime.king_report import KingReportStore
from aios.runtime.run_ledger import RunLedgerStore
from aios.runtime.snapshots import SnapshotManager
from aios.council import CouncilMissionRequest, CouncilOrchestrator
from aios.council.council_memory import CouncilMemory
from aios.council.council_state import CouncilState
from aios.council.queen_verdict import has_blocking_verdict
from aios.council.royal_decree import apply_royal_decree, should_use_royal_decree
from aios.runtime.cortex_bus import CortexBus
from aios.api.deps import (
    get_action_broker,
    get_memory_authority,
    require_privileged_operator,
)
from aios.application.memory.adapters import CouncilMemoryAdapter
from aios.domain.identity.models import Principal
from aios.api.action_guard import enforce_action_boundary


# Cross-cutting helpers shared with other route modules still living in
# main.py — imported rather than duplicated so there is exactly one
# implementation of session resolution / rate limiting / injection checks.
def _check_prompt_injection(text):
    """Deferred proxy to avoid circular dependency with main.py."""
    from aios.api.main import _check_prompt_injection as _impl

    return _impl(text)


def _enforce_conversation_rate_limit(session_id):
    """Deferred proxy to avoid circular dependency with main.py."""
    from aios.api.main import _enforce_conversation_rate_limit as _impl

    return _impl(session_id)


def _session_id_from_request(request, fallback=None):
    """Deferred proxy to avoid circular dependency with main.py."""
    from aios.api.main import _session_id_from_request as _impl

    return _impl(request, fallback)


def get_cortex_bus():
    """Deferred proxy to avoid circular dependency with main.py."""
    from aios.api.main import get_cortex_bus as _impl

    return _impl()


logger = get_logger(__name__)

router = APIRouter(dependencies=[Depends(enforce_action_boundary)])


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class CouncilDecisionRequest(BaseModel):
    """King decision for a Council mission or pending worker approval request."""

    mission_id: str = Field(..., alias="missionId")
    request_id: str | None = Field(None, alias="requestId")
    reason: str = ""
    contract_digest: str | None = Field(None, alias="contractDigest")

    model_config = {"populate_by_name": True}


class CouncilRollbackRequest(BaseModel):
    """Approval-gated restore of a Council mission workspace."""

    snapshot_id: Optional[str] = Field(None, alias="snapshotId")
    approval_token: Optional[str] = Field(None, alias="approvalToken")
    session_id: Optional[str] = Field(None, alias="sessionId")

    model_config = {"populate_by_name": True}


class CouncilMissionOriginationRequest(BaseModel):
    """Body for ``POST /api/v1/council/missions`` — originate a council mission.

    Scope is EXPLICIT and operator-provided (never LLM-inferred): allowedFiles is
    required and validated to stay inside the council workspace.
    """

    goal: str = Field(..., min_length=1, max_length=2000)
    allowed_files: list[str] = Field(..., alias="allowedFiles", min_length=1)
    workspace_root: Optional[str] = Field(None, alias="workspaceRoot")
    forbidden_files: list[str] = Field(
        default_factory=lambda: ["backend/", ".env", "aios/security/"],
        alias="forbiddenFiles",
    )
    verification_commands: list[str] = Field(
        default_factory=list, alias="verificationCommands"
    )
    risk_level: str = Field("YELLOW", alias="riskLevel")
    session_id: str = Field("council-session", alias="sessionId")
    complex_task: bool = Field(False, alias="complexTask")
    royal_decree: bool = Field(False, alias="royalDecree")


# --------------------------------------------------------------------------- #
# Dependencies
# --------------------------------------------------------------------------- #
def get_council_runtime_root() -> Path:
    """Runtime artifact root for Council missions."""
    config.COUNCIL_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    return config.COUNCIL_RUNTIME_DIR


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #
def _validate_council_mission_id(mission_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", mission_id):
        raise HTTPException(status_code=422, detail="invalid mission id")
    # The charset above admits "." and "..", which the path layer would treat
    # as traversal out of the missions/ tree. Reject them explicitly.
    if mission_id in {".", ".."} or ".." in mission_id:
        raise HTTPException(status_code=422, detail="invalid mission id")
    return mission_id


def _validate_council_request_id(request_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,180}", request_id):
        raise HTTPException(status_code=422, detail="invalid approval request id")
    if request_id in {".", ".."} or ".." in request_id:
        raise HTTPException(status_code=422, detail="invalid approval request id")
    return request_id


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _latest_intelligence_for_dashboard(report: KingReport) -> dict[str, Any]:
    model_routing = report.council_summary.get("model_routing", {})
    return model_routing if isinstance(model_routing, dict) else {}


def _mission_dir(runtime_root: Path, mission_id: str) -> Path:
    # Defense in depth alongside _validate_council_mission_id: resolve the
    # candidate and confirm it stays strictly inside the missions/ tree, so no
    # mission_id can ever address a sibling or parent directory.
    base = (runtime_root / "missions").resolve()
    candidate = (base / mission_id).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid mission id")
    return candidate


def _read_council_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("council_dashboard_json_skipped", path=str(path), exc_info=exc)
        return None
    return value if isinstance(value, dict) else None


def _king_decision(runtime_root: Path, mission_id: str) -> dict[str, Any] | None:
    return _read_council_json(
        _mission_dir(runtime_root, mission_id) / "king_decision.json"
    )


def _pending_approvals_for_dashboard(
    runtime_root: Path, mission_id: str
) -> list[dict[str, Any]]:
    approvals_dir = _mission_dir(runtime_root, mission_id) / "approvals"
    if not approvals_dir.is_dir():
        return []
    pending: list[dict[str, Any]] = []
    for request_path in sorted(
        approvals_dir.glob("*.request.json"), key=lambda path: path.stat().st_mtime
    ):
        request_id = request_path.name.removesuffix(".request.json")
        response_path = approvals_dir / f"{request_id}.response.json"
        if response_path.exists():
            continue
        payload = _read_council_json(request_path)
        if payload is None:
            continue
        pending.append(
            {
                "requestId": request_id,
                "workerId": payload.get("worker_id"),
                "action": payload.get("action"),
                "reason": payload.get("reason"),
                "createdAt": payload.get("created_at"),
            }
        )
    return pending


def _council_summary_from_artifacts(
    *,
    runtime_root: Path,
    mission_id: str,
    report: KingReport,
    ledger: RunLedger | None,
    updated_at: float,
) -> dict[str, Any]:
    verification = (
        report.verification_result
        if isinstance(report.verification_result, dict)
        else {}
    )
    commands = []
    raw_commands = verification.get("commands", [])
    if isinstance(raw_commands, list):
        commands = raw_commands
    return {
        # The TYPED verification the King approves on (Slice A1/A2): strength, whether
        # it meets the promotion floor, and the caution when a positive recommendation
        # rests on below-floor evidence. None when no strength was recorded.
        "verificationStrength": verification.get("strength"),
        "verificationMeetsFloor": verification.get("meets_floor"),
        "verificationBelowFloorWarning": verification.get("below_floor_warning"),
        "missionId": mission_id,
        "mission": report.mission,
        "status": report.status,
        "recommendation": report.recommendation,
        "risk": report.risk,
        "approvalNeeded": report.approval_needed,
        "rollbackAvailable": report.rollback_available,
        "rollbackId": report.rollback_id,
        "filesTouched": list(report.files),
        "blockedAttempts": (
            len(ledger.blocked_attempts)
            if ledger is not None
            else int(report.council_summary.get("blocked_attempts", 0) or 0)
        ),
        "verificationPassed": all(
            isinstance(command, dict) and command.get("returncode") == 0
            for command in commands
        )
        if commands
        else None,
        "councilVerdicts": report.council_summary.get("council_verdicts", []),
        "gangliaSignals": report.council_summary.get("ganglia_signals", []),
        "gangliaSynthesis": report.council_summary.get("ganglia_synthesis"),
        "modelRouting": _latest_intelligence_for_dashboard(report),
        "pendingApprovals": _pending_approvals_for_dashboard(runtime_root, mission_id),
        "kingDecision": _king_decision(runtime_root, mission_id),
        "royalDecree": report.council_summary.get("royal_decree"),
        "updatedAt": updated_at,
    }


def _write_council_decision(
    *,
    runtime_root: Path,
    req: CouncilDecisionRequest,
    approved: bool,
    principal_id: str,
) -> dict[str, Any]:
    safe_id = _validate_council_mission_id(req.mission_id)
    mission_dir = _mission_dir(runtime_root, safe_id)
    if not mission_dir.is_dir():
        raise HTTPException(status_code=404, detail="council mission not found")

    request_id = (
        _validate_council_request_id(req.request_id) if req.request_id else None
    )
    # One-shot mission-level decision under origination: an atomic mkdir lock makes
    # the King decision final and single. This closes the double-execute race (two
    # concurrent approves: only one wins the lock) and makes reject terminal (a
    # later approve cannot claim the lock, so it cannot execute).
    if config.COUNCIL_ORIGINATION and request_id is None:
        try:
            (mission_dir / "decision.lock").mkdir(exist_ok=False)
        except FileExistsError as exc:
            raise HTTPException(
                status_code=409, detail="council mission already decided"
            ) from exc
    decided_at = _utc_now_iso()
    response_written = False
    if request_id:
        approvals_dir = mission_dir / "approvals"
        request_path = approvals_dir / f"{request_id}.request.json"
        response_path = approvals_dir / f"{request_id}.response.json"
        if not request_path.exists():
            raise HTTPException(status_code=404, detail="approval request not found")
        if response_path.exists():
            raise HTTPException(
                status_code=409, detail="approval request already decided"
            )
        response_path.write_text(
            json.dumps(
                {
                    "request_id": request_id,
                    "mission_id": safe_id,
                    "approved": approved,
                    "reason": req.reason,
                    "decided_at": decided_at,
                    "decided_by": principal_id,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        response_written = True

    decision = {
        "mission_id": safe_id,
        "request_id": request_id,
        "decision": "approve" if approved else "reject",
        "approved": approved,
        "reason": req.reason,
        "decided_at": decided_at,
        "decided_by": principal_id,
    }
    (mission_dir / "king_decision.json").write_text(
        json.dumps(decision, indent=2),
        encoding="utf-8",
    )
    return {
        "missionId": safe_id,
        "decision": decision,
        "approvalResponseWritten": response_written,
    }


def _resolve_council_workspace(raw: Optional[str]) -> Path:
    """Return a writable workspace confined to config.COUNCIL_WORKSPACE_ROOT."""
    base = config.COUNCIL_WORKSPACE_ROOT.resolve()
    if raw is None:
        base.mkdir(parents=True, exist_ok=True)
        return base
    if os.path.isabs(raw) or ".." in PurePosixPath(raw).parts:
        raise HTTPException(
            status_code=422, detail="workspaceRoot escapes the council workspace"
        )
    candidate = (base / raw).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="workspaceRoot escapes the council workspace"
        )
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def _validate_mission_scope(
    allowed_files: list[str], workspace_root: Path
) -> list[str]:
    """Confine allowed_files to workspace_root — explicit, fail-closed, no traversal."""
    base = workspace_root.resolve()
    safe: list[str] = []
    for raw in allowed_files:
        if not isinstance(raw, str) or not raw.strip():
            raise HTTPException(
                status_code=422, detail="allowedFiles entries must be non-empty"
            )
        if any(ch in raw for ch in "*?[]"):
            raise HTTPException(
                status_code=422, detail=f"glob not allowed in scope: {raw}"
            )
        if os.path.isabs(raw) or ".." in PurePosixPath(raw).parts:
            raise HTTPException(status_code=422, detail=f"unsafe allowed file: {raw}")
        resolved = (base / raw).resolve()
        try:
            resolved.relative_to(base)
        except ValueError:
            raise HTTPException(
                status_code=422, detail=f"allowed file escapes workspace: {raw}"
            )
        safe.append(PurePosixPath(raw).as_posix())
    return safe


def _write_failed_council_report(
    runtime_root: Path, mission_id: str, reason: str
) -> None:
    """Persist a minimal failed report so a background failure is visible to the poll."""
    try:
        KingReportStore(runtime_root).write(
            KingReport(
                mission_id=mission_id,
                mission=mission_id,
                status="failed",
                recommendation="revise",
                risk="YELLOW",
                approval_needed=True,
                rollback_available=False,
                human_summary=f"Council mission failed: {reason}",
            )
        )
    except Exception as exc:  # noqa: BLE001 - best-effort failure surface
        logger.warning(
            "council_failed_report_write_failed", mission_id=mission_id, exc_info=exc
        )


def _run_council_deliberation(
    runtime_root: Path, request: CouncilMissionRequest, bus: CortexBus | None = None
) -> None:
    """Background: deliberate only (no worker). Failures surface as a failed report."""
    try:
        council_state = CouncilState(db_path=runtime_root / "council_state.db")
        council_memory = CouncilMemory(state=council_state)
        memory_authority = get_memory_authority().with_adapter(
            "council", CouncilMemoryAdapter(council_memory)
        )
        CouncilOrchestrator(
            runtime_root=runtime_root,
            council_state=council_state,
            council_memory=council_memory,
            memory_authority=memory_authority,
            bus=bus,
        ).deliberate(request)
    except Exception as exc:  # noqa: BLE001 - background task must not crash the server
        logger.warning(
            "council_deliberation_failed", mission_id=request.mission_id, exc_info=exc
        )
        _write_failed_council_report(runtime_root, request.mission_id, str(exc))


def _run_council_execution(
    runtime_root: Path, mission_id: str, bus: CortexBus | None = None
) -> None:
    """Background: run the approved worker — reads the deliberated ledger for the
    contract + verdicts, executes (worker acts), and writes the final report."""
    try:
        ledger = RunLedgerStore(runtime_root).read(mission_id)
        # Defense in depth: never execute a ledger that carries a blocking verdict
        # (guards against an on-disk ledger tampered between deliberate and approve).
        if has_blocking_verdict(list(ledger.council_verdicts)):
            raise RuntimeError("ledger carries a blocking verdict; refusing to execute")
        council_state = CouncilState(db_path=runtime_root / "council_state.db")
        council_memory = CouncilMemory(state=council_state)
        memory_authority = get_memory_authority().with_adapter(
            "council", CouncilMemoryAdapter(council_memory)
        )
        orchestrator = CouncilOrchestrator(
            runtime_root=runtime_root,
            council_state=council_state,
            council_memory=council_memory,
            memory_authority=memory_authority,
            bus=bus,
        )
        asyncio.run(
            orchestrator.execute(ledger.contract, list(ledger.council_verdicts))
        )
    except Exception as exc:  # noqa: BLE001 - background task must not crash the server
        logger.warning("council_execution_failed", mission_id=mission_id, exc_info=exc)
        _write_failed_council_report(runtime_root, mission_id, str(exc))


def _council_rollback_target(ledger: RunLedger, report: KingReport) -> str:
    if report.status == "rolled_back":
        raise HTTPException(
            status_code=409, detail="council mission already rolled back"
        )
    snapshot_id = ledger.rollback_id or report.rollback_id or ledger.snapshot_id
    if not snapshot_id:
        raise HTTPException(
            status_code=409,
            detail="council mission has no rollback snapshot",
        )
    return snapshot_id


def _write_council_rollback_artifacts(
    *,
    runtime_root: Path,
    ledger: RunLedger,
    report: KingReport,
    snapshot_id: str,
    result: Any,
) -> KingReport:
    restored_at = _utc_now_iso()
    rollback_evidence = {
        "snapshot_id": snapshot_id,
        "restored": bool(result.restored),
        "head_sha": result.head_sha,
        "reason": result.reason,
        "restored_at": restored_at,
    }
    ledger_evidence = dict(ledger.evidence)
    ledger_evidence["rollback"] = rollback_evidence
    updated_ledger = ledger.model_copy(
        update={
            "status": "rolled_back",
            "completed_at": restored_at,
            "evidence": ledger_evidence,
        }
    )
    RunLedgerStore(runtime_root).write(updated_ledger)

    report_evidence = dict(report.evidence)
    report_evidence["rollback"] = rollback_evidence
    updated_report = report.model_copy(
        update={
            "status": "rolled_back",
            "recommendation": "observe",
            "rollback_available": False,
            "rollback_id": snapshot_id,
            "evidence": report_evidence,
            "human_summary": (
                "Council rollback restored the workspace to snapshot "
                f"{snapshot_id[:12]}."
            ),
        }
    )
    KingReportStore(runtime_root).write(updated_report)
    return updated_report


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@router.post("/api/v1/council/missions")
def council_originate(
    req: CouncilMissionOriginationRequest,
    background: BackgroundTasks,
    principal: Principal = Depends(require_privileged_operator),
    runtime_root: Path = Depends(get_council_runtime_root),
    bus: Optional[CortexBus] = Depends(get_cortex_bus),
) -> dict[str, Any]:
    """Originate a Council mission from a goal: deliberate, then await King approval.

    The worker does NOT act here — origination runs only the Queen deliberation in
    the background and produces an ``awaiting_approval`` (or ``blocked``) report.
    Approving the mission later triggers execution. Scope is explicit + confined.
    """
    if not config.COUNCIL_ORIGINATION:
        raise HTTPException(status_code=404, detail="council origination is disabled")
    _enforce_conversation_rate_limit(principal.session_id)
    if injection_reason := _check_prompt_injection(req.goal):
        raise HTTPException(
            status_code=400, detail=f"[SECURITY BLOCK] {injection_reason}"
        )
    workspace_root = _resolve_council_workspace(req.workspace_root)
    safe_allowed = _validate_mission_scope(req.allowed_files, workspace_root)
    mission_id = f"mission-{uuid.uuid4().hex[:12]}"
    allowed_tools = ["read_file", "write_file", "run_command"]
    mission_metadata: dict[str, Any] = {}
    if config.WORKER_REASONING:
        allowed_tools.append("request_change")
        mission_metadata["model_policy"] = {"mode": "local", "allow_cloud": False}
    mission_request = CouncilMissionRequest(
        mission_id=mission_id,
        goal=req.goal,
        workspace_root=str(workspace_root),
        allowed_files=safe_allowed,
        forbidden_files=list(req.forbidden_files),
        # The worker's reasoning is governed by WORKER_REASONING (the LLM worker
        # uses request_change, not request_plan), so the origination default omits
        # request_plan: the deterministic worker needs no model when reasoning is off.
        allowed_tools=allowed_tools,
        verification_commands=list(req.verification_commands),
        risk_level=req.risk_level,  # type: ignore[arg-type]
        metadata=mission_metadata,
    )
    if req.royal_decree or req.complex_task or should_use_royal_decree(mission_request):
        mission_request = apply_royal_decree(
            mission_request,
            force=req.royal_decree or req.complex_task,
        )
    background.add_task(_run_council_deliberation, runtime_root, mission_request, bus)
    return {"missionId": mission_id, "status": "deliberating"}


@router.get("/api/v1/council/missions")
def council_missions(
    limit: int = 20,
    runtime_root: Path = Depends(get_council_runtime_root),
) -> dict[str, Any]:
    """List stored Council mission reports for the operator dashboard."""
    mission_root = runtime_root / "missions"
    if not mission_root.is_dir():
        return {"missions": [], "count": 0}

    reports = KingReportStore(runtime_root)
    ledgers = RunLedgerStore(runtime_root)
    items: list[dict[str, Any]] = []
    for mission_dir in mission_root.iterdir():
        if not mission_dir.is_dir():
            continue
        mission_id = mission_dir.name
        report_path = reports.path_for(mission_id)
        if not report_path.exists():
            continue
        try:
            report = reports.read(mission_id)
            ledger = (
                ledgers.read(mission_id)
                if ledgers.path_for(mission_id).exists()
                else None
            )
        except Exception as exc:  # noqa: BLE001 - one corrupt artifact must not kill the dashboard
            logger.warning(
                "council_dashboard_artifact_skipped",
                mission_id=mission_id,
                exc_info=exc,
            )
            continue
        items.append(
            _council_summary_from_artifacts(
                runtime_root=runtime_root,
                mission_id=mission_id,
                report=report,
                ledger=ledger,
                updated_at=report_path.stat().st_mtime,
            )
        )

    items.sort(key=lambda item: item["updatedAt"], reverse=True)
    bounded_limit = max(1, min(int(limit), 100))
    return {"missions": items[:bounded_limit], "count": len(items)}


@router.get("/api/v1/council/missions/{mission_id}")
def council_mission_detail(
    mission_id: str,
    runtime_root: Path = Depends(get_council_runtime_root),
) -> dict[str, Any]:
    """Return the stored RunLedger and KingReport for one Council mission."""
    safe_id = _validate_council_mission_id(mission_id)
    reports = KingReportStore(runtime_root)
    ledgers = RunLedgerStore(runtime_root)
    report_path = reports.path_for(safe_id)
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="council mission not found")
    try:
        report = reports.read(safe_id)
        ledger = ledgers.read(safe_id) if ledgers.path_for(safe_id).exists() else None
    except Exception as exc:  # noqa: BLE001 - a corrupt artifact is a 422, not a 500
        logger.warning(
            "council_dashboard_artifact_corrupt", mission_id=safe_id, exc_info=exc
        )
        raise HTTPException(
            status_code=422, detail="council artifact is corrupt"
        ) from exc
    authority: dict[str, Any] | None = None
    try:
        authoritative = SqliteMissionRepository(runtime_root / "missions.db").get(
            safe_id
        )
        authority = {
            "store": "sqlite_mission_repository",
            "state": authoritative.state.value,
            "operatorId": authoritative.operator_id,
            "contractDigest": authoritative.contract_digest,
            "runtimeContractDigest": authoritative.runtime_contract_digest,
            "capabilityDigest": authoritative.capability_digest,
        }
    except MissionNotFoundError:
        pass
    return {
        "missionId": safe_id,
        "summary": _council_summary_from_artifacts(
            runtime_root=runtime_root,
            mission_id=safe_id,
            report=report,
            ledger=ledger,
            updated_at=report_path.stat().st_mtime,
        ),
        "report": report.model_dump(),
        "ledger": ledger.model_dump() if ledger is not None else None,
        "pendingApprovals": _pending_approvals_for_dashboard(runtime_root, safe_id),
        "kingDecision": _king_decision(runtime_root, safe_id),
        "missionAuthority": authority,
    }


@router.get("/api/v1/council/reports/{mission_id}")
def council_report(
    mission_id: str,
    runtime_root: Path = Depends(get_council_runtime_root),
) -> dict[str, Any]:
    """Return only the human-facing KingReport for one Council mission."""
    safe_id = _validate_council_mission_id(mission_id)
    store = KingReportStore(runtime_root)
    if not store.path_for(safe_id).exists():
        raise HTTPException(status_code=404, detail="council report not found")
    try:
        report = store.read(safe_id)
    except Exception as exc:  # noqa: BLE001 - a corrupt artifact is a 422, not a 500
        logger.warning(
            "council_report_artifact_corrupt", mission_id=safe_id, exc_info=exc
        )
        raise HTTPException(
            status_code=422, detail="council report is corrupt"
        ) from exc
    return {"missionId": safe_id, "report": report.model_dump()}


@router.post("/api/v1/council/missions/{mission_id}/rollback")
def council_mission_rollback(
    mission_id: str,
    req: CouncilRollbackRequest,
    request: Request,
    _principal: Principal = Depends(require_privileged_operator),
    runtime_root: Path = Depends(get_council_runtime_root),
    broker: ActionBroker = Depends(get_action_broker),
) -> dict[str, Any]:
    """Restore one Council mission workspace to its pre-worker snapshot."""
    safe_id = _validate_council_mission_id(mission_id)
    reports = KingReportStore(runtime_root)
    ledgers = RunLedgerStore(runtime_root)
    if not reports.path_for(safe_id).exists() or not ledgers.path_for(safe_id).exists():
        raise HTTPException(status_code=404, detail="council mission not found")
    try:
        report = reports.read(safe_id)
        ledger = ledgers.read(safe_id)
    except Exception as exc:  # noqa: BLE001 - corrupt artifacts are caller-visible
        logger.warning(
            "council_rollback_artifact_corrupt", mission_id=safe_id, exc_info=exc
        )
        raise HTTPException(
            status_code=422, detail="council artifact is corrupt"
        ) from exc

    snapshot_id = _council_rollback_target(ledger, report)
    if req.snapshot_id and req.snapshot_id != snapshot_id:
        raise HTTPException(
            status_code=403,
            detail="requested snapshot does not match council mission rollback target",
        )
    # Mission rollback is destructive: a JSON session id cannot select the
    # principal. Only the validated httpOnly cookie may bind its approval.
    session_id = _session_id_from_request(request, None)
    if not session_id:
        raise HTTPException(
            status_code=422, detail="a valid session cookie is required"
        )

    payload = {"mission_id": safe_id, "snapshot_id": snapshot_id}
    resource = {
        "workspace_root": str(ledger.contract.workspace_root),
        "snapshot_id": snapshot_id,
    }
    envelope = ActionEnvelope(
        route=request.url.path,
        action_type=ActionType.COUNCIL_MISSION_ROLLBACK,
        http_method=request.method,
        payload=payload,
        principal=EnvelopePrincipal(
            session_id=_principal.session_id,
            actor_source="session",
            client_ip=_principal.client_address or "127.0.0.1",
        ),
        request_id=_principal.request_id or request.headers.get("x-request-id"),
        operator_id=_principal.principal_id,
        device_id=_principal.device_id,
        authentication_event_id=_principal.authentication_event_id,
        mission_id=safe_id,
        contract_digest=payload_digest(ledger.contract.model_dump(mode="json")),
        resource=resource,
        policy_version=getattr(ledger.contract, "policy_version", "v1"),
        requested_capability="council.rollback",
        correlation_id=(
            request.headers.get("x-correlation-id")
            or _principal.request_id
            or request.headers.get("x-request-id")
            or str(uuid.uuid4())
        ),
    )
    binding = CapabilityBinding(
        operator_id=_principal.principal_id,
        device_id=_principal.device_id,
        authentication_event_id=_principal.authentication_event_id,
        session_id=_principal.session_id,
        action_type="rollback",
        route=request.url.path,
        http_method=request.method,
        payload_digest=payload_digest(payload),
        resource_digest=resource_digest(resource),
        mission_id=safe_id,
        contract_digest=payload_digest(ledger.contract.model_dump(mode="json")),
        policy_version=getattr(ledger.contract, "policy_version", "v1"),
        scope=f"mission:{safe_id}/rollback",
        verification_requirement="rollback_snapshot_restore",
    )
    try:
        decision = broker.submit(
            envelope,
            capability_token=req.approval_token,
            capability_binding=binding,
        )
    except PolicyBrokerError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if decision.blocked:
        raise HTTPException(status_code=403, detail=decision.reason)
    if decision.requires_approval:
        return {
            "requiresApproval": True,
            "approvalToken": decision.approval_token,
            "actionType": "rollback",
            "missionId": safe_id,
            "snapshotId": snapshot_id,
            "executed": False,
        }
    try:
        result = SnapshotManager(runtime_root).rollback_snapshot(
            ledger.contract.workspace_root,
            snapshot_id,
        )
    except RollbackError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not result.restored:
        raise HTTPException(status_code=500, detail=result.reason)
    updated_report = _write_council_rollback_artifacts(
        runtime_root=runtime_root,
        ledger=ledger,
        report=report,
        snapshot_id=snapshot_id,
        result=result,
    )
    return {
        "requiresApproval": False,
        "missionId": safe_id,
        "snapshotId": snapshot_id,
        "executed": True,
        "result": asdict(result),
        "report": updated_report.model_dump(),
    }


@router.post("/api/v1/council/approve")
def council_approve(
    req: CouncilDecisionRequest,
    background: BackgroundTasks,
    request: Request,
    principal: Principal = Depends(require_privileged_operator),
    runtime_root: Path = Depends(get_council_runtime_root),
    bus: Optional[CortexBus] = Depends(get_cortex_bus),
) -> dict[str, Any]:
    """Record King approval; if the mission is awaiting execution, run the worker.

    A mission-level approval (no requestId) of a mission whose report is
    ``awaiting_approval`` schedules execute() in the background — this is the gate
    where a human authorizes the worker to act.
    """
    # Mission-level Council origination is authorized by the SQLite mission
    # record.  The JSON King decision is only a projection written after the
    # authoritative transition succeeds.
    if config.COUNCIL_ORIGINATION and req.request_id is None:
        safe_id = _validate_council_mission_id(req.mission_id)
        try:
            mission_service = MissionService(
                SqliteMissionRepository(runtime_root / "missions.db"),
                export_dir=runtime_root / "mission_exports",
            )
            authoritative = mission_service.repository.get(safe_id)
        except MissionNotFoundError as exc:
            # Legacy report-only artifacts cannot authorize execution.  Keep
            # the historical projection endpoint available, but it must never
            # schedule a worker without an authoritative mission row.
            result = _write_council_decision(
                runtime_root=runtime_root,
                req=req,
                approved=True,
                principal_id=principal.principal_id,
            )
            return result

        guard = getattr(request.state, "action_guard", None)
        capability_digest = getattr(guard, "capability_digest", None)
        if not capability_digest:
            raise HTTPException(
                status_code=403,
                detail="consumed exact capability is required for mission approval",
            )
        if not req.contract_digest:
            raise HTTPException(
                status_code=403,
                detail="authoritative contract digest is required for mission approval",
            )
        if req.contract_digest != authoritative.contract_digest:
            raise HTTPException(
                status_code=403,
                detail="contract digest does not match authoritative mission",
            )
        try:
            approved = mission_service.approve(
                safe_id,
                operator_id=principal.principal_id,
                capability_digest=capability_digest,
                contract_digest=req.contract_digest,
                authentication_event_id=principal.authentication_event_id,
                session_id=principal.session_id,
            )
        except MissionTransitionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        result = _write_council_decision(
            runtime_root=runtime_root,
            req=req,
            approved=True,
            principal_id=principal.principal_id,
        )
        result["missionAuthority"] = {
            "store": "sqlite_mission_repository",
            "state": approved.state.value,
            "operatorId": approved.operator_id,
            "contractDigest": approved.contract_digest,
            "runtimeContractDigest": approved.runtime_contract_digest,
            "capabilityDigest": approved.capability_digest,
        }
    else:
        result = _write_council_decision(
            runtime_root=runtime_root,
            req=req,
            approved=True,
            principal_id=principal.principal_id,
        )
    if config.COUNCIL_ORIGINATION and req.request_id is None:
        safe_id = result["missionId"]
        store = KingReportStore(runtime_root)
        try:
            awaiting = store.path_for(safe_id).exists() and (
                store.read(safe_id).status == "awaiting_approval"
            )
        except Exception:  # noqa: BLE001 - a read failure simply means "don't execute"
            awaiting = False
        if awaiting:
            background.add_task(_run_council_execution, runtime_root, safe_id, bus)
            result["execution"] = "scheduled"
    return result


@router.post("/api/v1/council/reject")
def council_reject(
    req: CouncilDecisionRequest,
    request: Request,
    principal: Principal = Depends(require_privileged_operator),
    runtime_root: Path = Depends(get_council_runtime_root),
) -> dict[str, Any]:
    """Record King rejection for a Council mission or pending worker request."""
    if config.COUNCIL_ORIGINATION and req.request_id is None:
        safe_id = _validate_council_mission_id(req.mission_id)
        try:
            mission_service = MissionService(
                SqliteMissionRepository(runtime_root / "missions.db"),
                export_dir=runtime_root / "mission_exports",
            )
            authoritative = mission_service.repository.get(safe_id)
        except MissionNotFoundError:
            return _write_council_decision(
                runtime_root=runtime_root,
                req=req,
                approved=False,
                principal_id=principal.principal_id,
            )
        guard = getattr(request.state, "action_guard", None)
        capability_digest = getattr(guard, "capability_digest", None)
        if not capability_digest:
            raise HTTPException(
                status_code=403,
                detail="consumed exact capability is required for mission rejection",
            )
        if not req.contract_digest:
            raise HTTPException(
                status_code=403,
                detail="authoritative contract digest is required for mission rejection",
            )
        if req.contract_digest != authoritative.contract_digest:
            raise HTTPException(
                status_code=403,
                detail="contract digest does not match authoritative mission",
            )
        try:
            rejected = mission_service.reject(
                safe_id,
                operator_id=principal.principal_id,
                reason=req.reason or "Operator rejected mission",
                capability_digest=capability_digest,
                contract_digest=req.contract_digest,
                authentication_event_id=principal.authentication_event_id,
                session_id=principal.session_id,
            )
        except MissionTransitionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        result = _write_council_decision(
            runtime_root=runtime_root,
            req=req,
            approved=False,
            principal_id=principal.principal_id,
        )
        result["missionAuthority"] = {
            "store": "sqlite_mission_repository",
            "state": rejected.state.value,
            "operatorId": rejected.operator_id,
            "contractDigest": rejected.contract_digest,
            "runtimeContractDigest": rejected.runtime_contract_digest,
            "capabilityDigest": rejected.capability_digest,
        }
        return result
    return _write_council_decision(
        runtime_root=runtime_root,
        req=req,
        approved=False,
        principal_id=principal.principal_id,
    )
