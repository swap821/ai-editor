"""System/observability routes: liveness, metrics, intent preview, onboarding,
security classification, and audit-chain verification.

Extracted from ``aios/api/main.py`` (monolith split tranche 2, 2026-07-06).
Dependency providers come from ``aios.api.deps`` — the SAME function objects
``main`` re-exports, so ``app.dependency_overrides`` keyed on either import
path keep working.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import asdict
from typing import Any, Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

import aios
from aios import config
from aios.api.deps import get_approval_store, get_autonomy, get_development_tracker
from aios.core.approvals import ApprovalStore
from aios.core.autonomy import AutonomyLedger
from aios.core.metrics import CONTENT_TYPE_LATEST, generate_latest, get_collector
from aios.logging_config import get_logger
from aios.memory.db import get_connection
from aios.memory.development import DevelopmentTracker
from aios.memory.episodic import EpisodicMemory
from aios.security.audit_logger import init_audit_db, verify_chain
from aios.security.gateway import classify

logger = get_logger(__name__)

router = APIRouter()

#: Process-wide metrics collector (get_collector() returns the module singleton
#: from aios.core.metrics, so this is the SAME object main's middleware uses).
_METRICS = get_collector()

#: Stateless DB wrapper over the shared episodic store (same DB as main's
#: ``_EPISODIC``; every call opens a fresh connection).
_EPISODIC = EpisodicMemory()


# --------------------------------------------------------------------------- #
# Request/response models
# --------------------------------------------------------------------------- #
class ClassifyRequest(BaseModel):
    """Body for ``/security/classify``."""

    command: str = Field(..., description="Action payload to classify.")


class IntentPreviewRequest(BaseModel):
    """Body for ``/api/v1/intent/preview`` — a lightweight rule-based prediction
    of what the operator is about to ask, so the UI can hint the dock before the
    turn is even sent. No LLM call; deterministic and cheap."""

    text: str = Field(..., max_length=2000, description="Operator's current draft.")


class IntentPreviewResponse(BaseModel):
    """Predicted intent class for the command dock."""

    intent: str = Field(..., description="chat | code | browse | swarm | command")
    confidence: float = Field(..., ge=0, le=1)
    tool: Optional[str] = Field(None, description="Primary tool if intent is actionable.")


class OnboardingStateResponse(BaseModel):
    """Read-only view of which product milestones the operator has reached."""

    firstDirective: bool
    firstApproval: bool
    firstVerify: bool
    firstCloudRoute: bool
    firstAutonomy: bool


# --------------------------------------------------------------------------- #
# Liveness + metrics
# --------------------------------------------------------------------------- #
@router.get("/health")
def health() -> dict[str, Any]:
    """Liveness probe."""
    return {"status": "ok", "version": aios.__version__}


@router.get("/metrics")
def metrics(
    tracker: DevelopmentTracker = Depends(get_development_tracker),
    approvals: ApprovalStore = Depends(get_approval_store),
    autonomy: AutonomyLedger = Depends(get_autonomy),
) -> Response:
    """Prometheus scrapable operational metrics."""
    _METRICS.update(
        tracker.summary(),
        approvals.grant_count(),
        autonomy.earned_count(),
        audit_db_path=config.AUDIT_DB_PATH,
    )
    return Response(
        content=generate_latest(_METRICS.registry),
        media_type=CONTENT_TYPE_LATEST,
    )


# --------------------------------------------------------------------------- #
# Intent preview
# --------------------------------------------------------------------------- #
def _classify_intent(text: str) -> IntentPreviewResponse:
    """Rule-based intent preview for the command dock."""
    t = text.lower().strip()
    if not t:
        return IntentPreviewResponse(intent="chat", confidence=1.0, tool=None)
    if re.search(r"https?://|^(browse|search|look\s+up)\b", t):
        return IntentPreviewResponse(intent="browse", confidence=0.92, tool="browse")
    if re.search(r"\b(swarm|workers|plan\s+(out|it)|decompose|multi-agent)\b", t):
        return IntentPreviewResponse(intent="swarm", confidence=0.9, tool="swarm")
    if re.match(r"^(run|execute|install|pip|npm|git|python|bash|sh)\b", t):
        return IntentPreviewResponse(intent="command", confidence=0.85, tool="execute")
    if re.match(r"^(write|build|create|make|code|implement|fix|add|generate)\b", t):
        return IntentPreviewResponse(intent="code", confidence=0.9, tool="edit_file")
    return IntentPreviewResponse(intent="chat", confidence=0.8, tool=None)


@router.post("/api/v1/intent/preview")
def intent_preview(req: IntentPreviewRequest) -> IntentPreviewResponse:
    """Return a cheap, deterministic intent preview for the current draft."""
    return _classify_intent(req.text)


# --------------------------------------------------------------------------- #
# Onboarding milestones
# --------------------------------------------------------------------------- #
def _has_any_approval_grant(store: ApprovalStore) -> bool:
    """True if any approval has ever been redeemed (cross-session)."""
    if store.db_path is not None:
        with store._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM approval_grants").fetchone()
            return int(row["n"]) > 0
    with store._lock:
        return any(store._grants.values())


def _has_verified_success() -> bool:
    """True if any development event has outcome verified_success."""
    with get_connection(config.MEMORY_DB_PATH) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM development_events WHERE outcome = ?",
            ("verified_success",),
        ).fetchone()
        return int(row["n"]) > 0


def _has_cloud_route() -> bool:
    """True if a cloud-route audit entry has been recorded."""
    init_audit_db(config.AUDIT_DB_PATH)
    conn = sqlite3.connect(str(config.AUDIT_DB_PATH), timeout=30.0)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM tamper_audit_trail WHERE actor = ?",
            ("cloud-route",),
        ).fetchone()
        return int(row["n"]) > 0
    finally:
        conn.close()


@router.get("/api/v1/onboarding/state")
def onboarding_state(
    approvals: ApprovalStore = Depends(get_approval_store),
    autonomy: AutonomyLedger = Depends(get_autonomy),
) -> OnboardingStateResponse:
    """Return which first-run milestones have been reached."""
    ledger = autonomy.ledger_map()
    return OnboardingStateResponse(
        firstDirective=_EPISODIC.count(None) > 0,
        firstApproval=_has_any_approval_grant(approvals),
        firstVerify=_has_verified_success(),
        firstCloudRoute=_has_cloud_route(),
        firstAutonomy=ledger["summary"]["earned"] > 0,
    )


# --------------------------------------------------------------------------- #
# Security classification + audit-chain verification
# --------------------------------------------------------------------------- #
@router.post("/api/v1/security/classify")
def security_classify(req: ClassifyRequest) -> dict[str, Any]:
    """Deterministic, fail-closed security-zone classification."""
    result = classify(req.command)
    return {
        "zone": result.zone.value,
        "confidence": result.confidence,
        "reason": result.reason,
    }


@router.get("/api/v1/audit/verify")
def audit_verify(from_entry: int = 1, to_entry: Optional[int] = None) -> dict[str, Any]:
    """Verify the tamper-evident audit hash chain over an optional id range."""
    status = verify_chain(from_id=from_entry, to_id=to_entry)
    if not status.valid:
        logger.critical(
            "Audit hash-chain verification failed",
            broken_at=status.broken_at,
            reason=status.reason,
            total_entries=status.total_entries,
        )
        _METRICS.record_audit_verify_failure()
    return asdict(status)
