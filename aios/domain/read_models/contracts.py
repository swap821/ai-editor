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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = ["MetricEnvelope", "MetricStatus", "SystemPortraitSnapshot"]
