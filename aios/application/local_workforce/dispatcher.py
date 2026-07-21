"""Clerical job dispatcher (Slice 32, organ 36).

Chooses between deterministic code, the local clerk, frontier escalation,
and human clarification for one clerical job. Granite (or any local model)
is never used merely because it is running: a caller that can answer
deterministically should never reach this function's local-clerk branch at
all, and an unqualified or failing-qualification model must escalate to
frontier intelligence rather than being trusted anyway.
"""

from __future__ import annotations

from typing import Literal

from aios.domain.local_workforce.qualifier import QualificationResult

DispatchDecision = Literal[
    "deterministic", "local_clerk", "frontier_escalation", "human_clarification"
]


def dispatch_clerical_job(
    *,
    deterministic_available: bool,
    qualification: QualificationResult | None,
    confidence: float | None = None,
    confidence_floor: float = 0.6,
) -> DispatchDecision:
    """Decide how one clerical job should be handled.

    Order matters: deterministic code wins whenever it is actually capable
    of answering (checked first, so Granite is never consulted for
    something a parser can already do exactly); an unqualified or failed-
    qualification local model always escalates to frontier, regardless of
    confidence, because a model that has not proven its own reliability
    cannot be trusted to self-report a high-confidence answer; only a
    qualified model's own low-confidence result routes to a human instead
    of silently proceeding or silently escalating.
    """
    if deterministic_available:
        return "deterministic"
    if qualification is None or not qualification.passed:
        return "frontier_escalation"
    if confidence is not None and confidence < confidence_floor:
        return "human_clarification"
    return "local_clerk"


__all__ = ["DispatchDecision", "dispatch_clerical_job"]
