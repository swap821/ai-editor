"""Amendments that actually change the constitution.

The defect this closes
----------------------
Before `ConstitutionChangeV1`, activating a ratified constitutional amendment
produced a snapshot identical to its predecessor apart from the version
counter. Measured directly:

    status  : activated
    version : 1 -> 2
    fields UNCHANGED after a ratified activation: 8/8
    diff text applied anywhere? : False

`proposed_diff` is free prose, and `build_constitution_snapshot` rebuilt every
field from the live config, so an amendment's own content was recomputed away
at the instant it was applied. Three red-team campaigns hardened the road to a
destination that did not exist: the capability gate was real, the screening was
real, and the terminal act was a version bump.

What replaces it
----------------
A closed, typed vocabulary. "Who ratifies" stopped being writable as prose when
`approval_model` became a type; "what changes" stops being writable as prose
here. There is no paraphrase of an invalid enum member.

The v1 direction limit
----------------------
Only protection-INCREASING changes apply: add a frozen path, remove a scope
root. The inverses are refused at ratification, not merely at activation, so an
operator cannot spend a real capability on something that would be refused
later.

That limit is not timidity. `frozen_paths` contains `aios/security/`, so an
amendment able to remove it is an amendment that unfreezes the security spine
-- the exact act the frozen-organ apparatus exists to make impossible without
ceremony that does not yet exist. And the permitted direction is the reversible
one: `rollback_amendment` returns the exact predecessor snapshot, so a mistaken
tightening is undoable.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from aios.application.governance.amendment_authority import (
    AmendmentError,
    activate_amendment,
    propose_amendment,
    ratify_amendment,
    rollback_amendment,
)
from aios.domain.governance.amendments import CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION
from aios.domain.governance.constitution import (
    ConstitutionChangeV1,
    changes_digest,
    apply_constitution_changes,
    build_constitution_snapshot,
)

OPERATOR = "operator:abc"


def _capability(**overrides: object) -> SimpleNamespace:
    fields: dict[str, object] = dict(
        action_type=CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION,
        operator_id=OPERATOR,
        consumed_at=1234567890.0,
        token_digest="d" * 64,
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _proposal(changes: tuple[ConstitutionChangeV1, ...] = (), **overrides: object):
    fields: dict[str, object] = dict(
        proposal_id="amend-applicable",
        target_articles=("frozen_paths",),
        proposed_diff="freeze the api layer as well",
        motivation="reduce the surface a worker can modify",
        migration_plan="no migration required",
        rollback_plan="revert to the predecessor snapshot",
        proposed_by=OPERATOR,
        proposer_type="human",
        changes=changes,
    )
    fields.update(overrides)
    return propose_amendment(**fields)


def _ratified(changes: tuple[ConstitutionChangeV1, ...]):
    return ratify_amendment(
        _proposal(changes), capability_proof=_capability(), operator_id=OPERATOR
    )


# --------------------------------------------------------------------------- #
# The defect itself.
# --------------------------------------------------------------------------- #


def test_a_ratified_amendment_actually_changes_the_constitution() -> None:
    """The whole point. This is the assertion that was impossible before."""
    before = build_constitution_snapshot(ratified_by_operator_id=OPERATOR)
    assert "aios/api/" not in before.frozen_paths

    proposal = _ratified(
        (
            ConstitutionChangeV1(
                target="frozen_paths", operation="add", value="aios/api/"
            ),
        )
    )
    activated, after = activate_amendment(proposal, previous_snapshot=before)

    assert activated.status == "activated"
    assert "aios/api/" in after.frozen_paths
    assert after.frozen_paths != before.frozen_paths
    assert after.snapshot_digest != before.snapshot_digest


def test_an_applied_change_survives_the_next_version_bump() -> None:
    """A change that vanishes at version N+1 is the original bug wearing a
    different shape: the snapshot must carry forward from its predecessor, not
    be re-derived from live config each time."""
    v1 = build_constitution_snapshot(ratified_by_operator_id=OPERATOR)
    _, v2 = activate_amendment(
        _ratified(
            (
                ConstitutionChangeV1(
                    target="frozen_paths", operation="add", value="aios/api/"
                ),
            )
        ),
        previous_snapshot=v1,
    )
    v3 = build_constitution_snapshot(
        ratified_by_operator_id=OPERATOR, previous_snapshot=v2
    )
    assert "aios/api/" in v3.frozen_paths


def test_an_amendment_with_no_typed_changes_changes_nothing_and_says_so() -> None:
    """Documentation-only amendments stay legitimate.

    The bug was never "activation changes nothing"; it was that activation
    changed nothing while *appearing* to change something. An amendment
    carrying no typed changes is honestly inert.
    """
    before = build_constitution_snapshot(ratified_by_operator_id=OPERATOR)
    proposal = _ratified(())
    activated, after = activate_amendment(proposal, previous_snapshot=before)

    assert activated.changes == ()
    assert after.scope_roots == before.scope_roots
    assert after.frozen_paths == before.frozen_paths


# --------------------------------------------------------------------------- #
# The direction limit.
# --------------------------------------------------------------------------- #

FORBIDDEN_DIRECTIONS = {
    "unfreezing_the_security_spine": ("frozen_paths", "remove", "aios/security/"),
    "unfreezing_anything": ("frozen_paths", "remove", "aios/api/"),
    "widening_scope": ("scope_roots", "add", "C:/"),
}


@pytest.mark.parametrize("name", sorted(FORBIDDEN_DIRECTIONS))
def test_protection_reducing_changes_are_refused_at_ratification(name: str) -> None:
    """Refused when the capability is spent, not later at activation.

    The most important member of this set is the first: `frozen_paths` holds
    `aios/security/`, so a removable frozen path is an unfreezable security
    spine.
    """
    target, operation, value = FORBIDDEN_DIRECTIONS[name]
    proposal = _proposal(
        (ConstitutionChangeV1(target=target, operation=operation, value=value),)
    )
    with pytest.raises(AmendmentError, match="reduces protection"):
        ratify_amendment(proposal, capability_proof=_capability(), operator_id=OPERATOR)


def test_one_forbidden_change_poisons_an_otherwise_permitted_batch() -> None:
    """A batch is accepted or refused whole. Applying the safe half of a
    proposal a human reviewed as a unit would activate something nobody
    ratified."""
    proposal = _proposal(
        (
            ConstitutionChangeV1(
                target="frozen_paths", operation="add", value="aios/api/"
            ),
            ConstitutionChangeV1(
                target="frozen_paths", operation="remove", value="aios/security/"
            ),
        )
    )
    with pytest.raises(AmendmentError, match="reduces protection"):
        ratify_amendment(proposal, capability_proof=_capability(), operator_id=OPERATOR)


# --------------------------------------------------------------------------- #
# The vocabulary is closed.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "target,operation,value",
    [
        ("foundation_laws", "remove", "no model self-approval"),
        ("ratified_by_operator_id", "replace", "someone-else"),
        ("snapshot_digest", "replace", "0" * 64),
        ("scope_roots", "rename", "C:/x"),
        ("scope_roots", "add", ""),
        ("scope_roots", "add", "  padded  "),
        ("scope_roots", "add", "has\ttab"),
        ("scope_roots", "add", "has\nnewline"),
    ],
)
def test_the_change_vocabulary_refuses_anything_outside_it(
    target: str, operation: str, value: str
) -> None:
    """Foundation laws, identity and derived digests are not addressable at
    all, and neither is an operation the enum does not name. This is the
    property prose could never have."""
    with pytest.raises(ValidationError):
        ConstitutionChangeV1(
            target=target,  # type: ignore[arg-type]
            operation=operation,  # type: ignore[arg-type]
            value=value,
        )


def test_foundation_laws_are_still_unreachable_through_an_applied_amendment() -> None:
    """Belt and braces: even the permitted direction cannot touch them, because
    the snapshot model rejects any foundation-law set but the canonical one."""
    before = build_constitution_snapshot(ratified_by_operator_id=OPERATOR)
    _, after = activate_amendment(
        _ratified(
            (
                ConstitutionChangeV1(
                    target="frozen_paths", operation="add", value="aios/api/"
                ),
            )
        ),
        previous_snapshot=before,
    )
    assert after.foundation_laws == before.foundation_laws


# --------------------------------------------------------------------------- #
# The fold, and reversibility.
# --------------------------------------------------------------------------- #


def test_applying_a_change_twice_is_a_no_op_not_an_error() -> None:
    """An amendment restating the status quo is redundant, not invalid.
    Refusing it would make the ceremony fail on its safest possible input."""
    scopes, frozen = apply_constitution_changes(
        scope_roots=("C:/a",),
        frozen_paths=("aios/security/",),
        changes=(
            ConstitutionChangeV1(
                target="frozen_paths", operation="add", value="aios/security/"
            ),
            ConstitutionChangeV1(
                target="scope_roots", operation="remove", value="C:/never-present"
            ),
        ),
    )
    assert scopes == ("C:/a",)
    assert frozen == ("aios/security/",)


def test_changes_apply_in_order() -> None:
    """The fold is ordered, so a later change sees the effect of an earlier
    one. Anything else would make a batch's meaning depend on iteration
    order."""
    scopes, frozen = apply_constitution_changes(
        scope_roots=("C:/a", "C:/b"),
        frozen_paths=(),
        changes=(
            ConstitutionChangeV1(
                target="scope_roots", operation="remove", value="C:/a"
            ),
            ConstitutionChangeV1(target="frozen_paths", operation="add", value="C:/a"),
        ),
    )
    assert scopes == ("C:/b",)
    assert frozen == ("C:/a",)


def test_a_tightening_is_reversible_by_rollback() -> None:
    """Why one-directional v1 is livable: the permitted direction is the
    recoverable one. An over-tightened constitution is not a trap."""
    before = build_constitution_snapshot(ratified_by_operator_id=OPERATOR)
    activated, after = activate_amendment(
        _ratified(
            (
                ConstitutionChangeV1(
                    target="frozen_paths", operation="add", value="aios/api/"
                ),
            )
        ),
        previous_snapshot=before,
    )
    assert "aios/api/" in after.frozen_paths

    rolled, restored = rollback_amendment(
        activated, current_snapshot=after, previous_snapshot=before
    )
    assert rolled.status == "rolled_back"
    assert restored.snapshot_digest == before.snapshot_digest
    assert "aios/api/" not in restored.frozen_paths


def test_applying_changes_still_requires_a_real_capability() -> None:
    """The new mechanism must not become a way around the old gate. An
    unratified proposal carrying typed changes activates nothing."""
    before = build_constitution_snapshot(ratified_by_operator_id=OPERATOR)
    unratified = _proposal(
        (
            ConstitutionChangeV1(
                target="frozen_paths", operation="add", value="aios/api/"
            ),
        )
    )
    with pytest.raises(AmendmentError):
        activate_amendment(unratified, previous_snapshot=before)

    with pytest.raises(AmendmentError, match="already-consumed"):
        ratify_amendment(
            unratified,
            capability_proof=_capability(consumed_at=None),
            operator_id=OPERATOR,
        )


# --------------------------------------------------------------------------- #
# Binding the capability to the change set.
#
# Found by hand an hour after writing the feature, before the fourth campaign
# ran. The direction guard lived at ratification and activation trusted it:
#
#     ratified with : add aios/api/
#     frozen BEFORE : ('aios/security/',)
#     frozen AFTER  : ()
#
# A ratified proposal is a frozen model, but `model_copy(update=...)` returns a
# NEW frozen model that keeps status="ratified" and carries anything. So a
# capability spent on "freeze the api layer" could activate "unfreeze the
# security spine". A guard enforced at one boundary and assumed at the next is
# not a guard.
# --------------------------------------------------------------------------- #


def test_ratification_records_a_digest_of_what_was_approved() -> None:
    proposal = _ratified(
        (
            ConstitutionChangeV1(
                target="frozen_paths", operation="add", value="aios/api/"
            ),
        )
    )
    assert proposal.ratified_changes_digest
    assert proposal.ratified_changes_digest == changes_digest(proposal.changes)


@pytest.mark.parametrize(
    "swapped_to",
    [
        # The severe one: a permitted-direction ratification laundering an
        # unfreeze of the security spine.
        ("frozen_paths", "remove", "aios/security/"),
        # And the subtle one: still a PERMITTED direction, but not the change
        # the operator reviewed. Direction-checking alone would allow this.
        ("frozen_paths", "add", "C:/anything-at-all"),
        ("scope_roots", "remove", "C:/some-other-root"),
    ],
)
def test_changes_swapped_after_ratification_are_refused(
    swapped_to: tuple[str, str, str],
) -> None:
    target, operation, value = swapped_to
    ratified = _ratified(
        (
            ConstitutionChangeV1(
                target="frozen_paths", operation="add", value="aios/api/"
            ),
        )
    )
    tampered = ratified.model_copy(
        update={
            "changes": (
                ConstitutionChangeV1(
                    target=target,  # type: ignore[arg-type]
                    operation=operation,  # type: ignore[arg-type]
                    value=value,
                ),
            )
        }
    )
    assert tampered.status == "ratified"  # the swap survives the status check

    before = build_constitution_snapshot(ratified_by_operator_id=OPERATOR)
    with pytest.raises(AmendmentError, match="do not match what was ratified"):
        activate_amendment(tampered, previous_snapshot=before)


def test_a_proposal_never_ratified_by_the_authority_cannot_activate() -> None:
    """Hand-building a `status="ratified"` object skips ratify_amendment and so
    has no ratified-changes digest. Activation refuses rather than treating a
    missing digest as "nothing to check"."""
    forged = _proposal(
        (
            ConstitutionChangeV1(
                target="frozen_paths", operation="add", value="aios/api/"
            ),
        )
    ).model_copy(update={"status": "ratified", "ratified_by_operator_id": OPERATOR})
    before = build_constitution_snapshot(ratified_by_operator_id=OPERATOR)
    with pytest.raises(AmendmentError, match="missing its ratified-changes digest"):
        activate_amendment(forged, previous_snapshot=before)


def test_the_legitimate_activation_still_works_after_all_that() -> None:
    """The guards must not have closed the door entirely."""
    before = build_constitution_snapshot(ratified_by_operator_id=OPERATOR)
    proposal = _ratified(
        (
            ConstitutionChangeV1(
                target="frozen_paths", operation="add", value="aios/api/"
            ),
        )
    )
    _, after = activate_amendment(proposal, previous_snapshot=before)
    assert "aios/api/" in after.frozen_paths
