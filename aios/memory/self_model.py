"""The narrative self — a grounded autobiographical self-model.

Synthesizes a short, first-person self-model from the system's OWN graded
telemetry: per-task verified-success rates (``DevelopmentTracker.task_profile``)
and recurring verified lessons (``MistakeMemory.recurring``). It is deliberately
DETERMINISTIC (no LLM narration) and GROUNDED-ONLY: a trait may be claimed only
from above-floor (STRONG) verified evidence — the sources read only verified
events/lessons (Phase 1 already excludes weak greens), and a trait additionally
needs at least ``min_attempts`` verified attempts. Cold-start is silent: with too
little evidence the model is empty and nothing is injected — the organism never
invents a personality.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class Trait:
    """One grounded self-observation, with the evidence that earned it."""

    kind: str  # "strength" | "soft_spot" | "caution"
    subject: str  # the task category (empty for cautions)
    detail: str  # the human-readable lesson/fragment
    attempts: int  # verified attempts (or recurrence count for a caution)
    rate: Optional[float] = None  # verified-success rate (None for a caution)


@dataclass(frozen=True)
class SelfModel:
    """The grounded self-model for one turn."""

    strengths: list[Trait] = field(default_factory=list)
    soft_spots: list[Trait] = field(default_factory=list)
    cautions: list[Trait] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.strengths or self.soft_spots or self.cautions)


def synthesize_self_model(
    development: Any,
    mistakes: Any,
    *,
    min_attempts: int = 4,
    strong_rate: float = 0.8,
    weak_rate: float = 0.5,
    max_traits: int = 3,
) -> SelfModel:
    """Derive a grounded self-model from verified telemetry (deterministic).

    A task category becomes a STRENGTH at ``rate >= strong_rate`` and a SOFT SPOT
    at ``rate <= weak_rate``, but ONLY with at least ``min_attempts`` verified
    attempts (the strength gate: too little verified evidence -> no trait). Cautions
    are the most-recurring verified lessons. Pure: callers handle store exceptions.
    """
    profile: dict[str, tuple[int, float]] = development.task_profile()
    strengths: list[Trait] = []
    soft_spots: list[Trait] = []
    # Most-exercised tasks first, so the strongest evidence leads.
    for task, (attempts, rate) in sorted(
        profile.items(), key=lambda kv: kv[1][0], reverse=True
    ):
        if attempts < min_attempts:
            continue
        if rate >= strong_rate and len(strengths) < max_traits:
            strengths.append(Trait("strength", task, f"reliable at {task}", attempts, rate))
        elif rate <= weak_rate and len(soft_spots) < max_traits:
            soft_spots.append(Trait("soft_spot", task, f"weaker at {task}", attempts, rate))

    cautions: list[Trait] = []
    for lesson in mistakes.recurring(limit=max_traits):
        text = str(lesson.get("lesson_text", "")).strip()
        if not text:
            continue
        cautions.append(
            Trait("caution", "", text, int(lesson.get("occurrence_count", 0) or 0), None)
        )

    return SelfModel(strengths=strengths, soft_spots=soft_spots, cautions=cautions)


def _pct(rate: Optional[float]) -> str:
    return f"{round((rate or 0.0) * 100)}%"


def render(model: SelfModel) -> str:
    """Render the self-model as a compact first-person paragraph (``""`` if empty)."""
    if model.is_empty:
        return ""
    bits: list[str] = []
    for trait in model.strengths:
        bits.append(f"I'm reliable at {trait.subject} ({_pct(trait.rate)} of {trait.attempts} verified)")
    for trait in model.soft_spots:
        bits.append(f"I'm weaker at {trait.subject} ({_pct(trait.rate)} of {trait.attempts} verified)")
    for trait in model.cautions:
        bits.append(f"a recurring lesson I've learned: {trait.detail}")
    return "Self-model from my verified work — " + "; ".join(bits) + "."


__all__ = ["SelfModel", "Trait", "render", "synthesize_self_model"]
