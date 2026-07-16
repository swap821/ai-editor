"""Bounded priority scheduling for temporary workers.

The scheduler is an application primitive, not a second authority system.  It
only decides when an already-admitted strategy may run.  Policy, capability,
scope, isolation and verification remain owned by their existing authorities.
"""
from __future__ import annotations

import asyncio
import heapq
import weakref
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, ClassVar

from aios.domain.workers.worker_contract import WorkerSpec


class SchedulerAdmissionError(RuntimeError):
    """Raised when a worker cannot be admitted under the configured bounds."""


class WorkerCancelledError(RuntimeError):
    """Raised when a queued or running worker is cancelled."""


@dataclass(order=True)
class _Ticket:
    sort_key: tuple[int, int] = field(init=False)
    priority: int
    sequence: int
    spec: WorkerSpec = field(compare=False)
    runner: Callable[[], Awaitable[Any]] = field(compare=False)
    future: asyncio.Future[Any] = field(compare=False)

    def __post_init__(self) -> None:
        # Higher priority first; FIFO for equal priority.
        self.sort_key = (-self.priority, self.sequence)


@dataclass(frozen=True)
class SchedulerSnapshot:
    queued: int
    active: int
    active_by_mission: dict[str, int]
    active_worker_ids: tuple[str, ...]


class WorkerScheduler:
    """Small bounded priority queue with per-mission fairness caps."""

    _instances: ClassVar[weakref.WeakSet["WorkerScheduler"]] = weakref.WeakSet()

    def __init__(
        self,
        *,
        max_active: int = 4,
        max_per_mission: int = 1,
        emergency_stop: Any | None = None,
    ) -> None:
        if max_active < 1 or max_per_mission < 1:
            raise ValueError("scheduler limits must be positive")
        self.max_active = max_active
        self.max_per_mission = max_per_mission
        self._sequence = 0
        self._queue: list[_Ticket] = []
        self._active: dict[str, asyncio.Task[Any]] = {}
        self._active_by_mission: Counter[str] = Counter()
        self._tickets: dict[str, _Ticket] = {}
        self._pumping = False
        self._emergency_stop = emergency_stop
        self._instances.add(self)

    async def submit(
        self,
        spec: WorkerSpec,
        runner: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Queue one worker and await its result.

        Worker IDs are unique admission keys.  A duplicate is rejected instead
        of silently replacing or running the earlier worker.
        """
        self._assert_operational()
        if spec.worker_id in self._tickets or spec.worker_id in self._active:
            raise SchedulerAdmissionError(f"worker already admitted: {spec.worker_id}")
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        ticket = _Ticket(
            priority=spec.priority,
            sequence=self._sequence,
            spec=spec,
            runner=runner,
            future=future,
        )
        self._sequence += 1
        self._tickets[spec.worker_id] = ticket
        heapq.heappush(self._queue, ticket)
        self._pump()
        try:
            return await future
        finally:
            self._tickets.pop(spec.worker_id, None)

    def cancel(self, worker_id: str, reason: str = "cancelled") -> bool:
        """Cancel one queued/running worker; return whether it was found."""
        ticket = self._tickets.get(worker_id)
        if ticket is not None:
            if not ticket.future.done():
                ticket.future.set_exception(WorkerCancelledError(reason))
            self._tickets.pop(worker_id, None)
            self._queue = [item for item in self._queue if item.spec.worker_id != worker_id]
            heapq.heapify(self._queue)
            self._pump()
            return True
        task = self._active.get(worker_id)
        if task is not None:
            task.cancel(reason)
            return True
        return False

    def cancel_all(self, reason: str = "emergency stop") -> int:
        """Cancel every queued and active worker and return the count touched."""
        worker_ids = tuple(dict.fromkeys((*self._tickets.keys(), *self._active.keys())))
        return sum(1 for worker_id in worker_ids if self.cancel(worker_id, reason))

    def cancel_queued(self, reason: str = "emergency stop") -> int:
        """Cancel only workers that have not started."""
        return sum(
            1
            for worker_id in tuple(self._tickets)
            if self.cancel(worker_id, reason)
        )

    def cancel_active(self, reason: str = "emergency stop") -> int:
        """Cancel only workers already running."""
        return sum(
            1
            for worker_id in tuple(self._active)
            if self.cancel(worker_id, reason)
        )

    @classmethod
    def cancel_queued_registered(cls, reason: str = "emergency stop") -> int:
        return sum(scheduler.cancel_queued(reason) for scheduler in tuple(cls._instances))

    @classmethod
    def cancel_active_registered(cls, reason: str = "emergency stop") -> int:
        return sum(scheduler.cancel_active(reason) for scheduler in tuple(cls._instances))

    def snapshot(self) -> SchedulerSnapshot:
        return SchedulerSnapshot(
            queued=len(self._queue),
            active=len(self._active),
            active_by_mission=dict(self._active_by_mission),
            active_worker_ids=tuple(sorted(self._active)),
        )

    def _pump(self) -> None:
        if self._pumping:
            return
        self._pumping = True
        try:
            while len(self._active) < self.max_active:
                index = self._next_admissible_index()
                if index is None:
                    return
                ticket = self._queue.pop(index)
                heapq.heapify(self._queue)
                self._active_by_mission[ticket.spec.mission_id] += 1
                task = asyncio.create_task(self._run(ticket))
                self._active[ticket.spec.worker_id] = task
        finally:
            self._pumping = False

    def _next_admissible_index(self) -> int | None:
        for ticket in sorted(self._queue):
            if (
                self._active_by_mission[ticket.spec.mission_id]
                < self.max_per_mission
            ):
                return self._queue.index(ticket)
        return None

    async def _run(self, ticket: _Ticket) -> None:
        worker_id = ticket.spec.worker_id
        try:
            self._assert_operational()
            result = await ticket.runner()
        except asyncio.CancelledError as exc:
            if not ticket.future.done():
                ticket.future.set_exception(WorkerCancelledError(str(exc) or "cancelled"))
        except Exception as exc:  # noqa: BLE001 - propagate exact strategy failure
            if not ticket.future.done():
                ticket.future.set_exception(exc)
        else:
            if not ticket.future.done():
                ticket.future.set_result(result)
        finally:
            self._active.pop(worker_id, None)
            mission_id = ticket.spec.mission_id
            self._active_by_mission[mission_id] -= 1
            if self._active_by_mission[mission_id] <= 0:
                self._active_by_mission.pop(mission_id, None)
            self._pump()

    def _assert_operational(self) -> None:
        if self._emergency_stop is not None:
            self._emergency_stop.assert_operational()


__all__ = [
    "SchedulerAdmissionError",
    "SchedulerSnapshot",
    "WorkerCancelledError",
    "WorkerScheduler",
]
