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

from aios.domain.governance.constitution import ConstitutionChangeV1

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

    #: WHO may ratify this amendment -- as typed data, not as prose.
    #:
    #: Two adversarial campaigns (49 agents, 24 confirmed findings) established
    #: that keyword screening over `proposed_diff` cannot decide whether a
    #: proposal reduces human authority. Paraphrase is unbounded; every round of
    #: hardening closed the shapes it found and left the rest. Attacks like
    #: "ratification is deemed complete if the operator does not respond within
    #: 72 hours" contain no marker in any encoding, and there is no marker list
    #: that ends that game.
    #:
    #: So the approval model stops being something a sentence can assert. It is
    #: a closed vocabulary with exactly one member in v1, and `extra="forbid"`
    #: plus `frozen=True` mean a proposal can neither invent a value nor mutate
    #: this one after construction. A proposal whose *prose* describes timeout
    #: approval, tiered auto-activation, or a delegate approver is now simply
    #: wrong about itself: the runtime reads this field, never the prose.
    #:
    #: Widening this vocabulary is a schema change -- code, review, a diff
    #: somebody has to sign off on. That is the entire point. It converts "who
    #: ratifies" from something a model can write into something only a human
    #: can ship, which is Law XIII expressed as a type instead of a sentence.
    approval_model: Literal["human_capability_required"] = "human_capability_required"

    #: WHAT this amendment changes -- as typed, applicable data.
    #:
    #: `proposed_diff` is prose, and prose cannot be applied. Until this field
    #: existed, activating a ratified amendment produced a snapshot identical
    #: to its predecessor apart from the version counter: three red-team
    #: campaigns hardened a road to a destination that was not there.
    #:
    #: Empty is legitimate and means exactly what it says -- a documentation or
    #: wording amendment that changes no constitutional value. It is not a
    #: silent no-op any more, because `activate_amendment` reports how many
    #: changes it applied and the tests assert the distinction.
    changes: tuple[ConstitutionChangeV1, ...] = ()
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
    #: Digest of `changes` at the moment of ratification. Activation refuses
    #: unless the changes still hash to this, so the operator's capability is
    #: bound to the exact change set they approved rather than to the proposal
    #: id alone.
    ratified_changes_digest: str | None = None
    activated_snapshot_digest: str | None = None
    predecessor_snapshot_digest: str | None = None
    created_at: str = Field(default_factory=_utc_now)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


__all__ = [
    "CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION",
    "ConstitutionalAmendmentProposalV1",
]
