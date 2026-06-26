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

    CPU = auto()  #: Heavy computation: compilation, model inference, numerical work.
    IO = auto()  #: Network or disk bound: file reads, HTTP requests, LLM calls.
    MIXED = auto()  #: Both CPU and I/O phases; may benefit from hybrid scheduling.
    UNKNOWN = auto()  #: Insufficient information to classify.


#: Tool names that signal CPU-bound work (compilation, heavy compute).
_CPU_TOOLS: Final[frozenset[str]] = frozenset({
    "execute_terminal",  # shell commands may compile, test, lint
})

#: Substrings in terminal commands that strongly imply CPU-heavy work.
_CPU_COMMAND_PATTERNS: Final[frozenset[str]] = frozenset({
    "gcc", "g++", "clang", "make", "cmake", "ninja", "cargo build",
    "npm run build", "webpack", "rollup", "tsc ", "javac", "gradle",
    "mvn ", "python -m compileall", "pytest", "go build", "rustc",
    "docker build", "docker-compose build", "pylint", "mypy",
    "black --check", "ruff check", "eslint", "prettier",
    "torch", "tensorflow", "onnx", "llama.cpp", "ollama",
    "training", "inference", "benchmark", "profile",
})

#: Tool names that signal I/O-bound work.
_IO_TOOLS: Final[frozenset[str]] = frozenset({
    "read_file", "read_directory", "browse", "write_file",
    "edit_file", "create_file", "verify",
})

#: Tools that are predominantly network waits.
_NETWORK_TOOLS: Final[frozenset[str]] = frozenset({
    "browse",
})


# --------------------------------------------------------------------------- #
# Result wrapper for process-safe transport
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _SerializedResult:
    """Pickle-safe container for results crossing process boundaries.

    Since process workers cannot return rich objects tied to the parent
    process (open sockets, unpickleable closures), the worker serialises
    its payload into this plain data class before returning.
    """

    index: int
    replica: int = 0
    payload_bytes: Optional[bytes] = None
    error: Optional[str] = None
    duration_s: float = 0.0


# --------------------------------------------------------------------------- #
# Exception types
# --------------------------------------------------------------------------- #


class ParallelBackendError(Exception):
    """Base exception for parallel backend failures."""


class SpawnFailureError(ParallelBackendError):
    """ProcessPoolExecutor failed to spawn workers (e.g. /dev/shm exhausted)."""


class AllTasksFailedError(ParallelBackendError):
    """Every task in the batch raised an exception."""


# --------------------------------------------------------------------------- #
# Process-pool worker entry point (module level for pickleability)
# --------------------------------------------------------------------------- #

def _process_worker(
    worker_id: int,
    func_bytes: bytes,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> _SerializedResult:
    """Entry point executed inside a process-pool worker.

    Reconstructs the callable from its pickled representation and executes it.
    Returns a :class:`_SerializedResult` so the parent can deserialise safely.

    Parameters
    ----------
    worker_id:
        Opaque identifier so the parent can correlate results.
    func_bytes:
        ``pickle.dumps(func)`` — the callable to invoke.
    args, kwargs:
        Positional and keyword arguments for *func*.

    Returns
    -------
    _SerializedResult
        Either ``payload_bytes`` (pickled return value) or ``error``.
    """
    t0 = time.monotonic()
    try:
        func = pickle.loads(func_bytes)
        result = func(*args, **kwargs)
        payload = pickle.dumps(result)
        return _SerializedResult(
            index=worker_id,
            payload_bytes=payload,
            duration_s=time.monotonic() - t0,
        )
    except Exception as exc:  # noqa: BLE001
        return _SerializedResult(
            index=worker_id,
            error=f"{type(exc).__name__}: {exc}",
            duration_s=time.monotonic() - t0,
        )


# --------------------------------------------------------------------------- #
# Public API: SwarmParallelBackend
# --------------------------------------------------------------------------- #


class SwarmParallelBackend:
    """Intelligent parallel execution backend for ant-colony worker swarms.

    Automatically selects the optimal concurrency strategy based on workload
    characteristics, available hardware, and operator-configured fidelity
    preferences.

    Parameters
    ----------
    max_workers:
        Upper bound on concurrent tasks.  Overridden by ``SWARM_MAX_WORKERS``.
    backend:
        One of ``"auto"``, ``"thread"``, ``"process"``, ``"asyncio"``,
        ``"hybrid"``.  ``"auto"`` analyses each batch and picks the best fit.
    pheromone_fidelity:
        ``"strong"`` enforces sequential execution (each worker sees prior
        deposits).  ``"fast"`` allows parallel fan-out with post-hoc deposit.
        Read from ``SWARM_PHEROMONE_FIDELITY`` when *None*.

    Examples
    --------
    >>> backend = SwarmParallelBackend(max_workers=4, backend="auto")
    >>> results = backend.execute_tasks(
    ...     [(worker_fn, (i,), {}) for i in range(4)],
    ...     task_type_hint="io",
    ... )
    """

    #: Supported backend names.
    _VALID_BACKENDS: Final[frozenset[str]] = frozenset({
        "auto", "thread", "process", "asyncio", "hybrid",
    })

    def __init__(
        self,
        max_workers: int = 4,
        backend: str = "auto",
        pheromone_fidelity: Optional[str] = None,
    ) -> None:
        # Resolve effective max_workers from env caps.
        env_max = self._env_max_workers()
        self.max_workers: int = max(1, min(int(max_workers), env_max))

        # Resolve backend.
        be = (backend or "auto").strip().lower()
        if be not in self._VALID_BACKENDS:
            _LOGGER.warning(
                "Unknown swarm backend %r; falling back to 'auto'", be,
            )
            be = "auto"
        self.backend: str = be

        # Resolve fidelity.
        fid = (pheromone_fidelity or self._env_fidelity()).strip().lower()
        self.pheromone_fidelity: str = "fast" if fid != "strong" else "strong"

        # Caches for executor reuse within a context.
        self._thread_pool: Optional[ThreadPoolExecutor] = None
        self._process_pool: Optional[ProcessPoolExecutor] = None
        self._process_pool_workers: int = 0
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Internal telemetry.
        self._call_count: int = 0
        self._fallback_count: int = 0

        _LOGGER.debug(
            "SwarmParallelBackend created: backend=%s max_workers=%d fidelity=%s",
            self.backend, self.max_workers, self.pheromone_fidelity,
        )

    # ------------------------------------------------------------------ #
    # Resource discovery
    # ------------------------------------------------------------------ #

    @staticmethod
    def _env_max_workers() -> int:
        """Return the hard ceiling on workers from the environment."""
        try:
            from aios import config  # deferred to keep import lightweight
            return max(1, getattr(config, "SWARM_MAX_WORKERS", 4))
        except Exception:  # noqa: BLE001
            raw = os.getenv("AIOS_SWARM_MAX_WORKERS", "4")
            try:
                return max(1, int(raw))
            except ValueError:
                return 4

    @staticmethod
    def _env_fidelity() -> str:
        """Return the configured pheromone fidelity mode."""
        try:
            from aios import config  # deferred
            return getattr(config, "SWARM_PHEROMONE_FIDELITY", "fast")
        except Exception:  # noqa: BLE001
            return os.getenv("AIOS_SWARM_PHEROMONE_FIDELITY", "fast").strip().lower()

    @staticmethod
    def _detect_container_cpus() -> Optional[float]:
        """Detect CPU limit when running inside a container (cgroups)."""
        # cgroup v2
        for path in (
            "/sys/fs/cgroup/cpu.max",
            "/sys/fs/cgroup/cpu/cpu.cfs_quota_us",
        ):
            if os.path.exists(path):
                try:
                    with open(path, encoding="utf-8") as fh:
                        content = fh.read().strip()
                    if " " in content:  # cgroup v2: "quota period"
                        quota, period = content.split()
                        if quota != "max":
                            return float(quota) / float(period)
                    else:  # cgroup v1: microseconds
                        quota = int(content)
                        if quota > 0:
                            period_path = path.replace("cpu.cfs_quota_us", "cpu.cfs_period_us")
                            with open(period_path, encoding="utf-8") as fh:
                                period = int(fh.read().strip())
                            return quota / period
                except Exception:  # noqa: BLE001
                    pass
        return None

    @staticmethod
    def _detect_container_memory_mb() -> Optional[int]:
        """Detect memory limit when running inside a container (cgroups)."""
        for path in (
            "/sys/fs/cgroup/memory.max",
            "/sys/fs/cgroup/memory.limit_in_bytes",
        ):
            if os.path.exists(path):
                try:
                    with open(path, encoding="utf-8") as fh:
                        raw = fh.read().strip()
                    limit = int(raw)
                    if limit > 0:
                        return limit // (1024 * 1024)
                except Exception:  # noqa: BLE001
                    pass
        return None

    # ------------------------------------------------------------------ #
    # Core API: execute_tasks
    # ------------------------------------------------------------------ #

    def execute_tasks(
        self,
        tasks: list[tuple[Callable[..., R], tuple[Any, ...], dict[str, Any]]],
        task_type_hint: Optional[str] = None,
    ) -> list[R]:
        """Execute a batch of tasks, selecting the optimal backend.

        Parameters
        ----------
        tasks:
            List of ``(callable, args_tuple, kwargs_dict)`` triples.
        task_type_hint:
            Override the auto-detector.  One of ``"cpu"``, ``"io"``,
            ``"mixed"``, or ``None``.

        Returns
        -------
        list
            Results in the same order as *tasks*.

        Raises
        ------
        ParallelBackendError
            If the selected backend fails and no fallback succeeds.
        ValueError
            If *tasks* is empty.
        """
        if not tasks:
            raise ValueError("execute_tasks called with empty task list")

        # Strong fidelity -> sequential execution (best stigmergy).
        if self.pheromone_fidelity == "strong" or self.max_workers == 1:
            _LOGGER.debug("Sequential mode (fidelity=%s)", self.pheromone_fidelity)
            return self._execute_sequential(tasks)

        # Determine effective backend for this batch.
        effective_backend = self._resolve_backend(tasks, task_type_hint)
        _LOGGER.debug(
            "execute_tasks: n=%d backend=%s (hint=%s)",
            len(tasks), effective_backend, task_type_hint,
        )

        # Dispatch.
        try:
            if effective_backend == "asyncio":
                return self._execute_asyncio(tasks)
            if effective_backend == "process":
                return self._execute_process(tasks)
            if effective_backend == "hybrid":
                return self._execute_hybrid(tasks)
            # Default: thread
            return self._execute_thread(tasks)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning(
                "Backend %s failed (%s); trying fallback chain", effective_backend, exc,
            )
            self._fallback_count += 1
            return self._fallback_execute(tasks, failed_backend=effective_backend)

    # ------------------------------------------------------------------ #
    # Sequential fallback (strongest stigmergy)
    # ------------------------------------------------------------------ #

    def _execute_sequential(
        self,
        tasks: list[tuple[Callable[..., R], tuple[Any, ...], dict[str, Any]]],
    ) -> list[R]:
        """Run every task in submission order."""
        results: list[R] = []
        for func, args, kwargs in tasks:
            results.append(func(*args, **kwargs))
        return results

    # ------------------------------------------------------------------ #
    # Thread-based execution
    # ------------------------------------------------------------------ #

    def _execute_thread(
        self,
        tasks: list[tuple[Callable[..., R], tuple[Any, ...], dict[str, Any]]],
    ) -> list[R]:
        """Run tasks in a :class:`ThreadPoolExecutor`.

        Best for I/O-bound work that shares the GIL comfortably.  Threads
        are lightweight and preserve shared memory (e.g. conversation state).
        """
        workers = min(len(tasks), self.max_workers)
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="swarm_t") as pool:
            futures = [
                pool.submit(func, *args, **kwargs)
                for func, args, kwargs in tasks
            ]
            return [f.result() for f in futures]

    # ------------------------------------------------------------------ #
    # Process-based execution
    # ------------------------------------------------------------------ #

    def _execute_process(
        self,
        tasks: list[tuple[Callable[..., R], tuple[Any, ...], dict[str, Any]]],
    ) -> list[R]:
        """Run tasks in a :class:`ProcessPoolExecutor` with ``spawn`` context.

        Best for CPU-bound work that needs to escape the GIL.  Each worker
        runs in its own Python process.  Callables and arguments must be
        pickleable.

        Falls back to threads if process spawn fails (e.g. memory limit,
        ``/dev/shm`` exhaustion, or unpickleable callables).
        """
        workers = min(len(tasks), self.max_workers)
        if workers <= 1:
            return self._execute_sequential(tasks)

        # Validate pickleability of all tasks before spawning processes.
        pickled_tasks: list[tuple[int, bytes, tuple[Any, ...], dict[str, Any]]] = []
        for idx, (func, args, kwargs) in enumerate(tasks):
            try:
                func_bytes = pickle.dumps(func, protocol=pickle.HIGHEST_PROTOCOL)
                pickled_tasks.append((idx, func_bytes, args, kwargs))
            except (pickle.PicklingError, TypeError, AttributeError) as exc:
                _LOGGER.warning(
                    "Task %d is not pickleable (%s); falling back to threads",
                    idx, exc,
                )
                return self._execute_thread(tasks)

        # Spawn context: "spawn" is safer than "fork" (avoids state pollution
        # from the parent process — especially important when the agent has
        # imported heavy libraries like torch or transformers).
        ctx = mp.get_context("spawn")

        try:
            with ProcessPoolExecutor(
                max_workers=workers,
                mp_context=ctx,
                initializer=_init_process_worker,
                initargs=(),
            ) as pool:
                futures = {
                    pool.submit(_process_worker, idx, fb, args, kwargs): idx
                    for idx, fb, args, kwargs in pickled_tasks
                }

                results: list[Optional[R]] = [None] * len(tasks)
                errors: list[str] = []
                for future in as_completed(futures):
                    idx = futures[future]
                    sr = future.result()
                    if sr.error:
                        errors.append(f"Task {idx}: {sr.error}")
                    elif sr.payload_bytes:
                        results[idx] = pickle.loads(sr.payload_bytes)

                if all(r is not None for r in results):
                    return results  # type: ignore[return-value]

                if errors:
                    raise ParallelBackendError(
                        f"Process pool partial failure ({len(errors)} errors): "
                        + "; ".join(errors[:3])
                    )
                raise ParallelBackendError(
                    "Process pool returned incomplete results"
                )

        except (OSError, BrokenPipeError, EOFError) as exc:
            # Common when /dev/shm is exhausted or memory limits are hit.
            _LOGGER.warning(
                "ProcessPoolExecutor spawn failed (%s); falling back to threads", exc,
            )
            return self._execute_thread(tasks)

    # ------------------------------------------------------------------ #
    # Asyncio-based execution
    # ------------------------------------------------------------------ #

    def _execute_asyncio(
        self,
        tasks: list[tuple[Callable[..., R], tuple[Any, ...], dict[str, Any]]],
    ) -> list[R]:
        """Run tasks using ``asyncio`` for maximum I/O concurrency.

        Best when tasks are dominated by network waits (LLM calls, HTTP
        requests).  Each task runs in an event-loop thread so regular
        synchronous callables work without modification.

        Falls back to ThreadPoolExecutor if no event loop is available.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # We are already inside an event loop — use ThreadPoolExecutor
            # instead of trying to nest asyncio (which raises errors).
            _LOGGER.debug(
                "Already inside an event loop; using threads instead of asyncio",
            )
            return self._execute_thread(tasks)

        # Run a new event loop in this thread.
        return asyncio.run(self._asyncio_run_all(tasks))

    async def _asyncio_run_all(
        self,
        tasks: list[tuple[Callable[..., R], tuple[Any, ...], dict[str, Any]]],
    ) -> list[R]:
        """Coroutine that schedules all tasks on the event loop."""
        sem = asyncio.Semaphore(self.max_workers)

        async def _bounded(func: Callable[..., R], args: tuple[Any, ...], kwargs: dict[str, Any]) -> R:
            async with sem:
                # Run the synchronous callable in a thread pool so it does
                # not block the event loop.
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(None, func, *args, **kwargs)

        coros = [_bounded(func, args, kwargs) for func, args, kwargs in tasks]
        return await asyncio.gather(*coros)

    # ------------------------------------------------------------------ #
    # Hybrid execution
    # ------------------------------------------------------------------ #

    def _execute_hybrid(
        self,
        tasks: list[tuple[Callable[..., R], tuple[Any, ...], dict[str, Any]]],
    ) -> list[R]:
        """Route each task to the best backend based on individual hints.

        Currently implements a simple heuristic: if *any* task looks CPU-heavy,
        the whole batch goes to the process pool (because CPU tasks can starve
        I/O tasks when colocated on the same threads).  A smarter future
        version could split the batch across two pools.

        For now, hybrid = asyncio with a process-pool sidecar for CPU tasks.
        """
        # Simple approach: if any task is CPU-heavy, use processes for all.
        # This avoids GIL contention where a CPU task blocks I/O tasks.
        has_cpu = any(
            self._guess_task_cpu_heavy(func)
            for func, _args, _kwargs in tasks
        )
        if has_cpu:
            return self._execute_process(tasks)
        return self._execute_asyncio(tasks)

    # ------------------------------------------------------------------ #
    # Fallback chain
    # ------------------------------------------------------------------ #

    def _fallback_execute(
        self,
        tasks: list[tuple[Callable[..., R], tuple[Any, ...], dict[str, Any]]],
        failed_backend: str,
    ) -> list[R]:
        """Graceful degradation: try remaining backends in priority order.

        Priority (most desirable -> safest):
        1. Threads (usually works, shares GIL)
        2. Sequential (always works, strongest stigmergy)
        """
        fallback_order: list[str]
        if failed_backend == "process":
            fallback_order = ["thread", "sequential"]
        elif failed_backend in ("asyncio", "hybrid"):
            fallback_order = ["thread", "sequential"]
        else:
            fallback_order = ["sequential"]

        for fb in fallback_order:
            try:
                _LOGGER.info("Fallback to %s backend", fb)
                if fb == "thread":
                    return self._execute_thread(tasks)
                return self._execute_sequential(tasks)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning("Fallback %s also failed: %s", fb, exc)
                continue

        raise ParallelBackendError(
            f"All backends failed (tried {failed_backend}, then {fallback_order})"
        )

    # ------------------------------------------------------------------ #
    # Backend resolution
    # ------------------------------------------------------------------ #

    def _resolve_backend(
        self,
        tasks: list[tuple[Callable[..., R], tuple[Any, ...], dict[str, Any]]],
        task_type_hint: Optional[str],
    ) -> str:
        """Determine the effective backend string for this batch."""
        if self.backend != "auto":
            return self.backend

        # Auto-detect from hint or task analysis.
        detected = self.detect_task_type(tasks, task_type_hint)
        mapping = {
            TaskType.CPU: "process",
            TaskType.IO: "asyncio",
            TaskType.MIXED: "hybrid",
            TaskType.UNKNOWN: "thread",
        }
        return mapping.get(detected, "thread")

    # ------------------------------------------------------------------ #
    # Task type detection
    # ------------------------------------------------------------------ #

    @classmethod
    def detect_task_type(
        cls,
        tasks: list[tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any]]],
        hint: Optional[str] = None,
    ) -> TaskType:
        """Estimate the workload type of a task batch.

        Parameters
        ----------
        tasks:
            The batch of tasks about to execute.
        hint:
            Optional override — one of ``"cpu"``, ``"io"``, ``"mixed"``.

        Returns
        -------
        TaskType
            The best-guess classification.

        Notes
        -----
        The heuristic inspects:
        1. The explicit *hint* if provided.
        2. Function name patterns (e.g. ``_run_worker`` containing LLM calls → IO).
        3. Argument content (tool names, command strings).
        """
        if hint:
            hint = hint.strip().lower()
            if hint == "cpu":
                return TaskType.CPU
            if hint == "io":
                return TaskType.IO
            if hint == "mixed":
                return TaskType.MIXED

        cpu_score = 0
        io_score = 0

        for func, args, kwargs in tasks:
            name = getattr(func, "__name__", "")
            # _run_worker wraps an LLM agent → heavily I/O bound (network wait).
            if "_run_worker" in name or "_run_leg" in name:
                io_score += 3

            # Inspect positional args for tool/command hints.
            for arg in args:
                arg_str = str(arg)
                if any(pat in arg_str for pat in _CPU_COMMAND_PATTERNS):
                    cpu_score += 2
                if any(t in arg_str for t in _IO_TOOLS):
                    io_score += 1

            # Inspect keyword args.
            for key, value in kwargs.items():
                val_str = str(value)
                if any(pat in val_str for pat in _CPU_COMMAND_PATTERNS):
                    cpu_score += 2
                if any(t in val_str for t in _IO_TOOLS):
                    io_score += 1
                if key in ("tools", "allowed_tools"):
                    tools = value if isinstance(value, (list, set, frozenset, tuple)) else [value]
                    for t in tools:
                        t_str = str(t)
                        if t_str in _CPU_TOOLS:
                            cpu_score += 2
                        if t_str in _IO_TOOLS:
                            io_score += 1
                        if t_str in _NETWORK_TOOLS:
                            io_score += 2

        # Classify.
        if cpu_score > 0 and io_score > 0:
            if cpu_score >= io_score * 2:
                return TaskType.CPU
            if io_score >= cpu_score * 2:
                return TaskType.IO
            return TaskType.MIXED
        if cpu_score > 0:
            return TaskType.CPU
        if io_score > 0:
            return TaskType.IO
        return TaskType.UNKNOWN

    def _guess_task_cpu_heavy(self, func: Callable[..., Any]) -> bool:
        """Quick heuristic: does *func* look CPU-bound?"""
        name = getattr(func, "__name__", "")
        cpu_indicators = ("compile", "build", "train", "infer", "benchmark",
                          "lint", "test", "check")
        return any(ind in name for ind in cpu_indicators)

    # ------------------------------------------------------------------ #
    # Stigmergy helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def order_preserving_zip(
        results: list[R],
        deposit_callback: Optional[Callable[[R], None]] = None,
    ) -> list[R]:
        """Return results in submission order, optionally depositing pheromones.

        In ``"fast"`` fidelity mode, all workers run concurrently and their
        deposits are appended after the pool finishes.  This helper ensures
        the deposit order matches the submission order for reproducible
        stigmergy trails.

        Parameters
        ----------
        results:
            Results already in submission order (as returned by
            :meth:`execute_tasks`).
        deposit_callback:
            If given, called once per result in order.

        Returns
        -------
        list
            The same *results* list (identity passthrough for convenience).
        """
        if deposit_callback:
            for r in results:
                deposit_callback(r)
        return results

    # ------------------------------------------------------------------ #
    # Telemetry
    # ------------------------------------------------------------------ #

    @property
    def stats(self) -> dict[str, Any]:
        """Return usage statistics for observability."""
        return {
            "backend": self.backend,
            "effective_backend": self.backend,
            "max_workers": self.max_workers,
            "pheromone_fidelity": self.pheromone_fidelity,
            "call_count": self._call_count,
            "fallback_count": self._fallback_count,
            "fallback_rate": (
                self._fallback_count / max(self._call_count, 1)
            ),
        }

    # ------------------------------------------------------------------ #
    # Context manager
    # ------------------------------------------------------------------ #

    def __enter__(self) -> SwarmParallelBackend:
        return self

    def __exit__(self, *exc: object) -> None:
        self.shutdown()

    def shutdown(self, wait: bool = True) -> None:
        """Release any held executor resources."""
        if self._thread_pool is not None:
            self._thread_pool.shutdown(wait=wait)
            self._thread_pool = None
        if self._process_pool is not None:
            self._process_pool.shutdown(wait=wait)
            self._process_pool = None
        _LOGGER.debug("SwarmParallelBackend shutdown complete")


# --------------------------------------------------------------------------- #
# Process-pool initializer (runs once per worker process)
# --------------------------------------------------------------------------- #

def _init_process_worker() -> None:
    """One-time setup for each process-pool worker.

    Imports heavy modules lazily inside the child so the parent process
    does not pay their import cost.  Sets CPU affinity when container
    limits are detected for more predictable scheduling.
    """
    # Suppress noisy warnings in worker processes.
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("ignore", category=UserWarning)

    # Attempt to set a deterministic random seed per worker to avoid
    # non-determinism when processes share the same PRNG state.
    try:
        import random
        # os.getpid() ensures each worker gets a distinct seed.
        random.seed(os.getpid() % (2**31))
    except Exception:
        pass

    # When torch is available, disable its intra-op parallelism inside
    # workers to avoid over-subscription (each worker already has its own
    # process; letting torch spawn more threads hurts throughput).
    try:
        import torch  # type: ignore[import-untyped]
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
    except Exception:
        pass

    # Same for OpenBLAS/MKL/etc.
    for env_name in (
        "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS",
    ):
        os.environ.setdefault(env_name, "1")


# --------------------------------------------------------------------------- #
# Convenience: module-level singleton
# --------------------------------------------------------------------------- #

#: Lazily-initialized default backend instance.
_default_backend: Optional[SwarmParallelBackend] = None


def get_default_backend() -> SwarmParallelBackend:
    """Return (and cache) the default :class:`SwarmParallelBackend`.

    Reads configuration from :mod:`aios.config` or environment variables.
    """
    global _default_backend
    if _default_backend is None:
        backend = _env_str("AIOS_SWARM_WORKER_BACKEND", "auto")
        fidelity = _env_str("AIOS_SWARM_PHEROMONE_FIDELITY", "fast")
        try:
            from aios import config  # deferred to avoid circular import
            max_workers = getattr(config, "SWARM_MAX_WORKERS", 4)
            backend = getattr(config, "SWARM_WORKER_BACKEND", backend)
            fidelity = getattr(config, "SWARM_PHEROMONE_FIDELITY", fidelity)
        except Exception:  # noqa: BLE001
            max_workers = int(os.getenv("AIOS_SWARM_MAX_WORKERS", "4"))
        _default_backend = SwarmParallelBackend(
            max_workers=max_workers,
            backend=backend,
            pheromone_fidelity=fidelity,
        )
    return _default_backend


def _env_str(name: str, default: str) -> str:
    """Read an environment variable, returning *default* when unset."""
    value = os.getenv(name)
    return value if value not in (None, "") else default


# --------------------------------------------------------------------------- #
# Low-level helpers (public for advanced use)
# --------------------------------------------------------------------------- #

def is_pickleable(obj: object) -> bool:
    """Return ``True`` if *obj* can be pickled (and thus sent to a process).

    This is a shallow check: it only attempts to pickle *obj* itself, not
    to verify that everything reachable from *obj* is also pickleable.
    """
    try:
        pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
        return True
    except (pickle.PicklingError, TypeError, AttributeError):
        return False


def recommended_workers(
    task_count: int,
    *,
    max_workers: Optional[int] = None,
    task_type: TaskType = TaskType.UNKNOWN,
) -> int:
    """Recommend a worker count given the task batch and available hardware.

    Parameters
    ----------
    task_count:
        Number of tasks to schedule.
    max_workers:
        Hard ceiling (defaults to ``SWARM_MAX_WORKERS``).
    task_type:
        Classification of the workload.

    Returns
    -------
    int
        A sensible worker count in ``[1, max_workers]``.
    """
    if max_workers is None:
        try:
            from aios import config  # deferred
            max_workers = getattr(config, "SWARM_MAX_WORKERS", 4)
        except Exception:  # noqa: BLE001
            max_workers = 4

    cpu_count = os.cpu_count() or 2

    # Respect container limits.
    try:
        container_cpus = SwarmParallelBackend._detect_container_cpus()
        if container_cpus is not None:
            cpu_count = min(cpu_count, max(1, int(container_cpus)))
    except Exception:  # noqa: BLE001
        pass

    if task_type is TaskType.CPU:
        # For CPU work, more workers than CPUs causes context-switch thrash.
        ideal = min(task_count, cpu_count)
    elif task_type is TaskType.IO:
        # I/O work can over-subscribe (while one waits, another runs).
        ideal = min(task_count, max(4, cpu_count * 2))
    else:
        ideal = min(task_count, max(2, cpu_count))

    return max(1, min(ideal, max_workers))


# --------------------------------------------------------------------------- #
# Standalone convenience wrappers
# --------------------------------------------------------------------------- #

def detect_task_type(
    tasks: list[tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any]]],
    hint: Optional[str] = None,
) -> TaskType:
    """Estimate the workload type of a task batch (standalone wrapper).

    Thin wrapper around :meth:`SwarmParallelBackend.detect_task_type`.
    See that method for full documentation.
    """
    return SwarmParallelBackend.detect_task_type(tasks, hint=hint)


# --------------------------------------------------------------------------- #
# Integration helper for swarm.py
# --------------------------------------------------------------------------- #

def execute_swarm_workers(
    worker_tasks: list[tuple[Callable[..., R], tuple[Any, ...], dict[str, Any]]],
    concurrency: int,
    backend: Optional[str] = None,
    fidelity: Optional[str] = None,
    task_type_hint: Optional[str] = None,
) -> list[R]:
    """Drop-in replacement for the ``ThreadPoolExecutor`` block in ``swarm.py``.

    Parameters
    ----------
    worker_tasks:
        Tasks as ``(callable, args, kwargs)`` triples.
    concurrency:
        Desired concurrency level (may be capped by ``SWARM_MAX_WORKERS``).
    backend:
        Override the default backend (e.g. ``"thread"``, ``"process"``).
    fidelity:
        Override pheromone fidelity (``"strong"`` or ``"fast"``).
    task_type_hint:
        Hint the workload type (``"cpu"``, ``"io"``, ``"mixed"``).

    Returns
    -------
    list
        Results in submission order.

    Examples
    --------
    Replaces the ``ThreadPoolExecutor`` block in :func:`run_swarm`::

        # OLD:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            indexed_results = list(pool.map(_worker_task, assignments))

        # NEW:
        from aios.agents.swarm_parallel import execute_swarm_workers
        indexed_results = execute_swarm_workers(
            [(_worker_task, (a,), {}) for a in assignments],
            concurrency=concurrency,
        )
    """
    # Concurrency of 1 means sequential (strongest stigmergy).
    if concurrency <= 1 or len(worker_tasks) <= 1:
        return [func(*args, **kwargs) for func, args, kwargs in worker_tasks]

    be = SwarmParallelBackend(
        max_workers=concurrency,
        backend=backend or _env_str("AIOS_SWARM_WORKER_BACKEND", "auto"),
        pheromone_fidelity=fidelity or _env_str("AIOS_SWARM_PHEROMONE_FIDELITY", "fast"),
    )
    return be.execute_tasks(worker_tasks, task_type_hint=task_type_hint)


# --------------------------------------------------------------------------- #
# Exports
# --------------------------------------------------------------------------- #

__all__ = [
    # Main class
    "SwarmParallelBackend",
    # Task classification
    "TaskType",
    "detect_task_type",
    # Exceptions
    "ParallelBackendError",
    "SpawnFailureError",
    "AllTasksFailedError",
    # Helpers
    "is_pickleable",
    "recommended_workers",
    "execute_swarm_workers",
    "get_default_backend",
]
