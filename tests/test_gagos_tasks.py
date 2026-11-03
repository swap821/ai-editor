"""Tasks the operator writes (2026-11-03): his words and one file, queued in
GAGOS's ledger for its workshop, counter and face to share. Pinned here, the
ledger's contract:

* a task needs words, at most MAX_TASK_CHARS, who wrote it, and a
  project-relative path (never absolute, a drive, nor ``..``);
* only an open task moves, once: taken by a writer's proposal, refused by
  GAGOS with a reason, or cancelled by the operator;
* the progress read shows each task with what became of its proposal: its
  status, the sandbox's outcome, the reviews and the PR.
"""

from __future__ import annotations

import pytest

from aios.maintenance import daily_work as dw

BEFORE = "import os\n\nX = 1\n"
AFTER = "X = 1\n"


def _ledger(tmp_path):
    return dw.DailyLedger(tmp_path / "ledger.db")


def test_a_task_is_queued_open_with_its_words_and_file(tmp_path) -> None:
    led = _ledger(tmp_path)
    tid = led.add_task(
        "aios\\core\\x.py", "  Add a docstring to X.  ", said_by="operator"
    )
    task = led.task(tid)
    assert tid.startswith("gt-")
    assert (task["rel"], task["text"], task["status"]) == (
        "aios/core/x.py",
        "Add a docstring to X.",
        "open",
    )
    assert [t["task_id"] for t in led.tasks(status="open")] == [tid]


@pytest.mark.parametrize(
    "rel",
    ["", "/etc/passwd", "C:/x.py", "aios/../x.py", "./x.py", "aios//x.py", "a" * 513],
)
def test_a_path_that_is_not_project_relative_is_refused(tmp_path, rel) -> None:
    with pytest.raises(dw.TaskRefused):
        _ledger(tmp_path).add_task(rel, "do it", said_by="operator")


def test_a_task_needs_words_within_the_bound_and_who_wrote_it(tmp_path) -> None:
    led = _ledger(tmp_path)
    with pytest.raises(dw.TaskRefused, match="needs words"):
        led.add_task("x.py", "   ", said_by="operator")
    with pytest.raises(dw.TaskRefused, match="at most"):
        led.add_task("x.py", "a" * (dw.MAX_TASK_CHARS + 1), said_by="operator")
    with pytest.raises(dw.TaskRefused, match="who wrote it"):
        led.add_task("x.py", "do it", said_by=" ")
    assert led.tasks() == []


def test_only_an_open_task_moves_and_only_once(tmp_path) -> None:
    led = _ledger(tmp_path)
    taken = led.add_task("x.py", "a", said_by="operator")
    assert led.take_task(taken, "gd-1")
    assert not led.cancel_task(taken), "a taken task is the proposal's now"
    assert not led.take_task(taken, "gd-2"), "never taken twice"
    assert led.task(taken)["proposal_id"] == "gd-1"
    cancelled = led.add_task("x.py", "b", said_by="operator")
    assert led.cancel_task(cancelled)
    assert not led.take_task(cancelled, "gd-3"), "a withdrawn task is not done"
    refused = led.add_task("aios/security/x.py", "c", said_by="operator")
    assert led.refuse_task(refused, "GAGOS may not edit its frozen core")
    assert led.task(refused)["reason"] == "GAGOS may not edit its frozen core"
    assert [t["status"] for t in led.tasks()] == ["taken", "cancelled", "refused"]


def test_the_progress_read_shows_what_became_of_the_proposal(tmp_path) -> None:
    led = _ledger(tmp_path)
    waiting = led.add_task("x.py", "a", said_by="operator")
    done = led.add_task("x.py", "remove the unused os import", said_by="operator")
    finding = dw.Finding(rel="x.py", rule=dw.TASK_RULE, warnings=())
    pid = led.record_proposal(
        finding,
        base_text=BEFORE,
        base_commit="c" * 40,
        model="claude-sonnet-5-5",
        new_text=AFTER,
        verdict=dw.StaticVerdict(True, "ok", 2),
    )
    assert led.take_task(done, pid)
    led.record_sandbox(pid, '{"outcome": "passed", "summary": "9 tests pass"}')
    led.record_review(pid, "claude", model="opus", verdict="accept", reason="fine")
    by = {t["task_id"]: t for t in led.task_progress()}
    assert by[waiting]["proposal"] is None and by[waiting]["status"] == "open"
    p = by[done]["proposal"]
    assert (p["proposal_id"], p["model"], p["sandbox"]) == (
        pid,
        "claude-sonnet-5-5",
        "passed",
    )
    assert p["status"] == "accepted"
    assert p["reviews"] == {"claude": {"verdict": "accept", "reason": "fine"}}
    assert p["pr_url"] is None
