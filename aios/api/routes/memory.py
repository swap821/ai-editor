"""Memory, facts, alignment-evaluation, and knowledge (RAG) routes.

Extracted from ``aios/api/main.py`` (monolith split, 2026-07-06) into an
APIRouter module. Dependency providers come from ``aios.api.deps`` — the SAME
function objects ``main`` re-exports, so ``app.dependency_overrides`` keyed on
either import path keep working (no council-style local-proxy trap).

One sibling route deliberately stays in ``main.py`` because it reads process
singletons owned there: ``POST /api/v1/memory/compact`` (the compactor's
working/semantic/episodic singleton cluster). ``POST /api/v1/conversation/
session`` moved HERE in tranche 2, with a module-local stateless
``EpisodicMemory()`` over the same DB.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from aios.api.deps import (
    _session_id_from_request,
    get_alignment_evaluation_store,
    get_conversation_state_store,
    get_memory_authority,
    get_memory_consolidator,
    get_semantic_facts,
    require_privileged_operator,
)
from aios.core.alignment import (
    apply_user_corrections,
    frame_from_state,
    validate_user_corrections,
)
from aios.logging_config import get_logger
from aios.memory.alignment_evaluation import AlignmentEvaluationStore
from aios.memory.consolidation import MemoryConsolidator
from aios.memory.conversation import ConversationStateStore
from aios.memory.facts import SemanticFacts
from aios.domain.identity.models import Principal
from aios.domain.memory import MemoryRecallContext
from aios.api.action_guard import enforce_action_boundary

logger = get_logger(__name__)

router = APIRouter(dependencies=[Depends(enforce_action_boundary)])


def _require_cookie_session(request: Request) -> str:
    """Resolve a stateful session only from the validated httpOnly cookie."""
    session_id = _session_id_from_request(request, None)
    if not session_id:
        raise HTTPException(
            status_code=422, detail="a valid session cookie is required"
        )
    return session_id


def _authority_owns(authority: Any, name: str, candidate: Any) -> bool:
    owns_store = getattr(authority, "owns_store", None)
    return bool(callable(owns_store) and owns_store(name, candidate))


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class MemorySearchRequest(BaseModel):
    """Body for ``/memory/search``."""

    query: str = Field(..., description="Natural-language search query.")
    top_k: int = Field(3, ge=1, le=50, description="Number of results to return.")


class FactPromotionRequest(BaseModel):
    """Body for human-approved contradiction-aware fact promotion."""

    subject: str
    predicate: str
    object: str
    # Deprecated compatibility field. Authority comes from the session-bound
    # Human Sovereign principal, never from request JSON.
    approved_by: str = Field("", alias="approvedBy")

    model_config = {"populate_by_name": True}


class FactProposalResolveRequest(BaseModel):
    """Body for resolving one auto-extracted fact proposal (human-gated)."""

    # Deprecated compatibility field. Authority comes from the session-bound
    # Human Sovereign principal, never from request JSON.
    resolved_by: str = Field("", alias="resolvedBy")

    model_config = {"populate_by_name": True}


class ConversationSessionRequest(BaseModel):
    """Request restoration of one durable conversation session."""

    session_id: str = Field(..., min_length=1, alias="sessionId")
    limit: int = Field(50, ge=1, le=100)

    model_config = {"populate_by_name": True}


class ConversationCorrectionRequest(BaseModel):
    """User-authored corrections to the current advisory interpretation."""

    session_id: str = Field(..., min_length=1, alias="sessionId")
    corrections: dict[str, Any]

    model_config = {"populate_by_name": True}


class AlignmentFeedbackRequest(BaseModel):
    """Explicit human evaluation of the latest visible understanding frame."""

    session_id: str = Field(..., min_length=1, alias="sessionId")
    observation_id: Optional[int] = Field(None, ge=1, alias="observationId")
    outcome: str
    issues: list[str] = Field(default_factory=list)
    notes: str = Field("", max_length=2000)

    model_config = {"populate_by_name": True}


# --------------------------------------------------------------------------- #
# Memory recall + consolidation
# --------------------------------------------------------------------------- #
@router.post("/api/v1/memory/search")
def memory_search(
    req: MemorySearchRequest,
    authority=Depends(get_memory_authority),
) -> dict[str, Any]:
    """Route semantic recall through the canonical memory authority."""
    from aios.api.main import get_cortex_bus

    bus = get_cortex_bus()
    results = authority.recall(
        req.query,
        MemoryRecallContext(limit=req.top_k, include_unverified=True),
    )

    if bus and results:
        from aios.core.events import (
            CanonicalEvent,
            CanonicalEventType,
            EventPhase,
            TrustLevel,
        )

        for r in results:
            trust = authority.trust_level(r)
            canonical = CanonicalEvent(
                event_type=CanonicalEventType.MEMORY_RECALLED.value,
                phase=EventPhase.WONDER.value,
                status="success",
                trust=trust,
                source="aios.api.routes.memory",
                session_id="system",
                payload={
                    "id": r.external_id or r.record_id or r.content_reference,
                    "text": r.text,
                    "score": r.score,
                },
            )
            event_id = r.external_id or r.record_id or r.content_reference
            bus.append(canonical)
            if r.memory_type == "workflow" and authority.is_trusted(r):
                canonical_workflow = CanonicalEvent(
                    event_type=CanonicalEventType.MEMORY_TRUSTED_WORKFLOW_APPLIED.value,
                    phase=EventPhase.WONDER.value,
                    status="success",
                    trust=TrustLevel.VERIFIED.value,
                    source="aios.api.routes.memory",
                    session_id="system",
                    payload={"workflowId": str(event_id), "query": req.query},
                )
                bus.append(canonical_workflow)

    return {
        "query": req.query,
        "results": [
            {
                "id": r.external_id or r.record_id or r.content_reference,
                "text": r.text,
                "score": r.score,
                "bm25": r.bm25,
                "faiss": r.faiss,
                "recency": r.recency,
                "memory_type": r.memory_type,
                "verification_status": r.verification_status,
            }
            for r in results
        ],
    }


@router.post("/api/v1/memory/consolidate")
def memory_consolidate(
    _principal: Principal = Depends(require_privileged_operator),
    consolidator: MemoryConsolidator = Depends(get_memory_consolidator),
    authority=Depends(get_memory_authority),
) -> dict[str, Any]:
    """Idempotently index current verified lessons and active approved facts."""
    if _authority_owns(authority, "consolidation", consolidator):
        return authority.consolidate()
    return consolidator.run()


# --------------------------------------------------------------------------- #
# Conversation session restore + alignment corrections + diagnostic evaluation
# --------------------------------------------------------------------------- #
@router.post("/api/v1/conversation/session")
def restore_conversation_session(
    req: ConversationSessionRequest,
    request: Request,
    state: ConversationStateStore = Depends(get_conversation_state_store),
    authority=Depends(get_memory_authority),
) -> dict[str, Any]:
    """Restore recent dialogue and the latest unverified alignment frame."""
    session_id = _require_cookie_session(request)
    rows = authority.recent_episodic(session_id, req.limit)
    messages = [
        {"role": str(row["role"]), "content": [{"text": str(row["content"])}]}
        for row in rows
        if row["role"] in {"user", "assistant"}
    ]
    return {
        "alignment": state.get(session_id),
        "activeCorrection": state.active_correction(session_id),
        "correctionHistory": state.correction_history(session_id),
        "messages": messages,
    }


@router.post("/api/v1/conversation/correction")
def correct_conversation_alignment(
    req: ConversationCorrectionRequest,
    request: Request,
    state: ConversationStateStore = Depends(get_conversation_state_store),
    evaluation: AlignmentEvaluationStore = Depends(get_alignment_evaluation_store),
) -> dict[str, Any]:
    """Apply user-authored interpretation overrides; never grant authority."""
    session_id = _require_cookie_session(request)
    current_payload = state.get(session_id)
    if current_payload is None:
        raise HTTPException(
            status_code=404, detail="no alignment frame exists for session"
        )
    try:
        incoming = validate_user_corrections(req.corrections)
        active = state.active_correction(session_id)
        merged = dict(active["corrections"]) if active is not None else {}
        merged.update(incoming)
        current = frame_from_state(current_payload)
        corrected = apply_user_corrections(current, merged, revision=1)
        corrected_payload = corrected.as_dict()
        evaluation_payload = current_payload.get("evaluation")
        if isinstance(evaluation_payload, dict):
            corrected_payload["evaluation"] = evaluation_payload
        revision, persisted = state.record_correction(
            session_id,
            before_frame=current_payload,
            after_frame=corrected_payload,
            corrections=merged,
            corrected_fields=sorted(merged),
            expected_revision=(int(active["revision"]) if active is not None else None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        observation_id = (
            evaluation_payload.get("observation_id")
            if isinstance(evaluation_payload, dict)
            else None
        )
        evaluation.mark_latest_corrected(
            session_id,
            sorted(merged),
            observation_id=int(observation_id) if observation_id else None,
        )
    except Exception as exc:  # noqa: BLE001 - diagnostic evidence must never break correction
        logger.warning(
            "Failed to mark alignment observation as corrected", exc_info=exc
        )
    return {
        "alignment": persisted,
        "activeCorrection": {
            "revision": revision,
            "corrections": merged,
            "fields": sorted(merged),
        },
        "correctionHistory": state.correction_history(session_id),
    }


@router.get("/api/v1/alignment/evaluation")
def alignment_evaluation_summary(
    evaluation: AlignmentEvaluationStore = Depends(get_alignment_evaluation_store),
) -> dict[str, Any]:
    """Return diagnostic alignment evidence without changing policy."""
    return evaluation.summary()


@router.post("/api/v1/alignment/feedback")
def record_alignment_feedback(
    req: AlignmentFeedbackRequest,
    request: Request,
    evaluation: AlignmentEvaluationStore = Depends(get_alignment_evaluation_store),
) -> dict[str, Any]:
    """Record explicit operator feedback on the latest session observation."""
    session_id = _require_cookie_session(request)
    try:
        observation_id = evaluation.record_feedback(
            session_id,
            outcome=req.outcome,
            issues=req.issues,
            notes=req.notes,
            observation_id=req.observation_id,
        )
    except ValueError as exc:
        status = 404 if "no alignment observation" in str(exc) else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return {
        "observationId": observation_id,
        "automaticPolicyUpdates": False,
    }


@router.post("/api/v1/conversation/correction/clear")
def clear_conversation_alignment_correction(
    req: ConversationSessionRequest,
    request: Request,
    state: ConversationStateStore = Depends(get_conversation_state_store),
) -> dict[str, Any]:
    """Clear active user corrections and restore the superseded base frame."""
    session_id = _require_cookie_session(request)
    try:
        restored = state.clear_correction(session_id)
        alignment = frame_from_state(restored).as_dict()
        evaluation_payload = restored.get("evaluation")
        if isinstance(evaluation_payload, dict):
            alignment["evaluation"] = evaluation_payload
        state.save(session_id, alignment)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "alignment": alignment,
        "activeCorrection": None,
        "correctionHistory": state.correction_history(session_id),
    }


# --------------------------------------------------------------------------- #
# Human-gated fact proposals + promotion + graph
# --------------------------------------------------------------------------- #
@router.get("/api/v1/memory/facts/pending")
def memory_facts_pending(
    facts: SemanticFacts = Depends(get_semantic_facts),
    authority=Depends(get_memory_authority),
) -> dict[str, Any]:
    """Auto-extracted fact proposals awaiting human review.

    Proposals are quarantined in their own table — no recall path reads them —
    so this queue is the ONLY window through which they can become knowledge.
    """
    pending_proposals = (
        authority.facts_pending_proposals()
        if _authority_owns(authority, "facts", facts)
        else facts.pending_proposals()
    )
    proposals = [
        {
            "id": int(row["id"]),
            "subject": row["subject"],
            "predicate": row["predicate"],
            "object": row["object"],
            "source": row["source"],
            "timestamp": row["timestamp"],
        }
        for row in pending_proposals
    ]
    return {"proposals": proposals}


@router.post("/api/v1/memory/facts/pending/{proposal_id}/approve")
def approve_fact_proposal(
    proposal_id: int,
    req: FactProposalResolveRequest,
    _principal: Principal = Depends(require_privileged_operator),
    facts: SemanticFacts = Depends(get_semantic_facts),
    authority=Depends(get_memory_authority),
) -> dict[str, Any]:
    """Human approval promotes a proposal through the contradiction check."""
    result = (
        authority.facts_approve_proposal(
            proposal_id, approved_by=_principal.principal_id
        )
        if _authority_owns(authority, "facts", facts)
        else facts.approve_proposal(proposal_id, approved_by=_principal.principal_id)
    )
    if result.reason == "contradiction":
        raise HTTPException(
            status_code=409,
            detail={
                "reason": result.reason,
                "conflictId": result.conflict_id,
                "conflictObject": result.conflict_object,
            },
        )
    if result.reason == "not pending":
        raise HTTPException(status_code=404, detail=result.reason)
    if not result.committed:
        raise HTTPException(status_code=422, detail=result.reason)
    return asdict(result)


@router.post("/api/v1/memory/facts/pending/{proposal_id}/reject")
def reject_fact_proposal(
    proposal_id: int,
    req: FactProposalResolveRequest,
    _principal: Principal = Depends(require_privileged_operator),
    facts: SemanticFacts = Depends(get_semantic_facts),
    authority=Depends(get_memory_authority),
) -> dict[str, Any]:
    """Human rejection resolves a proposal without it ever touching recall."""
    rejected = (
        authority.facts_reject_proposal(
            proposal_id, rejected_by=_principal.principal_id
        )
        if _authority_owns(authority, "facts", facts)
        else facts.reject_proposal(proposal_id, rejected_by=_principal.principal_id)
    )
    if not rejected:
        raise HTTPException(status_code=404, detail="not pending")
    return {"rejected": True, "proposalId": proposal_id}


@router.post("/api/v1/memory/facts")
def promote_fact(
    req: FactPromotionRequest,
    _principal: Principal = Depends(require_privileged_operator),
    consolidator: MemoryConsolidator = Depends(get_memory_consolidator),
    authority=Depends(get_memory_authority),
) -> dict[str, Any]:
    """Promote one human-approved fact, refusing unresolved contradictions."""
    result = (
        authority.promote_fact(
            req.subject, req.predicate, req.object, approved_by=_principal.principal_id
        )
        if _authority_owns(authority, "consolidation", consolidator)
        else consolidator.promote_fact(
            req.subject, req.predicate, req.object, approved_by=_principal.principal_id
        )
    )
    if result.reason == "contradiction":
        raise HTTPException(
            status_code=409,
            detail={
                "reason": result.reason,
                "conflictId": result.conflict_id,
                "conflictObject": result.conflict_object,
            },
        )
    if not result.committed:
        raise HTTPException(status_code=422, detail=result.reason)
    return asdict(result)


@router.post("/api/v1/memory/facts/reconcile")
def reconcile_fact(
    req: FactPromotionRequest,
    _principal: Principal = Depends(require_privileged_operator),
    consolidator: MemoryConsolidator = Depends(get_memory_consolidator),
    authority=Depends(get_memory_authority),
) -> dict[str, Any]:
    """Human-approved replacement of a contradictory fact and its vector."""
    result = (
        authority.reconcile_fact(
            req.subject, req.predicate, req.object, approved_by=_principal.principal_id
        )
        if _authority_owns(authority, "consolidation", consolidator)
        else consolidator.reconcile_fact(
            req.subject, req.predicate, req.object, approved_by=_principal.principal_id
        )
    )
    if not result.committed:
        raise HTTPException(status_code=422, detail=result.reason)
    return asdict(result)


@router.get("/api/v1/memory/facts/graph")
def memory_facts_graph(
    start: str,
    depth: int = 2,
    facts: SemanticFacts = Depends(get_semantic_facts),
    authority=Depends(get_memory_authority),
) -> dict[str, Any]:
    """Multi-hop fact-graph traversal from *start* — the transitive reasoning
    single-hop ``facts_for`` cannot do (G1). Read-only: returns the active-fact
    edges reachable within *depth* hops, each with its hop ``depth`` and a
    ``path``, so the planner (or the lattice's fact view) can reason over
    transitive knowledge. ``depth`` is clamped to [1, 4] in ``traverse``."""
    if not start.strip():
        raise HTTPException(status_code=422, detail="start is required")
    rows = (
        authority.facts_traverse(start, max_depth=depth)
        if _authority_owns(authority, "facts", facts)
        else facts.traverse(start, max_depth=depth)
    )
    edges = [
        {
            "subject": r["subject"],
            "predicate": r["predicate"],
            "object": r["object"],
            "depth": r["depth"],
            "path": r["path"],
        }
        for r in rows
    ]
    return {"start": start.strip(), "depth": max(1, min(int(depth), 4)), "edges": edges}


# --------------------------------------------------------------------------- #
# Knowledge graph query + (RAG document) ingestion
# --------------------------------------------------------------------------- #
@router.get("/api/v1/knowledge/query")
def knowledge_query(
    entity: str,
    max_depth: int = 3,
    min_confidence: float = 0.3,
    facts: SemanticFacts = Depends(get_semantic_facts),
    authority=Depends(get_memory_authority),
) -> dict[str, Any]:
    """Query the knowledge graph with confidence-weighted traversal.

    Read-only diagnostic/observability endpoint. Returns the weighted
    traversal and composed inference from the starting entity.
    """
    if not entity.strip():
        raise HTTPException(status_code=422, detail="entity is required")
    edges = (
        authority.facts_traverse_weighted(
            entity,
            max_depth=max_depth,
            min_path_confidence=min_confidence,
        )
        if _authority_owns(authority, "facts", facts)
        else facts.traverse_weighted(
            entity, max_depth=max_depth, min_path_confidence=min_confidence
        )
    )
    from aios.core.inference import infer

    result = infer(entity, edges, min_confidence=min_confidence)
    return {
        "entity": entity.strip(),
        "edges": [
            {
                "subject": e.subject,
                "predicate": e.predicate,
                "object": e.object,
                "depth": e.depth,
                "confidence": round(e.confidence, 4),
                "path_confidence": round(e.path_confidence, 4),
            }
            for e in edges
        ],
        "inference": {
            "answer": result.answer,
            "confidence": round(result.combined_confidence, 4),
            "chain_length": len(result.chain),
            "reached_horizon": result.reached_horizon,
        }
        if result
        else None,
    }


def get_doc_ingestor():
    """Provide the document ingestion pipeline."""
    from aios.memory.doc_ingest import DocumentIngestor

    return DocumentIngestor()


@router.post("/api/v1/knowledge/ingest")
async def knowledge_ingest(
    file: UploadFile = File(...),
    _principal: Principal = Depends(require_privileged_operator),
    ingestor=Depends(get_doc_ingestor),
) -> dict[str, Any]:
    """Ingest a document for RAG grounding."""
    raw = await file.read()
    mime = file.content_type or "application/octet-stream"
    filename = file.filename or "unnamed"
    try:
        return ingestor.ingest(filename, raw, mime)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/v1/knowledge/sources")
def knowledge_sources(
    ingestor=Depends(get_doc_ingestor),
) -> dict[str, Any]:
    """List all ingested knowledge sources."""
    return {"sources": ingestor.list_sources()}


@router.delete("/api/v1/knowledge/sources/{source_id}")
def knowledge_delete_source(
    source_id: int,
    _principal: Principal = Depends(require_privileged_operator),
    ingestor=Depends(get_doc_ingestor),
) -> dict[str, Any]:
    """Delete a knowledge source and its chunks."""
    if not ingestor.delete_source(source_id):
        raise HTTPException(status_code=404, detail="Source not found")
    return {"deleted": True}
