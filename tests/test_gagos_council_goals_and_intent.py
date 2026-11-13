"""The council's own goals, its completion measure, and a reviewer that
judges what a test means (2026-11-13).

After the first live council missions the operator asked for two things: give
the council a few days of real goals and measure how many it completes, and
make the reviewer judge intent. A goal finding no live envelope went to the
workshop's writers within the hour, so his goals measured nothing of the
council: one queued with ``--council`` is the council's alone and waits for a
slot. And #665's first test for EventThrottler.ts was accepted because every
assertion would pass, one of them pinning behaviour the module's own comment
rules out.
"""

from __future__ import annotations

import pytest

from aios.maintenance import daily_work as dw
from aios.maintenance.daily_work import DailyLedger, Finding
from tests.test_gagos_council_origination import TEST, WORDS, _briefed

from tools import gagos_daily as tool

OTHER = "frontend/src/superbrain/lib/other.ts"


@pytest.fixture()
def led(tmp_path, monkeypatch) -> DailyLedger:
    ledger = DailyLedger(tmp_path / "ledger.db")
    monkeypatch.setattr(tool, "ledger", lambda: ledger)
    monkeypatch.setattr(tool, "goals_through_clerk", lambda: True)
    return ledger


def _brief(led, tid):
    led.record_intake(tid, {**_briefed(), "reason": "", "mission_request": None})


def _sent(led, tid, mission_id, state, *, at=None):
    led.record_origination(
        tid,
        {
            "state": state,
            "reason": "",
            "mission_id": mission_id,
            "envelope_id": "envelope-1",
            "slot": 1,
        },
    )
    if at:
        with led._db() as db:
            db.execute(
                "UPDATE goal_missions SET created_at = ? WHERE mission_id = ?",
                (at, mission_id),
            )


class Live:
    def status(self):
        return {"live": True}


# -- the council's goals ----------------------------------------------------------


def test_the_writers_never_take_a_goal_queued_for_the_council(
    led, tmp_path, monkeypatch
) -> None:
    theirs = led.add_task(TEST, WORDS, said_by="operator", council=True)
    free = led.add_task(OTHER, "x", said_by="operator")
    made = []

    def build(root, head, task, **kw):
        made.append(task["task_id"])
        return "wait", "not now"

    monkeypatch.setattr(tool, "build_task_job", build)
    tool.task_jobs(led, tmp_path, "head", set(), (), (), budget=5)
    assert set(made) == {free}
    assert led.task(theirs)["status"] == "open"
    assert led.held_for_council() == {theirs}


def test_the_councils_goals_take_the_envelopes_slots_first(led, tmp_path) -> None:
    plain = led.add_task(OTHER, "x", said_by="operator")
    theirs = [
        led.add_task(TEST, WORDS, said_by="operator", council=True),
        led.add_task(
            "frontend/src/workbench/a.ts", "y", said_by="operator", council=True
        ),
    ]
    for tid in (plain, *theirs):
        _brief(led, tid)
    asked = []
    tool.missions_hour(
        led,
        tmp_path,
        envelope=Live(),
        originate=lambda task, seen: (
            asked.append(task["task_id"]) or {"state": "awaiting_approval"}
        ),
    )
    assert asked == theirs  # two slots an hour, the older plain goal waits


def test_the_command_line_queues_a_goal_for_the_council(led, capsys) -> None:
    assert tool.main(["task", "add", "--file", TEST, "--council", WORDS]) == 0
    tid = capsys.readouterr().out.strip()
    assert led.held_for_council() == {tid}
    assert "(the council's goal): open" in "\n".join(tool.task_section(led))


# -- the measure ------------------------------------------------------------------


def test_the_report_counts_the_missions_by_their_latest_state(led) -> None:
    """The six missions of 2026-11-13: two failed in deliberation (no
    verification key), two blocked by the Memory queen, two completed."""
    for n, state in enumerate(["failed", "failed", "blocked", "blocked"]):
        _sent(led, led.add_task(OTHER, f"g{n}", said_by="operator"), f"m-{n}", state)
    for n in (4, 5):
        tid = led.add_task(OTHER, f"g{n}", said_by="operator")
        _sent(led, tid, f"m-{n}", "awaiting_approval")
        _sent(led, tid, f"m-{n}", "completed")
    _sent(
        led, led.add_task(OTHER, "g6", said_by="operator"), "m-6", "awaiting_approval"
    )
    # A refusal spent no slot and is no mission.
    led.record_origination(
        led.add_task(OTHER, "g7", said_by="operator"), {"state": "refused"}
    )
    lines = tool.mission_section(led)
    day = led.missions()[0]["sent_at"][:10]
    assert lines[1] == (
        "- in all: sent 7; completed 2 (33% of 6 decided); failed in deliberation 2; "
        "blocked by the council 2; not yet run 1"
    )
    assert lines[2].startswith(f"- {day}: sent 7; completed 2")
    assert "**The council's missions**" in tool.report(led)


def test_each_day_is_counted_by_the_day_its_missions_were_sent(led) -> None:
    a = led.add_task(OTHER, "a", said_by="operator")
    _sent(led, a, "m-a", "completed", at="2026-11-14T09:00:00+00:00")
    b = led.add_task(OTHER, "b", said_by="operator")
    _sent(led, b, "m-b", "run_failed", at="2026-11-15T09:00:00+00:00")
    assert tool.mission_section(led)[2:4] == [
        "- 2026-11-14: sent 1; completed 1 (100% of 1 decided)",
        "- 2026-11-15: sent 1; completed 0 (0% of 1 decided); failed in its run 1",
    ]


def test_no_missions_no_section(led) -> None:
    assert tool.mission_section(led) == []


# -- the reviewer judges intent -----------------------------------------------------


def test_a_first_tests_reviewer_is_told_passing_is_not_enough() -> None:
    finding = Finding(
        "frontend/src/superbrain/core/Performance/EventThrottler.test.ts",
        dw.MISSING_TEST,
        (),
    )
    prompt = dw.first_test_review_prompt(finding, "module", "test")
    assert dw.TEST_INTENT in prompt
    assert "name the defect" in prompt


def test_a_tasks_reviewer_is_told_too_with_the_operators_words_deciding() -> None:
    one = dw.task_review_prompt(TEST, WORDS, "before", "diff")
    assert dw.TASK_TEST_INTENT in one
    many = dw.task_files_review_prompt(
        WORDS, [(TEST, "before", "diff"), (OTHER, "before", "diff")]
    )
    assert dw.TASK_TEST_INTENT in many
    assert "unless the operator's task asks for exactly that" in dw.TASK_TEST_INTENT
