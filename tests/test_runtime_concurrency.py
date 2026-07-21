"""Tests for the global worker-subprocess concurrency cap (fail-closed DoS guard)."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from aios import config
from aios.runtime import concurrency
from aios.runtime.concurrency import WorkerCapacityError, WorkerPool
from aios.runtime.contracts import MissionContract
from aios.runtime.spawner import WorkerSpawner


def test_pool_rejects_when_full() -> None:
    pool = WorkerPool(1)
    with pool.slot():
        with pytest.raises(WorkerCapacityError):
            with pool.slot():
                pass


def test_pool_releases_slot_for_reuse() -> None:
    pool = WorkerPool(1)
    with pool.slot():
        pass
    with pool.slot():  # reusable after release
        pass


def test_pool_allows_up_to_limit_then_rejects() -> None:
    pool = WorkerPool(2)
    with pool.slot(), pool.slot():
        with pytest.raises(WorkerCapacityError):
            with pool.slot():
                pass


def _mission(workspace: Path) -> MissionContract:
    return MissionContract(
        mission_id="mission-cap",
        goal="capacity test",
        worker_type="deterministic_worker",
        created_by="planner",
        workspace_root=str(workspace),
        allowed_files=["x.txt"],
        verification_commands=[],
    )


def test_spawner_fails_closed_at_global_capacity(tmp_path: Path) -> None:
    """When the global pool is exhausted, spawner.run fails closed (no subprocess)."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    contract = _mission(workspace)
    concurrency.WORKER_POOL.configure(1)
    try:
        with concurrency.WORKER_POOL.slot():  # occupy the only slot
            with pytest.raises(WorkerCapacityError):
                asyncio.run(WorkerSpawner(runtime_root=tmp_path / "runtime").run(contract))
    finally:
        concurrency.WORKER_POOL.configure(config.COUNCIL_MAX_CONCURRENT_WORKERS)
