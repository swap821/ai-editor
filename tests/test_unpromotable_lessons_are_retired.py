"""A lesson that can never be confirmed must not spend the recall budget.

Promotion matches a later success against the lesson's `failed_command`. A
lesson with an empty one has nothing to match, so it is not pending — it is
incapable. All 87 lessons in the live pool are in that state, because the
column landed in the same change that began populating it.

That matters twice over. Recall has a small limit, so an unpromotable lesson
displaces one that could actually graduate; and "0 verified / 87" has been read
as a broken promotion path when the path works and has never had anything to
act on. A counter that cannot move is worse than a bad one, because people stop
reading it.

The second half here is the gate-decision guard. An approval pause and a
security block are the cage WORKING, not mistakes to learn from, and 55 of
those 87 rows are `ApprovalRequired` from before the guard existed. The guard is
currently enforced by a `failed` flag two modules away from the reflection call
and a comment saying so, which is exactly the kind of invariant that gets
refactored away by someone who never read the comment.
"""

from __future__ import annotations

import pytest

from aios.memory.db import get_connection, init_memory_db
from aios.memory.mistake import MistakeMemory


@pytest.fixture()
def mistakes(tmp_path):
    db = tmp_path / "memory.sqlite"
    init_memory_db(db)
    return MistakeMemory(db_path=db)


def _record(mistakes, *, command: str, task="task-1", error="AssertionError") -> int:
    lesson_id, _ = mistakes.record_or_increment(
        task, error, "cause", "fix", "lesson", -0.2, failed_command=command
    )
    return lesson_id


class TestRecallSkipsWhatCanNeverPromote:
    def test_a_lesson_with_no_command_is_not_recalled(self, mistakes) -> None:
        _record(mistakes, command="")
        assert mistakes.pending_for_task("task-1") == []

    def test_a_whitespace_command_counts_as_none(self, mistakes) -> None:
        _record(mistakes, command="   ")
        assert mistakes.pending_for_task("task-1") == []

    def test_a_lesson_with_a_real_command_is_recalled(self, mistakes) -> None:
        lesson_id = _record(mistakes, command="pytest tests/a.py -q")
        rows = mistakes.pending_for_task("task-1")
        assert [int(r["id"]) for r in rows] == [lesson_id]

    def test_the_promotable_one_is_not_crowded_out(self, mistakes) -> None:
        """The real cost: recall's limit is small and shared."""
        for i in range(6):
            _record(mistakes, command="", error=f"Dead{i}")
        good = _record(mistakes, command="pytest tests/a.py -q", error="Live")

        rows = mistakes.pending_for_task("task-1", limit=5)
        assert [int(r["id"]) for r in rows] == [good]

    def test_retiring_them_does_not_delete_anything(self, mistakes) -> None:
        """`superseded` is already a legal state and already filtered by recall,
        so retiring needs no schema change and loses no history."""
        lesson_id = _record(mistakes, command="")
        with get_connection(mistakes.db_path) as conn:
            conn.execute("UPDATE mistake_pool SET verification_status = 'superseded'")
            row = conn.execute(
                "SELECT lesson_text, verification_status FROM mistake_pool WHERE id = ?",
                (lesson_id,),
            ).fetchone()
        assert row["verification_status"] == "superseded"
        assert row["lesson_text"] == "lesson", "the lesson text is still readable"


class TestAGateDecisionIsNotAMistake:
    """Approval pauses and security blocks are the cage working.

    Both reflection entry points are guarded, but by different mechanisms in
    different modules — `_GATE_STATUSES` in the verifier, and a `failed` flag
    that `tool_handlers` sets to False for BLOCKED / REQUIRE_APPROVAL. Pinning
    the flag is pinning the one an unrelated refactor would quietly break.
    """

    def test_an_approval_pause_does_not_report_failure(self) -> None:
        from aios.agents.tool_handlers import _format_exec_result

        class _Result:
            status = "BLOCKED"
            reason = "requires approval"
            exit_code = 0
            command = "rm -rf /"

        _output, _status, failed = _format_exec_result(_Result())
        assert failed is False, (
            "a security block reported as a failure would feed reflection and "
            "refill the pool with ApprovalRequired lessons — 55 of the 87 dead "
            "rows were made exactly that way"
        )

    def test_a_real_command_failure_still_reports_failure(self) -> None:
        """The guard must not swallow genuine failures along with gate ones."""
        from aios.agents.tool_handlers import _format_exec_result

        class _Result:
            status = "TIMEOUT"
            reason = "timed out"
            exit_code = 1
            command = "pytest"

        assert _format_exec_result(_Result())[2] is True

    def test_a_nonzero_exit_is_a_failure(self) -> None:
        from aios.agents.tool_handlers import _format_exec_result

        class _Result:
            status = "OK"
            reason = ""
            stdout = "boom"
            stderr = ""
            exit_code = 2
            command = "pytest"

        assert _format_exec_result(_Result())[2] is True


class TestTheRetirementScript:
    def test_it_reports_before_it_changes_anything(self, mistakes, capsys) -> None:
        from scripts.retire_unpromotable_lessons import main

        _record(mistakes, command="")
        assert main(["--db", str(mistakes.db_path), "--dry-run"]) == 0
        assert "dry run" in capsys.readouterr().out

        with get_connection(mistakes.db_path) as conn:
            still = conn.execute(
                "SELECT verification_status FROM mistake_pool"
            ).fetchone()["verification_status"]
        assert still == "pending", "a dry run must not write"

    def test_it_retires_only_the_unpromotable(self, mistakes) -> None:
        from scripts.retire_unpromotable_lessons import main

        dead = _record(mistakes, command="", error="Dead")
        live = _record(mistakes, command="pytest -q", error="Live")
        assert main(["--db", str(mistakes.db_path)]) == 0

        with get_connection(mistakes.db_path) as conn:
            rows = {
                int(r["id"]): r["verification_status"]
                for r in conn.execute(
                    "SELECT id, verification_status FROM mistake_pool"
                )
            }
        assert rows[dead] == "superseded"
        assert rows[live] == "pending", "a lesson that can still promote is untouched"

    def test_undo_puts_them_back(self, mistakes) -> None:
        from scripts.retire_unpromotable_lessons import main

        lesson_id = _record(mistakes, command="")
        main(["--db", str(mistakes.db_path)])
        main(["--db", str(mistakes.db_path), "--undo"])

        with get_connection(mistakes.db_path) as conn:
            status = conn.execute(
                "SELECT verification_status FROM mistake_pool WHERE id = ?",
                (lesson_id,),
            ).fetchone()["verification_status"]
        assert status == "pending"
