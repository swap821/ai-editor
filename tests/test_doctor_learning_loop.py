"""The learning-loop doctor line.

It exists because the loop's yield was invisible: on 2026-09-07 the shipped
database held 4 playbooks with 2 replays between them, and discovering that
took a hand-written SQLite session. It is ADVISORY on purpose -- there is no
correct number, because the yield is a fact about how the system has been used
rather than a fault to fix.
"""

from __future__ import annotations

import sqlite3


from aios import config
from aios.operations.doctor import _learning_loop_check
from tests.source_rules import executable_source


def _seed(db, skills, playbooks) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE procedural_skills (
            id INTEGER PRIMARY KEY, status TEXT, success_count INTEGER DEFAULT 0);
        CREATE TABLE compiled_playbooks (
            id INTEGER PRIMARY KEY, status TEXT, replay_count INTEGER DEFAULT 0);
        """
    )
    conn.executemany(
        "INSERT INTO procedural_skills (status, success_count) VALUES (?,?)", skills
    )
    conn.executemany(
        "INSERT INTO compiled_playbooks (status, replay_count) VALUES (?,?)", playbooks
    )
    conn.commit()
    conn.close()


def test_it_reports_the_shape_of_what_was_learned(tmp_path, monkeypatch) -> None:
    db = tmp_path / "m.db"
    _seed(
        db,
        [("verified", 5), ("candidate", 1), ("candidate", 0), ("candidate", 3)],
        [("compiled", 2), ("decompiled", 0)],
    )
    monkeypatch.setattr(config, "MEMORY_DB_PATH", db)

    result = _learning_loop_check()

    assert result.required is False, "the learning-loop line must never block"
    assert "1 verified" in result.message
    assert "3 candidate" in result.message
    # Two candidates have <=1 success; the one with 3 is a different story.
    assert "2 seen once or never" in result.message
    assert "1 compiled" in result.message
    assert "2 replay(s)" in result.message


def test_it_never_blocks_even_when_nothing_was_learned(tmp_path, monkeypatch) -> None:
    """An empty loop is a new install, not a fault."""
    monkeypatch.setattr(config, "MEMORY_DB_PATH", tmp_path / "absent.db")

    result = _learning_loop_check()

    assert result.required is False
    assert result.status != "fatal"
    assert "nothing has been learned" in result.message


def test_a_broken_database_is_reported_not_raised(tmp_path, monkeypatch) -> None:
    """Doctor reports; it does not crash.

    A diagnostic that dies on a damaged database is useless at exactly the
    moment it is needed.
    """
    db = tmp_path / "junk.db"
    db.write_bytes(b"this is not a database")
    monkeypatch.setattr(config, "MEMORY_DB_PATH", db)

    result = _learning_loop_check()

    assert result.required is False
    assert "unavailable" in result.message


def test_it_opens_the_database_read_only(tmp_path, monkeypatch) -> None:
    """A diagnostic must not be able to modify what it is diagnosing."""

    source = executable_source(_learning_loop_check)

    assert "mode=ro" in source, "the doctor check can write to the memory database"
