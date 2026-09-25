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

from aios import config
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
    monkeypatch.setattr(config, "DATA_DIR", data)
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
        with pytest.raises(EmergencyStopError):
            cerebellum.try_compile_all()
        with pytest.raises(EmergencyStopError):
            cerebellum.try_compile_skill(1)
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
        apart; the freeze must defer to the controller's own check."""
        import inspect

        source = inspect.getsource(learning_freeze)
        assert "assert_operational()" in source
        assert "emergency_stop_state" not in source, "the latch table is read directly"
