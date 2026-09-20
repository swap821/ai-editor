"""The scoreboard must measure without touching, and must move when learning does.

Two failure modes matter here, and they are opposite:

* A scoreboard that can WRITE the store it measures is not evidence of
  anything -- it becomes another thing that has to be trusted. `collect` opens
  the database `mode=ro` precisely so "the measurement created the data" is
  impossible rather than merely unlikely.
* A scoreboard whose numbers do not move when the underlying thing changes is
  worse than none: it reports "flat" forever and every learning change looks
  equally pointless. So each counter is pinned to an actual state transition
  performed through the real store APIs, not by writing rows by hand.
"""

from __future__ import annotations

import sqlite3

import pytest

from aios.memory.curriculum import CurriculumManager
from aios.memory.db import init_memory_db
from aios.memory.mistake import MistakeMemory
from aios.memory.skills import SkillMemory
from aios.core.verification_strength import VerificationStrength
from scripts.learning_scoreboard import collect, render


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "memory.sqlite"
    init_memory_db(path)
    return path


class TestItCannotChangeWhatItMeasures:
    def test_a_missing_database_is_reported_not_created(self, tmp_path) -> None:
        missing = tmp_path / "never-existed.sqlite"
        stats = collect(missing)
        assert stats["db_present"] is False
        assert not missing.exists(), (
            "the scoreboard created the store it was asked to measure -- every "
            "number it prints afterwards would be its own artifact"
        )

    def test_reading_cannot_write(self, db) -> None:
        """`mode=ro` is the guarantee; this proves the URI really is read-only."""
        collect(db)
        conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            with pytest.raises(sqlite3.OperationalError):
                conn.execute(
                    "INSERT INTO mistake_pool (task_id, error_type, "
                    "root_cause, fix_applied, lesson_text, confidence_delta) "
                    "VALUES ('t','E','c','f','l',-0.1)"
                )
        finally:
            conn.close()


class TestLessonsThatNeverTransfer:
    """The production reading that motivated this: 87 lessons, 0 verified."""

    def test_a_recorded_lesson_counts_as_pending_not_learned(self, db) -> None:
        mistakes = MistakeMemory(db_path=db)
        mistakes.record("task-1", "AssertionError", "cause", "fix", "lesson", -0.2)

        stats = collect(db)
        assert stats["lessons_total"] == 1
        assert stats["lessons_pending"] == 1
        assert stats["lessons_verified"] == 0

    def test_the_all_pending_case_is_called_out_by_name(self, db) -> None:
        mistakes = MistakeMemory(db_path=db)
        for i in range(3):
            mistakes.record(f"task-{i}", "AssertionError", "c", "f", "l", -0.2)

        report = render(collect(db))
        assert "still pending" in report, (
            "a store where no lesson has ever been confirmed must say so -- that "
            "is the finding, not a footnote"
        )

    def test_promotion_moves_the_number(self, db) -> None:
        mistakes = MistakeMemory(db_path=db)
        lesson_id = mistakes.record("task-1", "AssertionError", "c", "f", "l", -0.2)
        mistakes.promote(lesson_id)

        stats = collect(db)
        assert stats["lessons_verified"] == 1
        assert stats["lessons_pending"] == 0

    def test_a_weak_green_does_not_promote_a_lesson(self, db) -> None:
        """The floor is load-bearing: the scoreboard must not paper over it."""
        mistakes = MistakeMemory(db_path=db)
        lesson_id = mistakes.record("task-1", "AssertionError", "c", "f", "l", -0.2)
        mistakes.promote(lesson_id, strength=VerificationStrength.WEAK)

        assert collect(db)["lessons_verified"] == 0


class TestStrongAndWeakAreNotTheSameNumber:
    def test_weak_successes_are_counted_apart_from_strong(self, db) -> None:
        skills = SkillMemory(db_path=db)
        skills.record_attempt(
            "write a passing test",
            ["read file", "write file", "run pytest"],
            success=True,
            strength=VerificationStrength.STRONG,
        )
        skills.record_attempt(
            "tidy some imports",
            ["read file", "write file", "run ruff"],
            success=True,
            strength=VerificationStrength.WEAK,
        )

        stats = collect(db)
        assert stats["successes_promotable"] == 1
        assert stats["successes_weak"] == 1, (
            "weak_success_count existed but was read nowhere; surfacing it is the "
            "only way to see where the STRONG-only floor is the binding constraint"
        )


class TestUnreachableMasteryIsDistinguishedFromUnearned:
    def test_a_level_with_no_held_out_task_is_reported_unreachable(self, db) -> None:
        curriculum = CurriculumManager(db_path=db)
        curriculum.add_task("shell", 1, "write a passing test for add()")

        stats = collect(db)
        assert stats["curriculum_levels_unreachable"] == 1
        assert "UNREACHABLE" in render(stats)

    def test_a_level_with_a_held_out_task_is_not_flagged(self, db) -> None:
        curriculum = CurriculumManager(db_path=db)
        curriculum.add_task("shell", 1, "write a passing test for add()")
        curriculum.add_task("shell", 1, "write a passing test for sub()", held_out=True)

        stats = collect(db)
        assert stats["curriculum_levels_unreachable"] == 0
        assert "UNREACHABLE" not in render(stats)
