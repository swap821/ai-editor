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
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from aios.agents.reflection_agent import ReflectionAgent, ReflectionError
from aios.agents.rollback_engine import RollbackEngine, RollbackError
from aios.application.action_broker import ActionBroker, PolicyBrokerError
from aios.application.capabilities.authority import CapabilityAuthority, CapabilityError
from aios.api.deps import (
    _session_id_from_request,
    get_action_broker,
    get_capability_authority,
    get_emergency_stop,
    get_executor,
    get_llm_client,
    get_memory_authority,
    get_native_planner,
    get_rollback_engine,
    get_self_apply_engine,
    require_privileged_operator,
)
from aios.core.executor import Executor
from aios.core.llm import LLMClient
from aios.core.native_planner import NativePlanner
from aios.core.planner import Planner, PlannerError, serialize_plan
from aios.core.self_apply import SelfApplyEngine
from aios.domain.actions.envelope import (
    ActionEnvelope,
    ActionType,
    Principal as EnvelopePrincipal,
)
from aios.domain.identity.models import Principal
from aios.domain.capabilities.contracts import CapabilityBinding
from aios.domain.capabilities.digest import payload_digest, resource_digest
from aios.memory.db import get_connection, init_memory_db
from aios.security.audit_logger import log_action
from aios.security.gateway import Zone
from aios.api.action_guard import enforce_action_boundary

router = APIRouter(dependencies=[Depends(enforce_action_boundary)])


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class ReflectRequest(BaseModel):
    """Body for ``/reflect``."""

    command: str = Field(..., description="The action/command that failed.")
    error_output: str = Field(..., description="Captured error text.")
    task_id: Optional[str] = Field(
        None, description="Stable id for recurrence detection."
    )


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
    command: Optional[str] = Field(
        None,
        description="Exact command being rejected or approved; required for R3 capabilities.",
    )
    session_id: Optional[str] = Field(
        None,
        alias="sessionId",
        description="Fallback session id when the httpOnly session cookie is unavailable.",
    )
    approve: bool = Field(
        ..., description="True to authorise execution, False to reject."
    )

    model_config = {"populate_by_name": True}


class RollbackRequest(BaseModel):
    """Body for ``/rollback``."""

    snapshot_id: Optional[str] = Field(
        None, description="Target snapshot SHA; defaults to the previous snapshot."
    )
    approval_token: Optional[str] = Field(
        None,
        alias="approvalToken",
        description="Server-issued approval token authorising this destructive operation.",
    )
    session_id: Optional[str] = Field(
        None, alias="sessionId", description="Session that requested rollback."
    )

    model_config = {"populate_by_name": True}


class ApplyProposalRequest(BaseModel):
    """Body for Self-Analysis T3 apply; ``approvedBy`` is display-only legacy input."""

    approval_token: Optional[str] = Field(None, alias="approvalToken")
    approved_by: str = Field("", alias="approvedBy", deprecated=True)

    model_config = {"populate_by_name": True}


def _command_capability_binding(
    principal: Principal,
    command: str,
    *,
    route: str = "/api/v1/execute",
) -> CapabilityBinding:
    """Build the server-owned exact binding for a command approval."""
    payload = {"command": command}
    return CapabilityBinding(
        operator_id=principal.principal_id,
        device_id=principal.device_id,
        authentication_event_id=principal.authentication_event_id,
        session_id=principal.session_id,
        action_type="command",
        route=route,
        http_method="POST",
        payload_digest=payload_digest(payload),
        resource_digest=resource_digest({"workspace": "training_ground"}),
        mission_id=None,
        contract_digest=None,
        policy_version="v1",
        scope="training_ground/",
        verification_requirement="command_exit_zero",
    )


def _build_action_envelope(
    principal: Principal,
    request: Request,
    action_type: ActionType,
    payload: dict[str, Any],
    *,
    route: str | None = None,
    resource: Any = None,
    requested_capability: str | None = None,
) -> ActionEnvelope:
    """Build the complete R4 envelope from the authenticated request context."""
    return ActionEnvelope(
        route=route or request.url.path,
        action_type=action_type,
        http_method=request.method,
        payload=payload,
        principal=EnvelopePrincipal(
            session_id=principal.session_id,
            actor_source="session",
            client_ip=principal.client_address or "127.0.0.1",
        ),
        request_id=principal.request_id or request.headers.get("x-request-id"),
        operator_id=principal.principal_id,
        device_id=principal.device_id,
        authentication_event_id=principal.authentication_event_id,
        resource=(
            resource if resource is not None else {"workspace": "training_ground"}
        ),
        requested_capability=requested_capability,
        correlation_id=(
            request.headers.get("x-correlation-id")
            or principal.request_id
            or request.headers.get("x-request-id")
            or str(uuid.uuid4())
        ),
    )


def _command_action_envelope(
    principal: Principal,
    request: Request,
    command: str,
    *,
    route: str | None = None,
) -> ActionEnvelope:
    """Build the complete R4 envelope for a command mutation."""
    return _build_action_envelope(
        principal,
        request,
        ActionType.COMMAND,
        {"command": command},
        route=route,
        requested_capability="command.execute",
    )


# --------------------------------------------------------------------------- #
# Reflection + planning
# --------------------------------------------------------------------------- #
@router.post("/api/v1/reflect")
def reflect(
    req: ReflectRequest,
    llm: LLMClient = Depends(get_llm_client),
    authority=Depends(get_memory_authority),
) -> dict[str, Any]:
    """Run the reflection agent on a failure and store a structured lesson."""
    lessons = authority.adapters.get("lessons")
    store = getattr(lessons, "store", None)
    agent = ReflectionAgent(
        llm,
        mistakes=store,
        memory_authority=authority,
    )
    try:
        reflection = agent.reflect(req.command, req.error_output, task_id=req.task_id)
    except ReflectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return asdict(reflection)


@router.post("/api/v1/plan")
def plan(
    req: PlanRequest,
    llm: LLMClient = Depends(get_llm_client),
    native: NativePlanner = Depends(get_native_planner),
    authority=Depends(get_memory_authority),
) -> dict[str, Any]:
    """Decompose a goal into a confidence-gated task tree."""
    planner = Planner(llm, native=native, memory_authority=authority)
    try:
        result = planner.plan(req.goal)
    except PlannerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return serialize_plan(result)


# --------------------------------------------------------------------------- #
# Gated execution + human approval resolution
# --------------------------------------------------------------------------- #
@router.post("/api/v1/execute")
def execute(
    req: ExecuteRequest,
    request: Request,
    _principal: Principal = Depends(require_privileged_operator),
    executor: Executor = Depends(get_executor),
    broker: ActionBroker = Depends(get_action_broker),
) -> dict[str, Any]:
    """Classify, gate, audit, and (if GREEN) run a command in the sandbox."""
    # Command sessions are authoritative only when bound to the validated
    # httpOnly cookie.  The request-body session id is retained in the schema
    # for old clients, but is deliberately not an authorization fallback.
    session_id = _session_id_from_request(request, None)
    envelope = _command_action_envelope(_principal, request, req.command)
    binding = _command_capability_binding(_principal, req.command)
    try:
        decision = broker.submit(envelope, capability_binding=binding)
    except PolicyBrokerError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if decision.blocked:
        return {
            "status": "BLOCKED",
            "zone": decision.zone.value,
            "command": req.command,
            "reason": decision.reason,
        }
    if decision.requires_approval:
        if not session_id:
            raise HTTPException(
                status_code=400,
                detail="a valid session cookie is required to approve a YELLOW command",
            )
        return {
            "status": "REQUIRE_APPROVAL",
            "zone": decision.zone.value,
            "command": req.command,
            "reason": decision.reason,
            "approvalToken": decision.approval_token,
            "sessionId": session_id,
        }

    result = executor.execute(req.command, session_id=session_id)
    response = asdict(result)
    if result.status == "REQUIRE_APPROVAL":
        # The broker is authoritative for escalation. An executor that asks for
        # approval after the broker allowed execution is a policy drift and must
        # fail closed rather than mint a second capability here.
        raise HTTPException(
            status_code=500,
            detail="executor disagreed with ActionBroker decision",
        )
    return response


@router.post("/api/v1/approval/req")
def approval_req(
    req: ApprovalRequest,
    request: Request,
    _principal: Principal = Depends(require_privileged_operator),
    executor: Executor = Depends(get_executor),
    capabilities: CapabilityAuthority = Depends(get_capability_authority),
    broker: ActionBroker = Depends(get_action_broker),
) -> dict[str, Any]:
    """Resolve a human decision on an escalated (YELLOW) action.

    Approve -> run the command in the sandbox (RED is still refused). Reject ->
    audit the rejection and return without running.
    """
    session_id = _session_id_from_request(request, None)
    if not session_id:
        raise HTTPException(
            status_code=422, detail="a valid session cookie is required"
        )
    command = req.command or ""
    try:
        capability = capabilities.inspect(req.approval_token)
        route = capability.binding.route
        if route not in {"/api/v1/execute", "/api/terminal"}:
            raise CapabilityError("command capability route is not approved here")
        if req.command:
            expected_command = req.command
        else:
            payload = capability.action_payload
            if not isinstance(payload, dict) or not isinstance(
                payload.get("command"), str
            ):
                raise CapabilityError("command capability has no replayable payload")
            expected_command = str(payload["command"])
        binding = _command_capability_binding(
            _principal,
            expected_command,
            route=route,
        )
        envelope = _command_action_envelope(
            _principal,
            request,
            expected_command,
            route=route,
        )
        decision = broker.submit(
            envelope,
            capability_token=req.approval_token,
            capability_binding=binding,
        )
        command = expected_command
    except (CapabilityError, PolicyBrokerError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not req.approve:
        executor.reset_sensitive_actions(session_id)
        action_type = capability.binding.action_type
        target = command or action_type
        log_action("human-approval", f"REJECTED {action_type}: {target}", Zone.YELLOW)
        return {
            "decision": "rejected",
            "actionType": action_type,
            "command": command,
            "executed": False,
        }
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
    _principal: Principal = Depends(require_privileged_operator),
    engine: RollbackEngine = Depends(get_rollback_engine),
    broker: ActionBroker = Depends(get_action_broker),
    emergency_stop=Depends(get_emergency_stop),
) -> dict[str, Any]:
    """Restore the sandbox working tree to a prior snapshot.

    Rollback is a DESTRUCTIVE operation that requires a server-issued approval
    token. When called without a token, one is issued and returned so the UI
    can prompt the human approver; when called with a valid token, the token
    is consumed and the rollback executes.
    """
    # Organ 26: a destructive workspace restore must never proceed while the
    # emergency stop is engaged -- this route had no such check at all.
    emergency_stop.assert_operational()
    session_id = _session_id_from_request(request, None)
    if not session_id:
        raise HTTPException(
            status_code=422, detail="a valid session cookie is required"
        )
    try:
        snapshot_id = _effective_rollback_snapshot(engine, req.snapshot_id)
    except RollbackError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    payload = {"snapshot_id": snapshot_id}
    envelope = _build_action_envelope(
        _principal,
        request,
        ActionType.ROLLBACK,
        payload,
        resource={"snapshot_id": snapshot_id},
        requested_capability="rollback.restore",
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
        resource_digest=resource_digest({"snapshot_id": snapshot_id}),
        mission_id=None,
        contract_digest=None,
        policy_version="v1",
        scope=f"rollback:{snapshot_id}",
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
            "snapshotId": snapshot_id,
            "executed": False,
        }
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


def _proposal_capability_record(proposal_id: int) -> dict[str, Any]:
    """Read the proposal fields that are bound into a self-apply capability."""
    init_memory_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, target_path, proposed_diff, status "
            "FROM self_analysis_report WHERE id = ?",
            (proposal_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"no proposal with id {proposal_id}"
        )
    if row["status"] != "proposed":
        raise HTTPException(
            status_code=409,
            detail=f"proposal {proposal_id} is '{row['status']}', not 'proposed'",
        )
    target_path = str(row["target_path"] or "")
    proposed_diff = str(row["proposed_diff"] or "")
    if not target_path or not proposed_diff.strip():
        raise HTTPException(
            status_code=409, detail="proposal has no exact patch to approve"
        )
    return {
        "proposal_id": int(row["id"]),
        "target_path": target_path,
        "proposed_diff": proposed_diff,
    }


def _proposal_capability_binding(
    principal: Principal,
    request: Request,
    proposal: dict[str, Any],
) -> CapabilityBinding:
    """Bind approval to this principal, route, and the proposal's exact patch."""
    return CapabilityBinding(
        operator_id=principal.principal_id,
        device_id=principal.device_id,
        authentication_event_id=principal.authentication_event_id,
        session_id=principal.session_id,
        action_type="proposal_apply",
        route=request.url.path,
        http_method=request.method,
        payload_digest=payload_digest(proposal),
        resource_digest=resource_digest(
            {
                "proposal_id": proposal["proposal_id"],
                "target_path": proposal["target_path"],
            }
        ),
        mission_id=None,
        contract_digest=None,
        policy_version="v1",
        scope=str(proposal["target_path"]),
        verification_requirement="self_apply_verify_pass",
    )


@router.post("/api/v1/self-analysis/proposals/{proposal_id}/apply")
def apply_proposal(
    proposal_id: int,
    req: ApplyProposalRequest,
    request: Request,
    _principal: Principal = Depends(require_privileged_operator),
    engine: SelfApplyEngine = Depends(get_self_apply_engine),
    broker: ActionBroker = Depends(get_action_broker),
) -> dict[str, Any]:
    """Issue or consume an exact capability for a guarded self-apply (T3)."""
    proposal = _proposal_capability_record(proposal_id)
    binding = _proposal_capability_binding(_principal, request, proposal)
    envelope = _build_action_envelope(
        _principal,
        request,
        ActionType.PROPOSAL_APPLY,
        proposal,
        resource={
            "proposal_id": proposal["proposal_id"],
            "target_path": proposal["target_path"],
        },
        requested_capability="self_analysis.apply",
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
            "actionType": "proposal_apply",
            "proposalId": proposal_id,
            "targetPath": proposal["target_path"],
            "patchDigest": payload_digest({"proposed_diff": proposal["proposed_diff"]}),
            "executed": False,
        }
    result = engine.apply(proposal_id, approved_by=_principal.principal_id)
    return asdict(result)


@router.post("/api/v1/self-analysis/proposals/{proposal_id}/reject")
def reject_proposal(
    proposal_id: int,
    _principal: Principal = Depends(require_privileged_operator),
) -> dict[str, Any]:
    """Reject a ``proposed`` finding (status -> ``rejected``); never applies anything."""
    init_memory_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT status FROM self_analysis_report WHERE id = ?", (proposal_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"no proposal with id {proposal_id}"
            )
        if row["status"] != "proposed":
            raise HTTPException(
                status_code=409,
                detail=f"proposal {proposal_id} is '{row['status']}', not 'proposed'",
            )
        conn.execute(
            "UPDATE self_analysis_report SET status = 'rejected' WHERE id = ?",
            (proposal_id,),
        )
    return {"id": proposal_id, "status": "rejected"}
