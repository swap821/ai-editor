"""Plan Phase 6, slice 6b: bounded learning writes (threat T10, red-team RT-12).

Every write that creates or grows learned content spends from one process-wide
budget: at most N per table in any rolling minute. A refused write writes
nothing. Production attaches one budget to the lessons, skills, semantic and
facts adapters; the live callers are best-effort, so a refusal costs a row,
never a turn.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from aios.application.memory.adapters import (
    LegacySemanticMemoryAdapter,
    MistakeMemoryAdapter,
    SemanticFactsAdapter,
)
from aios.application.memory.institutional_skills import (
    InstitutionalSkillAdapter,
    SkillTrailIndex,
)
from aios.application.memory.write_budget import (
    WRITE_CAP_CONTROL,
    LearningWriteBudget,
    LearningWriteCapExceeded,
)
from aios.core.verification_strength import VerificationStrength
from aios.domain.learning.repository import SkillRepository
from aios.memory.db import init_memory_db
from aios.memory.facts import SemanticFacts
from aios.memory.mistake import MistakeMemory
from aios.memory.semantic import SemanticMemory

ROOT = Path(__file__).resolve().parents[1]


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


# ---------------------------------------------------------------- the budget


def test_the_budget_admits_the_cap_then_refuses() -> None:
    budget = LearningWriteBudget(3, clock=Clock())
    for _ in range(3):
        budget.spend("mistake_pool")
    with pytest.raises(LearningWriteCapExceeded) as refused:
        budget.spend("mistake_pool")
    assert refused.value.control == WRITE_CAP_CONTROL
    assert budget.status()["refused"] == {"mistake_pool": 1}


def test_the_window_rolls() -> None:
    clock = Clock()
    budget = LearningWriteBudget(2, clock=clock)
    budget.spend("t")
    clock.now += 30
    budget.spend("t")
    with pytest.raises(LearningWriteCapExceeded):
        budget.spend("t")
    clock.now += 30.5  # the first write is now more than 60 s old
    budget.spend("t")
    with pytest.raises(LearningWriteCapExceeded):
        budget.spend("t")


def test_tables_have_their_own_budgets() -> None:
    budget = LearningWriteBudget(1, clock=Clock())
    budget.spend("mistake_pool")
    budget.spend("institutional_skills")
    with pytest.raises(LearningWriteCapExceeded):
        budget.spend("mistake_pool")


def test_a_cap_below_one_is_refused() -> None:
    with pytest.raises(ValueError):
        LearningWriteBudget(0)


# ---------------------------------------------------------------- the adapters


def _count(db: Path, table: str) -> int:
    with sqlite3.connect(db) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_a_refused_lesson_writes_nothing(tmp_path: Path) -> None:
    db = tmp_path / "memory.sqlite"
    init_memory_db(db)
    lessons = MistakeMemoryAdapter(MistakeMemory(db))
    lessons.write_budget = LearningWriteBudget(2, clock=Clock())
    lessons.record("t1", "e1", "c", "f", "lesson one", -0.1)
    lessons.record_or_increment(
        task_id="t2",
        error_type="e2",
        root_cause="c",
        fix_applied="f",
        lesson_text="lesson two",
        confidence_delta=-0.1,
    )
    with pytest.raises(LearningWriteCapExceeded):
        lessons.record("t3", "e3", "c", "f", "lesson three", -0.1)
    with pytest.raises(LearningWriteCapExceeded):
        lessons.record_or_increment(
            task_id="t4",
            error_type="e4",
            root_cause="c",
            fix_applied="f",
            lesson_text="lesson four",
            confidence_delta=-0.1,
        )
    assert _count(db, "mistake_pool") == 2


def test_a_refused_skill_attempt_writes_nothing(tmp_path: Path) -> None:
    repository = SkillRepository(tmp_path / "ops.sqlite")
    skills = InstitutionalSkillAdapter(repository, SkillTrailIndex(repository.database))
    skills.write_budget = LearningWriteBudget(1, clock=Clock())
    skills.record_attempt(
        "goal one",
        ["verify: pytest"],
        success=True,
        strength=VerificationStrength.STRONG,
    )
    with pytest.raises(LearningWriteCapExceeded):
        skills.record_attempt(
            "goal two",
            ["verify: pytest -q"],
            success=True,
            strength=VerificationStrength.STRONG,
        )
    assert len(repository.list_skills()) == 1


class _RecordingSemanticStore(SemanticMemory):
    """A real SemanticMemory type (the adapter insists) that records instead
    of embedding: the embedder is not what this test is about."""

    def __init__(self, db_path: Path) -> None:  # no super(): no index, no model
        self.db_path = db_path
        self.added: list[str] = []

    def add(self, text: str, *_: object, **__: object) -> int:
        self.added.append(text)
        return len(self.added)


def test_a_refused_semantic_memory_writes_nothing(tmp_path: Path) -> None:
    store = _RecordingSemanticStore(tmp_path / "memory.sqlite")
    semantic = LegacySemanticMemoryAdapter(store)
    semantic.write_budget = LearningWriteBudget(1, clock=Clock())
    semantic.record_chat("first observation")
    with pytest.raises(LearningWriteCapExceeded):
        semantic.record_chat("second observation")
    with pytest.raises(LearningWriteCapExceeded):
        semantic.add("third")
    assert store.added == ["first observation"]


def test_a_refused_fact_writes_nothing(tmp_path: Path) -> None:
    db = tmp_path / "memory.sqlite"
    init_memory_db(db)
    facts = SemanticFactsAdapter(SemanticFacts(db))
    facts.write_budget = LearningWriteBudget(1, clock=Clock())
    facts.add_fact("release", "branch", "main", approved_by="operator:test")
    with pytest.raises(LearningWriteCapExceeded):
        facts.add_fact("release", "tag", "v1", approved_by="operator:test")
    with pytest.raises(LearningWriteCapExceeded):
        facts.strengthen_or_propose("release", "owner", "ops")
    assert _count(db, "semantic_facts") == 1


def test_an_adapter_without_a_budget_is_unbounded(tmp_path: Path) -> None:
    db = tmp_path / "memory.sqlite"
    init_memory_db(db)
    lessons = MistakeMemoryAdapter(MistakeMemory(db))
    for i in range(5):
        lessons.record(f"t{i}", f"e{i}", "c", "f", f"lesson {i}", -0.1)
    assert _count(db, "mistake_pool") == 5


# ---------------------------------------------------------------- production


def test_production_bounds_every_learning_adapter_with_one_budget() -> None:
    """The live path: the process authority's four learning adapters share one
    budget, sized by configuration. An unbounded adapter in production is the
    failure this pins."""
    from aios import config
    from aios.api.deps import get_memory_authority
    from aios.application.memory.bootstrap import LEARNING_WRITE_TABLES

    adapters = get_memory_authority().adapters
    budgets = {
        name: getattr(adapters[name], "write_budget", None)
        for name in LEARNING_WRITE_TABLES
    }
    assert set(LEARNING_WRITE_TABLES) == {"lessons", "skills", "semantic", "facts"}
    assert all(isinstance(b, LearningWriteBudget) for b in budgets.values()), budgets
    assert len({id(b) for b in budgets.values()}) == 1
    assert budgets["lessons"].per_minute == config.LEARNING_WRITE_CAP_PER_MINUTE


def test_the_production_default_is_sixty_a_minute(tmp_path: Path) -> None:
    """The suite pins the cap out of the way (tests/conftest.py); production
    does not set it, and gets 60."""
    env = {
        k: v for k, v in os.environ.items() if k != "AIOS_LEARNING_WRITE_CAP_PER_MINUTE"
    }
    env["AIOS_DATA_DIR"] = str(tmp_path)
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); from aios import config; "
            "print(config.LEARNING_WRITE_CAP_PER_MINUTE)",
            str(ROOT),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == "60"
