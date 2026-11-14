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
from types import SimpleNamespace

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


# -- remembered (organ 18) --------------------------------------------------------------

from aios.application.memory.authority import MemoryAuthority  # noqa: E402
from aios.infrastructure.memory import MemoryAuthorityStore  # noqa: E402
from aios.operations.mission_learning import (  # noqa: E402
    mission_memory_hints,
    remember_mission,
)


class _Semantic:
    """Production always registers a semantic store; with it, a recall of a
    type it does not own must still reach the authority's own records."""

    memory_types = ("semantic",)

    def recall(self, query, context):
        return ()

    def rebuild_derived_indexes(self) -> None:
        return None


@pytest.fixture()
def memory(tmp_path):
    return MemoryAuthority(
        store=MemoryAuthorityStore(tmp_path / "memory.db"),
        adapters={"semantic": _Semantic()},
    )


def test_a_completed_mission_is_remembered_and_recalled_for_its_files(
    world, store, memory
) -> None:
    out, record, _seen = run_tests._run(world)
    assert out["state"] == "completed", out
    _envelope, runtime, _mission, _repo = world
    mission_id = record.contract.mission_id
    remembered = remember_mission(mission_id, runtime_root=runtime, authority=memory)
    assert remembered.provenance.source_mission_id == mission_id
    (hint,) = mission_memory_hints(
        [run_tests.TEST], runtime_root=runtime, authority=memory
    )
    assert run_tests.TEST in hint and mission_id in hint
    assert (
        mission_memory_hints(
            ["frontend/src/elsewhere.ts"], runtime_root=runtime, authority=memory
        )
        == []
    ), "only goals over the same files are reminded"


def test_a_mission_the_reviewer_rejected_is_not_remembered(
    world, store, memory
) -> None:
    out, record, _seen = run_tests._run(
        world, review=lambda edits, verdict: (False, "not what he asked")
    )
    _envelope, runtime, _mission, _repo = world
    with pytest.raises(ValueError, match="only a completed mission"):
        remember_mission(
            record.contract.mission_id, runtime_root=runtime, authority=memory
        )


def test_the_hour_remembers_a_mission_it_completed(
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
    remembered: list = []

    def remember(mid, *, runtime_root):
        remembered.append(mid)
        return SimpleNamespace(record_id="memory-1")

    monkeypatch.setattr(tool, "_remember_mission", remember)
    tool.runs_hour(led, root, region="r", envelope=envelope)
    assert led.originations()[tid]["state"] == "completed"
    assert remembered == [mission_id]
    assert "memory: mission remembered (memory-1)" in capsys.readouterr().out


def test_a_later_goal_on_the_same_files_carries_the_memory_into_the_council(
    world, tmp_path, monkeypatch
) -> None:
    """The consumer: originate_goal hands what GAGOS remembers to the council
    as its trail, and the deliberated contract carries it."""
    from aios.operations import council_origination as co
    from aios.operations import mission_learning
    from aios.runtime.run_ledger import RunLedgerStore
    from tests.test_gagos_council_origination import _briefed, _envelope, _task

    asked: list = []

    def hints(files, *, runtime_root):
        asked.append(list(files))
        return ["GAGOS already completed a mission on a.ts: an earlier goal"]

    monkeypatch.setattr(mission_learning, "mission_memory_hints", hints)
    runtime = tmp_path / "later-runtime"
    runtime.mkdir()
    workspace = tmp_path / "later-workspace"
    workspace.mkdir()
    out = co.originate_goal(
        _task(),
        _briefed(),
        envelope=_envelope(tmp_path / "later"),
        workspace_root=co.gagos_workspace(workspace),
        runtime_root=runtime,
        detect_injection=lambda text: None,
    )
    assert out["state"] == "awaiting_approval", out
    assert asked == [[run_tests.TEST]]
    contract = RunLedgerStore(runtime).read(out["mission_id"]).contract
    assert "GAGOS already completed a mission on a.ts: an earlier goal" in (
        contract.pheromone_context
    )


def test_a_memory_that_cannot_be_read_never_blocks_a_goal(
    world, tmp_path, monkeypatch
) -> None:
    from aios.operations import council_origination as co
    from aios.operations import mission_learning
    from tests.test_gagos_council_origination import _briefed, _envelope, _task

    def broken(files, *, runtime_root):
        raise RuntimeError("the memory store is locked")

    monkeypatch.setattr(mission_learning, "mission_memory_hints", broken)
    runtime = tmp_path / "broken-runtime"
    runtime.mkdir()
    workspace = tmp_path / "broken-workspace"
    workspace.mkdir()
    out = co.originate_goal(
        _task(),
        _briefed(),
        envelope=_envelope(tmp_path / "broken"),
        workspace_root=co.gagos_workspace(workspace),
        runtime_root=runtime,
        detect_injection=lambda text: None,
    )
    assert out["state"] == "awaiting_approval", out
