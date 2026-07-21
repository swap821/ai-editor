"""Constitutional Amendment Authority (Slice 37).

Models may propose, critique, and simulate -- none of that touches the
active constitution. Only `ratify_amendment` can move a proposal toward
activation, and it can only be satisfied by a real, already-consumed exact
capability bound to the ratifying operator: models and workers have no path
to produce one (only `CapabilityAuthority.issue()`/`.consume()` against a
real authenticated human session can), and reusing an old capability is
already structurally impossible because exact capabilities are single-use
(Slice 25/26). `activate_amendment` reuses `build_constitution_snapshot`'s
existing version-chaining machinery, so activation produces a real next
constitution version the same way every other version bump does -- and
because every prior `MissionContract` already carries its own frozen
`constitution_digest` (Slice 26), existing missions are structurally pinned
to their original constitution without this module doing anything extra.
"""

from __future__ import annotations

from typing import Any

from aios.domain.governance.amendments import (
    CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION,
    ConstitutionalAmendmentProposalV1,
)
from aios.domain.governance.constitution import (
    FOUNDATION_LAWS,
    ConstitutionSnapshotV1,
    build_constitution_snapshot,
)


class AmendmentError(RuntimeError):
    """Raised when an amendment action is refused."""


_OPEN_STATUSES = frozenset({"proposed", "critiqued", "simulated"})


def propose_amendment(
    *,
    proposal_id: str,
    target_articles: tuple[str, ...],
    proposed_diff: str,
    motivation: str,
    migration_plan: str,
    rollback_plan: str,
    proposed_by: str,
    proposer_type: str,
    **extra: Any,
) -> ConstitutionalAmendmentProposalV1:
    """Models, humans, or workers may all propose -- a proposal has zero
    runtime effect until it is ratified and activated."""
    return ConstitutionalAmendmentProposalV1(
        proposal_id=proposal_id,
        target_articles=target_articles,
        proposed_diff=proposed_diff,
        motivation=motivation,
        migration_plan=migration_plan,
        rollback_plan=rollback_plan,
        proposed_by=proposed_by,
        proposer_type=proposer_type,
        status="proposed",
        **extra,
    )


def critique_amendment(
    proposal: ConstitutionalAmendmentProposalV1, critique_text: str
) -> ConstitutionalAmendmentProposalV1:
    """Models or humans may critique -- never changes runtime behavior."""
    if proposal.status not in _OPEN_STATUSES:
        raise AmendmentError(f"cannot critique a proposal in status {proposal.status!r}")
    return proposal.model_copy(
        update={
            "critiques": proposal.critiques + (critique_text,),
            "status": "critiqued",
        }
    )


def simulate_amendment(
    proposal: ConstitutionalAmendmentProposalV1, simulation_note: str
) -> ConstitutionalAmendmentProposalV1:
    """Models or humans may simulate -- never changes runtime behavior."""
    if proposal.status not in _OPEN_STATUSES:
        raise AmendmentError(f"cannot simulate a proposal in status {proposal.status!r}")
    return proposal.model_copy(
        update={
            "simulation_notes": proposal.simulation_notes + (simulation_note,),
            "status": "simulated",
        }
    )


def _touches_foundation_law(proposal: ConstitutionalAmendmentProposalV1) -> bool:
    haystack = " ".join((proposal.proposed_diff, *proposal.target_articles)).lower()
    return any(law.lower() in haystack for law in FOUNDATION_LAWS)


def ratify_amendment(
    proposal: ConstitutionalAmendmentProposalV1,
    *,
    capability_proof: Any,
    operator_id: str,
) -> ConstitutionalAmendmentProposalV1:
    """The only step that can move a proposal toward activation. Refuses
    without a real, already-consumed, exactly-bound capability -- there is
    no other path through this function."""
    if proposal.status not in _OPEN_STATUSES:
        raise AmendmentError(f"cannot ratify a proposal in status {proposal.status!r}")
    if _touches_foundation_law(proposal):
        raise AmendmentError(
            "foundation-law modifications are not amendable in v1"
        )
    if getattr(capability_proof, "action_type", None) != CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION:
        raise AmendmentError(
            "ratification capability must be bound to "
            f"{CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION!r}, got "
            f"{getattr(capability_proof, 'action_type', None)!r}"
        )
    if getattr(capability_proof, "operator_id", None) != operator_id:
        raise AmendmentError("ratification capability operator does not match")
    if getattr(capability_proof, "consumed_at", None) is None:
        raise AmendmentError("ratification requires an already-consumed capability")

    return proposal.model_copy(
        update={
            "status": "ratified",
            "ratified_by_operator_id": operator_id,
            "ratification_capability_digest": capability_proof.token_digest,
        }
    )


def reject_amendment(
    proposal: ConstitutionalAmendmentProposalV1, reason: str
) -> ConstitutionalAmendmentProposalV1:
    if proposal.status in {"activated", "rejected", "rolled_back"}:
        raise AmendmentError(f"cannot reject a proposal in status {proposal.status!r}")
    return proposal.model_copy(
        update={
            "status": "rejected",
            "simulation_notes": proposal.simulation_notes + (f"rejected: {reason}",),
        }
    )


def activate_amendment(
    proposal: ConstitutionalAmendmentProposalV1,
    *,
    previous_snapshot: ConstitutionSnapshotV1,
    emergency_stop: Any | None = None,
) -> tuple[ConstitutionalAmendmentProposalV1, ConstitutionSnapshotV1]:
    """Only a ratified proposal may activate. Produces the next chained
    constitution snapshot via the same machinery every other version bump
    uses (Slice 26) -- there is no separate, weaker activation path.

    Slice 27 named "constitutional amendment activation" as a required
    emergency-stop boundary before this organ existed to wire it into --
    closing that gap here."""
    if emergency_stop is not None:
        emergency_stop.assert_operational()
    if proposal.status != "ratified":
        raise AmendmentError(f"cannot activate a proposal in status {proposal.status!r}")
    if proposal.ratified_by_operator_id is None:
        raise AmendmentError("ratified proposal is missing its ratifying operator")
    new_snapshot = build_constitution_snapshot(
        ratified_by_operator_id=proposal.ratified_by_operator_id,
        previous_snapshot=previous_snapshot,
    )
    return proposal.model_copy(update={"status": "activated"}), new_snapshot


def rollback_amendment(
    proposal: ConstitutionalAmendmentProposalV1,
    *,
    current_snapshot: ConstitutionSnapshotV1,
    previous_snapshot: ConstitutionSnapshotV1,
) -> tuple[ConstitutionalAmendmentProposalV1, ConstitutionSnapshotV1]:
    """Every activation has a rollback: revert to the exact predecessor
    snapshot this activation chained from, never an arbitrary older one."""
    if proposal.status != "activated":
        raise AmendmentError(f"cannot roll back a proposal in status {proposal.status!r}")
    if current_snapshot.previous_snapshot_digest != previous_snapshot.snapshot_digest:
        raise AmendmentError(
            "previous_snapshot is not the exact predecessor of current_snapshot"
        )
    return proposal.model_copy(update={"status": "rolled_back"}), previous_snapshot


__all__ = [
    "AmendmentError",
    "activate_amendment",
    "critique_amendment",
    "propose_amendment",
    "reject_amendment",
    "ratify_amendment",
    "rollback_amendment",
    "simulate_amendment",
]
