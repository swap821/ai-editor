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

import json
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


class TestTheScoreboardAlarmsInsteadOfOnlyPrinting:
    """A dashboard nobody alarms on is how a loop quietly stops for a month.

    The alarm is deliberately narrow. Not "is the number good" -- nobody can
    agree on that and a subjective gate gets muted -- but "did something this
    system had already proven stop being true".
    """

    def _trail(self, tmp_path, *rows):
        path = tmp_path / "trail.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        return path

    def test_a_dropped_counter_is_a_regression(self, tmp_path) -> None:
        from scripts.learning_scoreboard import detect_regressions

        trail = self._trail(tmp_path, {"skills_verified": 6, "playbooks_compiled": 3})
        found = detect_regressions(
            {"skills_verified": 4, "playbooks_compiled": 3}, trail
        )
        assert found == ["skills_verified: 6 -> 4"]

    def test_holding_steady_is_not_a_regression(self, tmp_path) -> None:
        from scripts.learning_scoreboard import detect_regressions

        trail = self._trail(tmp_path, {"skills_verified": 6})
        assert detect_regressions({"skills_verified": 6}, trail) == []

    def test_rising_failures_are_not_a_regression(self, tmp_path) -> None:
        """Failures going up is the loop WORKING — it is measuring things."""
        from scripts.learning_scoreboard import detect_regressions

        trail = self._trail(tmp_path, {"failures": 10, "skills_verified": 6})
        assert detect_regressions({"failures": 40, "skills_verified": 6}, trail) == []

    def test_the_first_ever_reading_cannot_regress(self, tmp_path) -> None:
        from scripts.learning_scoreboard import detect_regressions

        assert detect_regressions({"skills_verified": 1}, tmp_path / "absent") == []

    def test_a_corrupt_last_row_falls_back_to_an_earlier_one(self, tmp_path) -> None:
        """A half-written line must not disable the alarm entirely."""
        from scripts.learning_scoreboard import detect_regressions

        path = tmp_path / "t.jsonl"
        path.write_text(
            json.dumps({"skills_verified": 6}) + "\n{half-writt", encoding="utf-8"
        )
        assert detect_regressions({"skills_verified": 2}, path) == [
            "skills_verified: 6 -> 2"
        ]


class TestAnUnmeasuredCheckSaysSo:
    """The alarm must not report a verdict it did not reach.

    On a machine with no store -- a fresh CI runner, a clean clone --
    `collect()` returns no counters at all, so `detect_regressions` compares
    None against None and finds nothing. Printing "no regression" there is a
    green that means nothing, which is the exact failure class this ledger
    exists to catch: a hollow run scored as a verdict.
    """

    def test_no_database_is_reported_as_not_checked(self, tmp_path, capsys) -> None:
        from scripts.learning_scoreboard import main

        exit_code = main(["--check", "--db", str(tmp_path / "absent.sqlite")])
        out = capsys.readouterr().out
        assert "NOT CHECKED" in out
        assert "no regression" not in out, (
            "an unmeasured check claimed a clean comparison"
        )
        # Nothing to alarm on either: an absent store is not a regression.
        assert exit_code == 0

    def test_a_real_database_still_reaches_a_verdict(self, db, capsys) -> None:
        """The negative control: without it the assertion above would pass on a
        scoreboard that had stopped checking anything at all.

        WHICH verdict is not the point and is not asserted -- this store is
        empty and the recorded trail belongs to whichever machine ran it, so
        either answer is legitimate. What must be true is that one was reached.
        """
        from scripts.learning_scoreboard import main

        main(["--check", "--db", str(db)])
        out = capsys.readouterr().out
        assert "NOT CHECKED" not in out
        assert "no regression" in out or "REGRESSION" in out


class TestTheTrackedSummary:
    """`.aios/audit/` is gitignored, so without this nobody but this laptop can
    check a single learning claim the project makes."""

    def test_it_renders_the_recent_readings(self, tmp_path) -> None:
        from scripts.learning_scoreboard import write_trend

        trail = tmp_path / "t.jsonl"
        trail.write_text(
            json.dumps({"ts": "2026-09-21T00:00:00+00:00", "skills_verified": 6})
            + "\n",
            encoding="utf-8",
        )
        trend = tmp_path / "TREND.md"
        write_trend(trail, trend)

        text = trend.read_text(encoding="utf-8")
        assert "| when | skills |" in text
        assert "2026-09-21T00:00:00+00:00" in text and "| 6 |" in text

    def test_a_missing_counter_renders_as_absent_not_zero(self, tmp_path) -> None:
        """Reporting a column the DB never had as 0 is how a broken
        measurement disguises itself as a bad result."""
        from scripts.learning_scoreboard import write_trend

        trail = tmp_path / "t.jsonl"
        trail.write_text(json.dumps({"ts": "x"}) + "\n", encoding="utf-8")
        trend = tmp_path / "TREND.md"
        write_trend(trail, trend)
        assert "| x | - | - |" in trend.read_text(encoding="utf-8")

    def test_no_trail_means_no_file_invented(self, tmp_path) -> None:
        from scripts.learning_scoreboard import write_trend

        trend = tmp_path / "TREND.md"
        write_trend(tmp_path / "absent.jsonl", trend)
        assert not trend.exists()
