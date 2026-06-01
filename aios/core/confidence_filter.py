"""Confidence gating — the second, independent human-in-the-loop layer.

Orthogonal to security-zone classification: any planned step whose confidence
falls below :data:`aios.config.CONFIDENCE_THRESHOLD` (default 0.72) is escalated
to human review regardless of how safe its security zone is. The two gates are
independent, so a GREEN-zone step can still require approval when the planner is
unsure (Blueprint Q4 / trust principle "Confidence Gating").
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from aios import config


@dataclass(frozen=True)
class TaskStep:
    """A single planned step carrying the planner's self-reported confidence."""

    step_id: str
    description: str
    confidence: float


@dataclass(frozen=True)
class GateResult:
    """Outcome of a single confidence check."""

    passed: bool
    reason: str


def gate(confidence: float, threshold: float = config.CONFIDENCE_THRESHOLD) -> GateResult:
    """Return whether *confidence* meets *threshold* (>=)."""
    passed = confidence >= threshold
    if passed:
        return GateResult(True, f"Confidence {confidence:.3f} meets threshold {threshold:.3f}")
    return GateResult(
        False,
        f"Confidence {confidence:.3f} below threshold {threshold:.3f} — human review required",
    )


def filter_steps(
    steps: Iterable[TaskStep], threshold: float = config.CONFIDENCE_THRESHOLD
) -> dict[str, list[Any]]:
    """Partition *steps* into auto-approved vs. human-escalation lists.

    Returns a dict with ``"approved"`` (list of :class:`TaskStep`) and
    ``"escalate"`` (list of ``{step, reason, action}`` records).
    """
    approved: list[TaskStep] = []
    escalate: list[dict[str, Any]] = []
    for step in steps:
        result = gate(step.confidence, threshold)
        if result.passed:
            approved.append(step)
        else:
            escalate.append(
                {"step": step, "reason": result.reason, "action": "REQUIRE_HUMAN_REVIEW"}
            )
    return {"approved": approved, "escalate": escalate}
