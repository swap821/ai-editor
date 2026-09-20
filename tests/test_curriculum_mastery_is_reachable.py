"""A level with no held-out task can never be mastered, and must say so.

`_refresh_level` gates mastery on ``held_out_passed = bool(held_out) and
all(...)``. With no held-out task that is ``bool([])`` -> False, so the level is
blocked forever -- while the plumbing keeps recording successes on every
matching turn and the counters climb. Nothing in the codebase creates a
held-out task automatically: the only caller that can is the privileged
operator route, so out of the box the mastery transition is a permanent,
*silent* no-op.

These tests pin both halves: that the gate really is unreachable without a
held-out task (so nobody "fixes" the symptom by loosening the gate), and that
the condition is now reported rather than silent.
"""

from __future__ import annotations

import pytest

from aios.memory.curriculum import CurriculumManager


@pytest.fixture()
def manager(tmp_path) -> CurriculumManager:
    return CurriculumManager(db_path=tmp_path / "curriculum.sqlite")


def _succeed(manager: CurriculumManager, skill: str, prompt: str, times: int) -> None:
    """Record `times` STRONG verified successes against a curriculum task.

    STRONG matters: `record_matching` only counts a pass toward mastery when it
    clears the promotion floor, so a WEAK green would record an attempt and
    advance nothing.
    """
    for _ in range(times):
        manager.record_matching(
            prompt,
            passed=True,
            evidence="[VERIFY PASS] 3 passed, 0 failed (strength=STRONG)",
        )


def test_a_level_without_a_held_out_task_never_masters(manager) -> None:
    """The gate itself -- unchanged, and deliberately strict."""
    manager.add_task("shell", 1, "write a passing test for add()")
    _succeed(manager, "shell", "write a passing test for add()", times=5)

    rows = manager.list("shell")
    assert rows, "the task should exist"
    assert all(row["status"] != "mastered" for row in rows), (
        "without a held-out task mastery must NOT be granted -- the point of "
        "this test is that the gate is real, not that it should be loosened"
    )


def test_the_missing_held_out_task_is_reported_not_silent(manager) -> None:
    """The fix: an unstated requirement becomes a named blocker.

    A requirement nobody states is indistinguishable from a system that does
    not work.
    """
    manager.add_task("shell", 1, "write a passing test for add()")
    _succeed(manager, "shell", "write a passing test for add()", times=5)

    report = manager.mastery_blockers("shell")
    assert report, "an unmastered level must explain itself"
    entry = next(row for row in report if row["level"] == 1)
    assert entry["reachable"] is False
    assert any("UNREACHABLE" in blocker for blocker in entry["blockers"]), (
        f"the no-held-out case must be named explicitly, got {entry['blockers']}"
    )


def test_a_level_with_a_held_out_task_is_reported_reachable(manager) -> None:
    """With the requirement satisfied, the blocker changes shape rather than vanishing."""
    manager.add_task("shell", 1, "write a passing test for add()")
    manager.add_task("shell", 1, "write a passing test for sub()", held_out=True)

    report = manager.mastery_blockers("shell")
    entry = next(row for row in report if row["level"] == 1)
    assert entry["reachable"] is True
    assert not any("UNREACHABLE" in blocker for blocker in entry["blockers"])
    assert any("held-out" in blocker for blocker in entry["blockers"]), (
        "it is still blocked -- on evidence now, not on an unstated requirement"
    )


def test_a_mastered_level_reports_no_blockers(manager) -> None:
    """The end state is silence, which is why silence must not mean 'blocked'."""
    manager.add_task("shell", 1, "write a passing test for add()")
    manager.add_task("shell", 1, "write a passing test for sub()", held_out=True)
    _succeed(manager, "shell", "write a passing test for add()", times=2)
    _succeed(manager, "shell", "write a passing test for sub()", times=1)

    mastered = [row for row in manager.list("shell") if row["status"] == "mastered"]
    assert mastered, "this is the path that proves mastery is reachable at all"
    assert not [row for row in manager.mastery_blockers("shell") if row["level"] == 1]


def test_the_route_surfaces_blockers_not_just_tasks(manager) -> None:
    """A report nobody can read is the same defect in a different place.

    `mastery_blockers` existing on the manager is not enough: if the only
    caller is a test, the operator still sees a level sitting at "available"
    forever with no stated reason — which is exactly the silence this work was
    supposed to end.
    """
    from aios.api.routes.development import development_curriculum

    manager.add_task("shell", 1, "write a passing test for add()")

    payload = development_curriculum(skill_name="shell", curriculum=manager)
    assert payload["tasks"], "tasks must still be returned"
    assert payload["blockers"], "the reason a level is stuck must reach the caller"
    assert any(
        "UNREACHABLE" in blocker
        for entry in payload["blockers"]
        for blocker in entry["blockers"]
    )
