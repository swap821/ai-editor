from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest

from aios.application.workers.foundry import UnknownWorkerStrategy, WorkerFoundry
from aios.application.workers.scheduler import WorkerScheduler
from aios.application.workspaces import StagedWorkspaceManager, WorkspacePathViolation
from aios.domain.missions.mission_contract import MissionContract
from aios.domain.workers.worker_contract import (
    WorkerState,
    WorkerStrategyName,
    contract_digest,
)
from aios.runtime.cortex_bus import CortexBus


def _contract(mission_id: str = "mission-worker") -> MissionContract:
    return MissionContract(
        mission_id=mission_id,
        operator_id="operator-1",
        goal="inspect a bounded project",
        worker_type="deterministic",
        created_by="queen:planner",
    )


def test_worker_identity_is_derived_from_exact_contract() -> None:
    original = _contract()
    changed = original.model_copy(update={"goal": "different bounded project"})
    assert contract_digest(original) != contract_digest(changed)


def test_scheduler_honours_priority_and_per_mission_cap() -> None:
    async def scenario() -> list[str]:
        scheduler = WorkerScheduler(max_active=1, max_per_mission=1)
        started: list[str] = []

        async def run(label: str) -> str:
            started.append(label)
            await asyncio.sleep(0)
            return label

        low = asyncio.create_task(
            scheduler.submit(_spec("low", "mission-a", priority=1), lambda: run("low"))
        )
        await asyncio.sleep(0)
        high = asyncio.create_task(
            scheduler.submit(
                _spec("high", "mission-b", priority=10), lambda: run("high")
            )
        )
        assert await asyncio.gather(low, high) == ["low", "high"]
        assert started == ["low", "high"]
        assert scheduler.snapshot().active == 0
        return started

    assert asyncio.run(scenario()) == ["low", "high"]


def test_foundry_rejects_unknown_strategy_before_running_anything() -> None:
    async def scenario() -> None:
        foundry = WorkerFoundry()
        with pytest.raises(UnknownWorkerStrategy):
            await foundry.run(_contract(), strategy="not-a-worker")
        assert foundry.scheduler.snapshot().active == 0

    asyncio.run(scenario())


def test_foundry_does_not_advertise_unwired_strategies() -> None:
    foundry = WorkerFoundry()

    assert foundry.strategies == ("deterministic",)
    with pytest.raises(UnknownWorkerStrategy):
        foundry.select("tool_loop", _contract())


def test_foundry_emits_canonical_worker_lifecycle_with_contract_context(
    tmp_path: Path,
) -> None:
    bus = CortexBus(tmp_path / "cortex.db")

    @dataclass
    class Result:
        status: str = "completed"

    async def handler(request) -> Result:  # noqa: ANN001
        assert request.spec.mission_id == "mission-worker"
        assert request.spec.allowed_tools == ("read_file",)
        assert request.spec.scope == {"root": "training_ground"}
        assert request.spec.budgets["max_steps"] == 12
        assert request.spec.data_classification == "private"
        assert request.spec.executor_policy == "private_executor"
        return Result()

    async def scenario() -> None:
        from aios.application.workers.strategies.legacy import CodeWorkerStrategy

        contract = _contract().model_copy(
            update={
                "allowed_tools": ["read_file"],
                "scope": {"root": "training_ground"},
                "metadata": {
                    "data_classification": "private",
                    "executor_policy": "private_executor",
                },
            }
        )
        foundry = WorkerFoundry(
            strategies={"code": CodeWorkerStrategy(handler)},
            bus=bus,
            max_active=1,
        )
        await foundry.run(contract, strategy=WorkerStrategyName.CODE)

    asyncio.run(scenario())
    events = bus.fetch_since(0)
    assert [event.event_type for event in events] == [
        "worker.requested",
        "worker.admitted",
        "worker.started",
        "worker.completed",
        "worker.dissolved",
    ]
    payload = events[0].payload["payload"]
    assert payload["worker_principal_id"].startswith("principal:worker:")
    assert payload["mission_id"] == "mission-worker"
    assert payload["contract_digest"]
    assert payload["allowed_tools"] == ["read_file"]
    assert payload["scope"] == {"root": "training_ground"}
    assert payload["budgets"]["max_steps"] == 12
    assert payload["data_classification"] == "private"
    assert payload["executor_policy"] == "private_executor"


def test_foundry_records_derived_principal_and_dissolution() -> None:
    @dataclass
    class Result:
        status: str = "completed"

    async def handler(request) -> Result:  # noqa: ANN001
        assert request.principal.authentication_level == "derived"
        assert request.principal.mission_id == "mission-worker"
        return Result()

    async def scenario() -> None:
        from aios.application.workers.strategies.legacy import CodeWorkerStrategy

        foundry = WorkerFoundry(
            strategies={"code": CodeWorkerStrategy(handler)}, max_active=1
        )
        result = await foundry.run(_contract(), strategy=WorkerStrategyName.CODE)
        assert result.status == "completed"
        worker_id = next(iter(foundry._principals))
        assert foundry.principal(worker_id) is not None
        assert foundry.lifecycle(worker_id).state == WorkerState.DISSOLVED

    asyncio.run(scenario())


def test_foundry_lifecycle_is_observation_only_on_existing_cortex_bus(
    tmp_path: Path,
) -> None:
    bus = CortexBus(tmp_path / "cortex.db")

    @dataclass
    class Result:
        status: str = "completed"

    async def handler(request) -> Result:  # noqa: ANN001
        return Result()

    async def scenario() -> None:
        from aios.application.workers.strategies.legacy import CodeWorkerStrategy

        foundry = WorkerFoundry(
            strategies={"code": CodeWorkerStrategy(handler)},
            bus=bus,
            max_active=1,
        )
        await foundry.run(_contract(), strategy=WorkerStrategyName.CODE)

    asyncio.run(scenario())
    events = bus.fetch_since(0)
    states = [event.payload["payload"]["state"] for event in events]
    assert states == [
        "requested",
        "admitted",
        "running",
        "completed",
        "dissolved",
    ]
    assert [event.event_type for event in events] == [
        "worker.requested",
        "worker.admitted",
        "worker.started",
        "worker.completed",
        "worker.dissolved",
    ]
    assert all(
        event.payload["payload"]["state"] not in {"approved", "granted"}
        for event in events
    )


def test_foundry_stages_worker_workspace_and_keeps_project_untouched(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = project / "source.txt"
    source.write_text("baseline\n", encoding="utf-8")
    manager = StagedWorkspaceManager(tmp_path / "staged", enrolled_roots=(project,))
    seen: list[Path] = []

    @dataclass
    class Result:
        status: str = "completed"

    async def handler(request) -> Result:  # noqa: ANN001
        workspace = Path(request.contract.workspace_root)
        seen.append(workspace)
        (workspace / "worker.txt").write_text("stage only\n", encoding="utf-8")
        return Result()

    async def scenario() -> None:
        from aios.application.workers.strategies.legacy import CodeWorkerStrategy

        foundry = WorkerFoundry(
            strategies={"code": CodeWorkerStrategy(handler)},
            workspace_manager=manager,
            max_active=1,
        )
        contract = _contract().model_copy(update={"workspace_root": str(project)})
        result = await foundry.run(contract, strategy=WorkerStrategyName.CODE)
        assert result.status == "completed"

    asyncio.run(scenario())
    assert seen and seen[0] != project
    assert not (project / "worker.txt").exists()
    lease = manager.for_mission("mission-worker")
    assert lease is not None
    assert (Path(lease.workspace_path) / "worker.txt").read_text() == "stage only\n"


def test_foundry_rejects_unenrolled_workspace_before_worker_handler(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    manager = StagedWorkspaceManager(tmp_path / "staged", enrolled_roots=())
    called: list[bool] = []

    async def scenario() -> None:
        nonlocal called
        from aios.application.workers.strategies.legacy import CodeWorkerStrategy

        async def handler(request) -> object:  # noqa: ANN001
            called.append(True)
            return object()

        foundry = WorkerFoundry(
            strategies={"code": CodeWorkerStrategy(handler)},
            workspace_manager=manager,
        )
        contract = _contract().model_copy(update={"workspace_root": str(project)})
        with pytest.raises(WorkspacePathViolation, match="enrolled"):
            await foundry.run(contract, strategy=WorkerStrategyName.CODE)

    asyncio.run(scenario())
    assert called == []


def _spec(worker_id: str, mission_id: str, priority: int):
    from aios.domain.workers.worker_contract import WorkerSpec

    return WorkerSpec(
        worker_id=worker_id,
        mission_id=mission_id,
        contract_digest="digest",
        strategy=WorkerStrategyName.DETERMINISTIC,
        priority=priority,
    )
