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
    assert "legacy history (read-only) 1 verified / 3 candidate" in result.message
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


def _library(path, *records) -> None:
    import json as _json

    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE institutional_skills (skill_id TEXT, version INTEGER, "
        "payload_json TEXT, PRIMARY KEY (skill_id, version))"
    )
    for skill_id, state, ok, provenance in records:
        payload = {
            "skill_id": skill_id,
            "version": 1,
            "problem_signature": "g",
            "applicability_conditions": {},
            "known_exclusions": [],
            "required_inputs": [],
            "required_project_state": {},
            "procedure": "[]",
            "allowed_tools": [],
            "allowed_scope_pattern": "",
            "expected_observations": [],
            "verification_plan": None,
            "escalation_conditions": [],
            "source_trajectory_ids": [],
            "confidence": 0.8,
            "success_count": ok,
            "failure_count": 0,
            "last_validated_versions": [],
            "state": state,
            "created_at": "2026-09-27T00:00:00+00:00",
            "updated_at": "2026-09-27T00:00:00+00:00",
            "provenance": provenance,
        }
        conn.execute(
            "INSERT INTO institutional_skills VALUES (?, 1, ?)",
            (skill_id, _json.dumps(payload)),
        )
    conn.commit()
    conn.close()


class TestTheSkillLibraryLeads:
    """Phase 2 slice 2.4c-B: the institutional library is the skill store."""

    def test_nothing_active_says_recall_and_reflexes_are_quiet(
        self, tmp_path, monkeypatch
    ) -> None:
        db = tmp_path / "m.db"
        _seed(db, [("verified", 5)], [("compiled", 2)])
        library = tmp_path / "op.db"
        _library(
            library,
            ("a", "candidate", 4, {"source": "migrated", "review_ready": "true"}),
            ("b", "candidate", 4, {"source": "migrated", "review_ready": "false"}),
        )
        before = library.read_bytes()
        monkeypatch.setattr(config, "MEMORY_DB_PATH", db)
        monkeypatch.setattr(config, "OPERATIONAL_STATE_DB_PATH", library)

        message = _learning_loop_check().message

        assert message.startswith(
            "skill library 0 active / 2 candidate (1 review-ready)"
        )
        assert (
            "recall and reflexes are quiet until the operator activates a skill"
            in message
        )
        assert message.index("skill library") < message.index(
            "legacy history (read-only)"
        ), "the library leads; the legacy store is labelled history"
        assert library.read_bytes() == before, "the doctor must not write the library"

    def test_an_active_skill_is_not_called_quiet(self, tmp_path, monkeypatch) -> None:
        db = tmp_path / "m.db"
        _seed(db, [], [])
        library = tmp_path / "op.db"
        _library(library, ("a", "active", 4, {"source": "migrated"}))
        monkeypatch.setattr(config, "MEMORY_DB_PATH", db)
        monkeypatch.setattr(config, "OPERATIONAL_STATE_DB_PATH", library)

        message = _learning_loop_check().message

        assert message.startswith("skill library 1 active / 0 candidate")
        assert "quiet" not in message

    def test_an_absent_library_is_said_plainly(self, tmp_path, monkeypatch) -> None:
        db = tmp_path / "m.db"
        _seed(db, [], [])
        monkeypatch.setattr(config, "MEMORY_DB_PATH", db)
        monkeypatch.setattr(config, "OPERATIONAL_STATE_DB_PATH", tmp_path / "none.db")

        message = _learning_loop_check().message

        assert message.startswith("no skill library yet")
        assert not (tmp_path / "none.db").exists()

    def test_a_broken_library_is_reported_not_raised(
        self, tmp_path, monkeypatch
    ) -> None:
        db = tmp_path / "m.db"
        _seed(db, [], [])
        junk = tmp_path / "op.db"
        junk.write_bytes(b"not a database at all" * 50)
        monkeypatch.setattr(config, "MEMORY_DB_PATH", db)
        monkeypatch.setattr(config, "OPERATIONAL_STATE_DB_PATH", junk)

        result = _learning_loop_check()

        assert result.required is False
        assert "skill library unavailable" in result.message
