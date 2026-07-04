"""Runtime Queen Services — long-lived wrappers with async inbox and lifecycle."""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

from aios.runtime.contracts import MissionContract, QueenVerdict


class QueenService(ABC):
    """Long-lived service wrapper for a Queen, with async inbox and lifecycle."""

    name: str

    def __init__(self, name: str, queue_depth: int = 16):
        self.name = name
        self._inbox: asyncio.Queue[tuple[MissionContract, asyncio.Future[QueenVerdict]]] = (
            asyncio.Queue(maxsize=queue_depth)
        )
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
            try:
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


class SecurityQueenService(QueenService):
    def __init__(self, queue_depth: int = 16):
        super().__init__("security", queue_depth)
        from aios.council.queens.security import SecurityQueen

        self._queen = SecurityQueen()

    async def _handle(self, contract: MissionContract) -> QueenVerdict:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._queen.review, contract)


QUEEN_SERVICES: dict[str, QueenService] = {}


def register_service(service: QueenService) -> None:
    QUEEN_SERVICES[service.name] = service


def unregister_service(name: str) -> None:
    QUEEN_SERVICES.pop(name, None)


__all__ = [
    "QUEEN_SERVICES",
    "QueenService",
    "SecurityQueenService",
    "register_service",
    "unregister_service",
]
