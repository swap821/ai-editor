"""Global concurrency cap for Council worker subprocesses.

A thin, in-process, fail-closed guard (NOT a service): a bounded semaphore that
limits how many worker subprocesses run at once across the whole process, so a
flood of approved missions cannot exhaust CPU/PIDs/disk. When the cap is reached,
an execution attempt fails closed with WorkerCapacityError — the caller surfaces
that as a visible "at capacity" King report rather than silently spawning anyway.

The pool is thread-safe (threading, not asyncio) on purpose: council executions
run in background-task threads, each with its own event loop, so the bound must
hold across threads.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

from aios import config


class WorkerCapacityError(RuntimeError):
    """Raised when the global concurrent-worker limit is reached (fail-closed)."""


class WorkerPool:
    """A bounded set of worker-execution slots shared process-wide."""

    def __init__(self, limit: int) -> None:
        self._limit = max(1, int(limit))
        self._semaphore = threading.BoundedSemaphore(self._limit)

    @property
    def limit(self) -> int:
        return self._limit

    @contextmanager
    def slot(self) -> Iterator[None]:
        """Hold one worker slot for the duration of the block; fail closed if full."""
        if not self._semaphore.acquire(blocking=False):
            raise WorkerCapacityError(
                f"council worker capacity reached ({self._limit} concurrent)"
            )
        try:
            yield
        finally:
            self._semaphore.release()

    def configure(self, limit: int) -> None:
        """Reset the pool to a new limit (test/admin use; drops in-flight counts)."""
        self._limit = max(1, int(limit))
        self._semaphore = threading.BoundedSemaphore(self._limit)


#: Process-wide singleton; bound from config at import.
WORKER_POOL = WorkerPool(config.COUNCIL_MAX_CONCURRENT_WORKERS)


__all__ = ["WORKER_POOL", "WorkerCapacityError", "WorkerPool"]
