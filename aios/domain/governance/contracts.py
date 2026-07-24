"""Immutable contracts for the operator emergency control and organ ledger."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

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


class OrganEvidence(BaseModel):
    """One piece of runtime evidence claimed for an organ.

    ``proof_level`` is explicit rather than inferred: a fixture-generated
    proof can never silently pass as a live runtime proof, and evidence
    stamped with a stale commit can never silently pass as current.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    description: str = Field(min_length=1, max_length=2000)
    commit_sha: str = Field(min_length=7, max_length=64)
    proof_level: Literal["live", "fixture"] = "fixture"

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class OrganRecord(BaseModel):
    """One row of the Organ Truth Ledger (Slice 25).

    A record is a claim, not a guarantee: `organ_ledger.validate_ledger`
    is the only function allowed to decide whether the claim is truthful.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    organ_id: int = Field(ge=1, le=54)
    name: str = Field(min_length=1, max_length=200)
    status: Literal["green", "yellow"]
    authority_owner: str = Field(min_length=1, max_length=200)
    production_entrypoints: tuple[str, ...] = Field(default_factory=tuple)
    focused_tests: tuple[str, ...] = Field(default_factory=tuple)
    integration_tests: tuple[str, ...] = Field(default_factory=tuple)
    live_evidence: tuple[OrganEvidence, ...] = Field(default_factory=tuple)
    known_blockers: tuple[str, ...] = Field(default_factory=tuple)
    last_verified_sha: str | None = None
    requires_live_evidence: bool = False
    requires_frontend_error_states: bool = False

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


__all__ = [
    "EmergencyStopRequest",
    "EmergencyStopState",
    "OrganEvidence",
    "OrganRecord",
]
