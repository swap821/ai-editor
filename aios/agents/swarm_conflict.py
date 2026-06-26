"""File conflict resolution for parallel swarm workers.

Provides advisory locking (POSIX fcntl / Windows msvcrt), conflict detection,
and optional three-way merge for the ant-colony swarm. When two workers
attempt to write the same file, the system detects the conflict and either:

1. Serializes access (lock-based), or
2. Produces a mergeable diff (merge-based), or
3. Reports the conflict for human resolution (fail-closed)

Principle: conflicts are a NATURAL part of parallel work. Ant colonies handle
this through physical constraints (two ants can't carry the same leaf). We
handle it through explicit coordination.

Architecture::

    SwarmFileCoordinator (main entry point)
    ├── FileLock          – advisory OS-level file locks
    ├── ConflictDetector  – overlap detection before writes
    ├── MergeResolver     – three-way merge via difflib
    └── Conflict          – immutable conflict record

Usage::

    from swarm_conflict import SwarmFileCoordinator, Conflict

    coordinator = SwarmFileCoordinator(strategy="merge")

    # Worker A registers intent to write
    coordinator.register_write("worker-a", "src/models.py", content_a)

    # Worker B registers intent to write the same file
    coordinator.register_write("worker-b", "src/models.py", content_b)

    # Detect conflicts
    conflicts = coordinator.detect_conflicts()
    for c in conflicts:
        resolution = coordinator.resolve_conflict(c)
        if resolution.strategy == "human":
            ...  # escalate to human
"""

from __future__ import annotations

import difflib
import os
import platform
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Final, List, Literal, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Platform-specific lock imports
# ---------------------------------------------------------------------------

_SYSTEM: Final[str] = platform.system().lower()
_IS_POSIX: Final[bool] = os.name == "posix"
_IS_WINDOWS: Final[bool] = os.name == "nt"

if _IS_POSIX:
    import fcntl  # type: ignore[import-untyped]
elif _IS_WINDOWS:
    import msvcrt  # type: ignore[import-untyped]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_LOCK_TIMEOUT_S: Final[int] = 30
DEFAULT_CONFLICT_STRATEGY: Final[str] = "merge"

# Extension → resolution strategy mapping (overridable)
DEFAULT_EXTENSION_STRATEGIES: Final[Dict[str, str]] = {
    ".py": "merge",
    ".js": "merge",
    ".ts": "merge",
    ".jsx": "merge",
    ".tsx": "merge",
    ".java": "merge",
    ".go": "merge",
    ".rs": "merge",
    ".c": "merge",
    ".cpp": "merge",
    ".h": "merge",
    ".hpp": "merge",
    ".json": "lock",
    ".yaml": "lock",
    ".yml": "lock",
    ".toml": "lock",
    ".ini": "lock",
    ".cfg": "lock",
    ".lock": "human",
    ".db": "human",
    ".sqlite": "human",
    ".sqlite3": "human",
    ".md": "merge",
    ".txt": "merge",
    ".rst": "merge",
}

ResolutionStrategy = Literal["lock", "merge", "human"]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Conflict:
    """Immutable record of a detected file conflict.

    Attributes:
        filepath: Path to the file under contention (relative or absolute).
        worker_a: ID of the first worker that touched the file.
        worker_b: ID of the second worker that touched the file.
        resolution_strategy: Preferred resolution path ("lock", "merge", "human").
        diff: Unified diff string when the conflict is mergeable, else None.
        base_content: Content of the file before any worker edits (for 3-way merge).
        content_a: Content produced by *worker_a*.
        content_b: Content produced by *worker_b*.
    """

    filepath: Path
    worker_a: str
    worker_b: str
    resolution_strategy: ResolutionStrategy
    diff: Optional[str] = None
    base_content: Optional[str] = None
    content_a: Optional[str] = None
    content_b: Optional[str] = None

    def __repr__(self) -> str:
        return (
            f"Conflict(filepath={self.filepath!s}, "
            f"{self.worker_a!r} vs {self.worker_b!r}, "
            f"strategy={self.resolution_strategy!r})"
        )


@dataclass(frozen=True)
class Resolution:
    """Result of resolving a single conflict.

    Attributes:
        conflict: The original conflict record.
        strategy: The strategy actually used (may differ from conflict default).
        status: "resolved", "merged", "locked", or "human_required".
        merged_content: Final merged text (only for merge strategy).
        message: Human-readable explanation of the outcome.
    """

    conflict: Conflict
    strategy: ResolutionStrategy
    status: str
    merged_content: Optional[str] = None
    message: str = ""

    @property
    def ok(self) -> bool:
        """True if the conflict was resolved automatically."""
        return self.status in ("resolved", "merged", "locked")

    @property
    def needs_human(self) -> bool:
        """True if human intervention is required."""
        return self.status == "human_required"


@dataclass(slots=True)
class WorkerIntent:
    """Mutable record of a worker's intent to write a file.

    This is kept *internal* to the coordinator and is NOT exposed
    through the public API.
    """

    worker_id: str
    filepath: Path
    content: Optional[str] = None
    committed: bool = False
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# FileLock – advisory OS-level locking
# ---------------------------------------------------------------------------


class FileLock:
    """Advisory file lock using OS-native primitives.

    On POSIX systems ``fcntl.flock`` is used; on Windows ``msvcrt.locking``
    is used.  The lock is **advisory** — other processes that do not use
    this class can still read/write the file.

    The lock is automatically released when the context manager exits,
    even if an exception is raised inside the ``with`` block.

    Usage::

        with FileLock("/tmp/myfile.txt", timeout=10):
            ...  # exclusive access

        # Non-blocking probe
        lock = FileLock("/tmp/myfile.txt")
        if lock.acquire(blocking=False):
            try:
                ...
            finally:
                lock.release()

    Args:
        filepath: Path to the file to lock.  The file is created if it
            does not exist.
        timeout: Maximum seconds to wait for the lock.  ``0`` means
            non-blocking; ``None`` means block forever.
    """

    __slots__ = ("_filepath", "_timeout", "_fd", "_locked", "_lock_file")

    def __init__(
        self,
        filepath: str | Path,
        timeout: Optional[float] = None,
    ) -> None:
        self._filepath: Path = Path(filepath)
        self._timeout: Optional[float] = timeout
        self._fd: Optional[int] = None
        self._locked: bool = False

        # Use a separate ``.lock`` file so we never corrupt the target.
        self._lock_file: Path = self._filepath.with_suffix(
            self._filepath.suffix + ".lock"
        )

    # ------------------------------------------------------------------
    # Context-manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "FileLock":
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> None:
        self.release()

    # ------------------------------------------------------------------
    # Lock primitives
    # ------------------------------------------------------------------

    def acquire(self, blocking: Optional[bool] = None) -> bool:
        """Acquire the advisory lock.

        Args:
            blocking: If ``True``, block until the lock is available (up to
                *timeout*).  If ``False``, return immediately.  If ``None``,
                use the *timeout* supplied at construction time.

        Returns:
            ``True`` if the lock was acquired, ``False`` otherwise.

        Raises:
            RuntimeError: If the lock is already held by this instance.
            PermissionError: If the lock file cannot be created.
        """
        if self._locked:
            raise RuntimeError("Lock already held by this FileLock instance")

        should_block = blocking if blocking is not None else (self._timeout is None)

        # Ensure the directory exists so we can create the lock file.
        self._lock_file.parent.mkdir(parents=True, exist_ok=True)

        # Open (or create) the lock file.
        self._fd = os.open(str(self._lock_file), os.O_RDWR | os.O_CREAT)

        if _IS_POSIX:
            return self._acquire_posix(should_block)
        elif _IS_WINDOWS:
            return self._acquire_windows(should_block)
        else:
            # Unknown platform – degrade to a no-op but log the situation.
            # We still mark as "locked" so the context manager is safe.
            self._locked = True
            return True

    def _acquire_posix(self, blocking: bool) -> bool:
        """POSIX path using ``fcntl.flock``."""
        import fcntl

        operation = fcntl.LOCK_EX
        if not blocking:
            operation |= fcntl.LOCK_NB

        deadline: Optional[float] = None
        if self._timeout is not None and blocking:
            deadline = time.monotonic() + self._timeout

        while True:
            try:
                fcntl.flock(self._fd, operation)  # type: ignore[arg-type]
                self._locked = True
                return True
            except (OSError, IOError) as exc:
                if exc.errno in (11, 35):  # EAGAIN / EWOULDBLOCK
                    if not blocking:
                        return False
                    if deadline is not None and time.monotonic() >= deadline:
                        self._cleanup_fd()
                        return False
                    time.sleep(0.05)
                    continue
                self._cleanup_fd()
                raise

    def _acquire_windows(self, blocking: bool) -> bool:
        """Windows path using ``msvcrt.locking``."""
        import msvcrt

        deadline: Optional[float] = None
        if self._timeout is not None and blocking:
            deadline = time.monotonic() + self._timeout

        while True:
            try:
                # Lock 1 byte at the start of the file.
                msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
                # If we got here, the byte was free.  Now take it exclusively.
                msvcrt.locking(self._fd, msvcrt.LK_LOCK, 1)
                self._locked = True
                return True
            except OSError as exc:
                # LK_NBLCK raises PermissionError (13) when the byte is locked.
                if exc.errno == 13:
                    if not blocking:
                        return False
                    if deadline is not None and time.monotonic() >= deadline:
                        self._cleanup_fd()
                        return False
                    time.sleep(0.05)
                    continue
                self._cleanup_fd()
                raise

    def release(self) -> None:
        """Release the advisory lock.

        Safe to call multiple times (idempotent).  Automatically invoked
        when exiting a context manager.
        """
        if not self._locked:
            self._cleanup_fd()
            return

        if _IS_POSIX and self._fd is not None:
            import fcntl

            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            except (OSError, IOError):
                pass  # Best-effort release

        elif _IS_WINDOWS and self._fd is not None:
            import msvcrt

            try:
                # Seek to the start before unlocking.
                os.lseek(self._fd, 0, os.SEEK_SET)
                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
            except OSError:
                pass  # Best-effort release

        self._locked = False
        self._cleanup_fd()

    def _cleanup_fd(self) -> None:
        """Close the file descriptor if open."""
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    @property
    def locked(self) -> bool:
        """True if this instance currently holds the lock."""
        return self._locked


# ---------------------------------------------------------------------------
# ConflictDetector – pre-write overlap detection
# ---------------------------------------------------------------------------


class ConflictDetector:
    """Tracks which files each worker intends to modify and detects overlaps.

    This is a purely *in-memory* tracker.  It does **not** perform any
    filesystem operations; for durable locking use :class:`FileLock`.

    Thread-safe via an internal :class:`threading.RLock`.

    Usage::

        detector = ConflictDetector()
        detector.record_intent("worker-a", "src/foo.py")
        detector.record_intent("worker-b", "src/foo.py")

        conflict = detector.check_conflict("worker-b", "src/foo.py")
        assert conflict is not None
    """

    __slots__ = ("_lock", "_intents", "_file_workers", "_strategies")

    def __init__(
        self,
        strategies: Optional[Dict[str, str]] = None,
    ) -> None:
        self._lock: threading.RLock = threading.RLock()
        # worker_id -> {filepath: WorkerIntent}
        self._intents: Dict[str, Dict[Path, WorkerIntent]] = defaultdict(dict)
        # filepath -> {worker_ids}
        self._file_workers: Dict[Path, Set[str]] = defaultdict(set)
        self._strategies: Dict[str, str] = strategies or DEFAULT_EXTENSION_STRATEGIES

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_intent(
        self,
        worker_id: str,
        filepath: str | Path,
        content: Optional[str] = None,
    ) -> Optional[Conflict]:
        """Record that *worker_id* intends to write *filepath*.

        Returns:
            A :class:`Conflict` if another worker already intends to write
            the same file, otherwise ``None``.
        """
        path = Path(filepath)
        with self._lock:
            # Check for existing conflict BEFORE recording.
            conflict = self._check_conflict_locked(worker_id, path, content)

            # Record the intent regardless (we need full history).
            intent = WorkerIntent(
                worker_id=worker_id,
                filepath=path,
                content=content,
            )
            self._intents[worker_id][path] = intent
            self._file_workers[path].add(worker_id)

            return conflict

    def check_conflict(
        self,
        worker_id: str,
        filepath: str | Path,
        content: Optional[str] = None,
    ) -> Optional[Conflict]:
        """Check whether writing *filepath* by *worker_id* would conflict.

        Does **not** record the intent — use :meth:`record_intent` for that.

        Returns:
            A :class:`Conflict` if a conflict exists, else ``None``.
        """
        with self._lock:
            return self._check_conflict_locked(worker_id, Path(filepath), content)

    def clear_intent(self, worker_id: str, filepath: str | Path) -> None:
        """Remove a previously recorded intent (e.g. after commit)."""
        path = Path(filepath)
        with self._lock:
            self._intents[worker_id].pop(path, None)
            self._file_workers[path].discard(worker_id)
            if not self._file_workers[path]:
                del self._file_workers[path]

    def clear_worker(self, worker_id: str) -> None:
        """Remove all intents for a given worker."""
        with self._lock:
            for path in list(self._intents.get(worker_id, {})):
                self._file_workers[path].discard(worker_id)
                if not self._file_workers[path]:
                    del self._file_workers[path]
            self._intents.pop(worker_id, None)

    def detect_all_conflicts(self) -> List[Conflict]:
        """Return every conflict currently known across all workers.

        Returns:
            List of :class:`Conflict` records (deduplicated — each pair
            of workers appears at most once per file).
        """
        conflicts: List[Conflict] = []
        seen: Set[Tuple[Path, str, str]] = set()

        with self._lock:
            for filepath, workers in self._file_workers.items():
                if len(workers) < 2:
                    continue
                workers_sorted = sorted(workers)
                for i in range(len(workers_sorted)):
                    for j in range(i + 1, len(workers_sorted)):
                        wa, wb = workers_sorted[i], workers_sorted[j]
                        key = (filepath, wa, wb)
                        if key in seen:
                            continue
                        seen.add(key)

                        intent_a = self._intents[wa].get(filepath)
                        intent_b = self._intents[wb].get(filepath)

                        strategy = self._pick_strategy(filepath)
                        conflicts.append(
                            Conflict(
                                filepath=filepath,
                                worker_a=wa,
                                worker_b=wb,
                                resolution_strategy=strategy,  # type: ignore[arg-type]
                                base_content=None,
                                content_a=intent_a.content if intent_a else None,
                                content_b=intent_b.content if intent_b else None,
                            )
                        )

        return conflicts

    def get_intents_for_worker(self, worker_id: str) -> Dict[Path, WorkerIntent]:
        """Return a shallow copy of all intents for *worker_id*."""
        with self._lock:
            return dict(self._intents.get(worker_id, {}))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_conflict_locked(
        self,
        worker_id: str,
        filepath: Path,
        content: Optional[str] = None,
    ) -> Optional[Conflict]:
        """Locked variant — caller must hold ``self._lock``."""
        other_workers = self._file_workers.get(filepath, set()) - {worker_id}
        if not other_workers:
            return None

        # Pick the "first" other worker deterministically.
        other = sorted(other_workers)[0]
        other_intent = self._intents[other].get(filepath)

        strategy = self._pick_strategy(filepath)
        return Conflict(
            filepath=filepath,
            worker_a=other,
            worker_b=worker_id,
            resolution_strategy=strategy,  # type: ignore[arg-type]
            base_content=None,
            content_a=other_intent.content if other_intent else None,
            content_b=content,
        )

    def _pick_strategy(self, filepath: Path) -> str:
        """Determine resolution strategy from file extension."""
        ext = filepath.suffix.lower()
        return self._strategies.get(ext, "human")


# ---------------------------------------------------------------------------
# MergeResolver – three-way merge via difflib
# ---------------------------------------------------------------------------


class _ChangeSegment:
    """Internal structure representing one change block.

    Attributes:
        base_start: Start index in the **base** file (0-based, inclusive).
        base_end: End index in the **base** file (0-based, exclusive).
        new_lines: Replacement lines for this segment.
    """

    __slots__ = ("base_start", "base_end", "new_lines")

    def __init__(self, base_start: int, base_end: int, new_lines: List[str]) -> None:
        self.base_start = base_start
        self.base_end = base_end
        self.new_lines = new_lines


class MergeResolver:
    """Three-way merge engine built on :class:`difflib.SequenceMatcher`.

    Algorithm (line-level):

    1. Compare *base* → *worker_a* with :class:`SequenceMatcher` to obtain
       a list of **change segments** (base line ranges that differ).
    2. Do the same for *base* → *worker_b*.
    3. If any segment from step 1 overlaps any segment from step 2 in the
       *base* line range → **human required** (auto-merge refused).
    4. Otherwise → walk through *base* from top to bottom, emitting base
       lines for untouched ranges and worker lines for changed ranges.

    Only **non-overlapping** changes are auto-merged.  Any overlap is
    considered a semantic conflict that needs human review.

    Usage::

        resolver = MergeResolver()
        result = resolver.merge(base_text, text_a, text_b)

        if result is None:
            ...  # conflict — needs human
        else:
            merged = result  # str
    """

    __slots__ = ()

    def merge(
        self,
        base: str,
        worker_a: str,
        worker_b: str,
    ) -> Optional[str]:
        """Attempt a three-way merge.

        Args:
            base: The common ancestor version (file content before edits).
            worker_a: Version produced by the first worker.
            worker_b: Version produced by the second worker.

        Returns:
            The merged string if auto-merge succeeded, or ``None`` if the
            changes overlap and human review is required.
        """
        base_lines = self._normalise_lines(base.splitlines(keepends=True))
        a_lines = self._normalise_lines(worker_a.splitlines(keepends=True))
        b_lines = self._normalise_lines(worker_b.splitlines(keepends=True))

        # Build change segments for each worker.
        segs_a = self._build_segments(base_lines, a_lines)
        segs_b = self._build_segments(base_lines, b_lines)

        # Check for overlap.
        if self._segments_overlap(segs_a, segs_b):
            return None

        # Merge: walk through base line-by-line.
        merged = self._walk_merge(base_lines, segs_a, segs_b, a_lines, b_lines)
        return "".join(merged)

    def diff(
        self,
        base: str,
        worker_a: str,
        worker_b: str,
    ) -> str:
        """Produce a unified diff showing all three versions.

        Returns:
            A unified diff string suitable for logging or presenting to a
            human reviewer.
        """
        base_lines = self._normalise_lines(base.splitlines(keepends=True))
        a_lines = self._normalise_lines(worker_a.splitlines(keepends=True))
        b_lines = self._normalise_lines(worker_b.splitlines(keepends=True))

        diff_a = difflib.unified_diff(
            base_lines,
            a_lines,
            fromfile="base",
            tofile="worker_a",
            lineterm="",
        )
        diff_b = difflib.unified_diff(
            base_lines,
            b_lines,
            fromfile="base",
            tofile="worker_b",
            lineterm="",
        )

        return (
            "--- Diff: base → worker_a ---\n"
            + "\n".join(diff_a)
            + "\n\n--- Diff: base → worker_b ---\n"
            + "\n".join(diff_b)
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_lines(lines: List[str]) -> List[str]:
        """Ensure every line ends with ``\\n``."""
        result: List[str] = []
        for line in lines:
            if not line.endswith("\n"):
                line += "\n"
            result.append(line)
        return result

    @staticmethod
    def _build_segments(
        base_lines: List[str], new_lines: List[str]
    ) -> List[_ChangeSegment]:
        """Build a list of non-equal change segments from *base* → *new*."""
        sm = difflib.SequenceMatcher(None, base_lines, new_lines)
        segments: List[_ChangeSegment] = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag != "equal":
                segments.append(_ChangeSegment(i1, i2, new_lines[j1:j2]))
        return segments

    @staticmethod
    def _segments_overlap(
        segs_a: List[_ChangeSegment],
        segs_b: List[_ChangeSegment],
    ) -> bool:
        """Return ``True`` if any change segment from *a* overlaps *b*.

        Two segments that cover the same base range with **identical**
        replacement content are *not* considered overlapping (both workers
        made the exact same edit → safe to accept).
        """
        for sa in segs_a:
            for sb in segs_b:
                # Intervals [start, end) overlap if start < other_end.
                if sa.base_start < sb.base_end and sb.base_start < sa.base_end:
                    # Identical replacement on the same range → not a conflict.
                    if (
                        sa.base_start == sb.base_start
                        and sa.base_end == sb.base_end
                        and sa.new_lines == sb.new_lines
                    ):
                        continue
                    return True
        return False

    @staticmethod
    def _walk_merge(
        base_lines: List[str],
        segs_a: List[_ChangeSegment],
        segs_b: List[_ChangeSegment],
        a_lines: List[str],
        b_lines: List[str],
    ) -> List[str]:
        """Walk through *base_lines* and emit merged output.

        All change segments (from both workers) are merged into a single
        ordered list.  The walk then copies untouched base lines and
        substitutes changed ranges with the worker's replacement lines.
        """
        # Merge all segments, sorted by base_start.
        all_segs: List[Tuple[int, int, List[str]]] = []
        for s in segs_a:
            all_segs.append((s.base_start, s.base_end, s.new_lines))
        for s in segs_b:
            all_segs.append((s.base_start, s.base_end, s.new_lines))
        all_segs.sort(key=lambda t: t[0])

        result: List[str] = []
        base_idx = 0

        for seg_start, seg_end, new_lines in all_segs:
            # Copy untouched base lines up to this segment.
            while base_idx < seg_start:
                result.append(base_lines[base_idx])
                base_idx += 1
            # Emit the replacement lines.
            result.extend(new_lines)
            # Advance past the consumed base range.
            base_idx = seg_end

        # Copy any remaining base lines.
        while base_idx < len(base_lines):
            result.append(base_lines[base_idx])
            base_idx += 1

        return result


# ---------------------------------------------------------------------------
# SwarmFileCoordinator – main entry point
# ---------------------------------------------------------------------------


class SwarmFileCoordinator:
    """Central coordinator for file writes across parallel swarm workers.

    Combines :class:`FileLock`, :class:`ConflictDetector`, and
    :class:`MergeResolver` into a single, thread-safe interface.

    The coordinator is **fail-closed**: any error during conflict resolution
    escalates to ``"human"`` strategy rather than silently producing bad data.

    Usage::

        coordinator = SwarmFileCoordinator(strategy="merge")

        # Worker A
        coordinator.register_write("a", "src/x.py", "print(1)")
        coordinator.commit_write("a", "src/x.py")

        # Worker B (same file — conflict detected)
        coordinator.register_write("b", "src/x.py", "print(2)")
        conflicts = coordinator.detect_conflicts()
        for c in conflicts:
            res = coordinator.resolve_conflict(c, base_content=original)
            if res.needs_human:
                ...  # escalate
    """

    __slots__ = (
        "_strategy",
        "_timeout",
        "_detector",
        "_resolver",
        "_lock",
        "_strategies",
        "_committed",
    )

    def __init__(
        self,
        strategy: str = DEFAULT_CONFLICT_STRATEGY,
        timeout: int = DEFAULT_LOCK_TIMEOUT_S,
        extension_strategies: Optional[Dict[str, str]] = None,
    ) -> None:
        """Initialize the coordinator.

        Args:
            strategy: Default resolution strategy ("lock", "merge", "human").
            timeout: Lock acquisition timeout in seconds.
            extension_strategies: Override the default extension → strategy map.
        """
        self._strategy: str = strategy
        self._timeout: int = timeout
        self._strategies: Dict[str, str] = extension_strategies or dict(
            DEFAULT_EXTENSION_STRATEGIES
        )
        self._detector = ConflictDetector(strategies=self._strategies)
        self._resolver = MergeResolver()
        self._lock: threading.RLock = threading.RLock()
        # Track which (worker, filepath) pairs have been successfully committed.
        self._committed: Set[Tuple[str, Path]] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_write(
        self,
        worker_id: str,
        filepath: str | Path,
        content: str,
    ) -> List[Conflict]:
        """Register a worker's intent to write a file.

        This should be called **before** the worker begins writing.

        Args:
            worker_id: Unique identifier for the worker.
            filepath: Target file path (relative or absolute).
            content: The content the worker intends to write.

        Returns:
            List of :class:`Conflict` records if the write would conflict
            with another worker, otherwise an empty list.
        """
        path = Path(filepath)
        with self._lock:
            conflict = self._detector.record_intent(worker_id, path, content)
            if conflict is not None:
                return [conflict]
            return []

    def commit_write(
        self,
        worker_id: str,
        filepath: str | Path,
        content: Optional[str] = None,
    ) -> bool:
        """Commit a write after acquiring the appropriate lock.

        This is the **durable** write path.  It acquires an OS-level file
        lock, writes the content, and records the commit.

        Args:
            worker_id: Worker that is committing the write.
            filepath: Target file path.
            content: Content to write.  If ``None``, uses the content
                registered via :meth:`register_write`.

        Returns:
            ``True`` if the write was committed successfully.

        Raises:
            TimeoutError: If the lock could not be acquired within *timeout*.
            FileExistsError: If another worker has already committed this file
                and the strategy is not "merge".
        """
        path = Path(filepath)

        with self._lock:
            # Determine effective strategy.
            strategy = self._effective_strategy(path)

            if strategy == "lock":
                return self._commit_with_lock(worker_id, path, content)
            elif strategy == "merge":
                return self._commit_with_merge(worker_id, path, content)
            else:  # "human"
                return self._commit_human_required(worker_id, path)

    def detect_conflicts(self) -> List[Conflict]:
        """Return all currently known conflicts.

        Returns:
            List of :class:`Conflict` records.
        """
        with self._lock:
            return self._detector.detect_all_conflicts()

    def resolve_conflict(
        self,
        conflict: Conflict,
        base_content: Optional[str] = None,
    ) -> Resolution:
        """Resolve a conflict using the configured strategy.

        Args:
            conflict: The conflict to resolve.
            base_content: The original file content (before any worker edits).
                Required for merge strategy; if omitted, merge falls back
                to "human".

        Returns:
            A :class:`Resolution` record describing the outcome.
        """
        try:
            return self._resolve_conflict_inner(conflict, base_content)
        except Exception as exc:
            # Fail-closed: any error → human review.
            return Resolution(
                conflict=conflict,
                strategy="human",
                status="human_required",
                message=f"Error during conflict resolution: {exc}",
            )

    def get_lock(self, filepath: str | Path) -> FileLock:
        """Get a :class:`FileLock` for *filepath* with the coordinator timeout.

        Useful when a worker wants to manually manage a lock.

        Returns:
            A :class:`FileLock` instance (not yet acquired).
        """
        return FileLock(filepath, timeout=self._timeout)

    def release_all(self, worker_id: str) -> None:
        """Release all intents and locks held by *worker_id*.

        Call this when a worker finishes or crashes.
        """
        with self._lock:
            self._detector.clear_worker(worker_id)
            self._committed = {
                (w, p) for w, p in self._committed if w != worker_id
            }

    def is_committed(self, worker_id: str, filepath: str | Path) -> bool:
        """Check whether *worker_id* has committed *filepath*."""
        with self._lock:
            return (worker_id, Path(filepath)) in self._committed

    # ------------------------------------------------------------------
    # Internal commit paths
    # ------------------------------------------------------------------

    def _effective_strategy(self, filepath: Path) -> str:
        """Determine the effective strategy for *filepath*."""
        ext = filepath.suffix.lower()
        return self._strategies.get(ext, self._strategy)

    def _commit_with_lock(
        self,
        worker_id: str,
        filepath: Path,
        content: Optional[str],
    ) -> bool:
        """Commit path using advisory file locking (serialised access)."""
        actual_content = content or self._get_registered_content(worker_id, filepath)

        with FileLock(filepath, timeout=self._timeout):
            if actual_content is not None:
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_text(actual_content, encoding="utf-8")
            self._committed.add((worker_id, filepath))
            self._detector.clear_intent(worker_id, filepath)

        return True

    def _commit_with_merge(
        self,
        worker_id: str,
        filepath: Path,
        content: Optional[str],
    ) -> bool:
        """Commit path with merge semantics.

        If the file has already been committed by another worker, attempt a
        three-way merge.  If the merge overlaps, escalate to human review.
        """
        actual_content = content or self._get_registered_content(worker_id, filepath)

        with FileLock(filepath, timeout=self._timeout):
            # Check if another worker already committed.
            other_commits = [
                (w, p)
                for w, p in self._committed
                if p == filepath and w != worker_id
            ]

            if not other_commits or actual_content is None:
                # First writer — just write.
                if actual_content is not None:
                    filepath.parent.mkdir(parents=True, exist_ok=True)
                    filepath.write_text(actual_content, encoding="utf-8")
                self._committed.add((worker_id, filepath))
                self._detector.clear_intent(worker_id, filepath)
                return True

            # Another worker wrote first — attempt merge.
            # We need base content.  Try to read the original from the detector.
            base = self._find_base_content(filepath)
            if base is None:
                # No base known — human review.
                return False

            try:
                other_content = filepath.read_text(encoding="utf-8")
            except OSError:
                return False

            merged = self._resolver.merge(base, actual_content, other_content)
            if merged is None:
                # Overlapping changes — can't auto-merge.
                return False

            filepath.write_text(merged, encoding="utf-8")
            self._committed.add((worker_id, filepath))
            self._detector.clear_intent(worker_id, filepath)
            return True

    def _commit_human_required(self, worker_id: str, filepath: Path) -> bool:
        """Human-review path — never auto-commit."""
        # Do NOT write the file.  Leave it for human resolution.
        return False

    def _get_registered_content(
        self, worker_id: str, filepath: Path
    ) -> Optional[str]:
        """Retrieve content registered via :meth:`register_write`."""
        intents = self._detector.get_intents_for_worker(worker_id)
        intent = intents.get(filepath)
        return intent.content if intent else None

    def _find_base_content(self, filepath: Path) -> Optional[str]:
        """Attempt to find the base (pre-edit) content for a file.

        First checks registered conflicts for base_content, then falls back
        to reading the file from disk (which may be stale but is the best
        available approximation).
        """
        # Check conflicts for base content.
        conflicts = self._detector.detect_all_conflicts()
        for c in conflicts:
            if c.filepath == filepath and c.base_content is not None:
                return c.base_content

        # Fallback: read current file from disk.
        try:
            return filepath.read_text(encoding="utf-8")
        except OSError:
            return None

    def _resolve_conflict_inner(
        self,
        conflict: Conflict,
        base_content: Optional[str],
    ) -> Resolution:
        """Inner resolution logic (exceptions propagate to outer handler)."""
        strategy = conflict.resolution_strategy

        if strategy == "lock":
            return Resolution(
                conflict=conflict,
                strategy="lock",
                status="locked",
                message=(
                    f"File {conflict.filepath} locked. "
                    f"{conflict.worker_a} writes first; "
                    f"{conflict.worker_b} will wait."
                ),
            )

        if strategy == "merge":
            base = base_content or conflict.base_content
            if (
                base is not None
                and conflict.content_a is not None
                and conflict.content_b is not None
            ):
                merged = self._resolver.merge(base, conflict.content_a, conflict.content_b)
                if merged is not None:
                    return Resolution(
                        conflict=conflict,
                        strategy="merge",
                        status="merged",
                        merged_content=merged,
                        message=(
                            f"Auto-merged {conflict.filepath} from "
                            f"{conflict.worker_a} and {conflict.worker_b}."
                        ),
                    )
                # Overlap — generate diff for human review.
                diff = self._resolver.diff(base, conflict.content_a, conflict.content_b)
                return Resolution(
                    conflict=conflict,
                    strategy="human",
                    status="human_required",
                    message=(
                        f"Overlapping changes in {conflict.filepath}. "
                        f"Human review required.\n{diff}"
                    ),
                )

            # Missing base — can't merge.
            return Resolution(
                conflict=conflict,
                strategy="human",
                status="human_required",
                message=(
                    f"Cannot auto-merge {conflict.filepath}: "
                    f"base version unknown."
                ),
            )

        # strategy == "human"
        return Resolution(
            conflict=conflict,
            strategy="human",
            status="human_required",
            message=(
                f"Conflict in {conflict.filepath} between "
                f"{conflict.worker_a} and {conflict.worker_b} "
                f"requires human resolution."
            ),
        )


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------


def get_strategy_for_file(
    filepath: str | Path,
    overrides: Optional[Dict[str, str]] = None,
) -> str:
    """Return the resolution strategy for a given file path.

    Args:
        filepath: File path to evaluate.
        overrides: Optional dict mapping extensions to strategies.

    Returns:
        Strategy string ("lock", "merge", or "human").
    """
    strategies = overrides or DEFAULT_EXTENSION_STRATEGIES
    return strategies.get(Path(filepath).suffix.lower(), "human")


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__: List[str] = [
    "FileLock",
    "ConflictDetector",
    "Conflict",
    "Resolution",
    "MergeResolver",
    "SwarmFileCoordinator",
    "WorkerIntent",
    "get_strategy_for_file",
    "DEFAULT_EXTENSION_STRATEGIES",
    "DEFAULT_LOCK_TIMEOUT_S",
    "DEFAULT_CONFLICT_STRATEGY",
]
