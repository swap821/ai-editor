from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest

from aios.application.workers.foundry import UnknownWorkerStrategy, WorkerFoundry
from aios.application.workers.scheduler import WorkerScheduler
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
            scheduler.submit(
                _spec("low", "mission-a", priority=1), lambda: run("low")
            )
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
        "born",
        "running",
        "completed",
        "dissolved",
    ]
    assert all(event.event_type == "tool.lifecycle.changed" for event in events)
    assert all(
        event.payload["payload"]["state"] not in {"approved", "granted"}
        for event in events
    )


def _spec(worker_id: str, mission_id: str, priority: int):
    from aios.domain.workers.worker_contract import WorkerSpec

    return WorkerSpec(
        worker_id=worker_id,
        mission_id=mission_id,
        contract_digest="digest",
        strategy=WorkerStrategyName.DETERMINISTIC,
        priority=priority,
    )
