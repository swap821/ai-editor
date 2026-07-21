"""Constitutional Amendment Authority contracts (Slice 37).

Builds on Slice 26's `ConstitutionSnapshotV1`/`build_constitution_snapshot`
version-chaining machinery rather than duplicating it: activating a ratified
amendment produces a new chained snapshot the same way any other version
bump does. What this module adds is the missing ceremony in front of that:
a typed proposal, and a ratification step that can only be satisfied by a
real, already-consumed exact capability -- never a model, a worker, or a
frontend flag.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

#: The one action type a capability must be bound to before it can satisfy
#: `ratify_amendment`. Deliberately not added to `aios.domain.actions.
#: envelope.ActionType` in this slice -- that enum feeds the full HTTP/
#: PolicyKernel routing table, and wiring a real issuance route for it is
#: separate follow-up work, not assumed here.
CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION = "constitutional_amendment_ratify"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ConstitutionalAmendmentProposalV1(BaseModel):
    """One proposed change to the constitution.

    A proposal has zero runtime effect by construction: nothing in this
    module or `aios.application.governance.amendment_authority` reads a
    proposal to alter the active constitution except `activate_amendment`,
    which requires `status == "ratified"` -- and ratification requires a
    real human capability, never a model or worker action alone.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    proposal_id: str = Field(min_length=1, max_length=200)
    target_articles: tuple[str, ...] = Field(min_length=1)
    proposed_diff: str = Field(min_length=1)
    motivation: str = Field(min_length=1)
    incident_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    threat_model: tuple[str, ...] = ()
    expected_benefits: tuple[str, ...] = ()
    new_risks: tuple[str, ...] = ()
    migration_plan: str = Field(min_length=1)
    rollback_plan: str = Field(min_length=1)
    proposed_by: str = Field(min_length=1, max_length=200)
    proposer_type: Literal["model", "human", "worker"]
    status: Literal[
        "proposed",
        "critiqued",
        "simulated",
        "ratified",
        "rejected",
        "activated",
        "rolled_back",
    ] = "proposed"
    critiques: tuple[str, ...] = ()
    simulation_notes: tuple[str, ...] = ()
    ratified_by_operator_id: str | None = None
    ratification_capability_digest: str | None = None
    created_at: str = Field(default_factory=_utc_now)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


__all__ = [
    "CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION",
    "ConstitutionalAmendmentProposalV1",
]
