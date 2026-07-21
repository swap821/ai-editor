"""Model Registry / Capability Passport and Provider Health contracts
(Slice 31).

`aios.core.router.Provider` already expresses a routable provider as pure
data (`name`, `privacy`, `cost`, `available`, `models`, `capability`) -- this
module does not replace it. `ModelPassportV1` is the durable, role-scoped
admission record `Provider.available`/`.capability` don't carry: whether a
specific exact model has actually been qualified for a specific role, not
merely whether the provider is reachable right now. `ProviderHealthSnapshot`
is the measured-health shape `aios.runtime.budget_guard.BudgetGuard` doesn't
track at all today (that module only does per-mission token/cost
accounting, nothing about reachability, credentials, or circuit state).

Neither contract fabricates qualification or health data: constructing one
is a claim, and nothing in this module or `aios.application.models.health`
runs a real qualification suite or a real network probe -- that is
Slice 32's job (against a real local Ollama model) and a follow-up for
cloud providers. What this module provides is the durable shape those real
probes will populate, plus a genuinely deterministic circuit-breaker state
machine over whatever call outcomes a caller reports.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class CostProfile(BaseModel):
    """Coarse cost shape; `None` means genuinely unknown, never zero."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_cost_per_1k: float | None = None
    output_cost_per_1k: float | None = None
    currency: str = "USD"


class RoleMetric(BaseModel):
    """Verified, role-specific outcome counts for one model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str = Field(min_length=1, max_length=200)
    success_count: int = Field(default=0, ge=0)
    failure_count: int = Field(default=0, ge=0)
    measured_latency_ms_p50: float | None = None


class ModelPassportV1(BaseModel):
    """Durable, evidence-backed admission record for one exact model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    passport_id: str = Field(min_length=1, max_length=200)
    provider: str = Field(min_length=1, max_length=100)
    exact_model_id: str = Field(min_length=1, max_length=300)
    model_version: str | None = None
    deployment_region: str | None = None
    privacy_class: str = Field(min_length=1, max_length=100)
    qualified_roles: tuple[str, ...] = ()
    disallowed_roles: tuple[str, ...] = ()
    tool_protocol_status: Literal["unknown", "unsupported", "supported", "verified"] = (
        "unknown"
    )
    structured_output_status: Literal[
        "unknown", "unsupported", "supported", "verified"
    ] = "unknown"
    context_limit: int = Field(gt=0)
    output_limit: int = Field(gt=0)
    cost_profile: CostProfile = Field(default_factory=CostProfile)
    measured_success_rates: tuple[RoleMetric, ...] = ()
    known_failure_modes: tuple[str, ...] = ()
    admission_status: Literal["proposed", "admitted", "suspended", "revoked"] = (
        "proposed"
    )
    qualification_suite_version: str | None = None
    last_qualified_at: str | None = None
    passport_digest: str = Field(min_length=64, max_length=64)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ProviderHealthSnapshot(BaseModel):
    """A point-in-time measured health read for one provider.

    `budget_remaining=None` means unknown, matching the brief's "unknown
    billing cost remains unknown, not zero" invariant -- the same convention
    `CostProfile` uses.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1, max_length=100)
    reachable: bool
    credential_valid: bool
    rate_limited: bool = False
    recent_failure_count: int = Field(default=0, ge=0)
    measured_latency_ms: float | None = None
    budget_remaining: float | None = None
    circuit_state: Literal["closed", "open", "half_open"] = "closed"
    last_successful_call_at: str | None = None
    evaluated_at: str = Field(default_factory=_utc_now)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


__all__ = [
    "CostProfile",
    "ModelPassportV1",
    "ProviderHealthSnapshot",
    "RoleMetric",
]
