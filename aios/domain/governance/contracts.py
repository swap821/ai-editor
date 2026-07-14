"""Immutable contracts for the operator emergency control."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class EmergencyStopRequest(BaseModel):
    """A request bound to a backend-authenticated privileged operator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operator_id: str = Field(min_length=1, max_length=256)
    authentication_event_id: str = Field(min_length=1, max_length=256)
    reason: str = Field(min_length=1, max_length=1000)
    requested_at: str = Field(default_factory=_utc_now)


class EmergencyStopState(BaseModel):
    """Durable, read-only view of the emergency-stop latch."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    engaged: bool = False
    generation: int = Field(default=0, ge=0)
    operator_id: str | None = None
    authentication_event_id: str | None = None
    reason: str = ""
    actions: dict[str, str] = Field(default_factory=dict)
    failure: str | None = None
    engaged_at: str | None = None
    cleared_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


__all__ = ["EmergencyStopRequest", "EmergencyStopState"]
