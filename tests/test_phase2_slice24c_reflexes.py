"""Phase 2 slice 2.4c (reflexes): the reflex table speaks library identity, and
every reflex no operator activation backs is retired with a reason.

Operator decision (2026-09-25): playbooks are not copied into the library;
reflexes recompile from ACTIVE skills only and the existing ones are retired.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from aios.memory.db import get_connection, init_memory_db
from tests.test_phase2_reflex_gate import GOAL, _activate, _migrated, build_world
from tools import retire_legacy_playbooks as retire


@pytest.fixture()
def world(tmp_path: Path, monkeypatch):
    return build_world(tmp_path, monkeypatch)


_OLD_TABLE = """
    CREATE TABLE compiled_playbooks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        compiled_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        skill_id INTEGER NOT NULL REFERENCES procedural_skills(id),
        goal_pattern TEXT NOT NULL,
        signature_v2 TEXT,
        steps_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'compiled'
               CHECK (status IN ('compiled','decompiled')),
        replay_count INTEGER NOT NULL DEFAULT 0,
        consecutive_failures INTEGER NOT NULL DEFAULT 0,
        decompiled_at_successes INTEGER
    )
"""


def _legacy_store(tmp_path: Path) -> Path:
    """A store as it was before 2.4c: the reflex table references procedural_skills."""
    db = tmp_path / "memory.db"
    init_memory_db(db)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DROP TABLE compiled_playbooks")
    conn.execute(_OLD_TABLE)
    conn.execute(
        "INSERT INTO procedural_skills (id, signature, goal_pattern, steps_json, status) "
        "VALUES (7, 'sig', 'g', '[]', 'verified')"
    )
    for pid, status in ((3, "compiled"), (5, "decompiled")):
        conn.execute(
            "INSERT INTO compiled_playbooks (id, skill_id, goal_pattern, steps_json, status) "
            "VALUES (?, 7, 'g', '[]', ?)",
            (pid, status),
        )
    conn.commit()
    conn.close()
    return db


class TestTheReflexTableSpeaksLibraryIdentity:
    def test_the_migration_drops_the_legacy_key_and_keeps_every_row(
        self, tmp_path
    ) -> None:
        db = _legacy_store(tmp_path)
        init_memory_db(db)
        conn = sqlite3.connect(db)
        assert (
            conn.execute("PRAGMA foreign_key_list(compiled_playbooks)").fetchall() == []
        )
        rows = conn.execute(
            "SELECT id, status FROM compiled_playbooks ORDER BY id"
        ).fetchall()
        assert rows == [(3, "compiled"), (5, "decompiled")], "ids and rows preserved"
        conn.close()
        assert list(tmp_path.glob("*.pre-library-reflexes.bak")), "a backup comes first"

    def test_a_library_issued_id_can_now_be_compiled(self, tmp_path) -> None:
        db = _legacy_store(tmp_path)
        init_memory_db(db)
        with get_connection(db) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                "INSERT INTO compiled_playbooks (skill_id, goal_pattern, steps_json) "
                "VALUES (1000000001, 'g', '[]')"
            )
            conn.execute(
                "UPDATE compiled_playbooks SET status = 'retired', retired_reason = 'r' "
                "WHERE id = 3"
            )

    def test_positive_control_before_the_migration_it_could_not(self, tmp_path) -> None:
        db = _legacy_store(tmp_path)
        conn = sqlite3.connect(db)
        conn.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO compiled_playbooks (skill_id, goal_pattern, steps_json) "
                "VALUES (1000000001, 'g', '[]')"
            )
        conn.close()

    def test_it_runs_once(self, tmp_path) -> None:
        db = _legacy_store(tmp_path)
        init_memory_db(db)
        init_memory_db(db)
        assert len(list(tmp_path.glob("*.pre-library-reflexes.bak"))) == 1


class TestRetirement:
    def _paths(self, world):
        legacy_db, _cerebellum, _bus, repository, _dual = world
        return legacy_db, Path(repository.database)

    def test_an_unbacked_reflex_is_listed_for_retirement(self, world) -> None:
        memory_db, library_db = self._paths(world)
        to_retire, to_keep = retire.plan(memory_db, library_db)
        assert len(to_retire) == 1 and to_keep == []

    def test_a_reflex_the_operator_activated_is_kept(self, world) -> None:
        memory_db, library_db = self._paths(world)
        _activate(world[3], _migrated(world[3]))
        to_retire, to_keep = retire.plan(memory_db, library_db)
        assert to_retire == [] and len(to_keep) == 1

    def test_apply_retires_with_a_reason_a_journal_entry_and_a_backup(
        self, world, tmp_path
    ) -> None:
        memory_db, library_db = self._paths(world)
        to_retire, _ = retire.plan(memory_db, library_db)
        backup = retire.apply(memory_db, tmp_path / "bk", [r["id"] for r in to_retire])
        assert backup.is_file()
        conn = sqlite3.connect(memory_db)
        status, reason = conn.execute(
            "SELECT status, retired_reason FROM compiled_playbooks WHERE id = ?",
            (to_retire[0]["id"],),
        ).fetchone()
        journal = conn.execute(
            "SELECT transition, detail_json FROM learning_events WHERE faculty='L5' "
            "AND transition='retired'"
        ).fetchall()
        conn.close()
        assert status == "retired" and "operator-activated" in reason
        assert journal and "Phase 2.4c" in json.loads(journal[0][1])["reason"]
        assert retire.plan(memory_db, library_db)[0] == [], "nothing unbacked remains"

    def test_a_retired_reflex_never_replays(self, world, tmp_path) -> None:
        memory_db, _library_db = self._paths(world)
        cerebellum, repository, slot = world[1], world[3], world[4]
        cerebellum.attach_reflex_gate(slot)
        _activate(repository, _migrated(repository))
        assert cerebellum.match(GOAL, principal="principal:test") is not None, (
            "positive control: it replays"
        )
        # Retired by id: an activated reflex is one the plan KEEPS.
        ids = [row["id"] for row in cerebellum.playbook_map()]
        retire.apply(memory_db, tmp_path / "bk", ids)
        assert cerebellum.match(GOAL, principal="principal:test") is None

    def test_retirement_does_not_block_a_reflex_the_operator_later_activates(
        self, world, tmp_path
    ) -> None:
        memory_db, library_db = self._paths(world)
        _legacy_db, cerebellum, _bus, repository, slot = world
        to_retire, _ = retire.plan(memory_db, library_db)
        retire.apply(memory_db, tmp_path / "bk", [r["id"] for r in to_retire])
        cerebellum.attach_reflex_gate(slot)
        _activate(repository, _migrated(repository))
        assert cerebellum.try_compile_all() == 1, "a NEW reflex, from the activation"
        assert cerebellum.match(GOAL, principal="principal:test") is not None

    def test_the_stop_refuses_retirement(self, world, tmp_path, monkeypatch) -> None:
        from aios.application.governance.emergency_stop import EmergencyStopError
        from aios.memory import learning_freeze

        memory_db, library_db = self._paths(world)
        to_retire, _ = retire.plan(memory_db, library_db)

        def frozen(what):
            raise EmergencyStopError(f"learning frozen: {what}")

        monkeypatch.setattr(learning_freeze, "assert_learning_permitted", frozen)
        with pytest.raises(EmergencyStopError):
            retire.apply(memory_db, tmp_path / "bk", [r["id"] for r in to_retire])
        assert len(retire.plan(memory_db, library_db)[0]) == 1, "nothing was retired"


_MINIMAL_TABLE = """
    CREATE TABLE compiled_playbooks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        skill_id INTEGER NOT NULL REFERENCES procedural_skills(id),
        goal_pattern TEXT NOT NULL,
        steps_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'compiled'
            CHECK (status IN ('compiled','decompiled'))
    )
"""


class TestOlderTableShapes:
    """A store from before a column existed still migrates; one missing a column
    no default can supply is refused, not guessed at."""

    def _store(self, tmp_path: Path, table: str) -> Path:
        db = tmp_path / "memory.db"
        init_memory_db(db)
        conn = sqlite3.connect(db)
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DROP TABLE compiled_playbooks")
        conn.execute(table)
        conn.execute(
            "INSERT INTO procedural_skills (id, signature, goal_pattern, steps_json, "
            "status) VALUES (7, 'sig', 'g', '[]', 'verified')"
        )
        conn.commit()
        conn.close()
        return db

    def test_a_table_without_the_optional_columns_migrates(self, tmp_path) -> None:
        db = self._store(tmp_path, _MINIMAL_TABLE)
        conn = sqlite3.connect(db)
        conn.execute(
            "INSERT INTO compiled_playbooks (id, skill_id, goal_pattern, steps_json) "
            "VALUES (4, 7, 'g', '[]')"
        )
        conn.commit()
        conn.close()
        init_memory_db(db)
        conn = sqlite3.connect(db)
        row = conn.execute(
            "SELECT id, status, replay_count, consecutive_failures, retired_reason "
            "FROM compiled_playbooks"
        ).fetchone()
        conn.close()
        assert row == (4, "compiled", 0, 0, None)

    def test_a_table_missing_a_required_column_is_refused(self, tmp_path) -> None:
        db = self._store(
            tmp_path,
            _MINIMAL_TABLE.replace("        goal_pattern TEXT NOT NULL,\n", ""),
        )
        with pytest.raises(RuntimeError, match="goal_pattern"):
            init_memory_db(db)
