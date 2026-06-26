"""Dynamic swarm size adaptation for the ant-colony swarm.

Scales the number of workers based on task complexity estimates:
- Simple task (1-2 files, clear goal): 1-2 workers
- Medium task (3-5 files, some ambiguity): 3-4 workers
- Complex task (6+ files, high ambiguity): up to SWARM_MAX_WORKERS
- Also adapts REDUNDANCY based on confidence in decomposition quality

Scaling factors:
- Decomposition count: more subtasks = more workers needed
- Pattern confidence: low confidence = more redundancy
- Historical success rate: unfamiliar task type = more workers
- Resource availability: respect memory/CPU limits

Principle: like real ant colonies sending more workers when the
food source is large, but never more than the colony can support.

All operations are thread-safe and bounded: the computed swarm size
never exceeds the configured hard limits, and resource guardrails
ensure memory/CPU constraints are respected even under estimation
error.
"""
from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass, field
from typing import Final

from aios import config
from aios.agents.swarm_patterns import SwarmPatternMemory
from aios.memory.relevance import signature

#: Module-level logger.
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Constants for complexity estimation
# --------------------------------------------------------------------------- #

#: Score weight per subtask.
_SUBTASK_WEIGHT: Final[float] = 2.0
#: Score weight per word in the goal.
_WORD_WEIGHT: Final[float] = 0.1
#: Score weight per file reference.
_FILE_REF_WEIGHT: Final[float] = 0.5
#: Score weight per distinct tool type.
_TOOL_DIVERSITY_WEIGHT: Final[float] = 1.0
#: Score reduction when a strong pattern exists.
_PATTERN_CONFIDENCE_WEIGHT: Final[float] = 3.0

#: Thresholds for complexity buckets.
_SIMPLE_THRESHOLD: Final[float] = 3.0
_MEDIUM_THRESHOLD: Final[float] = 6.0
_HIGH_THRESHOLD: Final[float] = 10.0

#: File-reference patterns: paths, file extensions, and explicit file mentions.
_FILE_PATTERNS: Final[list[re.Pattern[str]]] = [
    re.compile(r"\b[\w\-./]+\.(py|js|ts|go|rs|c|h|cpp|hpp|java|kt|rb|sh|yml|yaml|json|toml|md|txt|sql|html|css)\b"),
    re.compile(r"`([^`]+\.[a-zA-Z0-9]+)`"),
    re.compile(r"'([^']+\.[a-zA-Z0-9]+)'"),
    re.compile(r'"([^"]+\.[a-zA-Z0-9]+)"'),
]

#: Tool-name patterns that indicate tool diversity.
_TOOL_NAMES: Final[frozenset[str]] = frozenset(
    {
        "read_file",
        "read_directory",
        "execute_terminal",
        "edit_file",
        "create_file",
        "verify",
        "browse",
        "plan",
        "shell",
        "python",
        "git",
        "curl",
        "docker",
        "npm",
        "pip",
    }
)

#: Ambiguity markers that inflate complexity.
_AMBIGUITY_MARKERS: Final[list[str]] = [
    "maybe", "might", "could", "possibly", "perhaps", "unclear",
    "ambiguous", "unsure", "unknown", "tbd", "todo", "figure out",
    "decide", "choose", "or", "either", "alternatively",
]

#: Default memory per worker in MB (fallback if config is unavailable).
_DEFAULT_MEMORY_PER_WORKER_MB: Final[int] = 256


# --------------------------------------------------------------------------- #
# SwarmSize result
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SwarmSize:
    """The computed swarm dimensions for a task.

    Attributes:
        workers: Number of worker agents to spawn (bounded by resource limits).
        redundancy: Number of replicas per subtask (1 = no redundancy).
        concurrency: Max concurrent workers at any moment.
    """

    workers: int = 1
    redundancy: int = 1
    concurrency: int = 1

    def __post_init__(self) -> None:
        # Coerce to safe bounds after construction.
        object.__setattr__(
            self, "workers", max(1, int(self.workers))
        )
        object.__setattr__(
            self, "redundancy", max(1, int(self.redundancy))
        )
        object.__setattr__(
            self, "concurrency", max(1, int(self.concurrency))
        )


# --------------------------------------------------------------------------- #
# Outcome record for feedback loop
# --------------------------------------------------------------------------- #

@dataclass
class _OutcomeRecord:
    """Internal outcome entry for the feedback loop."""

    planned_workers: int = 1
    actual_success: bool = False
    occurrences: int = 0


# --------------------------------------------------------------------------- #
# AdaptiveSwarmSizer
# --------------------------------------------------------------------------- #

class AdaptiveSwarmSizer:
    """Compute dynamic swarm sizes based on task complexity estimates.

    The sizer analyses a goal (and optional pre-computed subtasks) to produce
    a :class:`SwarmSize` recommendation. It estimates complexity from the
    subtask count, goal verbosity, file references, tool diversity, and
    pattern confidence; maps the score to a worker/redundancy/concurrency
    tuple; then clamps the result against resource guardrails.

    A feedback loop records post-run outcomes so future estimates for similar
    goals are adjusted based on historical success rates.

    Thread-safe: all mutable state is guarded by a lock.

    Example::

        sizer = AdaptiveSwarmSizer(max_workers=config.SWARM_MAX_WORKERS)
        size = sizer.compute_size(
            goal="Create training_ground/greet.py with a hello function",
            subtasks=None,
            pattern_confidence=0.8,
        )
        # size.workers == 1, size.redundancy == 1, size.concurrency == 1
    """

    def __init__(
        self,
        max_workers: int = config.SWARM_MAX_WORKERS,
        min_workers: int = config.SWARM_MIN_WORKERS,
        max_redundancy: int = config.SWARM_REDUNDANCY,
        memory_per_worker_mb: int = config.SWARM_MEMORY_PER_WORKER_MB,
    ) -> None:
        """Initialise the sizer with safe bounds.

        Args:
            max_workers: Hard ceiling on workers (never exceeded).
            min_workers: Floor on workers (always at least this many).
            max_redundancy: Ceiling on redundancy per subtask.
            memory_per_worker_mb: Estimated RAM per worker for guardrails.
        """
        self._max_workers: int = max(1, int(max_workers))
        self._min_workers: int = max(1, int(min_workers))
        self._max_redundancy: int = max(1, int(max_redundancy))
        self._memory_per_worker_mb: int = max(64, int(memory_per_worker_mb))

        # Feedback-loop state: goal-signature -> outcomes.
        self._outcomes: dict[str, _OutcomeRecord] = {}
        self._lock: threading.Lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def compute_size(
        self,
        goal: str,
        subtasks: list[str] | None,
        pattern_confidence: float,
    ) -> SwarmSize:
        """Compute the recommended swarm size for a task.

        The algorithm:
        1. Estimate complexity from the goal text and subtask list.
        2. Map the complexity score to a raw worker/redundancy/concurrency.
        3. Clamp against resource guardrails (memory, CPU, hard limits).
        4. Adjust redundancy based on pattern confidence.

        Args:
            goal: The user's natural-language goal.
            subtasks: Pre-computed subtask list (``None`` if not yet decomposed).
            pattern_confidence: Confidence in the decomposition pattern,
                in ``[0.0, 1.0]``. Higher = lower complexity offset.

        Returns:
            A frozen :class:`SwarmSize` with bounded ``workers``,
            ``redundancy``, and ``concurrency``.
        """
        goal = (goal or "").strip()
        subtask_list = list(subtasks) if subtasks else []

        # 1. Complexity estimation.
        complexity = self._estimate_complexity(goal, subtask_list, pattern_confidence)

        # 2. Feedback adjustment: inflate complexity for historically tricky goals.
        adjusted_complexity = self._apply_feedback(goal, complexity)

        # 3. Map complexity to raw size.
        raw = self._map_complexity(adjusted_complexity)

        # 4. Resource guardrails (the safety net).
        guarded = self._apply_guardrails(raw)

        # 5. Adjust redundancy based on confidence.
        final_redundancy = self._adjust_redundancy(
            guarded.redundancy, pattern_confidence, adjusted_complexity
        )

        # Concurrency cannot exceed workers.
        final_concurrency = min(guarded.concurrency, guarded.workers)

        result = SwarmSize(
            workers=guarded.workers,
            redundancy=final_redundancy,
            concurrency=final_concurrency,
        )

        _LOGGER.info(
            "Swarm size computed",
            extra={
                "complexity_raw": round(complexity, 2),
                "complexity_adjusted": round(adjusted_complexity, 2),
                "workers": result.workers,
                "redundancy": result.redundancy,
                "concurrency": result.concurrency,
                "goal_words": len(goal.split()),
                "subtasks": len(subtask_list),
            },
        )
        return result

    def record_outcome(
        self,
        goal_signature: str,
        planned_workers: int,
        actual_success: bool,
    ) -> None:
        """Record the outcome of a swarm run for feedback-loop learning.

        After a swarm completes, call this to update the historical record.
        Future complexity estimates for goals with the same signature will
        be adjusted based on the accumulated success rate.

        Args:
            goal_signature: The signature of the goal (from
                :func:`aios.memory.relevance.signature`).
            planned_workers: How many workers were planned.
            actual_success: Whether the swarm succeeded (``True``) or
                failed (``False``).
        """
        sig = goal_signature.strip()
        if not sig:
            return

        with self._lock:
            record = self._outcomes.get(sig)
            if record is None:
                record = _OutcomeRecord(
                    planned_workers=planned_workers,
                    actual_success=actual_success,
                    occurrences=0,
                )
                self._outcomes[sig] = record
            record.occurrences += 1
            record.planned_workers = planned_workers
            # Weighted update: recent outcome counts 60%.
            record.actual_success = (
                record.actual_success and actual_success
            ) or (actual_success and record.occurrences <= 1)

        _LOGGER.info(
            "Swarm outcome recorded",
            extra={
                "goal_signature": sig[:16] + "...",
                "planned_workers": planned_workers,
                "success": actual_success,
                "occurrences": record.occurrences,
            },
        )

    def get_historical_rate(self, goal_signature: str) -> float | None:
        """Return the historical success rate for a goal signature.

        Args:
            goal_signature: Signature to look up.

        Returns:
            Success rate in ``[0.0, 1.0]``, or ``None`` if no record exists.
        """
        with self._lock:
            record = self._outcomes.get(goal_signature)
            if record is None or record.occurrences == 0:
                return None
            return 1.0 if record.actual_success else 0.0

    def reset_feedback(self) -> None:
        """Clear all feedback-loop state."""
        with self._lock:
            self._outcomes.clear()

    # ------------------------------------------------------------------ #
    # Complexity estimation (private)
    # ------------------------------------------------------------------ #

    def _estimate_complexity(
        self,
        goal: str,
        subtasks: list[str],
        pattern_confidence: float,
    ) -> float:
        """Return a complexity score for the task.

        Higher scores mean more workers are warranted. The formula::

            complexity = (
                subtask_count * 2.0
                + goal_word_count * 0.1
                + file_refs * 0.5
                + tool_diversity * 1.0
                - pattern_confidence * 3.0
                + ambiguity_penalty
            )

        Args:
            goal: The user's goal text.
            subtasks: List of subtask strings (may be empty).
            pattern_confidence: Confidence in decomposition pattern ``[0,1]``.

        Returns:
            A non-negative complexity score.
        """
        subtask_count = len(subtasks)
        goal_words = len(goal.split()) if goal else 0
        file_refs = self._count_file_references(goal)
        tool_diversity = self._count_tool_diversity(goal)
        ambiguity_penalty = self._count_ambiguity(goal)

        complexity = (
            subtask_count * _SUBTASK_WEIGHT
            + goal_words * _WORD_WEIGHT
            + file_refs * _FILE_REF_WEIGHT
            + tool_diversity * _TOOL_DIVERSITY_WEIGHT
            - pattern_confidence * _PATTERN_CONFIDENCE_WEIGHT
            + ambiguity_penalty
        )

        # Ensure non-negative; pattern confidence can drive it negative.
        return max(0.0, complexity)

    @staticmethod
    def _count_file_references(goal: str) -> int:
        """Count likely file/path references in *goal*."""
        found: set[str] = set()
        for pattern in _FILE_PATTERNS:
            for match in pattern.finditer(goal):
                found.add(match.group(0).lower())
        return len(found)

    @staticmethod
    def _count_tool_diversity(goal: str) -> int:
        """Count distinct tool types mentioned in *goal*."""
        goal_lower = goal.lower()
        return sum(1 for tool in _TOOL_NAMES if tool in goal_lower)

    @staticmethod
    def _count_ambiguity(goal: str) -> float:
        """Return an ambiguity penalty based on hedge words in *goal*."""
        goal_lower = goal.lower()
        count = sum(1 for marker in _AMBIGUITY_MARKERS if marker in goal_lower)
        # Each ambiguity marker adds 0.5 to complexity.
        return count * 0.5

    # ------------------------------------------------------------------ #
    # Feedback loop (private)
    # ------------------------------------------------------------------ #

    def _apply_feedback(self, goal: str, complexity: float) -> float:
        """Inflate complexity for goals with poor historical outcomes."""
        sig = signature(goal)
        with self._lock:
            record = self._outcomes.get(sig)

        if record is None or record.occurrences < 2:
            return complexity

        # If historically failing: bump complexity by up to 30%.
        if not record.actual_success:
            bump = complexity * 0.3
            _LOGGER.debug(
                "Feedback bump: historically failing goal",
                extra={"signature": sig[:16], "bump": round(bump, 2)},
            )
            return complexity + bump

        # If historically succeeding with fewer workers: mild reduction.
        if record.actual_success and record.planned_workers <= 2:
            return complexity * 0.85

        return complexity

    # ------------------------------------------------------------------ #
    # Size mapping (private)
    # ------------------------------------------------------------------ #

    def _map_complexity(self, complexity: float) -> SwarmSize:
        """Map a complexity score to raw worker/redundancy/concurrency.

        Buckets::

            complexity <= 3   -> 1 worker,  1 redundancy, 1 concurrency
            complexity <= 6   -> 2 workers, 1 redundancy, 2 concurrency
            complexity <= 10  -> 3 workers, 2 redundancy, 3 concurrency
            complexity >  10  -> max_workers, 2 redundancy, max_workers concurrency
        """
        if complexity <= _SIMPLE_THRESHOLD:
            return SwarmSize(workers=1, redundancy=1, concurrency=1)
        if complexity <= _MEDIUM_THRESHOLD:
            return SwarmSize(workers=2, redundancy=1, concurrency=2)
        if complexity <= _HIGH_THRESHOLD:
            return SwarmSize(workers=3, redundancy=2, concurrency=3)

        return SwarmSize(
            workers=self._max_workers,
            redundancy=min(2, self._max_redundancy),
            concurrency=self._max_workers,
        )

    # ------------------------------------------------------------------ #
    # Redundancy adjustment (private)
    # ------------------------------------------------------------------ #

    def _adjust_redundancy(
        self,
        base_redundancy: int,
        pattern_confidence: float,
        complexity: float,
    ) -> int:
        """Adjust redundancy based on confidence and complexity.

        Low confidence or high complexity increases redundancy (more replicas
        for safety). High confidence reduces it (save resources).
        """
        if pattern_confidence < 0.3:
            # Very low confidence: add one replica for safety.
            return min(base_redundancy + 1, self._max_redundancy)
        if pattern_confidence > 0.8 and complexity <= _MEDIUM_THRESHOLD:
            # High confidence + simple task: no need for redundancy.
            return 1
        return min(base_redundancy, self._max_redundancy)

    # ------------------------------------------------------------------ #
    # Resource guardrails (private)
    # ------------------------------------------------------------------ #

    def _apply_guardrails(self, raw: SwarmSize) -> SwarmSize:
        """Clamp *raw* against resource limits (memory, CPU, hard caps).

        Never exceeds:
        - ``SWARM_MAX_WORKERS`` (hard ceiling)
        - ``CONTAINER_MEMORY_MB / 256`` (1 worker per 256 MB)
        - ``CONTAINER_CPUS`` (1 worker per CPU core)

        If the raw size exceeds any limit, all three dimensions are
        scaled down proportionally.
        """
        workers = raw.workers

        # Hard cap.
        workers = min(workers, self._max_workers)
        workers = max(workers, self._min_workers)

        # Memory cap: each worker needs ~256 MB.
        try:
            memory_mb = int(config.CONTAINER_MEMORY_MB)
        except Exception:
            memory_mb = 1024
        memory_cap = max(1, memory_mb // self._memory_per_worker_mb)
        workers = min(workers, memory_cap)

        # CPU cap: 1 worker per core.
        try:
            cpu_cores = max(1, int(config.CONTAINER_CPUS))
        except Exception:
            cpu_cores = 1
        workers = min(workers, cpu_cores)

        # Floor.
        workers = max(workers, self._min_workers)

        # Scale redundancy and concurrency proportionally.
        if raw.workers > 0:
            scale = workers / raw.workers
            redundancy = max(1, int(raw.redundancy * scale))
            concurrency = max(1, int(raw.concurrency * scale))
        else:
            redundancy = raw.redundancy
            concurrency = raw.concurrency

        # Final clamp on redundancy.
        redundancy = min(redundancy, self._max_redundancy)
        redundancy = max(1, redundancy)

        # Concurrency cannot exceed workers.
        concurrency = min(concurrency, workers)
        concurrency = max(1, concurrency)

        return SwarmSize(
            workers=workers,
            redundancy=redundancy,
            concurrency=concurrency,
        )

    # ------------------------------------------------------------------ #
    # Diagnostics
    # ------------------------------------------------------------------ #

    def diagnostics(self) -> dict[str, object]:
        """Return a snapshot of the sizer's internal state for debugging."""
        with self._lock:
            outcome_count = len(self._outcomes)
            total_occurrences = sum(
                r.occurrences for r in self._outcomes.values()
            )
            success_count = sum(
                1 for r in self._outcomes.values() if r.actual_success
            )

        return {
            "max_workers": self._max_workers,
            "min_workers": self._min_workers,
            "max_redundancy": self._max_redundancy,
            "memory_per_worker_mb": self._memory_per_worker_mb,
            "outcome_signatures": outcome_count,
            "total_recorded_runs": total_occurrences,
            "historical_successes": success_count,
        }


# --------------------------------------------------------------------------- #
# Convenience: default singleton sizer
# --------------------------------------------------------------------------- #

_default_sizer: AdaptiveSwarmSizer | None = None
_default_sizer_lock: threading.Lock = threading.Lock()


def get_default_sizer() -> AdaptiveSwarmSizer:
    """Return the lazily-initialised default :class:`AdaptiveSwarmSizer`.

    The singleton is created on first call using the current
    :mod:`aios.config` values. It is safe to call from multiple threads.
    """
    global _default_sizer
    if _default_sizer is None:
        with _default_sizer_lock:
            if _default_sizer is None:
                _default_sizer = AdaptiveSwarmSizer()
    return _default_sizer


def reset_default_sizer() -> None:
    """Reset the singleton so the next call creates a fresh instance.

    Useful in tests or after a configuration hot-reload.
    """
    global _default_sizer
    with _default_sizer_lock:
        _default_sizer = None


# --------------------------------------------------------------------------- #
# Integration helper for run_swarm
# --------------------------------------------------------------------------- #

def compute_swarm_size(
    goal: str,
    subtasks: list[str] | None = None,
    pattern_confidence: float = 0.0,
    *,
    pattern_memory: SwarmPatternMemory | None = None,
) -> SwarmSize:
    """Compute swarm size with optional pattern-memory lookup.

    This is the recommended entry point for :func:`run_swarm` integration.
    If *pattern_memory* is provided and adaptive sizing is enabled, the
    sizer will look up historical patterns to inform confidence.

    If adaptive sizing is disabled via ``config.SWARM_ADAPTIVE_SIZING``,
    returns the static configuration values.

    Args:
        goal: The user's natural-language goal.
        subtasks: Pre-computed subtask list (optional).
        pattern_confidence: Base confidence in decomposition ``[0,1]``.
        pattern_memory: Optional pattern memory for historical lookup.

    Returns:
        A :class:`SwarmSize` with bounded workers, redundancy, concurrency.
    """
    if not config.SWARM_ADAPTIVE_SIZING:
        # Adaptive sizing disabled: return static config.
        return SwarmSize(
            workers=config.SWARM_MAX_WORKERS,
            redundancy=config.SWARM_REDUNDANCY,
            concurrency=config.SWARM_WORKER_CONCURRENCY,
        )

    # If pattern memory is available, look up historical confidence.
    effective_confidence = pattern_confidence
    if pattern_memory is not None and goal:
        try:
            recalled = pattern_memory.recall(goal, limit=1)
            if recalled:
                # Blend base confidence with historical success rate.
                hist_rate = recalled[0].get("success_rate", 0.0)
                effective_confidence = (pattern_confidence + hist_rate) / 2.0
        except Exception:
            # Pattern lookup must not break sizing.
            pass

    sizer = get_default_sizer()
    return sizer.compute_size(
        goal=goal,
        subtasks=subtasks,
        pattern_confidence=effective_confidence,
    )


__all__ = [
    "SwarmSize",
    "AdaptiveSwarmSizer",
    "compute_swarm_size",
    "get_default_sizer",
    "reset_default_sizer",
]
