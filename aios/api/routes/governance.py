"""Human Sovereign emergency-control routes, plus the Constitutional
Amendment Authority's (organ 45) and Constitutional Learning Organ's
(organ 46) HTTP surfaces."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from aios.api.action_guard import CAPABILITY_HEADER, enforce_action_boundary
from aios.api.deps import (
    get_constitution_snapshot_store,
    get_emergency_stop,
    get_governance_amendment_store,
    require_privileged_operator,
)
from aios.application.governance import EmergencyStopController, EmergencyStopError
from aios.application.governance.adversarial_simulations import (
    run_adversarial_simulations,
)
from aios.application.governance.amendment_authority import (
    AmendmentError,
    activate_amendment,
    critique_amendment,
    propose_amendment,
    reject_amendment,
    ratify_amendment,
    rollback_amendment,
    simulate_amendment,
)
from aios.application.governance.constitutional_learning import (
    ConstitutionalLearningError,
    lesson_to_amendment_proposal,
    propose_lesson,
    require_all_simulations_pass,
)
from aios.domain.capabilities.proof import ConsumedCapabilityProof
from aios.domain.governance import EmergencyStopRequest
from aios.domain.governance.constitution import build_constitution_snapshot
from aios.domain.governance.learning import (
    ADVERSARIAL_SIMULATION_CHECKS,
    GovernanceEventClass,
)
from aios.domain.identity.models import Principal
from aios.infrastructure.governance.constitution_snapshot_store import (
    ConstitutionSnapshotStore,
)
from aios.infrastructure.governance.sqlite_store import GovernanceAmendmentStore


router = APIRouter(dependencies=[Depends(enforce_action_boundary)])


class EmergencyStopEngageRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000)


def _state_payload(controller: EmergencyStopController) -> dict[str, Any]:
    state = controller.state()
    return {
        "engaged": state.engaged,
        "generation": state.generation,
        "operatorId": state.operator_id,
        "authenticationEventId": state.authentication_event_id,
        "reason": state.reason,
        "actions": state.actions,
        "failure": state.failure,
        "engagedAt": state.engaged_at,
        "clearedAt": state.cleared_at,
    }


@router.get("/api/v1/governance/emergency-stop")
def emergency_stop_state(
    controller: EmergencyStopController = Depends(get_emergency_stop),
) -> dict[str, Any]:
    return _state_payload(controller)


@router.post("/api/v1/governance/emergency-stop/engage")
def engage_emergency_stop(
    req: EmergencyStopEngageRequest,
    principal: Principal = Depends(require_privileged_operator),
    controller: EmergencyStopController = Depends(get_emergency_stop),
) -> dict[str, Any]:
    try:
        state = controller.engage(
            EmergencyStopRequest(
                operator_id=principal.principal_id,
                authentication_event_id=principal.authentication_event_id,
                reason=req.reason,
            )
        )
    except EmergencyStopError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _state_payload(controller) | {"engaged": state.engaged}


@router.post("/api/v1/governance/emergency-stop/clear")
def clear_emergency_stop(
    request: Request,
    principal: Principal = Depends(require_privileged_operator),
    controller: EmergencyStopController = Depends(get_emergency_stop),
) -> dict[str, Any]:
    token = request.headers.get(CAPABILITY_HEADER, "")
    try:
        state = controller.clear(
            operator_id=principal.principal_id,
            authentication_event_id=principal.authentication_event_id,
            session_id=principal.session_id,
            clear_capability=token,
        )
    except EmergencyStopError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _state_payload(controller) | {"engaged": state.engaged}


# --------------------------------------------------------------------------- #
# Constitutional Amendment Authority (organ 45)
#
# Models/humans/workers may propose, critique, and simulate through this
# surface -- none of that touches the active constitution (amendment_
# authority.py's own docstring). Only ratify/activate actually move a
# proposal toward changing the live constitution, and both are YELLOW-tier
# routes requiring a privileged operator session plus a real, exact,
# server-consumed capability -- the same two-phase issue/confirm mechanism
# every other YELLOW route in this codebase already uses (organ 45 does not
# invent new capability-issuance semantics, it reuses the existing one).
#
# `rollback_amendment()` is now wired via `ConstitutionSnapshotStore` (organ
# 45): every activation persists its new snapshot and advances a per-
# constitution "current" pointer, so a later rollback can look up "the
# exact predecessor" of a real, previously-activated chain instead of one
# rebuilt fresh (and never itself persisted) on every call.
# --------------------------------------------------------------------------- #


class ProposeAmendmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(min_length=1, max_length=200)
    target_articles: tuple[str, ...] = Field(min_length=1)
    proposed_diff: str = Field(min_length=1)
    motivation: str = Field(min_length=1)
    migration_plan: str = Field(min_length=1)
    rollback_plan: str = Field(min_length=1)
    incident_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    threat_model: tuple[str, ...] = ()
    expected_benefits: tuple[str, ...] = ()
    new_risks: tuple[str, ...] = ()


class CritiqueAmendmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    critique_text: str = Field(min_length=1)


class SimulateAmendmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulation_note: str = Field(min_length=1)


class RejectAmendmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1)


def _get_current_proposal_or_404(store: GovernanceAmendmentStore, proposal_id: str):
    current = store.get_current_proposal(proposal_id)
    if current is None:
        raise HTTPException(status_code=404, detail="no such amendment proposal")
    return current


@router.post("/api/v1/governance/amendments/propose")
def propose_amendment_route(
    body: ProposeAmendmentRequest,
    principal: Principal = Depends(require_privileged_operator),
    store: GovernanceAmendmentStore = Depends(get_governance_amendment_store),
) -> dict[str, Any]:
    """Client-supplied ``proposed_by``/``proposer_type`` are never trusted for
    an HTTP-originated proposal -- both are derived from the real
    authenticated principal, exactly like every other write route in this
    file."""
    proposal = propose_amendment(
        proposal_id=body.proposal_id,
        target_articles=body.target_articles,
        proposed_diff=body.proposed_diff,
        motivation=body.motivation,
        migration_plan=body.migration_plan,
        rollback_plan=body.rollback_plan,
        proposed_by=principal.principal_id,
        proposer_type="human",
        incident_refs=body.incident_refs,
        evidence_refs=body.evidence_refs,
        threat_model=body.threat_model,
        expected_benefits=body.expected_benefits,
        new_risks=body.new_risks,
    )
    store.save_proposal(proposal)
    return proposal.as_dict()


@router.get("/api/v1/governance/amendments/{proposal_id}")
def get_amendment_route(
    proposal_id: str,
    store: GovernanceAmendmentStore = Depends(get_governance_amendment_store),
) -> dict[str, Any]:
    return _get_current_proposal_or_404(store, proposal_id).as_dict()


@router.get("/api/v1/governance/amendments/{proposal_id}/history")
def get_amendment_history_route(
    proposal_id: str,
    store: GovernanceAmendmentStore = Depends(get_governance_amendment_store),
) -> dict[str, Any]:
    history = store.get_proposal_history(proposal_id)
    return {"items": [p.as_dict() for p in history]}


@router.post("/api/v1/governance/amendments/{proposal_id}/critique")
def critique_amendment_route(
    proposal_id: str,
    body: CritiqueAmendmentRequest,
    principal: Principal = Depends(require_privileged_operator),
    store: GovernanceAmendmentStore = Depends(get_governance_amendment_store),
) -> dict[str, Any]:
    current = _get_current_proposal_or_404(store, proposal_id)
    try:
        updated = critique_amendment(current, body.critique_text)
    except AmendmentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    store.save_proposal(updated)
    return updated.as_dict()


@router.post("/api/v1/governance/amendments/{proposal_id}/simulate")
def simulate_amendment_route(
    proposal_id: str,
    body: SimulateAmendmentRequest,
    principal: Principal = Depends(require_privileged_operator),
    store: GovernanceAmendmentStore = Depends(get_governance_amendment_store),
) -> dict[str, Any]:
    current = _get_current_proposal_or_404(store, proposal_id)
    try:
        updated = simulate_amendment(current, body.simulation_note)
    except AmendmentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    store.save_proposal(updated)
    return updated.as_dict()


@router.post("/api/v1/governance/amendments/{proposal_id}/reject")
def reject_amendment_route(
    proposal_id: str,
    body: RejectAmendmentRequest,
    principal: Principal = Depends(require_privileged_operator),
    store: GovernanceAmendmentStore = Depends(get_governance_amendment_store),
) -> dict[str, Any]:
    current = _get_current_proposal_or_404(store, proposal_id)
    try:
        updated = reject_amendment(current, body.reason)
    except AmendmentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    store.save_proposal(updated)
    return updated.as_dict()


@router.post("/api/v1/governance/amendments/{proposal_id}/ratify")
def ratify_amendment_route(
    proposal_id: str,
    request: Request,
    principal: Principal = Depends(require_privileged_operator),
    store: GovernanceAmendmentStore = Depends(get_governance_amendment_store),
) -> dict[str, Any]:
    """The only step that can move a proposal toward activation -- refuses
    without a real, exact, server-consumed capability, mirroring
    `activate_skill_route`'s established pattern exactly."""
    proof = getattr(request.state, "consumed_capability_proof", None)
    if proof is None or not isinstance(proof, ConsumedCapabilityProof):
        raise HTTPException(
            status_code=403,
            detail="ratification requires an exact server-consumed capability proof",
        )
    current = _get_current_proposal_or_404(store, proposal_id)
    try:
        updated = ratify_amendment(
            current, capability_proof=proof, operator_id=principal.principal_id
        )
    except AmendmentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    store.save_proposal(updated)
    return updated.as_dict()


def _current_or_baseline_snapshot(
    snapshot_store: ConstitutionSnapshotStore, *, ratified_by_operator_id: str
):
    """The real current snapshot for this operator's constitution chain, or
    -- the very first time this machine ever activates an amendment for
    them -- a freshly built version-1 baseline, persisted immediately so it
    becomes real chain history rather than a value computed and discarded."""
    constitution_id = f"constitution:{ratified_by_operator_id}"
    current = snapshot_store.get_current(constitution_id)
    if current is not None:
        return current
    baseline = build_constitution_snapshot(
        ratified_by_operator_id=ratified_by_operator_id
    )
    snapshot_store.save(baseline)
    return baseline


@router.post("/api/v1/governance/amendments/{proposal_id}/activate")
def activate_amendment_route(
    proposal_id: str,
    principal: Principal = Depends(require_privileged_operator),
    store: GovernanceAmendmentStore = Depends(get_governance_amendment_store),
    snapshot_store: ConstitutionSnapshotStore = Depends(get_constitution_snapshot_store),
    emergency_stop: EmergencyStopController = Depends(get_emergency_stop),
) -> dict[str, Any]:
    """Only a ratified proposal may activate -- `ratify_amendment` is the
    real gate; this step chains the next constitution version the same way
    every other version bump does (Slice 26), against the real durably-
    persisted current snapshot (organ 45) rather than a fresh one rebuilt
    and discarded every call."""
    current = _get_current_proposal_or_404(store, proposal_id)
    if current.ratified_by_operator_id is None:
        raise HTTPException(
            status_code=409, detail="proposal has not been ratified"
        )
    previous_snapshot = _current_or_baseline_snapshot(
        snapshot_store, ratified_by_operator_id=current.ratified_by_operator_id
    )
    try:
        updated, new_snapshot = activate_amendment(
            current,
            previous_snapshot=previous_snapshot,
            emergency_stop=emergency_stop,
        )
    except (AmendmentError, EmergencyStopError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    store.save_proposal(updated)
    snapshot_store.save(new_snapshot)
    return {
        "proposal": updated.as_dict(),
        "newConstitutionDigest": new_snapshot.snapshot_digest,
    }


@router.post("/api/v1/governance/amendments/{proposal_id}/rollback")
def rollback_amendment_route(
    proposal_id: str,
    principal: Principal = Depends(require_privileged_operator),
    store: GovernanceAmendmentStore = Depends(get_governance_amendment_store),
    snapshot_store: ConstitutionSnapshotStore = Depends(get_constitution_snapshot_store),
    emergency_stop: EmergencyStopController = Depends(get_emergency_stop),
) -> dict[str, Any]:
    """Revert an activated proposal's constitution version to its exact
    predecessor (organ 45) -- the real durable chain `activate_amendment_
    route()` now maintains, not an ephemeral pair of snapshots the caller
    happened to hold in memory.

    Honest, named limitation: this reverts the operator's *current* live
    constitution to its immediate predecessor. `ConstitutionalAmendmentProposalV1`
    does not itself record which snapshot digest its own activation produced
    (a real, separate schema gap, not invented here), so if another proposal
    has activated since this one, rolling back "this" proposal_id still only
    ever undoes the single most recent step, not specifically this
    proposal's own change. `rollback_amendment()`'s own pre-existing
    contract already has this shape -- this route does not weaken it
    further, but does not silently claim more precision than it has either.
    """
    try:
        emergency_stop.assert_operational()
    except EmergencyStopError as exc:
        raise HTTPException(
            status_code=503, detail=f"Emergency stop engaged: {exc}"
        ) from exc

    current_proposal = _get_current_proposal_or_404(store, proposal_id)
    if current_proposal.ratified_by_operator_id is None:
        raise HTTPException(
            status_code=409, detail="proposal has not been ratified"
        )
    constitution_id = f"constitution:{current_proposal.ratified_by_operator_id}"
    current_snapshot = snapshot_store.get_current(constitution_id)
    if current_snapshot is None:
        raise HTTPException(
            status_code=409,
            detail="no constitution snapshot history exists to roll back",
        )
    if current_snapshot.previous_snapshot_digest is None:
        raise HTTPException(
            status_code=409,
            detail="current constitution snapshot has no predecessor to roll back to",
        )
    previous_snapshot = snapshot_store.get_by_digest(
        current_snapshot.previous_snapshot_digest
    )
    if previous_snapshot is None:
        raise HTTPException(
            status_code=409,
            detail="predecessor snapshot is missing from durable history",
        )

    try:
        updated, reverted_snapshot = rollback_amendment(
            current_proposal,
            current_snapshot=current_snapshot,
            previous_snapshot=previous_snapshot,
        )
    except AmendmentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    store.save_proposal(updated)
    snapshot_store.save(reverted_snapshot)
    return {
        "proposal": updated.as_dict(),
        "revertedConstitutionDigest": reverted_snapshot.snapshot_digest,
    }


# --------------------------------------------------------------------------- #
# Constitutional Learning Organ (organ 46)
#
# A GovernanceLessonV1 can produce a real Slice 37 amendment *proposal*,
# never further -- ratification/activation still flow through the routes
# above, unchanged. `check-simulations` looks the proposal up by id and
# runs all 9 named adversarial simulations against it for real
# (`run_adversarial_simulations`) -- a caller can no longer assert a
# passing result it never earned; `require_all_simulations_pass` still
# refuses on any missing or failed check exactly like before.
# --------------------------------------------------------------------------- #


class ProposeLessonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson_id: str = Field(min_length=1, max_length=200)
    problem_class: GovernanceEventClass
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    observed_harm: str = Field(min_length=1)
    current_rule: str = Field(min_length=1)
    proposed_improvement: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class DraftAmendmentFromLessonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(min_length=1, max_length=200)
    target_articles: tuple[str, ...] = Field(min_length=1)
    proposed_diff: str = Field(min_length=1)
    migration_plan: str = Field(min_length=1)
    rollback_plan: str = Field(min_length=1)


class CheckSimulationsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(min_length=1, max_length=200)


@router.post("/api/v1/governance/lessons/propose")
def propose_lesson_route(
    body: ProposeLessonRequest,
    principal: Principal = Depends(require_privileged_operator),
    store: GovernanceAmendmentStore = Depends(get_governance_amendment_store),
) -> dict[str, Any]:
    lesson = propose_lesson(
        lesson_id=body.lesson_id,
        problem_class=body.problem_class,
        evidence_refs=body.evidence_refs,
        observed_harm=body.observed_harm,
        current_rule=body.current_rule,
        proposed_improvement=body.proposed_improvement,
        confidence=body.confidence,
    )
    store.save_lesson(lesson)
    return lesson.as_dict()


@router.get("/api/v1/governance/lessons/{lesson_id}")
def get_lesson_route(
    lesson_id: str,
    store: GovernanceAmendmentStore = Depends(get_governance_amendment_store),
) -> dict[str, Any]:
    lesson = store.get_current_lesson(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="no such governance lesson")
    return lesson.as_dict()


@router.get("/api/v1/governance/lessons/{lesson_id}/history")
def get_lesson_history_route(
    lesson_id: str,
    store: GovernanceAmendmentStore = Depends(get_governance_amendment_store),
) -> dict[str, Any]:
    history = store.get_lesson_history(lesson_id)
    return {"items": [lesson.as_dict() for lesson in history]}


@router.post("/api/v1/governance/lessons/{lesson_id}/draft-amendment")
def draft_amendment_from_lesson_route(
    lesson_id: str,
    body: DraftAmendmentFromLessonRequest,
    principal: Principal = Depends(require_privileged_operator),
    store: GovernanceAmendmentStore = Depends(get_governance_amendment_store),
) -> dict[str, Any]:
    """The resulting proposal is always `proposer_type="model"` -- a lesson
    is machine-derived even when a human later ratifies what it produced,
    matching `lesson_to_amendment_proposal`'s own contract exactly (its
    default `proposed_by` is never overridden here)."""
    lesson = store.get_current_lesson(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="no such governance lesson")
    try:
        updated_lesson, proposal = lesson_to_amendment_proposal(
            lesson,
            proposal_id=body.proposal_id,
            target_articles=body.target_articles,
            proposed_diff=body.proposed_diff,
            migration_plan=body.migration_plan,
            rollback_plan=body.rollback_plan,
        )
    except ConstitutionalLearningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    store.save_lesson(updated_lesson)
    store.save_proposal(proposal)
    return {"lesson": updated_lesson.as_dict(), "proposal": proposal.as_dict()}


@router.post("/api/v1/governance/lessons/check-simulations")
def check_lesson_simulations_route(
    body: CheckSimulationsRequest,
    principal: Principal = Depends(require_privileged_operator),
    store: GovernanceAmendmentStore = Depends(get_governance_amendment_store),
) -> dict[str, Any]:
    proposal = _get_current_proposal_or_404(store, body.proposal_id)
    results = run_adversarial_simulations(proposal)
    results_payload = [r.model_dump(mode="json") for r in results]
    try:
        require_all_simulations_pass(results)
    except ConstitutionalLearningError:
        # Recompute the reason from the typed results already in hand,
        # rather than relaying the exception's own message text into an
        # HTTP response (CodeQL: py/stack-trace-exposure) -- this mirrors
        # require_all_simulations_pass's own logic exactly, just without
        # turning an exception into response body content.
        seen = {r.check_name for r in results}
        missing = [name for name in ADVERSARIAL_SIMULATION_CHECKS if name not in seen]
        if missing:
            reason = f"missing required adversarial simulations: {missing}"
        else:
            failed = [r.check_name for r in results if not r.passed]
            reason = f"failed adversarial simulations: {failed}"
        return {"ready": False, "reason": reason, "results": results_payload}
    return {"ready": True, "reason": "", "results": results_payload}


__all__ = ["router"]
