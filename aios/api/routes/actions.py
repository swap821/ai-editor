"""Action routes: reflection, planning, gated execution, human approval
resolution, sandbox rollback, and Self-Analysis T3 review/apply.

Extracted from ``aios/api/main.py`` (monolith split tranche 2, 2026-07-06).
Dependency providers come from ``aios.api.deps`` — the SAME function objects
``main`` re-exports, so ``app.dependency_overrides`` keyed on either import
path keep working. Route bodies are byte-equivalent moves: every security
property (server-issued single-use approval tokens, RED refusal inside the
Executor, snapshot-bound rollback tokens, human-only self-apply) is unchanged.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from aios.agents.reflection_agent import ReflectionAgent, ReflectionError
from aios.agents.rollback_engine import RollbackEngine, RollbackError
from aios.api.deps import (
    _session_id_from_request,
    get_approval_store,
    get_executor,
    get_llm_client,
    get_native_planner,
    get_rollback_engine,
    get_self_apply_engine,
)
from aios.core.approvals import ApprovalError, ApprovalStore
from aios.core.executor import Executor
from aios.core.llm import LLMClient
from aios.core.native_planner import NativePlanner
from aios.core.planner import Planner, PlannerError
from aios.core.self_apply import SelfApplyEngine
from aios.memory.db import get_connection, init_memory_db
from aios.security.audit_logger import log_action
from aios.security.gateway import Zone

router = APIRouter()


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class ReflectRequest(BaseModel):
    """Body for ``/reflect``."""

    command: str = Field(..., description="The action/command that failed.")
    error_output: str = Field(..., description="Captured error text.")
    task_id: Optional[str] = Field(None, description="Stable id for recurrence detection.")


class PlanRequest(BaseModel):
    """Body for ``/plan``."""

    goal: str = Field(..., description="High-level goal to decompose into steps.")


class ExecuteRequest(BaseModel):
    """Body for ``/execute``."""

    command: str = Field(..., description="Command to classify, gate, and run.")
    session_id: Optional[str] = Field(
        None,
        alias="sessionId",
        description="Required for a YELLOW command's server-issued approval capability.",
    )

    model_config = {"populate_by_name": True}


class ApprovalRequest(BaseModel):
    """Body for ``/approval/req`` — a human's decision on an escalated action."""

    approval_token: str = Field(..., alias="approvalToken")
    session_id: Optional[str] = Field(
        None,
        alias="sessionId",
        description="Fallback session id when the httpOnly session cookie is unavailable.",
    )
    approve: bool = Field(..., description="True to authorise execution, False to reject.")

    model_config = {"populate_by_name": True}


class RollbackRequest(BaseModel):
    """Body for ``/rollback``."""

    snapshot_id: Optional[str] = Field(
        None, description="Target snapshot SHA; defaults to the previous snapshot."
    )
    approval_token: Optional[str] = Field(
        None, alias="approvalToken",
        description="Server-issued approval token authorising this destructive operation.",
    )
    session_id: Optional[str] = Field(
        None, alias="sessionId", description="Session that requested rollback."
    )

    model_config = {"populate_by_name": True}


class ApplyProposalRequest(BaseModel):
    """Body for the Self-Analysis T3 apply endpoint — the HUMAN approver's id."""

    approved_by: str = Field("", alias="approvedBy")

    model_config = {"populate_by_name": True}


# --------------------------------------------------------------------------- #
# Reflection + planning
# --------------------------------------------------------------------------- #
@router.post("/api/v1/reflect")
def reflect(req: ReflectRequest, llm: LLMClient = Depends(get_llm_client)) -> dict[str, Any]:
    """Run the reflection agent on a failure and store a structured lesson."""
    agent = ReflectionAgent(llm)
    try:
        reflection = agent.reflect(req.command, req.error_output, task_id=req.task_id)
    except ReflectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return asdict(reflection)


def _serialize_plan(plan: Any) -> dict[str, Any]:
    """Flatten a Plan (with TaskStep dataclasses) into JSON-safe primitives."""
    return {
        "goal": plan.goal,
        "requires_human": plan.requires_human,
        "steps": [asdict(s) for s in plan.steps],
        "approved": [asdict(s) for s in plan.approved],
        "escalate": [
            {"step": asdict(e["step"]), "reason": e["reason"], "action": e["action"]}
            for e in plan.escalate
        ],
        "calibrations": [asdict(c) for c in plan.calibrations],
    }


@router.post("/api/v1/plan")
def plan(
    req: PlanRequest,
    llm: LLMClient = Depends(get_llm_client),
    native: NativePlanner = Depends(get_native_planner),
) -> dict[str, Any]:
    """Decompose a goal into a confidence-gated task tree."""
    planner = Planner(llm, native=native)
    try:
        result = planner.plan(req.goal)
    except PlannerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _serialize_plan(result)


# --------------------------------------------------------------------------- #
# Gated execution + human approval resolution
# --------------------------------------------------------------------------- #
@router.post("/api/v1/execute")
def execute(
    req: ExecuteRequest,
    executor: Executor = Depends(get_executor),
    approvals: ApprovalStore = Depends(get_approval_store),
) -> dict[str, Any]:
    """Classify, gate, audit, and (if GREEN) run a command in the sandbox."""
    result = executor.execute(req.command, session_id=req.session_id)
    response = asdict(result)
    if result.status == "REQUIRE_APPROVAL":
        if not req.session_id:
            raise HTTPException(
                status_code=400,
                detail="sessionId is required to approve a YELLOW command",
            )
        response["approvalToken"] = approvals.issue(
            "command", {"command": req.command}, req.session_id
        )
        response["sessionId"] = req.session_id
    return response


@router.post("/api/v1/approval/req")
def approval_req(
    req: ApprovalRequest,
    request: Request,
    executor: Executor = Depends(get_executor),
    approvals: ApprovalStore = Depends(get_approval_store),
) -> dict[str, Any]:
    """Resolve a human decision on an escalated (YELLOW) action.

    Approve -> run the command in the sandbox (RED is still refused). Reject ->
    audit the rejection and return without running.
    """
    session_id = _session_id_from_request(request, req.session_id)
    if not session_id:
        raise HTTPException(status_code=422, detail="sessionId or session cookie is required")
    try:
        action = approvals.consume(req.approval_token, session_id)
    except ApprovalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    command = str(action.payload.get("command", ""))
    if not req.approve:
        if action.action_type == "command":
            executor.reset_sensitive_actions(session_id)
        target = command or str(action.payload.get("filepath", action.action_type))
        log_action("human-approval", f"REJECTED {action.action_type}: {target}", Zone.YELLOW)
        return {
            "decision": "rejected",
            "actionType": action.action_type,
            "command": command,
            "executed": False,
        }
    if action.action_type != "command":
        raise HTTPException(status_code=400, detail="approval token is not for a command")
    executor.reset_sensitive_actions(session_id)

    result = executor.execute_approved(command)
    return {
        "decision": "approved",
        "command": command,
        "executed": result.status == "OK",
        "result": asdict(result),
    }


# --------------------------------------------------------------------------- #
# Sandbox rollback (destructive; server-issued snapshot-bound token)
# --------------------------------------------------------------------------- #
def _effective_rollback_snapshot(
    engine: RollbackEngine, requested: Optional[str]
) -> str:
    """Resolve the rollback target before approval so the token binds a SHA."""
    if requested:
        return requested
    snapshots = engine.list_snapshots(limit=2)
    if len(snapshots) < 2:
        raise HTTPException(
            status_code=409,
            detail="No previous snapshot to roll back to.",
        )
    return snapshots[1].sha


@router.post("/api/v1/rollback")
def rollback(
    req: RollbackRequest,
    request: Request,
    engine: RollbackEngine = Depends(get_rollback_engine),
    approvals: ApprovalStore = Depends(get_approval_store),
) -> dict[str, Any]:
    """Restore the sandbox working tree to a prior snapshot.

    Rollback is a DESTRUCTIVE operation that requires a server-issued approval
    token. When called without a token, one is issued and returned so the UI
    can prompt the human approver; when called with a valid token, the token
    is consumed and the rollback executes.
    """
    session_id = _session_id_from_request(request, req.session_id)
    if not session_id:
        raise HTTPException(status_code=422, detail="sessionId or session cookie is required")
    try:
        snapshot_id = _effective_rollback_snapshot(engine, req.snapshot_id)
    except RollbackError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not req.approval_token:
        token = approvals.issue(
            "rollback", {"snapshot_id": snapshot_id}, session_id
        )
        return {
            "requiresApproval": True,
            "approvalToken": token,
            "actionType": "rollback",
            "snapshotId": snapshot_id,
            "executed": False,
        }
    try:
        action = approvals.consume(req.approval_token, session_id)
    except ApprovalError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if action.action_type != "rollback":
        raise HTTPException(status_code=400, detail="approval token is not for rollback")
    if action.payload.get("snapshot_id") != snapshot_id:
        raise HTTPException(status_code=403, detail="approval token snapshot does not match request")
    try:
        result = engine.rollback(snapshot_id)
    except RollbackError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return asdict(result)


# --------------------------------------------------------------------------- #
# Self-Analysis T3 — human-gated review + apply of fix proposals
# The agent has NO tool to apply (see tool_agent); these human-called endpoints
# are the ONLY path from a 'proposed' row to a real write in aios/.
# --------------------------------------------------------------------------- #
@router.get("/api/v1/self-analysis/proposals")
def list_proposals(status: Optional[str] = "proposed") -> dict[str, Any]:
    """List Self-Analysis findings (default the ``proposed`` ones) for the review UI."""
    init_memory_db()
    sql = (
        "SELECT id, target_path, finding_type, evidence, proposed_zone, "
        "proposed_diff, proposed_by, approved_by, status FROM self_analysis_report"
    )
    params: list[Any] = []
    if status:
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY id DESC LIMIT 200"
    with get_connection() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    return {"proposals": rows}


@router.post("/api/v1/self-analysis/proposals/{proposal_id}/apply")
def apply_proposal(
    proposal_id: int,
    req: ApplyProposalRequest,
    engine: SelfApplyEngine = Depends(get_self_apply_engine),
) -> dict[str, Any]:
    """Apply an approved proposal to ``aios/`` — gated, verified, auto-rollback (T3)."""
    result = engine.apply(proposal_id, approved_by=req.approved_by)
    return asdict(result)


@router.post("/api/v1/self-analysis/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: int) -> dict[str, Any]:
    """Reject a ``proposed`` finding (status -> ``rejected``); never applies anything."""
    init_memory_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT status FROM self_analysis_report WHERE id = ?", (proposal_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"no proposal with id {proposal_id}")
        if row["status"] != "proposed":
            raise HTTPException(
                status_code=409,
                detail=f"proposal {proposal_id} is '{row['status']}', not 'proposed'",
            )
        conn.execute(
            "UPDATE self_analysis_report SET status = 'rejected' WHERE id = ?", (proposal_id,)
        )
    return {"id": proposal_id, "status": "rejected"}
