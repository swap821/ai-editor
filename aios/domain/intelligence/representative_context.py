"""RepresentativeContextV1 (Slice 29: Human Representative Context Compiler).

One provider-neutral, immutable, digested packet every model call should be
built from -- never a raw, uncompiled user prompt. Provider adapters may
reformat this into whatever wire shape a given API expects, but they may not
add authority, add secrets, widen scope, remove evidence requirements, or
silently alter a human decision recorded here.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PreferenceProjection(BaseModel):
    """A minimal, already-privacy-reviewed projection of one active
    `OperatorPreferenceV1` -- deliberately narrower than the full record
    (no `source_ids`, no `contradicted_by`) so a provider adapter cannot
    reconstruct the operator's full preference history from one context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: str = Field(min_length=1, max_length=200)
    key: str = Field(min_length=1, max_length=200)
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)


class RepresentativeContextV1(BaseModel):
    """The complete, compiled context for exactly one model request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(min_length=1, max_length=200)
    operator_identity_digest: str = Field(min_length=1, max_length=200)
    constitution_digest: str = Field(min_length=64, max_length=64)
    goal: str
    desired_outcome: str
    explicit_constraints: tuple[str, ...] = ()
    current_decisions: tuple[str, ...] = ()
    approved_preferences: tuple[PreferenceProjection, ...] = ()
    project_passport_digest: str | None = None
    relevant_memory_refs: tuple[str, ...] = ()
    privacy_classification: str = Field(min_length=1, max_length=100)
    cloud_allowed_fields: tuple[str, ...] = ()
    forbidden_fields: tuple[str, ...] = ()
    delegated_authority_summary: str
    permitted_tools: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ()
    communication_mode: str = "direct"
    uncertainty: tuple[str, ...] = ()
    context_digest: str = Field(min_length=64, max_length=64)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


__all__ = ["PreferenceProjection", "RepresentativeContextV1"]
