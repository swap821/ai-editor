"""Phase 2 slice 2.4c-B: the skill library is the only skill store.

Operator decision (2026-09-25), carried out 2026-09-28: the institutional
library, which organ 43 governs, is the live skill store. The dual-write pilot
and ``AIOS_SKILL_STORE_MODE`` are gone, nothing promotes itself, and the legacy
``procedural_skills`` table is read-only history.
"""

from __future__ import annotations

import ast
import logging
import sqlite3
from pathlib import Path

import pytest

from aios import config
from aios.application.governance.emergency_stop import (
    EmergencyStopController,
    EmergencyStopError,
    EmergencyStopHooks,
)
from aios.application.memory.bootstrap import build_memory_authority
from aios.application.memory.institutional_skills import (
    LIBRARY_ID_BASE,
    SkillMigrationPendingError,
    SkillTrailIndex,
    build_skills_slot,
)
from aios.core.verification_strength import VerificationStrength
from aios.domain.governance.contracts import EmergencyStopRequest
from aios.domain.learning.repository import SkillRepository
from aios.memory import learning_freeze
from aios.memory.db import init_memory_db
from aios.memory.skills import ReadOnlySkillHistoryError, SkillMemory
from tools import migrate_skills_to_institutional as mig

REPO = Path(config.PROJECT_ROOT)
VERIFIED_GOAL = "run the parser tests and report the result"
VERIFIED_STEPS = ["verify: command=pytest tests/test_parser.py -q"]
NEW_GOAL = "list the files in the docs directory"
NEW_STEPS = ["read_directory: path=docs"]


def _noop(*_a, **_k):
    return None


def _rows(db: Path) -> int:
    with sqlite3.connect(db) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM procedural_skills").fetchone()[0])


@pytest.fixture()
def world(tmp_path: Path, monkeypatch):
    latch = tmp_path / "emergency_stop.db"
    monkeypatch.setattr(learning_freeze, "_latch_path", lambda: latch)
    monkeypatch.setattr(learning_freeze, "_controllers", {})
    legacy_db = tmp_path / "memory.db"
    init_memory_db(legacy_db)
    # Writable ONLY to create the history a live store already holds.
    history_writer = SkillMemory(legacy_db)
    for _ in range(3):  # promoted to 'verified' by the legacy rule, long ago
        history_writer.record_attempt(VERIFIED_GOAL, VERIFIED_STEPS, success=True)
    operational = tmp_path / "operational.db"

    def migrate() -> None:
        mig.run(
            source=legacy_db,
            target=operational,
            backup_dir=tmp_path / "backups",
            do_apply=True,
        )

    def slot():
        repository = SkillRepository(operational)
        return build_skills_slot(
            repository=repository,
            trails=SkillTrailIndex(operational),
            history=SkillMemory(legacy_db, read_only=True),
        )

    def engage() -> None:
        EmergencyStopController(
            latch,
            hooks=EmergencyStopHooks(
                revoke_capabilities=_noop,
                cancel_queued_missions=_noop,
                kill_active_workers=_noop,
                disable_autonomy=_noop,
                preserve_evidence=_noop,
            ),
        ).engage(
            EmergencyStopRequest(
                operator_id="operator:test",
                authentication_event_id="event:engage",
                reason="skill library freeze test",
            )
        )

    return legacy_db, migrate, slot, engage


def _legacy_verified_id(legacy_db: Path) -> int:
    with sqlite3.connect(legacy_db) as conn:
        return int(
            conn.execute(
                "SELECT id FROM procedural_skills WHERE status = 'verified'"
            ).fetchone()[0]
        )


def _activate(repository: SkillRepository, record) -> None:
    """The operator's act, in a test. Live, only the capability route does it."""
    repository.transition_state(record.skill_id, record.version, "human_reviewed")
    repository.transition_state(record.skill_id, record.version, "active")


def _migrated(repository: SkillRepository):
    return next(
        r for r in repository.list_skills() if r.provenance.get("source") == "migrated"
    )


class TestTheLegacyStoreIsReadOnlyHistory:
    def test_a_read_only_store_refuses_every_write(self, world) -> None:
        legacy_db, _, _, _ = world
        history = SkillMemory(legacy_db, read_only=True)
        before = _rows(legacy_db)
        with pytest.raises(ReadOnlySkillHistoryError):
            history.record_attempt(NEW_GOAL, NEW_STEPS, success=True)
        with pytest.raises(ReadOnlySkillHistoryError):
            history.record_reuse([_legacy_verified_id(legacy_db)], success=False)
        assert _rows(legacy_db) == before

    def test_positive_control_a_writable_store_writes(self, world) -> None:
        legacy_db, _, _, _ = world
        before = _rows(legacy_db)
        SkillMemory(legacy_db).record_attempt(NEW_GOAL, NEW_STEPS, success=True)
        assert _rows(legacy_db) == before + 1

    def test_history_is_still_readable(self, world) -> None:
        legacy_db, _, _, _ = world
        history = SkillMemory(legacy_db, read_only=True)
        assert [r["goal_pattern"] for r in history.list(status="verified")] == [
            VERIFIED_GOAL
        ]

    def test_the_turns_write_lands_in_the_library_not_the_legacy_table(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Through the authority, exactly as the turn pipeline records an arc."""
        monkeypatch.setattr(config, "OPERATIONAL_STATE_DB_PATH", tmp_path / "op.db")
        authority = build_memory_authority()
        init_memory_db(config.MEMORY_DB_PATH)
        before = _rows(config.MEMORY_DB_PATH)
        trail = authority.record_skill_attempt(
            NEW_GOAL,
            NEW_STEPS,
            success=True,
            strength=VerificationStrength.STRONG,
        )
        assert trail >= LIBRARY_ID_BASE
        assert _rows(config.MEMORY_DB_PATH) == before, "procedural_skills grew"
        (record,) = SkillRepository(tmp_path / "op.db").list_skills()
        assert record.problem_signature == NEW_GOAL and record.state == "candidate"


class TestNoProductionCodeBuildsAWritableLegacyStore:
    """Static: the runtime refusal above only bites the store bootstrap builds.
    A tool constructing its own writable `SkillMemory` on the live database
    would keep a second skill store alive, so none may."""

    ROOTS = ("aios", "tools", "scripts")

    def _constructions(self) -> list[tuple[str, int, bool]]:
        found = []
        for root in self.ROOTS:
            for path in (REPO / root).rglob("*.py"):
                if "__pycache__" in path.parts:
                    continue
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    func = node.func
                    name = (
                        func.id
                        if isinstance(func, ast.Name)
                        else func.attr
                        if isinstance(func, ast.Attribute)
                        else ""
                    )
                    if name != "SkillMemory":
                        continue
                    read_only = any(
                        kw.arg == "read_only"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value is True
                        for kw in node.keywords
                    )
                    found.append(
                        (path.relative_to(REPO).as_posix(), node.lineno, read_only)
                    )
        return found

    def test_every_production_construction_is_read_only(self) -> None:
        found = self._constructions()
        assert found, "positive control: the scan finds the bootstrap construction"
        assert [f for f in found if not f[2]] == []

    def test_positive_control_the_scan_catches_a_writable_one(self, tmp_path) -> None:
        tree = ast.parse("SkillMemory(db_path=DB)\nskills.SkillMemory()\n")
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and not any(kw.arg == "read_only" for kw in n.keywords)
        ]
        assert len(calls) == 2


class TestNothingLearnsBeforeTheHistoryIsMigrated:
    def test_unmigrated_history_refuses_new_arcs_loudly(self, world, caplog) -> None:
        _, _, slot, _ = world
        with caplog.at_level(logging.ERROR):
            adapter = slot()
        assert "has not been migrated" in caplog.text
        with pytest.raises(SkillMigrationPendingError):
            adapter.record_attempt(NEW_GOAL, NEW_STEPS, success=True)
        with pytest.raises(SkillMigrationPendingError):
            adapter.record_reuse([1], success=True)
        assert not adapter.repository.list_skills()
        assert (
            "migrate_skills_to_institutional"
            in adapter.trail_map()["migration_pending"]
        )

    def test_positive_control_after_the_migration_it_learns(self, world) -> None:
        _, migrate, slot, _ = world
        migrate()
        adapter = slot()
        assert adapter.migration_pending is None
        adapter.record_attempt(NEW_GOAL, NEW_STEPS, success=True)
        assert any(
            r.problem_signature == NEW_GOAL for r in adapter.repository.list_skills()
        )

    def test_a_fresh_install_has_nothing_to_migrate(self, tmp_path: Path) -> None:
        memory = tmp_path / "memory.db"
        init_memory_db(memory)
        operational = tmp_path / "operational.db"
        adapter = build_skills_slot(
            repository=SkillRepository(operational),
            trails=SkillTrailIndex(operational),
            history=SkillMemory(memory, read_only=True),
        )
        assert adapter.migration_pending is None
        assert adapter.record_attempt(NEW_GOAL, NEW_STEPS, success=True) >= (
            LIBRARY_ID_BASE
        )


class TestTheLibraryServesTheSlot:
    def test_a_migrated_arc_keeps_its_legacy_id(self, world) -> None:
        legacy_db, migrate, slot, _ = world
        migrate()
        adapter = slot()
        legacy_id = _legacy_verified_id(legacy_db)
        assert (
            adapter.record_attempt(VERIFIED_GOAL, VERIFIED_STEPS, success=True)
            == legacy_id
        )
        assert _migrated(adapter.repository).success_count == 4

    def test_a_new_arc_takes_a_library_id(self, world) -> None:
        _, migrate, slot, _ = world
        migrate()
        assert slot().record_attempt(NEW_GOAL, NEW_STEPS, success=True) >= (
            LIBRARY_ID_BASE
        )

    def test_recall_reads_only_what_the_operator_activated(self, world) -> None:
        legacy_db, migrate, slot, _ = world
        migrate()
        adapter = slot()
        assert adapter.relevant_verified(VERIFIED_GOAL, 3) == [], "a candidate"
        _activate(adapter.repository, _migrated(adapter.repository))
        rows = adapter.relevant_verified(VERIFIED_GOAL, 3)
        assert [r["skill_id"] for r in rows] == [_legacy_verified_id(legacy_db)]

    def test_reuse_credits_only_an_active_skill(self, world) -> None:
        legacy_db, migrate, slot, _ = world
        migrate()
        adapter = slot()
        legacy_id = _legacy_verified_id(legacy_db)
        assert adapter.record_reuse([legacy_id], success=True) == []
        _activate(adapter.repository, _migrated(adapter.repository))
        assert adapter.record_reuse([legacy_id], success=True) == [legacy_id]

    def test_a_weak_success_is_not_evidence(self, world) -> None:
        _, migrate, slot, _ = world
        migrate()
        adapter = slot()
        adapter.record_attempt(
            VERIFIED_GOAL,
            VERIFIED_STEPS,
            success=True,
            strength=VerificationStrength.WEAK,
        )
        assert _migrated(adapter.repository).success_count == 3

    def test_the_trail_map_names_the_one_store(self, world) -> None:
        _, migrate, slot, _ = world
        migrate()
        view = slot().trail_map()
        assert view["store"] == "institutional_skills"
        assert "pilot" not in view, "there is no mode left to report"

    def test_the_stop_refuses_the_write_and_touches_nothing(self, world) -> None:
        legacy_db, migrate, slot, engage = world
        migrate()
        adapter = slot()
        before = (len(adapter.repository.list_skills()), _rows(legacy_db))
        engage()
        with pytest.raises(EmergencyStopError):
            adapter.record_attempt(NEW_GOAL, NEW_STEPS, success=True)
        assert (len(adapter.repository.list_skills()), _rows(legacy_db)) == before


class TestOrgan55M5SaysItCannotBeDriven:
    """M5 drives the LIVE backend, where only the operator activates a skill.
    Its old seeding would now write read-only history and never compile, a
    vacuous FAIL. It reports that it cannot be driven, and writes nothing."""

    def test_m5_is_not_drivable_and_plants_nothing(self) -> None:
        from tools.governance_mission_drivers import DriverContext, drive_m5

        ctx = DriverContext(session=None, session_id="gov-m5-test")
        result = drive_m5(ctx)
        assert "operator-activated" in (result.not_drivable or "")
        assert ctx.planted == []
