"""A completed council mission becomes a trajectory (2026-11-14).

The learning service never saw GAGOS's missions: it read the operator's API
mission store, and the missions' evidence was kept in memory only until #677.
Pinned here on a real council mission (the run's fixtures): its trajectory is
captured from its own authoritative records, and the learning service refuses
a mission that did not complete or kept no evidence.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from aios import config
from aios.domain.learning.contracts import ToolObservation
from aios.domain.learning.trajectory_repository import TrajectoryRepository
from aios.operations.mission_learning import capture_mission_trajectory
from tests import test_gagos_mission_hour as hour_tests
from tests import test_gagos_mission_run as run_tests
from tools import gagos_daily as tool

repo, world = run_tests.repo, run_tests.world
led, workshop = hour_tests.led, hour_tests.workshop


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


OBSERVATIONS = (
    ToolObservation(
        observation_id="o-write",
        tool="writer",
        result_digest=_digest(run_tests.NEW),
        status="completed",
    ),
    ToolObservation(
        observation_id="o-sandbox",
        tool="sandbox",
        result_digest=_digest("2 tests in 1 files pass"),
        status="completed",
    ),
)


def _capture(world, mission_id):
    _envelope, runtime, _mission, (_root, base) = world
    return capture_mission_trajectory(
        mission_id,
        runtime_root=runtime,
        observations=OBSERVATIONS,
        expert_provider="plan",
        expert_model="claude-sonnet-5-5",
        project_digest=base,
        context_digest=_digest("the goal"),
        proposal_digest=_digest(run_tests.NEW),
        human_intervention_ids=("envelope:envelope-1",),
    )


@pytest.fixture()
def store(tmp_path, monkeypatch):
    path = tmp_path / "operational.db"
    monkeypatch.setattr(config, "OPERATIONAL_STATE_DB_PATH", path)
    return path


def test_a_completed_missions_trajectory_is_captured(world, store) -> None:
    out, record, _seen = run_tests._run(world)
    assert out["state"] == "completed", out
    trajectory = _capture(world, record.contract.mission_id)
    assert trajectory.mission_id == record.contract.mission_id
    assert trajectory.final_outcome == "success"
    assert trajectory.promotion_status == "promoted"
    assert trajectory.verification_results, "verified, from the durable store"
    assert trajectory.human_intervention_ids == ("envelope:envelope-1",)
    held = TrajectoryRepository(store).get(trajectory.trajectory_id)
    assert held is not None and held.expert_model == "claude-sonnet-5-5"


def test_a_failed_mission_is_not_learned_from(world, store) -> None:
    out, record, _seen = run_tests._run(
        world, review=lambda edits, verdict: (False, "not what he asked")
    )
    assert out["state"] != "completed"
    with pytest.raises(ValueError):
        _capture(world, record.contract.mission_id)


def test_a_mission_with_no_kept_evidence_is_not_learned_from(world, store) -> None:
    _envelope, _runtime, mission_id, _repo = world  # deliberated, never run
    with pytest.raises(ValueError):
        _capture(world, mission_id)


# -- in the hour ----------------------------------------------------------------------


def test_the_hour_captures_the_trajectory_of_a_mission_it_completed(
    world, led, workshop, store, monkeypatch, capsys
) -> None:
    envelope, runtime, mission_id, (root, base) = world
    tid = hour_tests._originated(led, mission_id=mission_id)
    monkeypatch.setattr(tool, "_git", lambda r, *a: base)
    monkeypatch.setattr(tool.config, "COUNCIL_RUNTIME_DIR", runtime)
    monkeypatch.setattr(
        tool,
        "MissionWork",
        lambda led_, root_, head, task, region: hour_tests._work(
            led_, task["task_id"], root_
        ),
    )
    tool.runs_hour(led, root, region="r", envelope=envelope)
    assert led.originations()[tid]["state"] == "completed"
    out = capsys.readouterr().out
    assert "learning: trajectory trajectory-" in out, out
    with TrajectoryRepository(store)._connection() as db:
        held = [
            json.loads(payload)["mission_id"]
            for (payload,) in db.execute("SELECT payload_json FROM expert_trajectories")
        ]
    assert held == [mission_id]


def test_a_refused_capture_is_said_and_changes_nothing(capsys) -> None:
    class Work:
        model = "claude-sonnet-5-5"
        task = {"text": "a goal", "files": ["a.ts"]}
        colony = None

        def _rows(self):
            return [{"proposal_id": "gd-1", "rel": "a.ts", "new_text": "x"}]

    def refuse(*args, **kwargs):
        raise ValueError("verification evidence is stale")

    tool.mission_trajectory(
        Work(), {"mission_id": "mission-1", "envelope_id": None}, "head", capture=refuse
    )
    assert "learning: no trajectory -- ValueError: verification evidence is stale" in (
        capsys.readouterr().out
    )
