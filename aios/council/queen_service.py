"""Runtime Queen Services — long-lived wrappers with async inbox and lifecycle."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

from aios import config
from aios.operations.tracing import bind_trace_context, new_trace_context
from aios.runtime.contracts import MissionContract, QueenVerdict


class QueenService(ABC):
    """Long-lived service wrapper for a Queen, with async inbox and lifecycle."""

    name: str

    def __init__(self, name: str, queue_depth: int = 16):
        self.name = name
        self._inbox: asyncio.Queue[
            tuple[MissionContract, asyncio.Future[QueenVerdict]]
        ] = asyncio.Queue(maxsize=queue_depth)
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._processed = 0
        self._errors = 0

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._drain_loop())

    async def stop(self) -> None:
        self._running = False
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def health(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "alive": self._running,
            "queue_depth": self._inbox.qsize(),
            "processed": self._processed,
            "errors": self._errors,
        }

    async def submit(self, contract: MissionContract) -> QueenVerdict:
        """Submit a contract for review. Returns defer verdict if queue full."""

        loop = asyncio.get_event_loop()
        future: asyncio.Future[QueenVerdict] = loop.create_future()
        try:
            self._inbox.put_nowait((contract, future))
        except asyncio.QueueFull:
            return QueenVerdict(
                queen=self.name,
                verdict="defer",
                risk="YELLOW",
                reason="queen service backpressure: queue full",
            )
        return await future

    @abstractmethod
    async def _handle(self, contract: MissionContract) -> QueenVerdict:
        """Process a single contract — implemented by concrete services."""

    async def _drain_loop(self) -> None:
        """Internal loop consuming from inbox."""

        while True:
            contract, future = await self._inbox.get()
            # Organ 52: this loop outlives any single HTTP request (started
            # once via asyncio.create_task()), so nothing propagates a trace
            # context into it for free -- bind one derived from the queued
            # item's own mission_id at the point it's actually dequeued.
            trace_context = new_trace_context().with_ids(mission_id=contract.mission_id)
            try:
                with bind_trace_context(trace_context):
                    verdict = await self._handle(contract)
            except Exception as exc:  # noqa: BLE001 - a queen crash must not kill the service
                self._errors += 1
                verdict = QueenVerdict(
                    queen=self.name,
                    verdict="deny",
                    risk="RED",
                    reason=f"queen service error: {exc}",
                )
            finally:
                self._processed += 1
                self._inbox.task_done()
            if not future.done():
                future.set_result(verdict)


class _SyncQueenService(QueenService):
    """Base for Queens whose review() method is synchronous."""

    def __init__(self, name: str, queen: Any, queue_depth: int):
        super().__init__(name, queue_depth)
        self._queen = queen

    async def _handle(self, contract: MissionContract) -> QueenVerdict:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._queen.review, contract)


class PlannerQueenService(_SyncQueenService):
    def __init__(self, queue_depth: int = config.QUEEN_SERVICE_QUEUE_DEPTH):
        from aios.council.queens.planner import PlannerQueen

        super().__init__("planner", PlannerQueen(), queue_depth)


class SecurityQueenService(_SyncQueenService):
    def __init__(self, queue_depth: int = config.QUEEN_SERVICE_QUEUE_DEPTH):
        from aios.council.queens.security import SecurityQueen

        super().__init__("security", SecurityQueen(), queue_depth)


class MemoryQueenService(_SyncQueenService):
    def __init__(self, queue_depth: int = config.QUEEN_SERVICE_QUEUE_DEPTH):
        from aios.council.queens.memory import MemoryQueen

        super().__init__("memory", MemoryQueen(), queue_depth)


class TestingQueenService(_SyncQueenService):
    def __init__(self, queue_depth: int = config.QUEEN_SERVICE_QUEUE_DEPTH):
        from aios.council.queens.testing import TestingQueen

        super().__init__("testing", TestingQueen(), queue_depth)


class CritiqueQueenService(_SyncQueenService):
    def __init__(self, queue_depth: int = config.QUEEN_SERVICE_QUEUE_DEPTH):
        from aios.council.queens.critique import CritiqueQueen

        super().__init__("critique", CritiqueQueen(), queue_depth)


class RoutingQueenService(_SyncQueenService):
    def __init__(self, queue_depth: int = config.QUEEN_SERVICE_QUEUE_DEPTH):
        from aios.council.queens.routing import RoutingQueen

        super().__init__("routing", RoutingQueen(), queue_depth)


class ReflectionQueenService(_SyncQueenService):
    def __init__(self, queue_depth: int = config.QUEEN_SERVICE_QUEUE_DEPTH):
        from aios.council.queens.reflection import ReflectionQueen

        super().__init__("reflection", ReflectionQueen(), queue_depth)


class ProjectUnderstandingQueenService(_SyncQueenService):
    def __init__(self, queue_depth: int = config.QUEEN_SERVICE_QUEUE_DEPTH):
        from aios.council.queens.project_understanding import ProjectUnderstandingQueen

        super().__init__(
            "project_understanding", ProjectUnderstandingQueen(), queue_depth
        )


# Global registry. Populated by init_queen_services() at application startup.
QUEEN_SERVICES: dict[str, QueenService] = {}


def register_service(service: QueenService) -> None:
    QUEEN_SERVICES[service.name] = service


def unregister_service(name: str) -> None:
    QUEEN_SERVICES.pop(name, None)


def init_queen_services() -> dict[str, QueenService]:
    """Initialize and register all Queen service instances.

    Returns the populated registry. Callers must still ``await service.start()``
    before submitting work and ``await service.stop()`` on shutdown.
    """
    if QUEEN_SERVICES:
        return QUEEN_SERVICES
    services: list[QueenService] = [
        PlannerQueenService(),
        SecurityQueenService(),
        MemoryQueenService(),
        TestingQueenService(),
        CritiqueQueenService(),
        RoutingQueenService(),
        ReflectionQueenService(),
        ProjectUnderstandingQueenService(),
    ]
    for svc in services:
        register_service(svc)
    return QUEEN_SERVICES


def clear_queen_services() -> None:
    """Clear the registry. Useful for tests."""
    QUEEN_SERVICES.clear()


__all__ = [
    "QUEEN_SERVICES",
    "QueenService",
    "PlannerQueenService",
    "SecurityQueenService",
    "MemoryQueenService",
    "TestingQueenService",
    "CritiqueQueenService",
    "RoutingQueenService",
    "ReflectionQueenService",
    "ProjectUnderstandingQueenService",
    "register_service",
    "unregister_service",
    "init_queen_services",
    "clear_queen_services",
]
