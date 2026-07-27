"""Organ 42: the transition journal is tamper-evident.

The journal recorded (mission_id, transition, sequence, recorded_at) and
nothing else, so a row could be edited, deleted or reordered on disk with no
way to tell. That is not only an audit gap: resumption reads this journal to
decide how far a mission actually got, so a silently altered row misdirects
recovery rather than merely misreporting it.

These tests do the tampering with raw SQL, deliberately bypassing the store's
own API -- an attacker with disk access does not politely call `append()`.
Each one proves a distinct failure the chain must catch: an edited row, a
deleted row, and a row whose own digest was recomputed to cover an edit (which
per-row digests alone would miss and only the chain link catches).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aios.infrastructure.missions.transition_journal_store import (
    JournalTamperedError,
    MissionTransitionJournal,
)


def _journal(tmp_path: Path) -> MissionTransitionJournal:
    return MissionTransitionJournal(tmp_path / "journal.db")


def _populate(journal: MissionTransitionJournal, mission_id: str = "m-1") -> None:
    journal.append(mission_id, "MISSION_CREATED")
    journal.append(mission_id, "APPROVED")
    journal.append(mission_id, "WORKSPACE_CREATED")


def _raw(journal: MissionTransitionJournal) -> sqlite3.Connection:
    conn = sqlite3.connect(str(journal.db_path))
    conn.row_factory = sqlite3.Row
    return conn


def test_an_untampered_journal_verifies_completely(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    _populate(journal)

    status = journal.verify_chain()

    assert status.verified == 3
    assert status.unverifiable_legacy == 0
    assert status.fully_verified is True


def test_the_chain_survives_a_restart(tmp_path: Path) -> None:
    """The chain is only useful if it verifies against a journal this process
    did not write -- that is the crash-recovery case it exists for."""
    _populate(_journal(tmp_path))

    reopened = MissionTransitionJournal(tmp_path / "journal.db")

    assert reopened.verify_chain().verified == 3


def test_an_edited_transition_is_detected(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    _populate(journal)

    with _raw(journal) as conn:
        conn.execute(
            "UPDATE mission_execution_transitions SET transition = 'COMPLETED' "
            "WHERE transition = 'WORKSPACE_CREATED'"
        )
        conn.commit()

    with pytest.raises(JournalTamperedError, match="does not match its own digest"):
        journal.verify_chain()


def test_an_edited_timestamp_is_detected(tmp_path: Path) -> None:
    """`recorded_at` is part of the digest: back-dating a transition would
    otherwise rewrite the timeline a recovery reads without leaving a trace."""
    journal = _journal(tmp_path)
    _populate(journal)

    with _raw(journal) as conn:
        conn.execute(
            "UPDATE mission_execution_transitions "
            "SET recorded_at = '1999-01-01T00:00:00+00:00' WHERE sequence = 1"
        )
        conn.commit()

    with pytest.raises(JournalTamperedError, match="does not match its own digest"):
        journal.verify_chain()


def test_a_deleted_row_is_detected(tmp_path: Path) -> None:
    """The case per-row digests cannot catch: every surviving row still
    matches its own content, and only the broken link reveals the deletion."""
    journal = _journal(tmp_path)
    _populate(journal)

    with _raw(journal) as conn:
        conn.execute(
            "DELETE FROM mission_execution_transitions WHERE transition = 'APPROVED'"
        )
        conn.commit()

    with pytest.raises(JournalTamperedError, match="chain broken"):
        journal.verify_chain()


def test_a_forged_row_digest_still_breaks_the_chain(tmp_path: Path) -> None:
    """The strongest case. An attacker who edits a row AND recomputes that
    row's own digest defeats per-row verification entirely. The link to the
    following row is what still gives them away, because they would have to
    rewrite every subsequent row too."""
    journal = _journal(tmp_path)
    _populate(journal)

    from aios.infrastructure.missions.transition_journal_store import _entry_digest

    with _raw(journal) as conn:
        row = conn.execute(
            "SELECT * FROM mission_execution_transitions WHERE sequence = 1"
        ).fetchone()
        forged = _entry_digest(
            mission_id=row["mission_id"],
            transition="COMPLETED",
            sequence=row["sequence"],
            recorded_at=row["recorded_at"],
            previous_entry_digest=row["previous_entry_digest"],
        )
        conn.execute(
            "UPDATE mission_execution_transitions "
            "SET transition = 'COMPLETED', entry_digest = ? WHERE sequence = 1",
            (forged,),
        )
        conn.commit()

    # The edited row now verifies against itself; the NEXT row's link does not.
    with pytest.raises(JournalTamperedError, match="chain broken"):
        journal.verify_chain()


def test_legacy_rows_are_reported_not_silently_passed(tmp_path: Path) -> None:
    """Rows written before migration 0023 carry no digest and cannot be
    retro-signed without inventing evidence. They must be surfaced as
    unverifiable, never counted as verified -- claiming otherwise would be
    exactly the fabricated-assurance failure this ledger exists to prevent.

    Models the real upgrade shape: undigested rows already on disk, then new
    rows appended through the store afterwards. Those new rows chain from
    nothing, because the head lookup ignores undigested rows.
    """
    journal = _journal(tmp_path)

    with _raw(journal) as conn:
        conn.executemany(
            "INSERT INTO mission_execution_transitions "
            "(mission_id, transition, sequence, recorded_at) VALUES (?, ?, ?, ?)",
            [
                ("m-legacy", "MISSION_CREATED", 0, "2026-01-01T00:00:00+00:00"),
                ("m-legacy", "APPROVED", 1, "2026-01-01T00:00:01+00:00"),
            ],
        )
        conn.commit()

    _populate(journal, "m-1")

    status = journal.verify_chain()

    assert status.unverifiable_legacy == 2
    assert status.verified == 3
    assert status.fully_verified is False


def test_tampering_with_a_digested_row_is_caught_despite_legacy_rows(
    tmp_path: Path,
) -> None:
    """Legacy rows must not become a blind spot: their presence cannot excuse
    a later, genuinely digested row from verification."""
    journal = _journal(tmp_path)
    with _raw(journal) as conn:
        conn.execute(
            "INSERT INTO mission_execution_transitions "
            "(mission_id, transition, sequence, recorded_at) VALUES (?, ?, ?, ?)",
            ("m-legacy", "MISSION_CREATED", 0, "2026-01-01T00:00:00+00:00"),
        )
        conn.commit()
    _populate(journal, "m-1")

    with _raw(journal) as conn:
        conn.execute(
            "UPDATE mission_execution_transitions SET transition = 'COMPLETED' "
            "WHERE mission_id = 'm-1' AND sequence = 2"
        )
        conn.commit()

    with pytest.raises(JournalTamperedError, match="does not match its own digest"):
        journal.verify_chain()


def test_the_chain_spans_missions(tmp_path: Path) -> None:
    """A per-mission chain would not notice one whole mission's rows being
    dropped. The chain is journal-wide precisely so that it does."""
    journal = _journal(tmp_path)
    _populate(journal, "m-1")
    _populate(journal, "m-2")
    assert journal.verify_chain().verified == 6

    with _raw(journal) as conn:
        conn.execute("DELETE FROM mission_execution_transitions WHERE mission_id = ?", ("m-1",))
        conn.commit()

    with pytest.raises(JournalTamperedError, match="chain broken"):
        journal.verify_chain()
