"""The emergency stop freezes learning, not only action (plan Phase 0b, #3).

The learning red-team reel measured master with the latch engaged (RT-07): a
skill, a lesson, a chat memory and a compiled reflex were all written. Every
test here engages the REAL durable latch and asserts over the store, and each
refusal test has a positive control proving the same write lands when the
latch is clear -- a refusal from a harness that could not write anyway would
be a vacuous pass.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aios.application.governance.emergency_stop import (
    EmergencyStopController,
    EmergencyStopError,
    EmergencyStopHooks,
)
from aios.core.cerebellum import Cerebellum
from aios.core.verification_strength import VerificationStrength
from aios.domain.governance.contracts import EmergencyStopRequest
from aios.memory import learning_freeze
from aios.memory.db import init_memory_db
from aios.memory.mistake import MistakeMemory
from aios.memory.semantic import SemanticMemory
from aios.memory.skills import SkillMemory


def _noop(*_a, **_k):
    return None


def _controller(data_dir: Path) -> EmergencyStopController:
    return EmergencyStopController(
        data_dir / "emergency_stop.db",
        hooks=EmergencyStopHooks(
            revoke_capabilities=_noop,
            cancel_queued_missions=_noop,
            kill_active_workers=_noop,
            disable_autonomy=_noop,
            preserve_evidence=_noop,
        ),
    )


@pytest.fixture()
def world(tmp_path, monkeypatch):
    """A throwaway DATA_DIR with its own latch and memory store."""
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(
        learning_freeze, "_latch_path", lambda: data / "emergency_stop.db"
    )
    monkeypatch.setattr(learning_freeze, "_controllers", {})
    db = data / "memory.db"
    init_memory_db(db)
    return data, db


def _engage(data: Path) -> EmergencyStopController:
    stop = _controller(data)
    stop.engage(
        EmergencyStopRequest(
            operator_id="operator:test",
            authentication_event_id="event:engage",
            reason="freeze learning test",
        )
    )
    assert stop.is_engaged()
    return stop


def _count(db: Path, table: str) -> int:
    with sqlite3.connect(db) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


class _Embedder:
    def encode(self, text):
        return [[0.0, 1.0]]


class _Index:
    def __init__(self, path: Path) -> None:
        self.path = path

    def add(self, vector_id, vector):
        pass

    def persist(self):
        pass


def _writes(db: Path):
    """Every learning write this containment covers, as (name, table, call)."""
    skills = SkillMemory(db_path=db)
    lessons = MistakeMemory(db_path=db)
    semantic = SemanticMemory(
        db, index=_Index(db.with_suffix(".faiss")), embedder=_Embedder()
    )
    return [
        (
            "skills.record_attempt",
            "procedural_skills",
            lambda: skills.record_attempt(
                "run the pin tests",
                ["verify: command=pytest x -q"],
                success=True,
                strength=VerificationStrength.STRONG,
            ),
        ),
        (
            "lessons.record",
            "mistake_pool",
            lambda: lessons.record("t", "e", "c", "f", "a lesson", -0.1),
        ),
        (
            "lessons.record_or_increment",
            "mistake_pool",
            lambda: lessons.record_or_increment(
                "t2", "e2", "c", "f", "another lesson", -0.1
            ),
        ),
        ("semantic.add", "semantic_memory", lambda: semantic.add("a note")),
    ]


class TestLearningWritesAreRefusedWhileTheStopIsEngaged:
    @pytest.mark.parametrize("index", range(4))
    def test_the_write_is_refused_and_nothing_lands(self, world, index) -> None:
        data, db = world
        name, table, write = _writes(db)[index]
        _engage(data)
        before = _count(db, table)
        with pytest.raises(EmergencyStopError, match=name.replace(".", r"\.")):
            write()
        assert _count(db, table) == before, f"{name} wrote while the stop was engaged"

    @pytest.mark.parametrize("index", range(4))
    def test_the_same_write_lands_when_the_stop_is_clear(self, world, index) -> None:
        """The positive control: the refusal above is not a harness that
        cannot write."""
        _data, db = world
        name, table, write = _writes(db)[index]
        before = _count(db, table)
        write()
        assert _count(db, table) > before, name

    def test_promotion_and_recurrence_are_refused(self, world) -> None:
        data, db = world
        lessons = MistakeMemory(db_path=db)
        lid = lessons.record("t", "e", "c", "f", "a lesson", -0.1)
        _engage(data)
        with pytest.raises(EmergencyStopError):
            lessons.promote(lid, strength=VerificationStrength.STRONG)
        with pytest.raises(EmergencyStopError):
            lessons.increment_occurrence(lid)
        with sqlite3.connect(db) as conn:
            status, count = conn.execute(
                "SELECT verification_status, occurrence_count FROM mistake_pool WHERE id = ?",
                (lid,),
            ).fetchone()
        assert status == "pending" and count == 1

    def test_no_reflex_is_compiled_while_the_stop_is_engaged(self, world) -> None:
        data, db = world
        skills = SkillMemory(db_path=db)
        for _ in range(3):
            skills.record_attempt(
                "run the pin tests",
                ["verify: command=pytest x -q"],
                success=True,
                strength=VerificationStrength.STRONG,
            )
        cerebellum = Cerebellum(db)
        _engage(data)
        before = _count(db, "compiled_playbooks")
        # Compilation is a sweep run on every request: frozen, it compiles
        # nothing and returns quietly instead of raising (a raising sweep made
        # read-only routes answer 503 -- tests/test_stop_does_not_blind_read_routes.py).
        assert cerebellum.try_compile_all() == 0
        assert cerebellum.try_compile_skill(1) is None
        assert _count(db, "compiled_playbooks") == before

    def test_clearing_the_stop_thaws_learning(self, world) -> None:
        data, db = world
        stop = _engage(data)
        lessons = MistakeMemory(db_path=db)
        with pytest.raises(EmergencyStopError):
            lessons.record("t", "e", "c", "f", "frozen", -0.1)
        token = stop.issue_clear_capability(
            operator_id="operator:test",
            authentication_event_id="event:clear",
            session_id="session:test",
        )
        stop.clear(
            operator_id="operator:test",
            authentication_event_id="event:clear",
            session_id="session:test",
            clear_capability=token,
        )
        assert not stop.is_engaged()
        lessons.record("t", "e", "c", "f", "thawed", -0.1)


class TestThePositiveControlsTheReviewFoundMissing:
    """An adversarial review found four guarded writes with a refusal test and
    no proof the same call writes when the latch is clear."""

    def test_promotion_and_recurrence_land_when_clear(self, world) -> None:
        _data, db = world
        lessons = MistakeMemory(db_path=db)
        lid = lessons.record("t", "e", "c", "f", "a lesson", -0.1)
        lessons.promote(lid, strength=VerificationStrength.STRONG)
        lessons.increment_occurrence(lid)
        with sqlite3.connect(db) as conn:
            status, count = conn.execute(
                "SELECT verification_status, occurrence_count FROM mistake_pool WHERE id = ?",
                (lid,),
            ).fetchone()
        assert (status, count) == ("verified", 2)

    def test_compilation_lands_when_clear(self, world) -> None:
        _data, db = world
        skills = SkillMemory(db_path=db)
        for _ in range(3):
            skills.record_attempt(
                "run the pin tests",
                ["verify: command=pytest x -q"],
                success=True,
                strength=VerificationStrength.STRONG,
            )
        assert Cerebellum(db).try_compile_all() == 1
        assert _count(db, "compiled_playbooks") == 1


class TestFactsAndCurriculumAreFrozenToo:
    """The review's critical finding: fact auto-extraction runs on every chat
    turn by default, and it wrote straight past the freeze."""

    def _fact_writes(self, db: Path):
        from aios.memory.facts import SemanticFacts

        facts = SemanticFacts(db)
        return [
            (
                "facts.strengthen_or_propose",
                "fact_proposals",
                lambda: facts.strengthen_or_propose("user", "prefers", "tea"),
            ),
            (
                "facts.propose",
                "fact_proposals",
                lambda: facts.propose("user", "prefers", "coffee"),
            ),
            (
                "facts.add_fact",
                "semantic_facts",
                lambda: facts.add_fact(
                    "user", "lives_in", "Pune", approved_by="operator"
                ),
            ),
        ]

    @pytest.mark.parametrize("index", range(3))
    def test_fact_writes_are_refused_while_engaged(self, world, index) -> None:
        data, db = world
        name, table, write = self._fact_writes(db)[index]
        _engage(data)
        before = _count(db, table)
        with pytest.raises(EmergencyStopError, match=name.replace(".", r"\.")):
            write()
        assert _count(db, table) == before

    @pytest.mark.parametrize("index", range(3))
    def test_fact_writes_land_when_clear(self, world, index) -> None:
        _data, db = world
        name, table, write = self._fact_writes(db)[index]
        before = _count(db, table)
        write()
        assert _count(db, table) > before, name

    def test_curriculum_writes_are_refused_while_engaged_and_land_when_clear(
        self, world
    ) -> None:
        from aios.memory.curriculum import CurriculumManager

        data, db = world
        curriculum = CurriculumManager(db)
        curriculum.add_task("pinning", 1, "pin the relevance function")
        before = _count(db, "curriculum_tasks")
        _engage(data)
        with pytest.raises(EmergencyStopError, match=r"curriculum\.add_task"):
            curriculum.add_task("pinning", 1, "pin another function")
        with pytest.raises(EmergencyStopError, match=r"curriculum\.record_matching"):
            curriculum.record_matching(
                "pin the relevance function", passed=True, evidence="1 passed"
            )
        assert _count(db, "curriculum_tasks") == before


class TestReplayBookkeepingFreezesInsteadOfCounting:
    """A replay the stop refused is not evidence about the playbook. Counting
    it would decompile a reflex after two refused turns; raising mid-replay
    would crash the turn. Frozen bookkeeping neither counts nor forgives."""

    def _compiled(self, db: Path):
        skills = SkillMemory(db_path=db)
        for _ in range(3):
            skills.record_attempt(
                "run the pin tests",
                ["verify: command=pytest x -q"],
                success=True,
                strength=VerificationStrength.STRONG,
            )
        cerebellum = Cerebellum(db)
        assert cerebellum.try_compile_all() == 1
        return cerebellum

    def _row(self, db: Path):
        with sqlite3.connect(db) as conn:
            return conn.execute(
                "SELECT status, consecutive_failures, replay_count FROM compiled_playbooks"
            ).fetchone()

    def test_nothing_about_a_reflex_moves_while_engaged(self, world) -> None:
        data, db = world
        cerebellum = self._compiled(db)
        before = self._row(db)
        _engage(data)
        for _ in range(cerebellum.max_consecutive_failures + 1):
            cerebellum._record_replay_failure(1)
        cerebellum._record_replay_success(1)
        cerebellum.decompile(1)
        assert cerebellum.invalidate_for_skill(1) is False
        assert self._row(db) == before, "the stop moved a reflex's state"

    def test_the_same_bookkeeping_moves_when_clear(self, world) -> None:
        _data, db = world
        cerebellum = self._compiled(db)
        cerebellum._record_replay_failure(1)
        assert self._row(db)[1] == 1
        cerebellum.decompile(1)
        assert self._row(db)[0] == "decompiled"


class TestOneLatch:
    def test_the_freeze_reads_the_latch_production_engages(self) -> None:
        """One derivation: the path is the controller's own default, which is
        what `get_emergency_stop` builds with. Rebuilding it from DATA_DIR
        could diverge (adversarial review, 2026-09-25)."""
        from aios.api import deps

        assert Path(deps.get_emergency_stop().db_path) == learning_freeze._latch_path()


class TestTheFreezeFailsClosed:
    def test_an_unreadable_latch_refuses_the_write(self, world, monkeypatch) -> None:
        _data, db = world

        def _unreadable():
            raise sqlite3.OperationalError("database disk image is malformed")

        monkeypatch.setattr(learning_freeze, "_latch", _unreadable)
        with pytest.raises(sqlite3.OperationalError):
            MistakeMemory(db_path=db).record("t", "e", "c", "f", "a lesson", -0.1)
        assert _count(db, "mistake_pool") == 0

    def test_it_reads_the_canonical_controller_not_its_own_copy(self) -> None:
        """This codebase paid for three spellings of the stop rule drifting
        apart; the freeze must defer to the controller's own check. Executable
        source only, so a comment mentioning the check cannot satisfy it."""
        from tests.source_rules import executable_source

        source = executable_source(learning_freeze)
        assert "assert_operational()" in source
        assert "emergency_stop_state" not in source, "the latch table is read directly"
