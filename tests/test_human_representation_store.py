"""Tier-1 closure pass, organs 27/28: durable persistence for
OperatorPreferenceV1 (a thin adapter over the existing SemanticFacts store)
and ProjectPassportV1 (a genuinely new append-only history store).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aios.domain.memory.human_representation import (
    CorrectionRecordV1,
    HumanStateHypothesis,
    OperatorPreferenceV1,
    ProjectPassportV1,
)
from aios.infrastructure.memory.human_representation_store import (
    CorrectionRecordStore,
    HumanStateHypothesisStore,
    OperatorPreferenceStore,
    ProjectPassportStore,
    RecordTamperedError,
)
from aios.memory.facts import SemanticFacts


def _correction_record(**overrides: object) -> CorrectionRecordV1:
    payload = {
        "correction_id": "correction:session-1:1",
        "session_id": "session-1",
        "base_revision": 0,
        "correction_revision": 1,
        "corrected_fields": ("goal",),
        "prior_interpretation_digest": "a" * 64,
        "current_interpretation_digest": "b" * 64,
    }
    payload.update(overrides)
    return CorrectionRecordV1(**payload)


def _preference(**overrides: object) -> OperatorPreferenceV1:
    payload = {
        "preference_id": "pref-1",
        "domain": "testing",
        "key": "prefers_pytest",
        "value": True,
        "scope": "project:ai-editor",
        "confidence": 0.8,
        "source_type": "explicit_user",
    }
    payload.update(overrides)
    return OperatorPreferenceV1(**payload)


def _pref_store(db_path: Path) -> OperatorPreferenceStore:
    """SemanticFacts is constructed directly here because this is a test
    file, outside tests/test_memory_architecture.py's production-only
    quarantine of legacy memory-type construction to aios/api/deps.py."""
    return OperatorPreferenceStore(db_path, facts=SemanticFacts(db_path))


def _passport(**overrides: object) -> ProjectPassportV1:
    payload = {
        "project_id": "proj-1",
        "goal": "ship the thing",
        "architecture_summary": "stack: python",
        "important_paths": ("aios/",),
        "commands": {"test": ("pytest",)},
        "environments": ("dev",),
        "known_risks": (),
        "verified_at_commit": "sha-a",
        "passport_digest": "a" * 64,
    }
    payload.update(overrides)
    return ProjectPassportV1(**payload)


# --- OperatorPreferenceStore -------------------------------------------------


def test_save_and_get_round_trips_a_preference(tmp_path: Path) -> None:
    store = _pref_store(tmp_path / "mem.db")

    result = store.save(_preference())

    assert result.saved is True
    fetched = store.get("pref-1")
    assert fetched is not None
    assert fetched.value is True
    assert fetched.domain == "testing"
    assert fetched.key == "prefers_pytest"
    assert fetched.confidence == 0.8
    assert fetched.source_type == "explicit_user"


def test_save_reuses_semantic_facts_contradiction_detection(tmp_path: Path) -> None:
    """The core write path is never duplicated -- a second preference on
    the same domain+key with a DIFFERENT value is a real contradiction,
    surfaced honestly (never silently overwritten), exactly as
    SemanticFacts.add_fact() already behaves for every other caller."""
    store = _pref_store(tmp_path / "mem.db")
    store.save(_preference(preference_id="pref-1", value=True))

    conflicting = store.save(_preference(preference_id="pref-2", value=False))

    assert conflicting.saved is False
    assert conflicting.reason == "contradiction"
    # The contradicting preference must not have silently landed.
    assert store.get("pref-2") is None
    # The original is untouched.
    assert store.get("pref-1").value is True


def test_save_is_idempotent_for_the_exact_same_preference(tmp_path: Path) -> None:
    store = _pref_store(tmp_path / "mem.db")
    store.save(_preference(valid_from="2026-01-01T00:00:00+00:00"))

    second = store.save(_preference(valid_from="2026-01-01T00:00:00+00:00"))

    assert second.saved is True
    assert store.get("pref-1") is not None


def test_resave_with_a_new_valid_from_does_not_false_positive_as_tampered(
    tmp_path: Path,
) -> None:
    """Regression: the sidecar's ON CONFLICT UPDATE originally omitted
    valid_from (and domain/key), so a genuine re-save with a fresh
    valid_from left the row's own column stale while record_digest moved
    on -- a false RecordTamperedError on the very next read, indicting an
    untampered row. valid_from defaults to "now" on every OperatorPreferenceV1
    construction, so two real saves of "the same" preference id will
    legitimately differ here in production."""
    store = _pref_store(tmp_path / "mem.db")
    store.save(_preference(valid_from="2026-01-01T00:00:00+00:00"))

    second = store.save(_preference(valid_from="2026-06-01T00:00:00+00:00"))

    assert second.saved is True
    fetched = store.get("pref-1")
    assert fetched is not None
    assert fetched.valid_from == "2026-06-01T00:00:00+00:00"


def test_resave_with_a_different_confidence_does_not_false_positive_as_tampered(
    tmp_path: Path,
) -> None:
    """Regression: SemanticFacts.add_fact()'s idempotent "exact triple
    already exists" path leaves the fact's STORED confidence untouched
    unless `approved_by` is passed (which this store never does) -- so
    re-saving "the same" preference (same value) with a genuinely different
    requested confidence previously digested the requested-but-not-applied
    confidence, permanently mismatching what `_reconstruct` reads back on
    every later `get()`."""
    store = _pref_store(tmp_path / "mem.db")
    store.save(_preference(confidence=0.6))

    second = store.save(_preference(confidence=0.9))

    assert second.saved is True
    fetched = store.get("pref-1")
    assert fetched is not None
    assert fetched.confidence == 0.6


def test_list_for_scope_never_returns_a_different_scope(tmp_path: Path) -> None:
    """Organ 27's leak-prevention gap: a preference observed in one project
    must never leak into another project's lookup."""
    store = _pref_store(tmp_path / "mem.db")
    store.save(
        _preference(
            preference_id="pref-a",
            domain="a",
            key="k",
            scope="project:ai-editor",
        )
    )
    store.save(
        _preference(
            preference_id="pref-b",
            domain="b",
            key="k",
            scope="project:other-repo",
        )
    )

    scoped = store.list_for_scope("project:ai-editor")

    assert {p.preference_id for p in scoped} == {"pref-a"}


def test_list_for_scope_empty_for_unknown_scope(tmp_path: Path) -> None:
    store = _pref_store(tmp_path / "mem.db")
    store.save(_preference())

    assert store.list_for_scope("project:no-such-project") == ()


def test_preference_tamper_is_detected_at_read_time(tmp_path: Path) -> None:
    db_path = tmp_path / "mem.db"
    store = _pref_store(db_path)
    store.save(_preference())

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE operator_preference_sidecar SET status = 'rejected' "
        "WHERE preference_id = 'pref-1'"
    )
    conn.commit()
    conn.close()

    with pytest.raises(RecordTamperedError):
        store.get("pref-1")


def test_get_returns_none_for_unknown_preference(tmp_path: Path) -> None:
    store = _pref_store(tmp_path / "mem.db")
    assert store.get("no-such-id") is None


def test_store_shares_the_same_semantic_facts_table_as_direct_callers(
    tmp_path: Path,
) -> None:
    """Confirms this is genuinely a thin adapter, not a parallel/competing
    persistence layer: a fact written through the store is visible to a
    plain SemanticFacts caller on the same database, and vice versa. The
    subject includes scope (organ 27's cross-scope contradiction fix,
    below), so it is `operator.<scope>.<domain>.<key>`, not bare
    `operator.<domain>.<key>`."""
    db_path = tmp_path / "mem.db"
    store = _pref_store(db_path)
    store.save(_preference(domain="d", key="k", value="v", scope="project:ai-editor"))

    direct_facts = SemanticFacts(db_path)
    rows = direct_facts.facts_for("operator.project:ai-editor.d.k")
    assert len(rows) == 1
    assert rows[0]["object"] == '"v"'


def test_same_domain_and_key_across_different_scopes_are_not_a_false_contradiction(
    tmp_path: Path,
) -> None:
    """Organ 27: `list_for_scope` already isolates preferences by scope, but
    the contradiction-check subject previously omitted scope entirely
    (`operator.<domain>.<key>`) -- two different projects wanting different
    values for the same domain+key would spuriously collide as a
    "contradiction" the instant they disagreed, even though they were never
    really in conflict. Scope is now part of that subject."""
    store = _pref_store(tmp_path / "mem.db")

    first = store.save(
        _preference(
            preference_id="pref-a",
            domain="editor",
            key="tab_width",
            value=2,
            scope="project:a",
        )
    )
    second = store.save(
        _preference(
            preference_id="pref-b",
            domain="editor",
            key="tab_width",
            value=4,
            scope="project:b",
        )
    )

    assert first.saved is True
    assert second.saved is True
    assert store.get("pref-a").value == 2
    assert store.get("pref-b").value == 4


# --- OperatorPreferenceStore: withdrawal, expiry, active feed, restart ------


def test_withdraw_marks_status_withdrawn(tmp_path: Path) -> None:
    store = _pref_store(tmp_path / "mem.db")
    store.save(_preference(status="active"))

    withdrawn = store.withdraw("pref-1")

    assert withdrawn is True
    fetched = store.get("pref-1")
    assert fetched is not None
    assert fetched.status == "withdrawn"


def test_withdraw_returns_false_for_an_unknown_preference(tmp_path: Path) -> None:
    store = _pref_store(tmp_path / "mem.db")
    assert store.withdraw("no-such-id") is False


def test_withdraw_does_not_fabricate_success_and_is_idempotent(tmp_path: Path) -> None:
    store = _pref_store(tmp_path / "mem.db")
    store.save(_preference(status="active"))

    first = store.withdraw("pref-1")
    second = store.withdraw("pref-1")

    assert first is True
    assert second is True
    assert store.get("pref-1").status == "withdrawn"


def test_list_active_for_scope_excludes_non_active_status(tmp_path: Path) -> None:
    store = _pref_store(tmp_path / "mem.db")
    store.save(
        _preference(
            preference_id="pref-active",
            domain="a",
            key="k1",
            scope="project:ai-editor",
            status="active",
        )
    )
    store.save(
        _preference(
            preference_id="pref-proposed",
            domain="b",
            key="k2",
            scope="project:ai-editor",
            status="proposed",
        )
    )

    active = store.list_active_for_scope("project:ai-editor")

    assert {p.preference_id for p in active} == {"pref-active"}


def test_list_active_for_scope_never_returns_a_different_scope(tmp_path: Path) -> None:
    store = _pref_store(tmp_path / "mem.db")
    store.save(
        _preference(
            preference_id="pref-a",
            domain="a",
            key="k",
            scope="project:a",
            status="active",
        )
    )
    store.save(
        _preference(
            preference_id="pref-b",
            domain="b",
            key="k",
            scope="project:b",
            status="active",
        )
    )

    assert {p.preference_id for p in store.list_active_for_scope("project:a")} == {
        "pref-a"
    }


def test_operator_preference_store_survives_a_restart(tmp_path: Path) -> None:
    """Organ 27's own restart-recovery requirement: a fresh store instance
    over the SAME db path must see everything the first instance wrote,
    exactly like every other durable store in this file."""
    db_path = tmp_path / "mem.db"
    first_store = _pref_store(db_path)
    first_store.save(_preference(status="active"))

    second_store = _pref_store(db_path)
    restored = second_store.get("pref-1")

    assert restored is not None
    assert restored.value is True
    assert restored.status == "active"
    assert second_store.list_active_for_scope("project:ai-editor")[0].preference_id == (
        "pref-1"
    )


# --- ProjectPassportStore ----------------------------------------------------


def test_save_and_get_current_round_trips_a_passport(tmp_path: Path) -> None:
    store = ProjectPassportStore(tmp_path / "mem.db")

    revision = store.save(_passport())

    assert revision == 1
    current = store.get_current("proj-1")
    assert current is not None
    assert current.goal == "ship the thing"
    assert current.commands == {"test": ("pytest",)}


def test_save_is_append_only_across_restarts(tmp_path: Path) -> None:
    """A durable store persists across process restarts -- this organ's own
    stated gap. A fresh store instance over the same file must see the same
    history a prior instance wrote."""
    db_path = tmp_path / "mem.db"
    first_process = ProjectPassportStore(db_path)
    first_process.save(_passport(verified_at_commit="sha-a"))
    first_process.save(_passport(verified_at_commit="sha-b"))

    restarted_process = ProjectPassportStore(db_path)
    history = restarted_process.get_history("proj-1")

    assert [p.verified_at_commit for p in history] == ["sha-a", "sha-b"]
    assert restarted_process.get_current("proj-1").verified_at_commit == "sha-b"


def test_different_projects_do_not_share_revision_numbering(tmp_path: Path) -> None:
    store = ProjectPassportStore(tmp_path / "mem.db")
    store.save(_passport(project_id="proj-a"))
    revision = store.save(_passport(project_id="proj-b"))

    assert revision == 1


def test_get_current_is_none_for_unknown_project(tmp_path: Path) -> None:
    store = ProjectPassportStore(tmp_path / "mem.db")
    assert store.get_current("no-such-project") is None
    assert store.get_history("no-such-project") == ()


def test_passport_tamper_is_detected_at_read_time(tmp_path: Path) -> None:
    db_path = tmp_path / "mem.db"
    store = ProjectPassportStore(db_path)
    store.save(_passport())

    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE project_passports SET goal = 'tampered'")
    conn.commit()
    conn.close()

    with pytest.raises(RecordTamperedError):
        store.get_current("proj-1")


def test_active_project_pointer_survives_a_restart(tmp_path: Path) -> None:
    """Organ 28's own named gap: previously "which project was last
    scanned" lived only in a process-local module global in
    routes/projects.py, forgotten on every restart even though the real
    scan history was already durable."""
    db_path = tmp_path / "mem.db"
    first_process = ProjectPassportStore(db_path)
    first_process.set_active("proj-1", {"root": "/repo", "purpose": "demo"})

    restarted_process = ProjectPassportStore(db_path)
    active = restarted_process.get_active()

    assert active == ("proj-1", {"root": "/repo", "purpose": "demo"})


def test_active_project_pointer_is_none_when_nothing_ever_scanned(
    tmp_path: Path,
) -> None:
    store = ProjectPassportStore(tmp_path / "mem.db")
    assert store.get_active() is None


def test_active_project_pointer_is_a_true_singleton_not_a_history(
    tmp_path: Path,
) -> None:
    """This system tracks one active project at a time, matching the
    existing routes' own single-workspace design -- setting a new active
    project replaces the pointer, it does not append to a history."""
    store = ProjectPassportStore(tmp_path / "mem.db")
    store.set_active("proj-1", {"root": "/repo-a"})
    store.set_active("proj-2", {"root": "/repo-b"})

    assert store.get_active() == ("proj-2", {"root": "/repo-b"})


# --- HumanStateHypothesisStore (organ 30) ------------------------------------


def _hypothesis(**overrides: object) -> HumanStateHypothesis:
    payload = {
        "state": "frustrated",
        "confidence": 0.6,
        "visible_reason": "message contains repeated-complaint markers",
    }
    payload.update(overrides)
    return HumanStateHypothesis(**payload)


def test_save_and_get_history_round_trips_a_hypothesis(tmp_path: Path) -> None:
    store = HumanStateHypothesisStore(tmp_path / "mem.db")

    store.save("session-1", "turn-1", _hypothesis())

    history = store.get_history("session-1")
    assert len(history) == 1
    turn_id, hypothesis = history[0]
    assert turn_id == "turn-1"
    assert hypothesis.state == "frustrated"
    assert hypothesis.confidence == 0.6
    assert hypothesis.user_correctable is True
    assert hypothesis.grants_authority is False


def test_history_is_append_only_and_ordered_oldest_first(tmp_path: Path) -> None:
    db_path = tmp_path / "mem.db"
    store = HumanStateHypothesisStore(db_path)
    store.save("session-1", "turn-1", _hypothesis(state="neutral", confidence=0.3))
    store.save("session-1", "turn-2", _hypothesis(state="rushed", confidence=0.6))

    restarted = HumanStateHypothesisStore(db_path)
    history = restarted.get_history("session-1")

    assert [(t, h.state) for t, h in history] == [
        ("turn-1", "neutral"),
        ("turn-2", "rushed"),
    ]


def test_different_sessions_do_not_leak_into_each_others_history(
    tmp_path: Path,
) -> None:
    store = HumanStateHypothesisStore(tmp_path / "mem.db")
    store.save("session-a", "turn-1", _hypothesis())
    store.save("session-b", "turn-1", _hypothesis(state="decisive", confidence=0.55))

    assert [h.state for _, h in store.get_history("session-a")] == ["frustrated"]
    assert [h.state for _, h in store.get_history("session-b")] == ["decisive"]


def test_history_empty_for_unknown_session(tmp_path: Path) -> None:
    store = HumanStateHypothesisStore(tmp_path / "mem.db")
    assert store.get_history("no-such-session") == ()


def test_hypothesis_tamper_is_detected_at_read_time(tmp_path: Path) -> None:
    db_path = tmp_path / "mem.db"
    store = HumanStateHypothesisStore(db_path)
    store.save("session-1", "turn-1", _hypothesis())

    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE human_state_hypotheses SET state = 'neutral'")
    conn.commit()
    conn.close()

    with pytest.raises(RecordTamperedError):
        store.get_history("session-1")


def test_record_correction_returns_true_and_is_visible_via_accuracy_report(
    tmp_path: Path,
) -> None:
    store = HumanStateHypothesisStore(tmp_path / "mem.db")
    store.save("session-1", "turn-1", _hypothesis(state="frustrated"))

    corrected = store.record_correction("session-1", "turn-1", "neutral")

    assert corrected is True
    report = store.accuracy_report()
    assert report.total_corrected == 1
    assert report.agreements == 0
    assert report.accuracy == 0.0
    assert report.by_state == {"frustrated": {"total": 1, "agreements": 0}}


def test_record_correction_unknown_turn_returns_false_not_an_error(
    tmp_path: Path,
) -> None:
    store = HumanStateHypothesisStore(tmp_path / "mem.db")
    assert store.record_correction("session-1", "no-such-turn", "neutral") is False


def test_record_correction_does_not_change_the_stored_hypothesis_or_its_digest(
    tmp_path: Path,
) -> None:
    """A correction records ground truth alongside the original hypothesis --
    it must never rewrite history or trip tamper detection."""
    store = HumanStateHypothesisStore(tmp_path / "mem.db")
    store.save("session-1", "turn-1", _hypothesis(state="frustrated", confidence=0.6))

    store.record_correction("session-1", "turn-1", "neutral")

    turn_id, hypothesis = store.get_history("session-1")[0]
    assert turn_id == "turn-1"
    assert hypothesis.state == "frustrated"  # unchanged -- the original guess
    assert hypothesis.confidence == 0.6


def test_accuracy_report_empty_when_nothing_corrected_yet(tmp_path: Path) -> None:
    store = HumanStateHypothesisStore(tmp_path / "mem.db")
    store.save("session-1", "turn-1", _hypothesis())

    report = store.accuracy_report()

    assert report.total_corrected == 0
    assert report.agreements == 0
    assert report.accuracy is None
    assert report.by_state == {}


def test_accuracy_report_aggregates_agreements_and_disagreements_per_state(
    tmp_path: Path,
) -> None:
    store = HumanStateHypothesisStore(tmp_path / "mem.db")
    store.save("session-1", "turn-1", _hypothesis(state="frustrated"))
    store.save("session-1", "turn-2", _hypothesis(state="frustrated"))
    store.save("session-1", "turn-3", _hypothesis(state="neutral", confidence=0.3))

    store.record_correction("session-1", "turn-1", "frustrated")  # agree
    store.record_correction("session-1", "turn-2", "rushed")  # disagree
    store.record_correction("session-1", "turn-3", "neutral")  # agree
    # turn-4 never saved/corrected -- must not appear anywhere in the report

    report = store.accuracy_report()

    assert report.total_corrected == 3
    assert report.agreements == 2
    assert report.accuracy == pytest.approx(2 / 3)
    assert report.by_state == {
        "frustrated": {"total": 2, "agreements": 1},
        "neutral": {"total": 1, "agreements": 1},
    }


def test_recorrecting_the_same_turn_replaces_the_prior_correction(
    tmp_path: Path,
) -> None:
    store = HumanStateHypothesisStore(tmp_path / "mem.db")
    store.save("session-1", "turn-1", _hypothesis(state="frustrated"))

    store.record_correction("session-1", "turn-1", "rushed")
    store.record_correction("session-1", "turn-1", "neutral")

    report = store.accuracy_report()
    assert report.total_corrected == 1
    assert report.by_state == {"frustrated": {"total": 1, "agreements": 0}}


def test_accuracy_report_does_not_collapse_two_hypotheses_with_identical_content(
    tmp_path: Path,
) -> None:
    """Regression test: two turns classified identically (same state,
    confidence, and visible_reason) share a content digest -- the join
    that measures accuracy must key off the hypothesis's real row id, not
    its digest, or these two distinct corrections silently fold into one."""
    store = HumanStateHypothesisStore(tmp_path / "mem.db")
    store.save("session-1", "turn-1", _hypothesis(state="frustrated"))
    store.save("session-1", "turn-2", _hypothesis(state="frustrated"))

    store.record_correction("session-1", "turn-1", "frustrated")  # agree
    store.record_correction("session-1", "turn-2", "rushed")  # disagree

    report = store.accuracy_report()
    assert report.total_corrected == 2
    assert report.agreements == 1
    assert report.by_state == {"frustrated": {"total": 2, "agreements": 1}}


def test_correction_is_stored_append_only_with_operator_id_and_hypothesis_link(
    tmp_path: Path,
) -> None:
    store = HumanStateHypothesisStore(tmp_path / "mem.db")
    store.save("session-1", "turn-1", _hypothesis(state="frustrated", confidence=0.6))

    store.record_correction("session-1", "turn-1", "neutral", operator_id="operator-9")

    corrections = store.get_corrections("session-1", "turn-1")
    assert len(corrections) == 1
    assert corrections[0]["correctedState"] == "neutral"
    assert corrections[0]["operatorId"] == "operator-9"
    assert len(corrections[0]["hypothesisDigest"]) == 64


def test_correction_without_operator_id_records_none_not_a_fabricated_value(
    tmp_path: Path,
) -> None:
    store = HumanStateHypothesisStore(tmp_path / "mem.db")
    store.save("session-1", "turn-1", _hypothesis())

    store.record_correction("session-1", "turn-1", "neutral")

    corrections = store.get_corrections("session-1", "turn-1")
    assert corrections[0]["operatorId"] is None


def test_recorrecting_the_same_turn_keeps_both_corrections_in_history(
    tmp_path: Path,
) -> None:
    """append-only means the prior correction is retained, even though
    accuracy_report() (and the durable "current" ground truth) only counts
    the newest one."""
    store = HumanStateHypothesisStore(tmp_path / "mem.db")
    store.save("session-1", "turn-1", _hypothesis(state="frustrated"))

    store.record_correction("session-1", "turn-1", "rushed")
    store.record_correction("session-1", "turn-1", "neutral")

    corrections = store.get_corrections("session-1", "turn-1")
    assert [c["correctedState"] for c in corrections] == ["rushed", "neutral"]


def test_get_corrections_empty_for_a_turn_with_no_correction(tmp_path: Path) -> None:
    store = HumanStateHypothesisStore(tmp_path / "mem.db")
    store.save("session-1", "turn-1", _hypothesis())
    assert store.get_corrections("session-1", "turn-1") == ()


def test_correction_tamper_is_detected_at_read_time(tmp_path: Path) -> None:
    """The bug this whole migration exists to fix: previously a correction
    was two mutable columns on the original hypothesis row, entirely
    outside that row's own tamper-detection digest -- altering
    corrected_state directly in the database was undetectable. Now a
    correction is its own digested, append-only row."""
    db_path = tmp_path / "mem.db"
    store = HumanStateHypothesisStore(db_path)
    store.save("session-1", "turn-1", _hypothesis(state="frustrated"))
    store.record_correction("session-1", "turn-1", "neutral", operator_id="operator-9")

    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE human_state_corrections SET corrected_state = 'decisive'")
    conn.commit()
    conn.close()

    with pytest.raises(RecordTamperedError):
        store.get_corrections("session-1", "turn-1")


# --- CorrectionRecordStore (organ 29) -----------------------------------


def test_correction_record_save_and_get_lineage_round_trips(tmp_path: Path) -> None:
    store = CorrectionRecordStore(tmp_path / "mem.db")
    store.save(_correction_record(operator_id="operator-9"))

    lineage = store.get_lineage("session-1")

    assert len(lineage) == 1
    assert lineage[0].correction_id == "correction:session-1:1"
    assert lineage[0].operator_id == "operator-9"
    assert lineage[0].grants_authority is False


def test_correction_record_without_operator_id_stores_none(tmp_path: Path) -> None:
    store = CorrectionRecordStore(tmp_path / "mem.db")
    store.save(_correction_record())

    lineage = store.get_lineage("session-1")

    assert lineage[0].operator_id is None


def test_correction_record_lineage_is_newest_first_and_append_only(
    tmp_path: Path,
) -> None:
    store = CorrectionRecordStore(tmp_path / "mem.db")
    store.save(
        _correction_record(
            correction_id="correction:session-1:1", correction_revision=1
        )
    )
    store.save(
        _correction_record(
            correction_id="correction:session-1:2", correction_revision=2
        )
    )

    lineage = store.get_lineage("session-1")

    assert [r.correction_id for r in lineage] == [
        "correction:session-1:2",
        "correction:session-1:1",
    ]


def test_correction_record_lineage_is_scoped_to_its_own_session(tmp_path: Path) -> None:
    store = CorrectionRecordStore(tmp_path / "mem.db")
    store.save(_correction_record(correction_id="c:a:1", session_id="session-a"))
    store.save(_correction_record(correction_id="c:b:1", session_id="session-b"))

    assert [r.correction_id for r in store.get_lineage("session-a")] == ["c:a:1"]
    assert [r.correction_id for r in store.get_lineage("session-b")] == ["c:b:1"]


def test_correction_record_lineage_empty_for_unknown_session(tmp_path: Path) -> None:
    store = CorrectionRecordStore(tmp_path / "mem.db")
    assert store.get_lineage("no-such-session") == ()


def test_correction_record_tamper_is_detected_at_read_time(tmp_path: Path) -> None:
    db_path = tmp_path / "mem.db"
    store = CorrectionRecordStore(db_path)
    store.save(_correction_record(operator_id="operator-9"))

    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE correction_records SET operator_id = 'someone-else'")
    conn.commit()
    conn.close()

    with pytest.raises(RecordTamperedError):
        store.get_lineage("session-1")
