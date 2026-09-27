"""Organ 55's M2 must not conclude anything about a trusted-memory store it never read.

M2 asks whether a model claim reached trusted memory without being earned. Its
adjudicator already returns ``unproven`` when memory was not sourced -- but the
collector declared memory sourced whenever a reader was ATTACHED, and the reader
answered an unreadable store (missing file, missing table) with "no rows". So
M2 could pass on a store it never saw. Found 2026-09-27 while mapping Phase 2
slice 2.4, which will retire the table M2 reads.

The opposite failure is pinned too: an unread BASELINE is empty, which would
make every verified row already in the store look like a write the mission made.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aios.application.governance.governance_observation import (
    GovernanceObservationCollector,
    MemoryUnreadable,
    VerifiedMemoryReader,
)
from aios.memory.db import init_memory_db
from tools.governance_conformance_runner import _adjudicate_m2


def _store(tmp_path: Path) -> Path:
    db = tmp_path / "memory.db"
    init_memory_db(db)
    return db


def _add_verified_skill(db: Path, signature: str, strength: str | None) -> None:
    conn = sqlite3.connect(db)
    try:
        with conn:
            conn.execute(
                "INSERT INTO procedural_skills (signature, goal_pattern, steps_json, "
                "status, verification_strength) VALUES (?, 'g', '[]', 'verified', ?)",
                (signature, strength),
            )
    finally:
        conn.close()


class _SwitchableReader:
    """A real reader whose store can become unreadable mid-window."""

    def __init__(self, db: Path) -> None:
        self.db = db
        self.readable = True

    def _reader(self) -> VerifiedMemoryReader:
        path = self.db if self.readable else self.db.with_name("gone.db")
        return VerifiedMemoryReader(path)

    def verified_ids(self):
        return self._reader().verified_ids()

    def verified_since(self, baseline):
        return self._reader().verified_since(baseline)


class TestTheReaderSaysWhenItCannotRead:
    def test_a_missing_store_is_unread_and_not_created(self, tmp_path: Path) -> None:
        missing = tmp_path / "nowhere.db"
        with pytest.raises(MemoryUnreadable):
            VerifiedMemoryReader(missing).verified_ids()
        assert not missing.exists(), "reading must never create an empty store"

    def test_a_missing_table_is_unread_not_empty(self, tmp_path: Path) -> None:
        db = tmp_path / "partial.db"
        sqlite3.connect(db).close()  # a real file with no tables
        with pytest.raises(MemoryUnreadable):
            VerifiedMemoryReader(db).verified_ids()

    def test_a_file_that_is_not_a_store_is_unread(self, tmp_path: Path) -> None:
        db = tmp_path / "corrupt.db"
        db.write_bytes(b"this is not a sqlite database" * 64)
        with pytest.raises(MemoryUnreadable):
            VerifiedMemoryReader(db).verified_ids()

    def test_a_store_the_os_will_not_open_is_unread(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Permissions, a lock, a dropped share: the open itself fails."""
        db = _store(tmp_path)

        def refuse(*_args, **_kwargs):
            raise sqlite3.OperationalError("unable to open database file")

        monkeypatch.setattr(sqlite3, "connect", refuse)
        with pytest.raises(MemoryUnreadable):
            VerifiedMemoryReader(db).verified_ids()

    def test_positive_control_a_real_store_reads(self, tmp_path: Path) -> None:
        db = _store(tmp_path)
        _add_verified_skill(db, "s1", "STRONG")
        assert VerifiedMemoryReader(db).verified_ids() == {("procedural_skills", 1)}


def _window(reader, *, readable_at_start: bool, readable_at_end: bool, during=None):
    collector = GovernanceObservationCollector(memory_reader=reader)
    reader.readable = readable_at_start
    snapshot = collector.begin()
    if during is not None:
        during()
    reader.readable = readable_at_end
    return collector.collect(snapshot)


class TestM2OnlyConcludesFromARealRead:
    def test_an_unreadable_store_is_unproven_not_clean(self, tmp_path: Path) -> None:
        reader = _SwitchableReader(_store(tmp_path))
        obs = _window(reader, readable_at_start=False, readable_at_end=False)
        assert "memory" not in obs.collected
        verdict = _adjudicate_m2(obs)
        assert verdict.outcome == "unproven"
        assert "trusted memory was not read" in verdict.reason

    def test_a_store_lost_during_the_window_is_unproven(self, tmp_path: Path) -> None:
        reader = _SwitchableReader(_store(tmp_path))
        obs = _window(reader, readable_at_start=True, readable_at_end=False)
        assert "memory" not in obs.collected
        verdict = _adjudicate_m2(obs)
        assert verdict.outcome == "unproven"
        assert "trusted memory was not read" in verdict.reason

    def test_an_unread_baseline_does_not_fabricate_writes(self, tmp_path: Path) -> None:
        """Pre-existing verified rows must not be blamed on the mission."""
        db = _store(tmp_path)
        _add_verified_skill(db, "old-unearned", None)
        reader = _SwitchableReader(db)
        obs = _window(reader, readable_at_start=False, readable_at_end=True)
        assert "memory" not in obs.collected
        verdict = _adjudicate_m2(obs)
        assert verdict.outcome == "unproven"
        assert "trusted memory was not read" in verdict.reason

    def test_positive_control_an_unearned_write_is_caught(self, tmp_path: Path) -> None:
        db = _store(tmp_path)
        reader = _SwitchableReader(db)
        obs = _window(
            reader,
            readable_at_start=True,
            readable_at_end=True,
            during=lambda: _add_verified_skill(db, "claimed", None),
        )
        assert "memory" in obs.collected
        assert _adjudicate_m2(obs).outcome == "failed"

    def test_positive_control_a_clean_window_is_read(self, tmp_path: Path) -> None:
        db = _store(tmp_path)
        _add_verified_skill(db, "old-earned", "STRONG")
        reader = _SwitchableReader(db)
        obs = _window(reader, readable_at_start=True, readable_at_end=True)
        assert "memory" in obs.collected
        assert obs.memory_writes == ()
        # M2 may still be unproven for another reason (no verification event
        # in this window), but never because memory went unread.
        assert "trusted memory was not read" not in _adjudicate_m2(obs).reason
