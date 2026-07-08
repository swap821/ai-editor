"""Sovereign Roadmap Phase 3B-8 routes: Queen Services, Pheromones, Live Surface,
Rollback Registry, Audit Anchor, Policy Engine.

Extracted from aios/api/main.py.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aios import config
from aios.runtime.budget_guard import BudgetGuard
from aios.runtime.hibernation import HibernationManager, HibernationPolicyError

router = APIRouter()
_LAST_HIBERNATION_REPORT: dict[str, Any] | None = None


@router.get("/api/v1/council/services")
def council_services() -> dict:
    """Queen service health/status for all registered services."""
    if not config.QUEEN_SERVICES:
        raise HTTPException(status_code=404, detail="queen services not enabled")
    from aios.council.queen_service import QUEEN_SERVICES
    return {"services": {name: svc.health() for name, svc in QUEEN_SERVICES.items()}}


@router.get("/api/v1/pheromones/surface")
def pheromone_surface(resource: str | None = None, ptype: str | None = None) -> dict:
    """Query the pheromone store."""
    if not config.PHEROMONE_ENABLED:
        raise HTTPException(status_code=404, detail="pheromone store not enabled")
    from aios.memory.pheromones import PheromoneStore, PheromoneType
    store = PheromoneStore(db_path=config.PHEROMONE_DB)
    ptype_enum = PheromoneType(ptype) if ptype else None
    results = store.query(resource=resource, ptype=ptype_enum)
    return {"pheromones": [
        {"id": p.pheromone_id, "type": p.ptype.value, "resource": p.resource,
         "depositor": p.depositor, "strength": round(p.strength, 4),
         "payload": p.payload, "created_at": p.created_at}
        for p in results
    ]}


@router.get("/api/v1/runtime/surface")
def live_surface_snapshot() -> dict:
    """Live pheromone surface snapshot."""
    if not config.LIVE_SURFACE:
        raise HTTPException(status_code=404, detail="live surface not enabled")
    from aios.runtime.live_surface import LiveSurface
    surface = LiveSurface(db_path=config.LIVE_SURFACE_DB)
    return surface.snapshot()


@router.get("/api/v1/resource/status")
def resource_status() -> dict:
    """Current process resource/budget mode."""
    guard = BudgetGuard()
    return guard.snapshot().to_dict() | {"source": "process_default"}


class HibernationRunRequest(BaseModel):
    allow_writes: bool = Field(False, alias="allowWrites")
    allow_cloud: bool = Field(False, alias="allowCloud")
    rebuild_repo_map: bool = Field(True, alias="rebuildRepoMap")
    repo_root: str | None = Field(None, alias="repoRoot")
    model_config = {"populate_by_name": True}


@router.post("/api/v1/hibernation/run")
def hibernation_run(req: HibernationRunRequest) -> dict:
    """Run local-only hibernation maintenance in proposal/evidence mode."""
    global _LAST_HIBERNATION_REPORT
    compactor = None
    try:
        from aios.api.main import get_compactor

        compactor = get_compactor()
    except Exception:
        compactor = None
    pheromone_store = None
    if config.PHEROMONE_ENABLED:
        from aios.memory.pheromones import PheromoneStore

        pheromone_store = PheromoneStore(db_path=config.PHEROMONE_DB)
    try:
        report = HibernationManager(
            repo_root=req.repo_root or config.PROJECT_ROOT,
            compactor=compactor,
            pheromone_store=pheromone_store,
            budget_guard=BudgetGuard(mode="hibernation"),
        ).run(
            allow_writes=req.allow_writes,
            allow_cloud=req.allow_cloud,
            rebuild_repo_map=req.rebuild_repo_map,
        )
    except HibernationPolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = report.to_dict()
    _LAST_HIBERNATION_REPORT = _hibernation_status_summary(payload)
    return payload


@router.get("/api/v1/hibernation/status")
def hibernation_status() -> dict:
    """Return hibernation policy/status without running maintenance."""
    return {
        "configuredMode": config.RESOURCE_MODE,
        "hibernationMode": "hibernation",
        "localOnly": True,
        "writesAllowed": False,
        "cloudAllowed": False,
        "lastRun": _LAST_HIBERNATION_REPORT,
    }


def _hibernation_status_summary(payload: dict[str, Any]) -> dict[str, Any]:
    project_passport = payload.get("projectPassport", {})
    resource_status = payload.get("resourceStatus", {})
    return {
        "ranAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "mode": payload.get("mode"),
        "localOnly": payload.get("localOnly") is True,
        "writesPerformed": payload.get("writesPerformed") is True,
        "cloudCalls": int(payload.get("cloudCalls") or 0),
        "proposalCount": len(payload.get("proposals") or []),
        "projectPassport": {
            "skipped": project_passport.get("skipped") is True,
            "activation": project_passport.get("activation", "proposal/evidence"),
        },
        "resourceMode": resource_status.get("mode", "hibernation"),
    }


@router.get("/api/v1/runtime/rollbacks")
def rollback_registry_query(
    mission_id: str | None = None,
    file_pattern: str | None = None,
    workspace_root: str | None = None,
) -> dict:
    """Query the rollback registry."""
    if not config.ROLLBACK_REGISTRY:
        raise HTTPException(status_code=404, detail="rollback registry not enabled")
    from aios.runtime.rollback_registry import RollbackRegistry
    registry = RollbackRegistry(db_path=config.ROLLBACK_REGISTRY_DB)
    entries = registry.query(
        mission_id=mission_id, file_pattern=file_pattern, workspace_root=workspace_root
    )
    return {"entries": [
        {"snapshot_id": e.snapshot_id, "mission_id": e.mission_id,
         "workspace_root": e.workspace_root, "created_at": e.created_at,
         "files_covered": e.files_covered, "metadata": e.metadata}
        for e in entries
    ]}


@router.get("/api/v1/runtime/rollbacks/health")
def rollback_registry_health() -> dict:
    """Rollback registry coverage report."""
    if not config.ROLLBACK_REGISTRY:
        raise HTTPException(status_code=404, detail="rollback registry not enabled")
    from aios.runtime.rollback_registry import RollbackRegistry
    registry = RollbackRegistry(db_path=config.ROLLBACK_REGISTRY_DB)
    return registry.health()


class AuditAnchorVerifyRequest(BaseModel):
    expected_hash: str = Field(..., alias="expectedHash")
    model_config = {"populate_by_name": True}


@router.get("/api/v1/audit/anchor")
def audit_anchor() -> dict:
    """Get the current audit chain anchor for external publication."""
    if not config.AUDIT_ANCHOR_API:
        raise HTTPException(status_code=404, detail="audit anchor API not enabled")
    from aios.audit_anchor import get_external_anchor
    return get_external_anchor()


@router.post("/api/v1/audit/anchor/verify")
def audit_anchor_verify(req: AuditAnchorVerifyRequest) -> dict:
    """Verify the current chain tip matches a previously published anchor hash."""
    if not config.AUDIT_ANCHOR_API:
        raise HTTPException(status_code=404, detail="audit anchor API not enabled")
    from aios.audit_anchor import verify_anchor
    return verify_anchor(req.expected_hash)


@router.get("/api/v1/policy/current")
def policy_current() -> dict:
    """Return all enacted (non-suspended) policies."""
    if not config.POLICY_ENGINE:
        raise HTTPException(status_code=404, detail="policy engine not enabled")
    from aios.policy.engine import PolicyEngine
    engine = PolicyEngine(db_path=config.POLICY_DB)
    policies = engine.current_policies()
    return {"policies": [
        {"policy_id": p.policy_id, "version": p.version, "constraint": p.constraint,
         "status": p.status.value, "proposed_by": p.proposed_by,
         "enacted_at": p.enacted_at}
        for p in policies
    ]}


class PolicyProposeRequest(BaseModel):
    constraint: str
    proposed_by: str = Field(..., alias="proposedBy")
    model_config = {"populate_by_name": True}


@router.post("/api/v1/policy/propose")
def policy_propose(req: PolicyProposeRequest) -> dict:
    """Propose a new additive-only policy constraint."""
    if not config.POLICY_ENGINE:
        raise HTTPException(status_code=404, detail="policy engine not enabled")
    from aios.policy.engine import PolicyEngine
    engine = PolicyEngine(db_path=config.POLICY_DB)
    if not engine.validate_additive(req.constraint):
        raise HTTPException(status_code=400, detail="constraint must be additive-only")
    policy_id = engine.propose(req.constraint, proposed_by=req.proposed_by)
    return {"policy_id": policy_id}


# ═══════════════════════════════════════════════════════════════════════════════
# Sovereign Roadmap — Write/Mutation Endpoints (Wave 2B)
# ═══════════════════════════════════════════════════════════════════════════════


# --- Pheromone write endpoints ---


class PheromoneDepositRequest(BaseModel):
    ptype: str
    resource: str
    depositor: str
    strength: float = 1.0
    payload: dict = Field(default_factory=dict)


@router.post("/api/v1/pheromones/deposit")
def pheromone_deposit(req: PheromoneDepositRequest) -> dict:
    """Deposit a new pheromone signal."""
    if not config.PHEROMONE_ENABLED:
        raise HTTPException(status_code=404, detail="pheromone store not enabled")
    from aios.memory.pheromones import PheromoneStore, PheromoneType
    try:
        ptype_enum = PheromoneType(req.ptype)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid pheromone type: {req.ptype}")
    store = PheromoneStore(db_path=config.PHEROMONE_DB)
    pid = store.deposit(
        ptype=ptype_enum, resource=req.resource,
        depositor=req.depositor, strength=req.strength, payload=req.payload,
    )
    return {"pheromone_id": pid}


class PheromoneReinforceRequest(BaseModel):
    pheromone_id: int = Field(..., alias="pheromoneId")
    boost: float = 0.2
    model_config = {"populate_by_name": True}


@router.post("/api/v1/pheromones/reinforce")
def pheromone_reinforce(req: PheromoneReinforceRequest) -> dict:
    """Reinforce an existing pheromone signal."""
    if not config.PHEROMONE_ENABLED:
        raise HTTPException(status_code=404, detail="pheromone store not enabled")
    from aios.memory.pheromones import PheromoneStore
    store = PheromoneStore(db_path=config.PHEROMONE_DB)
    store.reinforce(req.pheromone_id, boost=req.boost)
    return {"reinforced": True}


@router.post("/api/v1/pheromones/decay")
def pheromone_decay() -> dict:
    """Run decay sweep — prune signals below floor strength."""
    if not config.PHEROMONE_ENABLED:
        raise HTTPException(status_code=404, detail="pheromone store not enabled")
    from aios.memory.pheromones import PheromoneStore
    store = PheromoneStore(db_path=config.PHEROMONE_DB)
    pruned = store.decay_all()
    return {"pruned": pruned}


# --- Live Surface write endpoints ---


class LiveSurfaceEmitRequest(BaseModel):
    stype: str
    resource: str
    worker_id: str = Field(..., alias="workerId")
    ttl_seconds: int = Field(30, alias="ttlSeconds")
    payload: dict = Field(default_factory=dict)
    model_config = {"populate_by_name": True}


@router.post("/api/v1/runtime/surface/emit")
def live_surface_emit(req: LiveSurfaceEmitRequest) -> dict:
    """Emit an ephemeral coordination signal."""
    if not config.LIVE_SURFACE:
        raise HTTPException(status_code=404, detail="live surface not enabled")
    from aios.runtime.live_surface import LiveSurface, SignalType
    try:
        stype_enum = SignalType(req.stype)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid signal type: {req.stype}")
    surface = LiveSurface(db_path=config.LIVE_SURFACE_DB)
    signal_id = surface.emit(
        stype=stype_enum, resource=req.resource,
        worker_id=req.worker_id, ttl_seconds=req.ttl_seconds, payload=req.payload,
    )
    return {"signal_id": signal_id}


@router.delete("/api/v1/runtime/surface/{signal_id}")
def live_surface_revoke(signal_id: int) -> dict:
    """Revoke a live surface signal."""
    if not config.LIVE_SURFACE:
        raise HTTPException(status_code=404, detail="live surface not enabled")
    from aios.runtime.live_surface import LiveSurface
    surface = LiveSurface(db_path=config.LIVE_SURFACE_DB)
    revoked = surface.revoke(signal_id)
    if not revoked:
        raise HTTPException(status_code=404, detail=f"signal {signal_id} not found")
    return {"revoked": True}


@router.post("/api/v1/runtime/surface/sweep")
def live_surface_sweep() -> dict:
    """Sweep expired signals from the live surface."""
    if not config.LIVE_SURFACE:
        raise HTTPException(status_code=404, detail="live surface not enabled")
    from aios.runtime.live_surface import LiveSurface
    surface = LiveSurface(db_path=config.LIVE_SURFACE_DB)
    swept = surface.sweep_expired()
    return {"swept": swept}


# --- Rollback Registry write endpoints ---


class RollbackRegisterRequest(BaseModel):
    snapshot_id: str = Field(..., alias="snapshotId")
    mission_id: str = Field(..., alias="missionId")
    workspace_root: str = Field(..., alias="workspaceRoot")
    files_covered: list[str] = Field(default_factory=list, alias="filesCovered")
    metadata: dict = Field(default_factory=dict)
    model_config = {"populate_by_name": True}


@router.post("/api/v1/runtime/rollbacks/register")
def rollback_register(req: RollbackRegisterRequest) -> dict:
    """Register a new snapshot point in the rollback registry."""
    if not config.ROLLBACK_REGISTRY:
        raise HTTPException(status_code=404, detail="rollback registry not enabled")
    from aios.runtime.rollback_registry import RollbackRegistry
    registry = RollbackRegistry(db_path=config.ROLLBACK_REGISTRY_DB)
    registry.register(
        snapshot_id=req.snapshot_id, mission_id=req.mission_id,
        workspace_root=req.workspace_root,
        files_covered=req.files_covered, metadata=req.metadata,
    )
    return {"registered": True, "snapshot_id": req.snapshot_id}


@router.post("/api/v1/runtime/rollbacks/prune")
def rollback_prune() -> dict:
    """Prune rollback entries past the retention window."""
    if not config.ROLLBACK_REGISTRY:
        raise HTTPException(status_code=404, detail="rollback registry not enabled")
    from aios.runtime.rollback_registry import RollbackRegistry
    registry = RollbackRegistry(db_path=config.ROLLBACK_REGISTRY_DB)
    pruned = registry.prune()
    return {"pruned": pruned}


# --- Audit Anchor write endpoints ---


@router.get("/api/v1/audit/anchor/history")
def audit_anchor_history(limit: int = 10) -> dict:
    """Retrieve anchor publication history."""
    if not config.AUDIT_ANCHOR_API:
        raise HTTPException(status_code=404, detail="audit anchor API not enabled")
    from aios.audit_anchor import anchor_history
    entries = anchor_history(limit=limit)
    return {"entries": entries, "count": len(entries)}


# --- Policy Engine write endpoints ---


class PolicyVoteRequest(BaseModel):
    queen: str
    approve: bool
    reason: str = ""


@router.post("/api/v1/policy/{policy_id}/vote")
def policy_vote(policy_id: str, req: PolicyVoteRequest) -> dict:
    """Cast a queen's vote on a proposed policy."""
    if not config.POLICY_ENGINE:
        raise HTTPException(status_code=404, detail="policy engine not enabled")
    from aios.policy.engine import PolicyEngine
    engine = PolicyEngine(db_path=config.POLICY_DB)
    try:
        engine.vote(policy_id, queen=req.queen, approve=req.approve, reason=req.reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"voted": True}


class PolicyEnactRequest(BaseModel):
    required_approvals: int = Field(3, alias="requiredApprovals")
    model_config = {"populate_by_name": True}


@router.post("/api/v1/policy/{policy_id}/enact")
def policy_enact(policy_id: str, req: PolicyEnactRequest) -> dict:
    """Enact a proposed policy if it has enough approvals."""
    if not config.POLICY_ENGINE:
        raise HTTPException(status_code=404, detail="policy engine not enabled")
    from aios.policy.engine import PolicyEngine
    engine = PolicyEngine(db_path=config.POLICY_DB)
    try:
        policy = engine.enact(policy_id, required_approvals=req.required_approvals)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "enacted": True, "policy_id": policy.policy_id,
        "version": policy.version, "enacted_at": policy.enacted_at,
    }


class PolicySuspendRequest(BaseModel):
    suspended_by: str = Field(..., alias="suspendedBy")
    model_config = {"populate_by_name": True}


@router.post("/api/v1/policy/{policy_id}/suspend")
def policy_suspend(policy_id: str, req: PolicySuspendRequest) -> dict:
    """Suspend an enacted policy."""
    if not config.POLICY_ENGINE:
        raise HTTPException(status_code=404, detail="policy engine not enabled")
    from aios.policy.engine import PolicyEngine
    engine = PolicyEngine(db_path=config.POLICY_DB)
    try:
        policy = engine.suspend(policy_id, suspended_by=req.suspended_by)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"suspended": True, "policy_id": policy.policy_id}


@router.get("/api/v1/policy/chain")
def policy_chain() -> dict:
    """Full version history of all policies (proposed, enacted, suspended)."""
    if not config.POLICY_ENGINE:
        raise HTTPException(status_code=404, detail="policy engine not enabled")
    from aios.policy.engine import PolicyEngine
    engine = PolicyEngine(db_path=config.POLICY_DB)
    chain = engine.policy_chain()
    return {"policies": [
        {"policy_id": p.policy_id, "version": p.version, "constraint": p.constraint,
         "status": p.status.value, "proposed_by": p.proposed_by,
         "enacted_at": p.enacted_at}
        for p in chain
    ]}


# --- Queen Services management endpoints ---


@router.post("/api/v1/council/services/{name}/start")
async def council_service_start(name: str) -> dict:
    """Start a registered queen service."""
    if not config.QUEEN_SERVICES:
        raise HTTPException(status_code=404, detail="queen services not enabled")
    from aios.council.queen_service import QUEEN_SERVICES
    service = QUEEN_SERVICES.get(name)
    if service is None:
        raise HTTPException(status_code=404, detail=f"service '{name}' not registered")
    await service.start()
    return {"started": True, "name": name}


@router.post("/api/v1/council/services/{name}/stop")
async def council_service_stop(name: str) -> dict:
    """Stop a registered queen service."""
    if not config.QUEEN_SERVICES:
        raise HTTPException(status_code=404, detail="queen services not enabled")
    from aios.council.queen_service import QUEEN_SERVICES
    service = QUEEN_SERVICES.get(name)
    if service is None:
        raise HTTPException(status_code=404, detail=f"service '{name}' not registered")
    await service.stop()
    return {"stopped": True, "name": name}
