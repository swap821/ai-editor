"""Reconciliation pass, item 6: durable, append-only history for
ConstitutionalAmendmentProposalV1 (Slice 37) and GovernanceLessonV1
(Slice 38). Both organs were pure in-memory pipelines before this store
existed -- these tests drive the real amendment_authority.py /
constitutional_learning.py transition functions end to end and verify
every transition survives as its own row, not just the final status.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aios.application.governance.amendment_authority import (
    critique_amendment,
    propose_amendment,
    ratify_amendment,
)
from aios.application.governance.constitutional_learning import (
    lesson_to_amendment_proposal,
    propose_lesson,
)
from aios.infrastructure.governance.sqlite_store import (
    GovernanceAmendmentStore,
    RecordTamperedError,
)


class _FakeConsumedCapability:
    action_type = "constitutional_amendment_ratify"

    def __init__(self, operator_id: str) -> None:
        self.operator_id = operator_id
        self.consumed_at = "2026-07-22T00:00:00+00:00"
        self.token_digest = "cap-digest-abc"


def _proposal(proposal_id: str = "amend-1"):
    return propose_amendment(
        proposal_id=proposal_id,
        target_articles=("article-3",),
        proposed_diff="widen the local-model allowlist",
        motivation="observed repeated false-negative admission rejections",
        migration_plan="apply via next constitution snapshot",
        rollback_plan="revert to previous snapshot digest",
        proposed_by="operator-1",
        proposer_type="human",
    )


def test_full_lifecycle_preserves_every_revision_not_just_final_status(
    tmp_path: Path,
) -> None:
    store = GovernanceAmendmentStore(tmp_path / "amendments.db")

    proposed = _proposal()
    rev1 = store.save_proposal(proposed)

    critiqued = critique_amendment(proposed, "needs a named rollback owner")
    rev2 = store.save_proposal(critiqued)

    ratified = ratify_amendment(
        critiqued,
        capability_proof=_FakeConsumedCapability("operator-1"),
        operator_id="operator-1",
    )
    rev3 = store.save_proposal(ratified)

    assert (rev1, rev2, rev3) == (1, 2, 3)

    current = store.get_current_proposal("amend-1")
    assert current is not None
    assert current.status == "ratified"
    assert current.ratified_by_operator_id == "operator-1"

    history = store.get_proposal_history("amend-1")
    assert [p.status for p in history] == ["proposed", "critiqued", "ratified"]
    # the critique text from revision 2 must still be readable in history,
    # not overwritten by revision 3's ratification.
    assert history[1].critiques == ("needs a named rollback owner",)


def test_unknown_proposal_id_returns_none_not_an_error(tmp_path: Path) -> None:
    store = GovernanceAmendmentStore(tmp_path / "amendments.db")
    assert store.get_current_proposal("does-not-exist") is None
    assert store.get_proposal_history("does-not-exist") == ()


def test_two_proposals_do_not_collide_on_revision_numbering(tmp_path: Path) -> None:
    store = GovernanceAmendmentStore(tmp_path / "amendments.db")

    store.save_proposal(_proposal("amend-a"))
    store.save_proposal(_proposal("amend-b"))
    store.save_proposal(critique_amendment(_proposal("amend-a"), "note"))

    assert len(store.get_proposal_history("amend-a")) == 2
    assert len(store.get_proposal_history("amend-b")) == 1


def test_tampered_proposal_row_is_detected_at_read_time(tmp_path: Path) -> None:
    db_path = tmp_path / "amendments.db"
    store = GovernanceAmendmentStore(db_path)
    store.save_proposal(_proposal())

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE governance_amendment_proposals SET motivation = ? "
        "WHERE proposal_id = 'amend-1' AND revision = 1",
        ("a motivation nobody wrote",),
    )
    conn.commit()
    conn.close()

    with pytest.raises(RecordTamperedError):
        store.get_current_proposal("amend-1")


def test_lesson_to_proposal_pipeline_persists_both_with_linkage(
    tmp_path: Path,
) -> None:
    store = GovernanceAmendmentStore(tmp_path / "amendments.db")

    lesson = propose_lesson(
        lesson_id="lesson-1",
        problem_class="approval_friction",
        evidence_refs=("incident-42",),
        observed_harm="operators repeatedly denied a safe capability request",
        current_rule="capability scope is all-or-nothing per action type",
        proposed_improvement="add a narrower capability scope tier",
        confidence=0.72,
    )
    store.save_lesson(lesson)

    updated_lesson, proposal = lesson_to_amendment_proposal(
        lesson,
        proposal_id="amend-from-lesson-1",
        target_articles=("article-5",),
        proposed_diff="add narrower capability scope tier",
        migration_plan="ship behind a feature flag first",
        rollback_plan="remove the new tier",
    )
    store.save_lesson(updated_lesson)
    store.save_proposal(proposal)

    stored_lesson = store.get_current_lesson("lesson-1")
    assert stored_lesson is not None
    assert stored_lesson.status == "amendment_drafted"
    assert stored_lesson.amendment_proposal_id == "amend-from-lesson-1"

    stored_proposal = store.get_current_proposal("amend-from-lesson-1")
    assert stored_proposal is not None
    assert stored_proposal.proposer_type == "model"
    assert stored_proposal.evidence_refs == ("incident-42",)

    lesson_history = store.get_lesson_history("lesson-1")
    assert [entry.status for entry in lesson_history] == [
        "proposed",
        "amendment_drafted",
    ]


def test_tampered_lesson_row_is_detected_at_read_time(tmp_path: Path) -> None:
    db_path = tmp_path / "amendments.db"
    store = GovernanceAmendmentStore(db_path)
    lesson = propose_lesson(
        lesson_id="lesson-tamper",
        problem_class="rollback_event",
        evidence_refs=("incident-1",),
        observed_harm="harm text",
        current_rule="rule text",
        proposed_improvement="improvement text",
        confidence=0.5,
    )
    store.save_lesson(lesson)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE governance_lessons SET confidence = 0.99 "
        "WHERE lesson_id = 'lesson-tamper' AND revision = 1"
    )
    conn.commit()
    conn.close()

    with pytest.raises(RecordTamperedError):
        store.get_current_lesson("lesson-tamper")
