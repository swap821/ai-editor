"""Adapters that place existing worker runtimes behind the Foundry boundary."""
from __future__ import annotations

import inspect
from typing import Any, Callable

from aios.domain.workers.worker_contract import WorkerStrategyName


class StrategyUnavailable(RuntimeError):
    """Raised when a strategy is requested without its explicit runtime input."""


class DeterministicWorkerStrategy:
    name = WorkerStrategyName.DETERMINISTIC

    def __init__(self, spawner: Any | None = None) -> None:
        self.spawner = spawner

    async def run(self, request: Any) -> Any:
        if self.spawner is None:
            runtime_root = request.context.get("runtime_root")
            if runtime_root is None:
                raise StrategyUnavailable(
                    "deterministic strategy requires runtime_root in context or an explicit spawner"
                )
            from aios.runtime.spawner import WorkerSpawner

            self.spawner = WorkerSpawner(runtime_root=runtime_root)
        return await self.spawner.run(request.contract, claim=request.context.get("claim", True))


class _CallableStrategy:
    name: WorkerStrategyName

    def __init__(self, handler: Callable[..., Any] | None = None) -> None:
        self.handler = handler

    async def run(self, request: Any) -> Any:
        if self.handler is None:
            raise StrategyUnavailable(
                f"{self.name.value} strategy requires an explicit runtime handler"
            )
        value = self.handler(request)
        if inspect.isawaitable(value):
            return await value
        return value


class ToolLoopWorkerStrategy(_CallableStrategy):
    name = WorkerStrategyName.TOOL_LOOP


class RolePassWorkerStrategy(_CallableStrategy):
    name = WorkerStrategyName.ROLE_PASS


class SwarmWorkerStrategy(_CallableStrategy):
    name = WorkerStrategyName.SWARM


class ResearchWorkerStrategy(_CallableStrategy):
    name = WorkerStrategyName.RESEARCH


class CodeWorkerStrategy(_CallableStrategy):
    name = WorkerStrategyName.CODE


class TestWorkerStrategy(_CallableStrategy):
    name = WorkerStrategyName.TEST


class InspectionWorkerStrategy(_CallableStrategy):
    name = WorkerStrategyName.INSPECTION


__all__ = [
    "CodeWorkerStrategy",
    "DeterministicWorkerStrategy",
    "InspectionWorkerStrategy",
    "ResearchWorkerStrategy",
    "RolePassWorkerStrategy",
    "StrategyUnavailable",
    "SwarmWorkerStrategy",
    "TestWorkerStrategy",
    "ToolLoopWorkerStrategy",
]
