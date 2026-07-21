"""Multi-Model Deliberation and Dissent contracts (Slice 34).

No prior art exists for this anywhere in the codebase (confirmed by a
repo-wide search for "dissent"/"disagreement"/"DeliberationRole" before
writing this file) -- unlike most other Slices 25-33 contracts, this one
does not wrap an existing subsystem. Council Queens' own LLM slots
(`PlannerQueen`, `CouncilOrchestrator.king_complete`) are wired to accept a
client but nothing in production ever supplies one, so there is no working
deliberation path to extend either; this is a from-scratch, typed
foundation for when one exists.

The central invariant: a local clerk (Slice 32) may *summarise* disagreement
for a human, but nothing in this module lets it erase a minority finding.
`DeliberationRecord.unresolved_minority_concerns` is derived, not
hand-authored, specifically so no synthesis step can silently drop one.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DeliberationRoleName = Literal[
    "primary",
    "critic",
    "security_reviewer",
    "test_reviewer",
    "alternative",
    "synthesizer",
]


class DeliberationRole(BaseModel):
    """One seat in a deliberation: what it's for and what independence it needs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: DeliberationRoleName
    provider_requirements: tuple[str, ...] = ()
    independence_required: bool = False


class ModelPosition(BaseModel):
    """One model's independent, complete contribution to a deliberation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: DeliberationRoleName
    provider: str = Field(min_length=1, max_length=100)
    exact_model_id: str = Field(min_length=1, max_length=300)
    answer: str
    assumptions: tuple[str, ...] = ()
    evidence_references: tuple[str, ...] = ()
    confidence: float = Field(ge=0.0, le=1.0)
    security_concerns: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class DeliberationRecord(BaseModel):
    """The complete, durable record of one deliberation.

    `final_disposition` is a deterministic string a caller supplies (e.g.
    "promote", "reject", "escalate_to_human") -- no field here can itself
    grant authority; a disposition still has to flow through the real
    authority paths (ActionBroker, PromotionAuthority, etc.) to take effect.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    deliberation_id: str = Field(min_length=1, max_length=200)
    mission_id: str | None = None
    trigger_reasons: tuple[str, ...] = Field(min_length=1)
    positions: tuple[ModelPosition, ...] = Field(min_length=2)
    disagreements: tuple[str, ...] = ()
    unresolved_minority_concerns: tuple[str, ...] = ()
    final_disposition: str = Field(min_length=1)
    created_at: str
    deliberation_digest: str = Field(min_length=64, max_length=64)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


__all__ = [
    "DeliberationRole",
    "DeliberationRoleName",
    "DeliberationRecord",
    "ModelPosition",
]
