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
from tests import test_gagos_mission_run as run_tests

from tools import gagos_daily as tool

MissionWork = tool.MissionWork  # the real class, before a test stands in for it
BASE, NEW = run_tests.BASE, run_tests.NEW
# The real council mission of the run's tests, as fixtures here too.
repo, world = run_tests.repo, run_tests.world


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
    # Each task is made for both routes (#651); the council's never.
    assert set(made) == {free} and with_council not in made


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
    built = []

    def build(root, head, task, **kw):
        built.append(kw.get("plan"))
        return "job", _job(led, task["task_id"])

    monkeypatch.setattr(tool, "build_task_job", build)
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
    return tested, built


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
    tested, built = workshop
    assert tested == [{TEST: NEW}]
    # The mission's writer is on the operator's plan: its route's build (#651).
    assert built == [True]
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


# -- the keys a run signs with -------------------------------------------------------


class _Store:
    def __init__(self, **values) -> None:
        self.values, self.asked = values, []

    def get(self, name):
        self.asked.append(name)
        return self.values.get(name)


def test_a_run_loads_only_its_two_keys_from_the_keystore(monkeypatch) -> None:
    # Set empty through monkeypatch, so what the load puts in the environment
    # is taken out again after the test.
    for name in tool.MISSION_KEYS:
        monkeypatch.setenv(name, "")
    store = _Store(
        AIOS_VERIFICATION_AUTHORITY_KEY="v" * 40,
        AIOS_PROMOTION_AUTHORITY_KEY="p" * 40,
        AWS_BEARER_TOKEN_BEDROCK="never asked",
    )
    assert tool.mission_keys_missing(store) == []
    assert sorted(store.asked) == sorted(tool.MISSION_KEYS)


def test_without_its_keys_no_mission_runs_and_the_hour_says_which(
    led, tmp_path, monkeypatch, capsys
) -> None:
    _originated(led)
    monkeypatch.setattr(tool, "_git", lambda r, *a: "head")
    monkeypatch.setattr(
        tool, "mission_keys_missing", lambda: ["AIOS_PROMOTION_AUTHORITY_KEY"]
    )
    tool.runs_hour(led, tmp_path, region="r")
    assert "AIOS_PROMOTION_AUTHORITY_KEY" in capsys.readouterr().out
    assert led.originations()  # nothing recorded beyond the origination
    assert {o["state"] for o in led.originations().values()} == {"awaiting_approval"}


# -- the council's events reach the cortex bus ----------------------------------------


def test_the_hours_missions_and_originations_post_to_the_cortex_bus(
    led, tmp_path, monkeypatch
) -> None:
    """2026-11-13: both ran with no bus, so the face's portrait never saw a
    GAGOS mission. They now post where the hour's writers do."""
    from aios.operations import council_origination

    bus = object()
    monkeypatch.setattr(tool, "cortex_bus", lambda: bus)
    monkeypatch.setattr(tool, "mission_keys_missing", lambda: [])
    monkeypatch.setattr(tool, "_git", lambda r, *a: "head")
    seen = {}

    def run_gagos_mission(mission_id, **kw):
        seen["run"] = kw.get("bus")
        return {"state": "completed", "reason": "", "files": {}}

    def originate_goal(task, intake, **kw):
        seen["originate"] = kw.get("bus")
        return {"state": "refused", "reason": "test", "mission_id": None}

    monkeypatch.setattr(council_origination, "run_gagos_mission", run_gagos_mission)
    monkeypatch.setattr(council_origination, "originate_goal", originate_goal)
    _originated(led)
    tool.runs_hour(led, tmp_path, region="r", envelope=object())
    assert seen["run"] is bus

    class Live:
        def status(self):
            return {"live": True}

    fresh = led.add_task(
        "frontend/src/superbrain/lib/other.ts", "x", said_by="operator"
    )
    led.record_intake(fresh, {**_briefed(), "reason": "", "mission_request": None})
    tool.missions_hour(led, tmp_path, envelope=Live())
    assert seen["originate"] is bus


def test_no_slot_is_taken_before_the_councils_keys_are_loaded(
    led, tmp_path, monkeypatch, capsys
) -> None:
    """2026-11-13, the first live envelope: both slots were spent on
    deliberations that failed at once for want of the verification key, which
    the hour loaded only for the runs, one step later."""
    from aios.operations import council_origination

    tid = led.add_task("frontend/src/superbrain/lib/other.ts", "x", said_by="operator")
    led.record_intake(tid, {**_briefed(), "reason": "", "mission_request": None})
    monkeypatch.setattr(
        tool, "mission_keys_missing", lambda: ["AIOS_VERIFICATION_AUTHORITY_KEY"]
    )
    asked = []
    monkeypatch.setattr(
        council_origination, "originate_goal", lambda *a, **k: asked.append(a)
    )

    class Live:
        def status(self):
            return {"live": True}

    tool.missions_hour(led, tmp_path, envelope=Live())
    assert asked == [] and led.originations() == {}
    assert "AIOS_VERIFICATION_AUTHORITY_KEY" in capsys.readouterr().out
