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
import re
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from aios import config
from aios.logging_config import get_logger
from aios.core.approvals import ApprovalError, ApprovalStore
from aios.agents.rollback_engine import RollbackError
from aios.runtime.contracts import KingReport, RunLedger
from aios.runtime.king_report import KingReportStore
from aios.runtime.run_ledger import RunLedgerStore
from aios.runtime.snapshots import SnapshotManager
from aios.council import CouncilMissionRequest, CouncilOrchestrator
from aios.council.council_state import CouncilState
from aios.council.queen_verdict import has_blocking_verdict

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


def get_approval_store():
    """Deferred proxy to avoid circular dependency with main.py."""
    from aios.api.main import get_approval_store as _impl
    return _impl()

logger = get_logger(__name__)

router = APIRouter()


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class CouncilDecisionRequest(BaseModel):
    """King decision for a Council mission or pending worker approval request."""

    mission_id: str = Field(..., alias="missionId")
    request_id: str | None = Field(None, alias="requestId")
    reason: str = ""

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
    if base not in candidate.parents:
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
    return _read_council_json(_mission_dir(runtime_root, mission_id) / "king_decision.json")


def _pending_approvals_for_dashboard(runtime_root: Path, mission_id: str) -> list[dict[str, Any]]:
    approvals_dir = _mission_dir(runtime_root, mission_id) / "approvals"
    if not approvals_dir.is_dir():
        return []
    pending: list[dict[str, Any]] = []
    for request_path in sorted(approvals_dir.glob("*.request.json"), key=lambda path: path.stat().st_mtime):
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
    verification = report.verification_result if isinstance(report.verification_result, dict) else {}
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
        ) if commands else None,
        "councilVerdicts": report.council_summary.get("council_verdicts", []),
        "modelRouting": _latest_intelligence_for_dashboard(report),
        "pendingApprovals": _pending_approvals_for_dashboard(runtime_root, mission_id),
        "kingDecision": _king_decision(runtime_root, mission_id),
        "updatedAt": updated_at,
    }


def _write_council_decision(
    *,
    runtime_root: Path,
    req: CouncilDecisionRequest,
    approved: bool,
) -> dict[str, Any]:
    safe_id = _validate_council_mission_id(req.mission_id)
    mission_dir = _mission_dir(runtime_root, safe_id)
    if not mission_dir.is_dir():
        raise HTTPException(status_code=404, detail="council mission not found")

    request_id = _validate_council_request_id(req.request_id) if req.request_id else None
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
            raise HTTPException(status_code=409, detail="approval request already decided")
        response_path.write_text(
            json.dumps(
                {
                    "request_id": request_id,
                    "mission_id": safe_id,
                    "approved": approved,
                    "reason": req.reason,
                    "decided_at": decided_at,
                    "decided_by": "king_dashboard",
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
        "decided_by": "king_dashboard",
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
    candidate = Path(raw).resolve()
    if candidate != base and base not in candidate.parents:
        raise HTTPException(status_code=422, detail="workspaceRoot escapes the council workspace")
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def _validate_mission_scope(allowed_files: list[str], workspace_root: Path) -> list[str]:
    """Confine allowed_files to workspace_root — explicit, fail-closed, no traversal."""
    base = workspace_root.resolve()
    safe: list[str] = []
    for raw in allowed_files:
        if not isinstance(raw, str) or not raw.strip():
            raise HTTPException(status_code=422, detail="allowedFiles entries must be non-empty")
        if any(ch in raw for ch in "*?[]"):
            # Origination scope must be concrete operator files; a glob like "*"
            # would let the approved worker touch every file under the workspace.
            raise HTTPException(status_code=422, detail=f"glob not allowed in scope: {raw}")
        candidate = Path(raw)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise HTTPException(status_code=422, detail=f"unsafe allowed file: {raw}")
        resolved = (base / candidate).resolve()
        if resolved != base and base not in resolved.parents:
            raise HTTPException(status_code=422, detail=f"allowed file escapes workspace: {raw}")
        safe.append(candidate.as_posix())
    return safe


def _write_failed_council_report(runtime_root: Path, mission_id: str, reason: str) -> None:
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
        logger.warning("council_failed_report_write_failed", mission_id=mission_id, exc_info=exc)


def _run_council_deliberation(runtime_root: Path, request: CouncilMissionRequest) -> None:
    """Background: deliberate only (no worker). Failures surface as a failed report."""
    try:
        CouncilOrchestrator(
            runtime_root=runtime_root,
            council_state=CouncilState(db_path=runtime_root / "council_state.db"),
        ).deliberate(request)
    except Exception as exc:  # noqa: BLE001 - background task must not crash the server
        logger.warning("council_deliberation_failed", mission_id=request.mission_id, exc_info=exc)
        _write_failed_council_report(runtime_root, request.mission_id, str(exc))


def _run_council_execution(runtime_root: Path, mission_id: str) -> None:
    """Background: run the approved worker — reads the deliberated ledger for the
    contract + verdicts, executes (worker acts), and writes the final report."""
    try:
        ledger = RunLedgerStore(runtime_root).read(mission_id)
        # Defense in depth: never execute a ledger that carries a blocking verdict
        # (guards against an on-disk ledger tampered between deliberate and approve).
        if has_blocking_verdict(list(ledger.council_verdicts)):
            raise RuntimeError("ledger carries a blocking verdict; refusing to execute")
        orchestrator = CouncilOrchestrator(
            runtime_root=runtime_root,
            council_state=CouncilState(db_path=runtime_root / "council_state.db"),
        )
        asyncio.run(orchestrator.execute(ledger.contract, list(ledger.council_verdicts)))
    except Exception as exc:  # noqa: BLE001 - background task must not crash the server
        logger.warning("council_execution_failed", mission_id=mission_id, exc_info=exc)
        _write_failed_council_report(runtime_root, mission_id, str(exc))


def _council_rollback_target(ledger: RunLedger, report: KingReport) -> str:
    if report.status == "rolled_back":
        raise HTTPException(status_code=409, detail="council mission already rolled back")
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
    runtime_root: Path = Depends(get_council_runtime_root),
) -> dict[str, Any]:
    """Originate a Council mission from a goal: deliberate, then await King approval.

    The worker does NOT act here — origination runs only the Queen deliberation in
    the background and produces an ``awaiting_approval`` (or ``blocked``) report.
    Approving the mission later triggers execution. Scope is explicit + confined.
    """
    if not config.COUNCIL_ORIGINATION:
        raise HTTPException(status_code=404, detail="council origination is disabled")
    _enforce_conversation_rate_limit(req.session_id)
    if (injection_reason := _check_prompt_injection(req.goal)):
        raise HTTPException(status_code=400, detail=f"[SECURITY BLOCK] {injection_reason}")
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
    background.add_task(_run_council_deliberation, runtime_root, mission_request)
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
            ledger = ledgers.read(mission_id) if ledgers.path_for(mission_id).exists() else None
        except Exception as exc:  # noqa: BLE001 - one corrupt artifact must not kill the dashboard
            logger.warning("council_dashboard_artifact_skipped", mission_id=mission_id, exc_info=exc)
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
        logger.warning("council_dashboard_artifact_corrupt", mission_id=safe_id, exc_info=exc)
        raise HTTPException(status_code=422, detail="council artifact is corrupt") from exc
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
        logger.warning("council_report_artifact_corrupt", mission_id=safe_id, exc_info=exc)
        raise HTTPException(status_code=422, detail="council report is corrupt") from exc
    return {"missionId": safe_id, "report": report.model_dump()}


@router.post("/api/v1/council/missions/{mission_id}/rollback")
def council_mission_rollback(
    mission_id: str,
    req: CouncilRollbackRequest,
    request: Request,
    runtime_root: Path = Depends(get_council_runtime_root),
    approvals: ApprovalStore = Depends(get_approval_store),
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
        logger.warning("council_rollback_artifact_corrupt", mission_id=safe_id, exc_info=exc)
        raise HTTPException(status_code=422, detail="council artifact is corrupt") from exc

    snapshot_id = _council_rollback_target(ledger, report)
    if req.snapshot_id and req.snapshot_id != snapshot_id:
        raise HTTPException(
            status_code=403,
            detail="requested snapshot does not match council mission rollback target",
        )
    session_id = _session_id_from_request(request, req.session_id)
    if not session_id:
        raise HTTPException(status_code=422, detail="sessionId or session cookie is required")

    payload = {"mission_id": safe_id, "snapshot_id": snapshot_id}
    if not req.approval_token:
        token = approvals.issue("rollback", payload, session_id)
        return {
            "requiresApproval": True,
            "approvalToken": token,
            "actionType": "rollback",
            "missionId": safe_id,
            "snapshotId": snapshot_id,
            "executed": False,
        }
    try:
        action = approvals.consume(req.approval_token, session_id)
    except ApprovalError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if action.action_type != "rollback":
        raise HTTPException(status_code=400, detail="approval token is not for rollback")
    if action.payload != payload:
        raise HTTPException(
            status_code=403,
            detail="approval token does not match council mission rollback target",
        )
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
    runtime_root: Path = Depends(get_council_runtime_root),
) -> dict[str, Any]:
    """Record King approval; if the mission is awaiting execution, run the worker.

    A mission-level approval (no requestId) of a mission whose report is
    ``awaiting_approval`` schedules execute() in the background — this is the gate
    where a human authorizes the worker to act.
    """
    result = _write_council_decision(runtime_root=runtime_root, req=req, approved=True)
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
            background.add_task(_run_council_execution, runtime_root, safe_id)
            result["execution"] = "scheduled"
    return result


@router.post("/api/v1/council/reject")
def council_reject(
    req: CouncilDecisionRequest,
    runtime_root: Path = Depends(get_council_runtime_root),
) -> dict[str, Any]:
    """Record King rejection for a Council mission or pending worker request."""
    return _write_council_decision(runtime_root=runtime_root, req=req, approved=False)
