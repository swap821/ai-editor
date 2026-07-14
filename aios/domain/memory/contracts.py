"""Immutable contracts for evidence-aware memory authority."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class MemoryStatus(StrEnum):
    PROPOSED = "proposed"
    VERIFIED = "verified"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class MemoryRecallContext(BaseModel):
    """Routing hints; they never grant permission or trust."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str | None = None
    session_id: str | None = None
    task_signature: str | None = None
    memory_types: tuple[str, ...] = ()
    limit: int = Field(default=10, ge=1, le=100)
    include_unverified: bool = False


class MemoryRecordProvenance(BaseModel):
    """Lineage required on every durable promoted record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_principal: str = Field(min_length=1)
    source_turn_id: str | None = None
    source_mission_id: str | None = None
    source_action_id: str | None = None
    evidence_ids: tuple[str, ...] = ()
    verification_strength: int = Field(ge=0, le=5)
    operator_approval: str | None = None
    project_id: str | None = None
    policy_version: str = Field(min_length=1)
    confidence_basis: str = Field(min_length=1)
    contradictions: tuple[str, ...] = ()
    supersession_lineage: tuple[str, ...] = ()
    review_after: str | None = None


class MemoryProposal(BaseModel):
    """A quarantined reference to content held by a specialized store."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    proposal_id: str = Field(min_length=1)
    memory_type: str = Field(min_length=1)
    content_reference: str = Field(min_length=1)
    content_digest: str = Field(min_length=1)
    project_id: str | None = None
    source_principal: str = Field(min_length=1)
    source_turn_id: str | None = None
    source_mission_id: str | None = None
    source_action_id: str | None = None
    evidence_ids: tuple[str, ...] = ()
    required_strength: int = Field(default=3, ge=1, le=5)
    policy_version: str = Field(min_length=1)
    confidence_basis: str = Field(min_length=1)
    requires_operator_approval: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    proposed_at: str = Field(default_factory=_utc_now)
    evidence_freshness_seconds: int = Field(default=3600, ge=1, le=604800)


class MemoryPromotionActor(BaseModel):
    """The only actors allowed to promote a memory reference."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_id: str = Field(min_length=1)
    actor_type: Literal["operator", "policy"]
    authentication_event_id: str | None = None
    operator_approval: bool = False


class MemoryRecord(BaseModel):
    """An authoritative, provenance-bound memory reference."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    memory_type: str = Field(min_length=1)
    content_reference: str = Field(min_length=1)
    content_digest: str = Field(min_length=1)
    project_id: str | None = None
    provenance: MemoryRecordProvenance
    status: MemoryStatus = MemoryStatus.VERIFIED
    promoted_at: str = Field(default_factory=_utc_now)


class MemoryVerification(BaseModel):
    """Deterministic verification result consumed by promotion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    proposal_id: str = Field(min_length=1)
    verified: bool
    strength: int = Field(ge=0, le=5)
    evidence_ids: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    evaluated_at: str = Field(default_factory=_utc_now)


class MemoryHit(BaseModel):
    """Typed result from a routed specialized memory adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str | None = None
    external_id: int | str | None = None
    memory_type: str = Field(min_length=1)
    content_reference: str = Field(min_length=1)
    text: str = ""
    score: float = 0.0
    bm25: float = 0.0
    faiss: float = 0.0
    recency: float = 0.0
    verification_status: str = "unverified"
    project_id: str | None = None
    source: str = Field(min_length=1)
    advisory: bool = False


__all__ = [
    "MemoryHit",
    "MemoryProposal",
    "MemoryPromotionActor",
    "MemoryRecallContext",
    "MemoryRecord",
    "MemoryRecordProvenance",
    "MemoryStatus",
    "MemoryVerification",
]
