"""Boltzmann probabilistic SCOUT for the ant-colony swarm.

Replaces the binary USE_PATTERN/DECOMPOSE decision with a smooth
probabilistic choice based on pattern strength and temperature.

Mathematical model::

    P(follow pattern_i) = exp(Q_i / T) / sum_j(exp(Q_j / T))

Where:
  - Q_i = quality of pattern_i (success_rate * recency * relevance)
  - T   = temperature (exploration parameter)

Temperature schedule:
  - T_high → nearly uniform (explore widely)
  - T_low  → nearly deterministic (exploit best)
  - T = 0  → deterministic (always pick best, backward-compatible)

This is EXACTLY how real ant colonies work: pheromone strength biases
probability but never eliminates exploration.

Integration
-----------
Call :func:`boltzmann_scout_decision` from ``swarm.py`` in place of the
binary ``if parsed and "DECOMPOSE" not in scout.answer.upper()`` check.
When *temperature* is ``0`` the scout degenerates to the original
deterministic behaviour (always pick the highest-quality pattern if one
exists).
"""
from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from aios import config
from aios.agents.swarm_patterns import SwarmPatternMemory
from aios.memory.relevance import relevance as _relevance

#: Module logger — child of the swarm logger.
_LOGGER: logging.Logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Constants — tunable via config                                              #
# --------------------------------------------------------------------------- #

#: Weight of historical success rate in the quality function.
_WEIGHT_SUCCESS_RATE: float = 0.4
#: Weight of recency (freshness) in the quality function.
_WEIGHT_RECENCY: float = 0.3
#: Weight of semantic relevance to the current goal in the quality function.
_WEIGHT_RELEVANCE: float = 0.2
#: Weight of reuse history in the quality function.
_WEIGHT_REUSE: float = 0.1

#: Minimum quality a pattern must have to be considered at all.
_MIN_PATTERN_QUALITY: float = 0.05
#: Minimum confidence required to select ``use_pattern`` over ``decompose``.
_DECOMPOSE_CONFIDENCE_THRESHOLD: float = 0.35

# --------------------------------------------------------------------------- #
# Data classes                                                                #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class PatternChoice:
    """The result of a Boltzmann scout decision.

    Attributes:
        action: ``"use_pattern"`` or ``"decompose"``.
        pattern_id: The chosen pattern's database id (``None`` when
            *action* is ``"decompose"``).
        confidence: Probability mass assigned to the chosen action. For
            ``use_pattern`` this is the softmax probability of that pattern;
            for ``decompose`` it is the aggregate probability of all patterns
            falling below the quality threshold.
        all_probabilities: Full softmax distribution over every pattern
            that was evaluated, keyed by ``pattern_id``. Useful for audit
            logging and diagnostic dashboards.
    """

    action: str
    pattern_id: int | None = None
    confidence: float = 0.0
    all_probabilities: dict[int, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.action not in ("use_pattern", "decompose"):
            raise ValueError(f"invalid action: {self.action!r}")


@dataclass
class _ParsedTemperatureConfig:
    """Internal representation of a temperature configuration string."""

    mode: str  # "adaptive" | "fixed" | "annealing"
    start: float
    minimum: float
    cooling_rate: float


# --------------------------------------------------------------------------- #
# Temperature parsing                                                         #
# --------------------------------------------------------------------------- #


def _parse_temperature(raw: str) -> _ParsedTemperatureConfig:
    """Parse a temperature config string into its components.

    Expected format::

        <mode>:<start>:<min>:<cooling>

    Examples:
        - ``"adaptive:1.0:0.01:0.95"`` — start at 1.0, cool to 0.01, rate 0.95
        - ``"fixed:0.5:0.5:1.0"`` — constant 0.5 (cooling ignored)
        - ``"annealing:2.0:0.001:0.90"`` — exponential anneal, rate 0.90
    """
    parts = raw.strip().split(":")
    if len(parts) != 4:
        _LOGGER.warning(
            "Invalid temperature config %r; expected mode:start:min:cooling. "
            "Falling back to adaptive:1.0:0.01:0.95",
            raw,
        )
        return _ParsedTemperatureConfig("adaptive", 1.0, 0.01, 0.95)

    mode = parts[0].strip().lower()
    if mode not in ("adaptive", "fixed", "annealing"):
        _LOGGER.warning(
            "Unknown temperature mode %r; defaulting to adaptive.", mode
        )
        mode = "adaptive"

    try:
        start = float(parts[1])
        minimum = float(parts[2])
        cooling = float(parts[3])
    except ValueError:
        _LOGGER.warning(
            "Non-numeric temperature config %r; falling back to "
            "adaptive:1.0:0.01:0.95",
            raw,
        )
        return _ParsedTemperatureConfig("adaptive", 1.0, 0.01, 0.95)

    # Sanitise bounds.
    start = max(0.0, start)
    minimum = max(0.0, min(start, minimum))
    cooling = max(0.0, min(1.0, cooling))

    return _ParsedTemperatureConfig(mode, start, minimum, cooling)


# --------------------------------------------------------------------------- #
# Quality computation                                                         #
# --------------------------------------------------------------------------- #


def _hours_since(updated_at_str: str | None) -> float:
    """Return hours elapsed since *updated_at_str* (ISO-8601-ish) or inf."""
    if not updated_at_str:
        return float("inf")
    try:
        # Try the most common SQLite datetime format first.
        parsed = time.strptime(str(updated_at_str), "%Y-%m-%d %H:%M:%S")
        delta = time.time() - time.mktime(parsed)
        return max(0.0, delta / 3600.0)
    except (ValueError, OverflowError):
        # Gracefully degrade when the timestamp is unparseable.
        return float("inf")


def _compute_quality(pattern: dict[str, Any], goal: str) -> float:
    """Compute the quality score Q_i for a single pattern.

    Q(pattern, goal) = (
        success_rate * 0.4
        + recency_score * 0.3
        + relevance_score * 0.2
        + reuse_score * 0.1
    )

    Each sub-score is clamped to ``[0, 1]`` so Q naturally lives in
    ``[0, 1]`` as well.
    """
    # 1. Historical success (40%) — already in [0, 1].
    success_rate = float(pattern.get("success_rate", 0.0))
    success_rate = max(0.0, min(1.0, success_rate))

    # 2. Recency (30%) — exponential decay since last update.
    updated_at = pattern.get("updated_at")
    hours = _hours_since(updated_at)
    lambda_decay = config.SKILL_LAMBDA_DECAY_PER_HOUR
    recency_score = math.exp(-lambda_decay * hours)
    recency_score = max(0.0, min(1.0, recency_score))

    # 3. Semantic relevance (20%) — call the existing relevance function
    #    unless the recall already computed it.
    relevance_score = float(pattern.get("relevance", 0.0))
    if relevance_score == 0.0 and goal:
        goal_pattern = pattern.get("goal_pattern", "")
        if goal_pattern:
            relevance_score = _relevance(goal, str(goal_pattern))
    relevance_score = max(0.0, min(1.0, relevance_score))

    # 4. Reuse score (10%) — how often has this pattern been reused
    #    relative to its direct attempts? High reuse/use ratio means
    #    the colony finds it reliably useful.
    use_count = int(pattern.get("use_count", 0))
    total_attempts = int(pattern.get("success_count", 0)) + int(
        pattern.get("failure_count", 0)
    )
    if total_attempts > 0:
        reuse_ratio = use_count / total_attempts
        # Logistic squashing so ratio -> 1 maps to score -> 1 smoothly.
        reuse_score = 1.0 / (1.0 + math.exp(-3.0 * (reuse_ratio - 1.0)))
    else:
        reuse_score = 0.0
    reuse_score = max(0.0, min(1.0, reuse_score))

    quality = (
        _WEIGHT_SUCCESS_RATE * success_rate
        + _WEIGHT_RECENCY * recency_score
        + _WEIGHT_RELEVANCE * relevance_score
        + _WEIGHT_REUSE * reuse_score
    )

    return round(max(0.0, min(1.0, quality)), 6)


# --------------------------------------------------------------------------- #
# Exploration bonus (UCB-style)                                               #
# --------------------------------------------------------------------------- #


def _compute_exploration_bonus(
    pattern: dict[str, Any],
    total_uses_all_patterns: int,
) -> float:
    """Upper Confidence Bound bonus for under-sampled patterns.

    ``bonus = c * sqrt(2 * ln(N) / n)``

    where *N* is total uses across all patterns, *n* is uses of this
    pattern, and *c* is the exploration-bonus coefficient from config.

    Patterns that have never been used get a large bonus so the scout
    will try them at least once.
    """
    c = config.SWARM_SCOUT_EXPLORATION_BONUS
    n = int(pattern.get("use_count", 0))
    N = max(total_uses_all_patterns, 1)

    if n <= 0:
        # Never-used patterns get the maximum possible bonus.
        return c * math.sqrt(2.0 * math.log(N + 1))

    return c * math.sqrt(2.0 * math.log(N) / n)


# --------------------------------------------------------------------------- #
# Softmax / Boltzmann distribution                                            #
# --------------------------------------------------------------------------- #


def _softmax(qualities: list[float], temperature: float) -> list[float]:
    """Return a probability distribution over *qualities* using the
    Boltzmann (Gibbs) distribution.

    When *temperature* is ``0`` the distribution degenerates to a one-hot
    vector over the arg-max (deterministic exploitation).

    Numerically stabilised by subtracting the max before exponentiation.
    """
    if not qualities:
        return []

    if temperature <= 0.0:
        # Deterministic: one-hot over the best quality.
        best_idx = max(range(len(qualities)), key=lambda i: qualities[i])
        result = [0.0] * len(qualities)
        result[best_idx] = 1.0
        return result

    # Numerical stabilisation: subtract max before exp.
    max_q = max(qualities)
    shifted = [(q - max_q) / temperature for q in qualities]
    exps = [math.exp(s) for s in shifted]
    sum_exps = sum(exps)

    if sum_exps == 0.0 or not math.isfinite(sum_exps):
        # Degenerate case — fall back to uniform.
        n = len(qualities)
        return [1.0 / n] * n

    return [e / sum_exps for e in exps]


# --------------------------------------------------------------------------- #
# BoltzmannScout class                                                        #
# --------------------------------------------------------------------------- #


class BoltzmannScout:
    """Probabilistic pattern selector for the SCOUT caste.

    Uses a Boltzmann (softmax) distribution over pattern qualities to
    decide whether to follow a known decomposition pattern or decompose
    afresh. The *temperature* parameter smoothly interpolates between
    pure exploration (high T, near-uniform sampling) and pure exploitation
    (low T, near-deterministic best-choice).

    Thread-safe: internal mutable state is protected by a :class:`threading.Lock`.

    Args:
        temperature: Initial temperature value, or a config string like
            ``"adaptive:1.0:0.01:0.95"``. If ``None``, reads from
            :data:`config.SWARM_SCOUT_TEMPERATURE`.
        min_temperature: Floor for temperature cooling (default ``0.01``).
        cooling_rate: Multiplicative cooling factor per decision call
            (default ``0.95``). Ignored when the parsed config provides its
            own cooling rate.

    Example::

        scout = BoltzmannScout()
        choice = scout.choose_pattern(recalled_patterns, goal="refactor auth")
        if choice.action == "use_pattern":
            subtasks = pattern_by_id[choice.pattern_id]["subtasks"]
        else:
            subtasks = None  # fall through to DECOMPOSER
    """

    def __init__(
        self,
        temperature: str | float | None = None,
        min_temperature: float = 0.01,
        cooling_rate: float = 0.95,
    ) -> None:
        raw: str = (
            str(temperature)
            if temperature is not None
            else config.SWARM_SCOUT_TEMPERATURE
        )
        self._cfg = BoltzmannScout._parse_temperature_config(
            raw, min_temperature, cooling_rate
        )

        # Mutable state — protected by _lock.
        self._lock = threading.Lock()
        self._call_count: int = 0
        self._current_temperature: float = self._cfg.start

    # -- configuration resolution -------------------------------------------

    @staticmethod
    def _parse_temperature_config(
        raw: str,
        min_temperature: float,
        cooling_rate: float,
    ) -> _ParsedTemperatureConfig:
        if ":" in raw:
            return _parse_temperature(raw)
        # Plain float — treat as fixed mode.
        try:
            t = float(raw)
        except ValueError:
            _LOGGER.warning(
                "Non-numeric temperature %r; defaulting to 0.5 (fixed).", raw
            )
            t = 0.5
        return _ParsedTemperatureConfig("fixed", t, min_temperature, cooling_rate)

    # -- temperature schedule -----------------------------------------------

    @property
    def temperature(self) -> float:
        """Current temperature value (thread-safe read)."""
        with self._lock:
            return self._current_temperature

    def _update_temperature(self) -> float:
        """Apply the configured schedule and return the new temperature."""
        with self._lock:
            self._call_count += 1
            if self._cfg.mode == "fixed":
                return self._current_temperature
            if self._cfg.mode == "annealing":
                self._current_temperature = max(
                    self._cfg.minimum,
                    self._cfg.start * (self._cfg.cooling_rate**self._call_count),
                )
            elif self._cfg.mode == "adaptive":
                # Adaptive cools on every call but never below minimum.
                self._current_temperature = max(
                    self._cfg.minimum,
                    self._current_temperature * self._cfg.cooling_rate,
                )
            return self._current_temperature

    # -- core decision ------------------------------------------------------

    def choose_pattern(
        self,
        patterns: list[dict[str, Any]],
        goal: str,
    ) -> PatternChoice:
        """Select a pattern (or decide to decompose) via Boltzmann sampling.

        Args:
            patterns: List of pattern dicts as returned by
                :meth:`SwarmPatternMemory.recall`.
            goal: The user's current goal text.

        Returns:
            A :class:`PatternChoice` describing the selected action and the
            full probability distribution for audit logging.
        """
        if not patterns:
            return PatternChoice(
                action="decompose",
                pattern_id=None,
                confidence=1.0,
                all_probabilities={},
            )

        # 1. Compute quality for each pattern.
        qualities: list[float] = []
        total_uses = sum(int(p.get("use_count", 0)) for p in patterns)
        for pattern in patterns:
            q = _compute_quality(pattern, goal)
            bonus = _compute_exploration_bonus(pattern, total_uses)
            qualities.append(q + bonus)

        # 2. Filter out patterns below the minimum quality threshold.
        #    Those that fail are implicitly folded into "decompose".
        viable_indices: list[int] = [
            i
            for i, q in enumerate(qualities)
            if q >= _MIN_PATTERN_QUALITY
        ]

        if not viable_indices:
            # No pattern is good enough — always decompose.
            return PatternChoice(
                action="decompose",
                pattern_id=None,
                confidence=1.0,
                all_probabilities={
                    int(p.get("pattern_id", i)): 0.0
                    for i, p in enumerate(patterns)
                },
            )

        # 3. Get current temperature (and cool for next call).
        t = self._update_temperature()

        # 4. Softmax over viable patterns only.
        viable_qualities = [qualities[i] for i in viable_indices]
        probabilities = _softmax(viable_qualities, t)

        # 5. Build full distribution keyed by pattern_id.
        all_probs: dict[int, float] = {}
        for i, p in enumerate(patterns):
            pid = int(p.get("pattern_id", i))
            all_probs[pid] = 0.0
        for vi, prob in zip(viable_indices, probabilities):
            pid = int(patterns[vi].get("pattern_id", vi))
            all_probs[pid] = round(prob, 6)

        # 6. Select the winning pattern (argmax = deterministic at T=0,
        #    most-likely otherwise). Sampling would be:
        #    ``random.choices(viable_indices, weights=probabilities)[0]``
        #    but argmax keeps the scout reproducible and audit-friendly.
        best_local_idx = max(range(len(probabilities)), key=lambda i: probabilities[i])
        best_global_idx = viable_indices[best_local_idx]
        best_pattern = patterns[best_global_idx]
        best_prob = probabilities[best_local_idx]
        best_pid = int(best_pattern.get("pattern_id", best_global_idx))

        # 7. If the best pattern's probability is too low, prefer decompose.
        if best_prob < _DECOMPOSE_CONFIDENCE_THRESHOLD:
            decompose_confidence = 1.0 - best_prob
            return PatternChoice(
                action="decompose",
                pattern_id=None,
                confidence=round(decompose_confidence, 6),
                all_probabilities=all_probs,
            )

        return PatternChoice(
            action="use_pattern",
            pattern_id=best_pid,
            confidence=round(best_prob, 6),
            all_probabilities=all_probs,
        )


# --------------------------------------------------------------------------- #
# Integration helper — drop-in replacement for binary check                   #
# --------------------------------------------------------------------------- #

#: Module-level singleton — lazily created on first use.
_scout_singleton: Optional[BoltzmannScout] = None
_scout_singleton_lock = threading.Lock()


def _get_scout() -> BoltzmannScout:
    """Return (and possibly create) the module-level :class:`BoltzmannScout`."""
    global _scout_singleton  # noqa: PLW0603
    if _scout_singleton is None:
        with _scout_singleton_lock:
            if _scout_singleton is None:
                _scout_singleton = BoltzmannScout()
    return _scout_singleton


@dataclass(frozen=True, slots=True)
class ScoutDecision:
    """Rich return type for :func:`boltzmann_scout_decision`.

    Attributes:
        use_pattern: ``True`` when a pattern was selected.
        subtasks: The subtask list from the chosen pattern (empty when
            ``use_pattern`` is ``False``).
        pattern_id: The database id of the chosen pattern (``None`` when
            no pattern was selected).
        choice: The underlying :class:`PatternChoice` for audit logging.
    """

    use_pattern: bool
    subtasks: list[str]
    pattern_id: int | None
    choice: PatternChoice


def boltzmann_scout_decision(
    patterns: list[dict[str, Any]],
    goal: str,
    *,
    scout: Optional[BoltzmannScout] = None,
) -> ScoutDecision:
    """Probabilistic SCOUT decision — drop-in for the binary DECOMPOSE check.

    This function is intended to be called from :func:`run_swarm` in
    ``swarm.py`` after the pattern-recall step. It replaces::

        if parsed and "DECOMPOSE" not in scout.answer.upper():
            plan = parsed
            pattern_memory.bump_use(recalled[0]["pattern_id"])

    With::

        decision = boltzmann_scout_decision(recalled, goal)
        if decision.use_pattern:
            plan = decision.subtasks
            pattern_memory.bump_use(decision.pattern_id)

    Args:
        patterns: Verified patterns recalled by
            :meth:`SwarmPatternMemory.recall`.
        goal: The user's current goal text.
        scout: An optional :class:`BoltzmannScout` instance. When ``None``
            a module-level singleton is used.

    Returns:
        A :class:`ScoutDecision` describing whether to use a pattern
        (and which one) or decompose.

    Audit logging:
        The full probability distribution is logged at DEBUG level under
        the key ``scout_probabilities`` so that operators can trace why
        the swarm chose a particular path.
    """
    if not patterns:
        return ScoutDecision(
            use_pattern=False,
            subtasks=[],
            pattern_id=None,
            choice=PatternChoice(
                action="decompose",
                confidence=1.0,
                all_probabilities={},
            ),
        )

    active_scout = scout or _get_scout()
    choice = active_scout.choose_pattern(patterns, goal)

    subtasks: list[str] = []
    if choice.action == "use_pattern" and choice.pattern_id is not None:
        # Find the chosen pattern in the recalled list.
        for p in patterns:
            if int(p.get("pattern_id", -1)) == choice.pattern_id:
                subtasks = list(p.get("subtasks", []))
                break

    _LOGGER.debug(
        "bolt_scout_decision",
        extra={
            "goal": goal[:200],
            "action": choice.action,
            "pattern_id": choice.pattern_id,
            "confidence": choice.confidence,
            "temperature": round(active_scout.temperature, 4),
            "scout_probabilities": choice.all_probabilities,
        },
    )

    return ScoutDecision(
        use_pattern=choice.action == "use_pattern",
        subtasks=subtasks,
        pattern_id=choice.pattern_id,
        choice=choice,
    )


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #

__all__ = [
    "BoltzmannScout",
    "PatternChoice",
    "ScoutDecision",
    "boltzmann_scout_decision",
    "_compute_quality",
    "_compute_exploration_bonus",
    "_softmax",
]
