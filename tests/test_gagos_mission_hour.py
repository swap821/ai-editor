"""GAGOS's hour runs the missions the council deliberated (2026-11-13).

Move A3 in the hour. A goal GAGOS originated runs inside the operator's
envelope before the workshop's batch, and the batch's writers leave it to the
mission's worker. The worker is the workshop's own writer, sandbox and
reviewer, recorded in the workshop's ledger, so a change the council promoted
and the reviewer accepted is delivered with the hour's work, and anything else
is withdrawn.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aios.domain.missions.mission_state import MissionState
from aios.infrastructure.missions.sqlite_mission_repository import (
    SqliteMissionRepository,
)
from aios.maintenance import sandbox_tests as sb
from aios.maintenance.daily_work import TASK_RULE, DailyLedger, Finding, StaticVerdict
from aios.api.routes import council as council_route
from tests.test_gagos_council_origination import TEST, WORDS, _briefed
from tests.test_gagos_mission_run import BASE, NEW, repo, world  # noqa: F401 - fixtures

from tools import gagos_daily as tool

MissionWork = tool.MissionWork  # the real class, before a test stands in for it


@pytest.fixture()
def led(tmp_path, monkeypatch) -> DailyLedger:
    ledger = DailyLedger(tmp_path / "ledger.db")
    monkeypatch.setattr(tool, "ledger", lambda: ledger)
    monkeypatch.setattr(tool, "goals_through_clerk", lambda: True)
    monkeypatch.setattr(tool, "cloud_coding_allowed", lambda: (True, ""))
    return ledger


def _originated(led, mission_id="mission-0123456789ab", state="awaiting_approval"):
    tid = led.add_task(TEST, WORDS, said_by="operator")
    led.record_intake(tid, {**_briefed(), "reason": "", "mission_request": None})
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
    return tid


# -- the hour's bookkeeping ----------------------------------------------------------


@pytest.mark.parametrize(
    "said,state",
    [
        ("completed", "completed"),
        ("failed", "run_failed"),
        ("refused", "run_refused"),
    ],
)
def test_each_waiting_mission_runs_once_and_its_end_is_recorded(
    led, tmp_path, said, state
) -> None:
    tid = _originated(led)
    ran = []

    def run(task, mission_id, work):
        ran.append(mission_id)
        return {"state": said, "reason": "" if said == "completed" else "why"}

    for _ in range(2):
        tool.runs_hour(led, tmp_path, region="r", run=run)
    assert ran == ["mission-0123456789ab"]
    assert led.originations()[tid]["state"] == state
    assert tid in tool.council_goals(led)


def test_a_run_that_raises_is_a_failed_run_said_not_hidden(led, tmp_path) -> None:
    tid = _originated(led)

    def run(task, mission_id, work):
        raise RuntimeError("docker is gone")

    tool.runs_hour(led, tmp_path, region="r", run=run)
    row = led.originations()[tid]
    assert row["state"] == "run_failed" and "docker is gone" in row["reason"]


def test_the_missions_wait_when_the_cloud_may_not_be_asked(
    led, tmp_path, monkeypatch
) -> None:
    _originated(led)
    monkeypatch.setattr(tool, "cloud_coding_allowed", lambda: (False, "revoked"))
    ran = []
    tool.runs_hour(led, tmp_path, region="r", run=lambda *a: ran.append(a))
    assert ran == []


def test_the_batch_leaves_the_councils_goals_to_their_missions(
    led, tmp_path, monkeypatch
) -> None:
    with_council = _originated(led)
    free = led.add_task("frontend/src/superbrain/lib/other.ts", "x", said_by="operator")
    made = []

    def build(root, head, task, **kw):
        made.append(task["task_id"])
        return "wait", "not now"

    monkeypatch.setattr(tool, "build_task_job", build)
    tool.task_jobs(led, tmp_path, "head", set(), (), (), budget=5)
    assert made == [free] and with_council not in made


def test_a_goal_the_council_ran_is_never_originated_again(led, tmp_path) -> None:
    _originated(led, state="completed")
    asked = []
    tool.missions_hour(
        led,
        tmp_path,
        envelope=object(),
        originate=lambda task, seen: asked.append(task),
    )
    assert asked == []


# -- the worker is the workshop's own --------------------------------------------------


def _job(led, tid):
    return (
        Finding(TEST, TASK_RULE, ()),
        BASE,
        BASE,
        {},
        "the prompt",
        "the system",
        dict(base_text=BASE, base_commit="head", facts=()),
        tid,
        None,
    )


@pytest.fixture()
def workshop(led, monkeypatch):
    """The workshop's steps with no model, no linter and no container: the
    writer answers NEW, the static checks pass, the tests pass."""
    monkeypatch.setattr(
        tool,
        "build_task_job",
        lambda root, head, task, **kw: ("job", _job(led, task["task_id"])),
    )
    monkeypatch.setattr(tool, "project_facts", lambda root: ())

    def record_one_file(led_, root, lint, job, *, model, raw, took, started):
        f, text, *_ = job
        took(
            led_.record_proposal(
                f,
                **job[6],
                model=model,
                new_text=raw,
                verdict=StaticVerdict(True, "", 1),
            )
        )

    monkeypatch.setattr(tool, "record_one_file", record_one_file)
    tested = []

    def run_change_tests(trees, *, base_commit, changes):
        tested.append(dict(changes))
        return sb.SandboxVerdict(
            sb.PASSED, "2 tests in 1 files pass", tests=(TEST,), passed_count=2
        )

    monkeypatch.setattr(tool, "run_change_tests", run_change_tests)
    monkeypatch.setattr(tool, "review_evidence", lambda p, finding: "evidence")
    return tested


def _work(led, tid, root, *, word="accept"):
    return MissionWork(
        led,
        root,
        "head",
        led.task(tid),
        region="r",
        complete=lambda prompt, system, rid: NEW,
        reviewer=lambda prompt: (word, "it does what he asked", "claude-opus"),
    )


def test_the_hour_runs_a_real_mission_and_its_change_is_delivered(
    world, led, workshop, monkeypatch
) -> None:
    envelope, runtime, mission_id, (root, base) = world
    tid = _originated(led, mission_id=mission_id)
    monkeypatch.setattr(tool, "_git", lambda r, *a: base)
    monkeypatch.setattr(tool.config, "COUNCIL_RUNTIME_DIR", runtime)
    monkeypatch.setattr(
        tool,
        "MissionWork",
        lambda led_, root_, head, task, region: _work(led_, task["task_id"], root_),
    )
    tool.runs_hour(led, root, region="r", envelope=envelope)
    assert led.originations()[tid]["state"] == "completed"
    record = SqliteMissionRepository(runtime / council_route.MISSIONS_DB_NAME).get(
        mission_id
    )
    assert record.state is MissionState.COMPLETED
    (p,) = led.proposals()
    assert p["status"] == "accepted" and p["new_text"] == NEW
    assert sb.SandboxVerdict.from_json(p["sandbox"]).outcome == sb.PASSED
    assert led.reviews(p["proposal_id"])["claude"]["verdict"] == "accept"
    assert led.task(tid)["status"] == "taken"
    assert workshop == [{TEST: NEW}]
    assert Path(record.contract.workspace_root, TEST).read_text(encoding="utf-8") == NEW


def test_a_rejected_change_is_withdrawn_and_the_mission_fails(
    world, led, workshop, monkeypatch
) -> None:
    envelope, runtime, mission_id, (root, base) = world
    tid = _originated(led, mission_id=mission_id)
    monkeypatch.setattr(tool, "_git", lambda r, *a: base)
    monkeypatch.setattr(tool.config, "COUNCIL_RUNTIME_DIR", runtime)
    monkeypatch.setattr(
        tool,
        "MissionWork",
        lambda led_, root_, head, task, region: _work(
            led_, task["task_id"], root_, word="reject"
        ),
    )
    tool.runs_hour(led, root, region="r", envelope=envelope)
    row = led.originations()[tid]
    assert row["state"] == "run_failed" and "the reviewer rejects" in row["reason"]
    (p,) = led.proposals()
    assert p["status"] == "refused"  # never delivered
    record = SqliteMissionRepository(runtime / council_route.MISSIONS_DB_NAME).get(
        mission_id
    )
    assert record.state is MissionState.FAILED
