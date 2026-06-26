"""Intelligent parallel execution backend for the ant-colony swarm.

Auto-detects the optimal parallelism strategy:
- CPU-bound (compilation, model inference): ProcessPoolExecutor
- I/O-bound (file reads, network calls): asyncio or ThreadPoolExecutor
- Mixed: hybrid approach with intelligent routing

Design principle: stigmergy must be preserved. Sequential execution (concurrency=1)
has the strongest pheromone trail fidelity. Parallel execution trades some trail
fidelity for speed. The backend makes this tradeoff explicit and tunable.
"""
from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import multiprocessing as mp
import os
import pickle
import sys
import time
import warnings
from concurrent.futures import (
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    as_completed,
)
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import (
    Any,
    Callable,
    Coroutine,
    Final,
    Generic,
    Iterator,
    Optional,
    Protocol,
    TypeVar,
    Union,
)

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Type variables
# --------------------------------------------------------------------------- #
T = TypeVar("T")
R = TypeVar("R")

# --------------------------------------------------------------------------- #
# Task type classification
# --------------------------------------------------------------------------- #


class TaskType(Enum):
    """Classification of a worker task based on its expected resource profile."""

    CPU = auto()  #: Heavy computation: compilation, model inference, numerical
    IO = auto()  #: Network/disk: API calls, file reads, DB queries
    MIXED = auto()  #: Both CPU and I/O in varying proportions


# --------------------------------------------------------------------------- #
# Work item
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class WorkItem(Generic[T, R]):
    """A single unit of work submitted to the parallel backend."""

    func: Callable[..., R]
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    task_type: TaskType = TaskType.MIXED
    priority: int = 5  # 1 = highest, 10 = lowest
    timeout_seconds: Optional[float] = None
    # Stigmergy
    pheromone_key: Optional[str] = None  # key for trail read/write
    stigmergy_required: bool = False  # if True, forces sequential execution

    @property
    def name(self) -> str:
        return getattr(self.func, "__name__", repr(self.func))


# --------------------------------------------------------------------------- #
# Execution backend registry
# --------------------------------------------------------------------------- #


class _BackendRegistry:
    """Keeps track of the best backend for each task type."""

    def __init__(self) -> None:
        self._cpu: Optional[ProcessPoolExecutor] = None
        self._io: Optional[ThreadPoolExecutor] = None
        self._max_workers_cpu: int = max(1, (os.cpu_count() or 2) - 1)
        self._max_workers_io: int = min(32, (os.cpu_count() or 2) * 2)

    # --- lazy init -------------------------------------------------------- #

    def _ensure_cpu(self) -> ProcessPoolExecutor:
        if self._cpu is None or self._cpu._shutdown:
            ctx = mp.get_context("spawn")
            self._cpu = ProcessPoolExecutor(
                max_workers=self._max_workers_cpu,
                mp_context=ctx,
            )
        return self._cpu

    def _ensure_io(self) -> ThreadPoolExecutor:
        if self._io is None or self._io._shutdown:
            self._io = ThreadPoolExecutor(max_workers=self._max_workers_io)
        return self._io

    # --- dispatch --------------------------------------------------------- #

    def submit(
        self, item: WorkItem[T, R]
    ) -> asyncio.Future:
        """Submit *item* to the most appropriate executor."""
        loop = asyncio.get_running_loop()

        # Stigmergy-guard: sequential execution for pheromone-sensitive tasks
        if item.stigmergy_required:
            _LOGGER.debug("Stigmergy guard: sequential for %s", item.name)
            return loop.create_future_for(
                functools.partial(item.func, *item.args, **item.kwargs)
            )

        if item.task_type is TaskType.CPU:
            executor = self._ensure_cpu()
            return loop.run_in_executor(
                executor,
                functools.partial(item.func, *item.args, **item.kwargs),
            )

        if item.task_type is TaskType.IO:
            executor = self._ensure_io()
            return loop.run_in_executor(
                executor,
                functools.partial(item.func, *item.args, **item.kwargs),
            )

        # MIXED: use thread pool for flexibility
        executor = self._ensure_io()
        return loop.run_in_executor(
            executor,
            functools.partial(item.func, *item.args, **item.kwargs),
        )

    def shutdown(self) -> None:
        """Gracefully shut down all executors."""
        if self._cpu is not None:
            self._cpu.shutdown(wait=True)
            self._cpu = None
        if self._io is not None:
            self._io.shutdown(wait=True)
            self._io = None


# Global singleton
_BACKEND = _BackendRegistry()


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def configure(max_cpu_workers: int, max_io_workers: int) -> None:
    """Configure global executor pool sizes."""
    _BACKEND._max_workers_cpu = max_cpu_workers
    _BACKEND._max_workers_io = max_io_workers
    _BACKEND.shutdown()  # will recreate with new sizes on next submit


async def run_parallel(
    items: list[WorkItem[T, R]],
    *,
    concurrency: int = 0,  # 0 = unlimited
    preserve_order: bool = False,
    return_exceptions: bool = True,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> list[Union[R, BaseException]]:
    """Execute a batch of work items with controlled parallelism.

    Parameters
    ----------
    items:
        Work items to execute.
    concurrency:
        Maximum number of items to run concurrently.
        ``0`` means unlimited (bounded only by executor pool size).
    preserve_order:
        If ``True``, results are returned in the same order as *items*.
    return_exceptions:
        If ``True``, exceptions are returned in the result list instead of
        being raised.
    progress_callback:
        Called as ``progress_callback(done_count, total_count)`` after each
        item completes.

    Returns
    -------
    List of results (or exceptions if *return_exceptions* is ``True``).
    """
    total = len(items)
    if total == 0:
        return []

    semaphore = asyncio.Semaphore(concurrency) if concurrency > 0 else None

    async def _run_one(idx: int, item: WorkItem[T, R]) -> tuple[int, Union[R, BaseException]]:
        async with semaphore if semaphore else _NoOpCtx():
            try:
                future = _BACKEND.submit(item)
                if item.timeout_seconds is not None:
                    result = await asyncio.wait_for(
                        asyncio.wrap_future(future),
                        timeout=item.timeout_seconds,
                    )
                else:
                    result = await asyncio.wrap_future(future)
                return idx, result
            except Exception as exc:
                if return_exceptions:
                    return idx, exc
                raise
            finally:
                if progress_callback:
                    progress_callback(1, total)

    # Launch all tasks
    tasks = [asyncio.create_task(_run_one(i, item)) for i, item in enumerate(items)]

    # Collect results
    results: list[tuple[int, Union[R, BaseException]]] = []
    for coro in asyncio.as_completed(tasks):
        idx, result = await coro
        results.append((idx, result))

    if preserve_order:
        results.sort(key=lambda x: x[0])

    return [r for _, r in results]


class _NoOpCtx:
    """Async context manager that does nothing (for unlimited concurrency)."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


# --------------------------------------------------------------------------- #
# Stigmergy-aware helpers
# --------------------------------------------------------------------------- #


def classify_task(func: Callable) -> TaskType:
    """Heuristically classify a callable as CPU, IO, or MIXED.

    Inspects the function's source code (if available) for I/O keywords.
    Falls back to MIXED if source cannot be read.
    """
    io_keywords = {
        "open(", "read(", "write(", "requests.", "httpx.", "aiohttp",
        "fetch", "download", "upload", "query", "db.", "cursor.",
        "socket", "recv", "send", "subscribe", "publish",
        "os.", "subprocess", "popen", "communicate",
    }
    cpu_keywords = {
        "for ", "while ", "map(", "filter(", "reduce(", "sum(", "max(", "min(",
        "numpy", "torch", "tensorflow", "jax", "compile(", "eval(", "exec(",
        "sort(", "sorted(", "list comprehension",
    }

    try:
        source = inspect.getsource(func).lower()
    except (OSError, TypeError):
        return TaskType.MIXED

    io_score = sum(1 for kw in io_keywords if kw in source)
    cpu_score = sum(1 for kw in cpu_keywords if kw in source)

    if io_score > cpu_score * 2:
        return TaskType.IO
    if cpu_score > io_score * 2:
        return TaskType.CPU
    return TaskType.MIXED


def auto_work_item(
    func: Callable[..., R],
    *args: Any,
    priority: int = 5,
    pheromone_key: Optional[str] = None,
    **kwargs: Any,
) -> WorkItem[Any, R]:
    """Create a ``WorkItem`` with automatic task-type classification."""
    task_type = classify_task(func)
    stigmergy = pheromone_key is not None
    return WorkItem(
        func=func,
        args=args,
        kwargs=kwargs,
        task_type=task_type,
        priority=priority,
        pheromone_key=pheromone_key,
        stigmergy_required=stigmergy,
    )


# --------------------------------------------------------------------------- #
# Graceful shutdown hook
# --------------------------------------------------------------------------- #


def shutdown() -> None:
    """Shut down all internal executor pools."""
    _BACKEND.shutdown()


import atexit

atexit.register(shutdown)
