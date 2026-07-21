"""Immutable, status-aware values exposed by the Living Mirror."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MetricStatus(StrEnum):
    MEASURED = "measured"
    DERIVED = "derived"
    UNAVAILABLE = "unavailable"
    STALE = "stale"
    SIMULATED = "simulated"


class MetricEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: Any = None
    status: MetricStatus
    measured_at: str | None = Field(default_factory=lambda: _utc_now())
    source: str
    freshness: int | None = None


class SystemPortraitSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0"
    status: str
    phase: str
    active_turns: tuple[str, ...] = ()
    active_missions: tuple[str, ...] = ()
    active_workers: tuple[str, ...] = ()
    active_models: tuple[str, ...] = ()
    last_event_id: int = 0
    metrics: dict[str, MetricEnvelope] = {}


class ConstitutionProjection(BaseModel):
    """Slice 39. Every field is a `MetricEnvelope`, not a bare value -- a
    missing active constitution must show `unavailable`, never a silently
    absent or default-guessed version number."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    constitution_id: MetricEnvelope
    version: MetricEnvelope
    ratified_by_operator_id: MetricEnvelope
    snapshot_digest: MetricEnvelope
    foundation_laws_count: MetricEnvelope


class EmergencyStopProjection(BaseModel):
    """Slice 39. Must always be renderable, even with a stopped/unreachable
    controller -- see `project_emergency_stop`'s `unavailable` fallback."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    engaged: MetricEnvelope
    generation: MetricEnvelope
    reason: MetricEnvelope
    engaged_at: MetricEnvelope


class ProviderHealthProjection(BaseModel):
    """Slice 39. `budget_remaining` in particular must be `unavailable`
    when unknown -- never coerced to zero (see `CostProfile`'s existing
    same convention from Slice 31)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str
    reachable: MetricEnvelope
    circuit_state: MetricEnvelope
    recent_failure_count: MetricEnvelope
    budget_remaining: MetricEnvelope


class ApprovalProjection(BaseModel):
    """Slice 39: the pinned (never scrolled-away) exact-decision surface.

    Deliberately has no `approved`/`decision`/`grants_authority` field --
    this projection only presents what a human needs to decide; the actual
    approve/reject action happens through the real capability/ActionBroker
    path, never through a field on this object.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    requested_action: MetricEnvelope
    requesting_model: MetricEnvelope
    mission_id: MetricEnvelope
    risk: MetricEnvelope
    scope: MetricEnvelope
    reversibility: MetricEnvelope
    verification_plan: MetricEnvelope
    constitution_version: MetricEnvelope


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "ApprovalProjection",
    "ConstitutionProjection",
    "EmergencyStopProjection",
    "MetricEnvelope",
    "MetricStatus",
    "ProviderHealthProjection",
    "SystemPortraitSnapshot",
]
