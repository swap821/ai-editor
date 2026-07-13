"""Immutable contracts for the governed learning loop."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aios.core.verification_strength import VerificationStrength


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class AutonomyDecisionStatus(StrEnum):
    REQUIRE_CAPABILITY = "require_capability"
    ALLOW_AUTONOMOUS = "allow_autonomous"
    DENY = "deny"


class ActionClassKey(BaseModel):
    """The complete context that an earned action class is allowed to reuse."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1)
    action_type: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    target: str = Field(min_length=1)
    path_class: str = Field(min_length=1)
    verification_plan_digest: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    data_classification: str = Field(min_length=1)


class AutonomyOutcome(BaseModel):
    """Authoritative outcome supplied by verification, not model narration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool
    strength: VerificationStrength
    scope_violation: bool = False
    hidden_network: bool = False
    secret_access: bool = False
    audit_anomaly: bool = False
    reversible: bool = True


class AutonomyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: AutonomyDecisionStatus
    key_digest: str = Field(min_length=1)
    ledger_status: str = Field(min_length=1)
    reason_codes: tuple[str, ...] = ()
    profile_enabled: bool = False
    evaluated_at: str = Field(default_factory=_utc_now)


class CerebellumProposal(BaseModel):
    """A fast-path proposal; it is never an approval or policy decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    playbook_id: int = Field(ge=1)
    goal_pattern: str = Field(min_length=1)
    key_digest: str = Field(min_length=1)
    requires_policy_evaluation: Literal[True] = True
    created_at: str = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ActionClassKey",
    "AutonomyDecision",
    "AutonomyDecisionStatus",
    "AutonomyOutcome",
    "CerebellumProposal",
]
