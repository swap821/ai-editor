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

from aios.application.governance.text_screening import screen_text
from aios.domain.governance.amendments import (
    CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION,
    ConstitutionalAmendmentProposalV1,
)
from aios.domain.governance.constitution import (
    FOUNDATION_LAWS,
    changes_digest,
    ConstitutionSnapshotV1,
    build_constitution_snapshot,
)


class AmendmentError(RuntimeError):
    """Raised when an amendment action is refused."""


_OPEN_STATUSES = frozenset({"proposed", "critiqued", "simulated"})

#: Fields that only a real ratification may write.
_RATIFICATION_ONLY_FIELDS = frozenset(
    {
        "status",
        "ratified_by_operator_id",
        "ratification_capability_digest",
        "ratified_changes_digest",
        "activated_snapshot_digest",
        "predecessor_snapshot_digest",
    }
)


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
    # `**extra` is a convenience for optional descriptive fields (incident_refs,
    # threat_model, changes...). It must never carry the fields that record a
    # ratification: a caller could otherwise hand a brand-new proposal a
    # `ratified_changes_digest`, which is a claim about an operator decision
    # that has not happened. Activation independently refuses such a proposal
    # today, but a field whose only honest source is `ratify_amendment` should
    # not be settable by its caller at all.
    forbidden = _RATIFICATION_ONLY_FIELDS.intersection(extra)
    if forbidden:
        raise AmendmentError(
            f"{sorted(forbidden)} may only be set by ratify_amendment, "
            "never supplied when proposing"
        )
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
        raise AmendmentError(
            f"cannot critique a proposal in status {proposal.status!r}"
        )
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
        raise AmendmentError(
            f"cannot simulate a proposal in status {proposal.status!r}"
        )
    return proposal.model_copy(
        update={
            "simulation_notes": proposal.simulation_notes + (simulation_note,),
            "status": "simulated",
        }
    )


def _touches_foundation_law(proposal: ConstitutionalAmendmentProposalV1) -> bool:
    """Does *proposal* modify one of the six unamendable foundation laws?

    Screened through `text_screening`, not raw `.lower()` substring matching.
    This guard is not a pre-screen -- it runs inside `ratify_amendment`, so
    evading it is what turns "unamendable in v1" into "amendable by anyone who
    types a Cyrillic 'a'". Measured before the fix: `no model self-approval`
    with U+0430 substituted, plus a zero-width space in the article name, was
    not detected. `screen_text` also refuses mixed-script words outright, so
    an unenumerated homoglyph fails closed rather than passing silently.

    Field scope is deliberately narrow -- what the proposal *changes*
    (`target_articles`, `proposed_diff`, `migration_plan`), not why it wants
    to (`motivation`) or how to undo it (`rollback_plan`). A pro-sovereignty
    proposal that merely cites a foundation law as its reason should not be
    unratifiable, and a rollback plan naming the law it restores is normal.
    Text smuggled into those fields is caught by the authority-reduction
    screen in `constitutional_learning`, which reads every field.
    """
    haystack = " ".join(
        (proposal.proposed_diff, proposal.migration_plan, *proposal.target_articles)
    )
    law_id_markers = tuple(f"law {index}" for index in range(1, 7))
    return screen_text(haystack, law_id_markers + tuple(FOUNDATION_LAWS)) is not None


class ConstitutionalAmendmentAuthority:
    """Own the fail-closed capability gate for constitutional ratification."""

    def ratify_amendment(
        self,
        proposal: ConstitutionalAmendmentProposalV1,
        *,
        capability_proof: Any,
        operator_id: str,
    ) -> ConstitutionalAmendmentProposalV1:
        """The only step that can move a proposal toward activation. Refuses
        without a real, already-consumed, exactly-bound capability -- there is
        no other path through this function."""
        if proposal.status not in _OPEN_STATUSES:
            raise AmendmentError(
                f"cannot ratify a proposal in status {proposal.status!r}"
            )
        if proposal.approval_model != "human_capability_required":
            # Unreachable through the schema today -- `approval_model` is a
            # single-member Literal, so Pydantic refuses any other value at
            # construction. Checked anyway, because the day someone widens that
            # vocabulary this must fail closed rather than silently accept the
            # new member. A type that is enforced in one place and assumed in
            # another is how the assumption gets lost.
            raise AmendmentError(
                f"unsupported approval model {proposal.approval_model!r}; "
                "ratification requires a human capability"
            )
        if _touches_foundation_law(proposal):
            raise AmendmentError("foundation-law modifications are not amendable in v1")
        forbidden = [
            change
            for change in proposal.changes
            if not change.describes_a_permitted_direction()
        ]
        if forbidden:
            # Checked at RATIFICATION, not only at activation, so the operator
            # cannot spend a real capability on something that will be refused
            # later. `frozen_paths` currently holds `aios/security/`; the
            # direction this refuses is precisely the one that would unfreeze
            # the security spine.
            first = forbidden[0]
            raise AmendmentError(
                f"amendment change {first.operation!r} on {first.target!r} "
                "reduces protection and is not applicable in v1; only adding a "
                "frozen path or removing a scope root can be applied"
            )
        if (
            getattr(capability_proof, "action_type", None)
            != CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION
        ):
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
                "ratified_changes_digest": changes_digest(proposal.changes),
            }
        )


_AMENDMENT_AUTHORITY = ConstitutionalAmendmentAuthority()


def ratify_amendment(
    proposal: ConstitutionalAmendmentProposalV1,
    *,
    capability_proof: Any,
    operator_id: str,
) -> ConstitutionalAmendmentProposalV1:
    """Compatibility entrypoint for the production governance routes."""
    return _AMENDMENT_AUTHORITY.ratify_amendment(
        proposal,
        capability_proof=capability_proof,
        operator_id=operator_id,
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
        raise AmendmentError(
            f"cannot activate a proposal in status {proposal.status!r}"
        )
    if proposal.ratified_by_operator_id is None:
        raise AmendmentError("ratified proposal is missing its ratifying operator")

    # Re-verify at THIS boundary rather than trusting the one before it.
    # `ratify_amendment` checks direction, but a ratified proposal can be
    # `model_copy(update={"changes": ...})`-ed into a new frozen model that
    # keeps status="ratified" and carries something else entirely. Checking
    # only at ratification meant a capability spent on "add aios/api/" could
    # activate "remove aios/security/" -- unfreezing the security spine.
    if proposal.ratified_changes_digest is None:
        raise AmendmentError(
            "ratified proposal is missing its ratified-changes digest; it was "
            "not produced by ratify_amendment"
        )
    if changes_digest(proposal.changes) != proposal.ratified_changes_digest:
        raise AmendmentError(
            "proposal changes do not match what was ratified; the change set "
            "was altered after the operator's capability was consumed"
        )
    forbidden = [
        change
        for change in proposal.changes
        if not change.describes_a_permitted_direction()
    ]
    if forbidden:
        raise AmendmentError(
            f"amendment change {forbidden[0].operation!r} on "
            f"{forbidden[0].target!r} reduces protection and is not applicable"
        )
    new_snapshot = build_constitution_snapshot(
        ratified_by_operator_id=proposal.ratified_by_operator_id,
        previous_snapshot=previous_snapshot,
        changes=proposal.changes,
    )
    activated_proposal = proposal.model_copy(
        update={
            "status": "activated",
            "predecessor_snapshot_digest": previous_snapshot.snapshot_digest,
            "activated_snapshot_digest": new_snapshot.snapshot_digest,
        }
    )
    return activated_proposal, new_snapshot


def rollback_amendment(
    proposal: ConstitutionalAmendmentProposalV1,
    *,
    current_snapshot: ConstitutionSnapshotV1,
    previous_snapshot: ConstitutionSnapshotV1,
) -> tuple[ConstitutionalAmendmentProposalV1, ConstitutionSnapshotV1]:
    """Every activation has a rollback: revert to the exact predecessor
    snapshot this activation chained from, never an arbitrary older one."""
    if proposal.status != "activated":
        raise AmendmentError(
            f"cannot roll back a proposal in status {proposal.status!r}"
        )
    # Rollback only applies to the amendment CURRENTLY in force.
    #
    # The predecessor check below confirms the target is this proposal's own
    # predecessor, but said nothing about whether this proposal's activation is
    # still the live one. So an older amendment could be rolled back while a
    # newer snapshot was in force, and every change activated since would be
    # silently discarded. Measured:
    #
    #   v3 live : ('aios/security/', 'aios/api/', 'aios/core/')
    #   roll back the FIRST amendment
    #   restored: ('aios/security/',)   -- 'aios/api/' and 'aios/core/' gone
    #
    # That is a protection-REDUCING outcome reached through a permitted
    # operation, which is exactly what the v1 direction limit exists to
    # prevent. Found by the self-run adversarial pass; the fourth campaign
    # reported the same shape.
    if (
        proposal.activated_snapshot_digest is not None
        and current_snapshot.snapshot_digest != proposal.activated_snapshot_digest
    ):
        raise AmendmentError(
            "cannot roll back an amendment that is no longer in force: the live "
            f"constitution is {current_snapshot.snapshot_digest[:12]}... but this "
            f"proposal activated {proposal.activated_snapshot_digest[:12]}.... "
            "Roll back the later amendments first."
        )
    if proposal.predecessor_snapshot_digest is not None:
        if previous_snapshot.snapshot_digest != proposal.predecessor_snapshot_digest:
            raise AmendmentError(
                f"previous_snapshot digest {previous_snapshot.snapshot_digest!r} does not match proposal predecessor_snapshot_digest {proposal.predecessor_snapshot_digest!r}"
            )
    elif current_snapshot.previous_snapshot_digest != previous_snapshot.snapshot_digest:
        raise AmendmentError(
            "previous_snapshot is not the exact predecessor of current_snapshot"
        )
    return proposal.model_copy(update={"status": "rolled_back"}), previous_snapshot


__all__ = [
    "AmendmentError",
    "ConstitutionalAmendmentAuthority",
    "activate_amendment",
    "critique_amendment",
    "propose_amendment",
    "reject_amendment",
    "ratify_amendment",
    "rollback_amendment",
    "simulate_amendment",
]
