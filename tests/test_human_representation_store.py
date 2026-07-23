"""Tier-1 closure pass, organs 27/28: durable persistence for
OperatorPreferenceV1 (a thin adapter over the existing SemanticFacts store)
and ProjectPassportV1 (a genuinely new append-only history store).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aios.domain.memory.human_representation import (
    HumanStateHypothesis,
    OperatorPreferenceV1,
    ProjectPassportV1,
)
from aios.infrastructure.memory.human_representation_store import (
    HumanStateHypothesisStore,
    OperatorPreferenceStore,
    ProjectPassportStore,
    RecordTamperedError,
)
from aios.memory.facts import SemanticFacts


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

    conflicting = store.save(
        _preference(preference_id="pref-2", value=False)
    )

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
    plain SemanticFacts caller on the same database, and vice versa."""
    db_path = tmp_path / "mem.db"
    store = _pref_store(db_path)
    store.save(_preference(domain="d", key="k", value="v"))

    direct_facts = SemanticFacts(db_path)
    rows = direct_facts.facts_for("operator.d.k")
    assert len(rows) == 1
    assert rows[0]["object"] == '"v"'


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
