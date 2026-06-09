"""Chain-of-thought planner — decomposes a goal into a confidence-scored tree.

The planner asks the local LLM to break a high-level goal into a small, ordered
set of concrete sub-tasks, each carrying a self-reported confidence. Those steps
are then run through the independent confidence gate
(:mod:`aios.core.confidence_filter`): any step below
:data:`aios.config.CONFIDENCE_THRESHOLD` is escalated to human review regardless
of its eventual security zone (Blueprint Q4 — confidence and security are
orthogonal gates).

The planner never executes anything; it only proposes. Like the reflection
agent, it depends on the :class:`~aios.core.llm.LLMClient` protocol, so tests
inject a deterministic fake and need neither Ollama nor a model.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from aios import config
from aios.core.confidence_filter import TaskStep, filter_steps
from aios.core.llm import LLMClient
from aios.memory.development import DevelopmentTracker
from aios.memory.mistake import MistakeMemory

PLAN_SYSTEM_PROMPT = """You are the planning module of a supervised AI operating system.
Decompose the user's goal into 3 to 6 concrete, ordered sub-tasks. For each sub-task,
estimate your confidence (a float from 0.0 to 1.0) that you can complete it correctly
without human help.

Respond with ONLY a single valid JSON object, no prose and no code fences, matching this
schema exactly:
{
  "steps": [
    {"step_id": "1", "description": "what this step does", "confidence": 0.0}
  ]
}
confidence must be a number between 0.0 and 1.0."""

PLAN_USER_TEMPLATE = "Goal:\n{goal}"

#: Greedy match to pull the JSON object out of otherwise-noisy LLM text.
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


class PlannerError(RuntimeError):
    """Raised when the LLM output cannot be parsed into a valid task tree."""


@dataclass(frozen=True)
class Plan:
    """A decomposed goal: the full step tree plus the confidence partition."""

    goal: str
    steps: list[TaskStep]
    approved: list[TaskStep]
    escalate: list[dict[str, Any]]
    calibrations: list["Calibration"]

    @property
    def requires_human(self) -> bool:
        """True if any step fell below the confidence threshold."""
        return len(self.escalate) > 0


@dataclass(frozen=True)
class Calibration:
    """Explainable evidence used to adjust one model-reported confidence."""

    step_id: str
    raw_confidence: float
    lesson_adjustment: float
    history_adjustment: float
    final_confidence: float
    lesson_ids: list[int]
    outcome_attempts: int = 0
    outcome_success_rate: Optional[float] = None


def _clamp_confidence(value: Any) -> float:
    """Coerce *value* to a float in ``[0.0, 1.0]``; unparseable -> 0.0 (fail-low)."""
    try:
        c = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, c))


def _parse_steps(raw: str) -> list[TaskStep]:
    """Extract and validate the ``steps`` array from raw LLM text."""
    if not raw or not raw.strip():
        raise PlannerError("Empty LLM response.")
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    match = _JSON_OBJECT.search(cleaned)
    if not match:
        raise PlannerError("No JSON object found in LLM response.")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise PlannerError(f"Malformed JSON in LLM response: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        raise PlannerError("LLM response is missing a 'steps' array.")

    steps: list[TaskStep] = []
    for index, item in enumerate(data["steps"], start=1):
        if not isinstance(item, dict):
            continue
        description = str(item.get("description", "")).strip()
        if not description:
            continue
        step_id = str(item.get("step_id") or index)
        steps.append(
            TaskStep(
                step_id=step_id,
                description=description,
                confidence=_clamp_confidence(item.get("confidence")),
            )
        )
    if not steps:
        raise PlannerError("LLM response contained no usable steps.")
    return steps


class Planner:
    """Turns a goal into a confidence-gated :class:`Plan` via the local LLM."""

    def __init__(
        self,
        llm: LLMClient,
        *,
        threshold: float = config.CONFIDENCE_THRESHOLD,
        mistakes: Optional[MistakeMemory] = None,
        development: Optional[DevelopmentTracker] = None,
    ) -> None:
        self.llm = llm
        self.threshold = threshold
        self.mistakes = mistakes or MistakeMemory()
        self.development = development or DevelopmentTracker()

    def _calibrate(self, goal: str, step: TaskStep) -> tuple[TaskStep, Calibration]:
        """Adjust self-reported confidence using only verified external evidence."""
        query = f"{goal} {step.description}"
        lessons: list[dict[str, Any]] = []
        outcome = None
        try:
            lessons = self.mistakes.relevant_verified(query, limit=5)
        except Exception:  # noqa: BLE001 - planning remains available if memory is down
            pass
        try:
            outcome = self.development.relevant_success_rate(query)
        except Exception:  # noqa: BLE001 - planning remains available if metrics are down
            pass

        lesson_adjustment = max(
            -0.4,
            sum(float(item["confidence_delta"]) * float(item["relevance"]) for item in lessons),
        )
        history_adjustment = 0.0
        if outcome is not None:
            history_adjustment = max(
                -0.15,
                min(
                    0.15,
                    (outcome.success_rate - 0.5) * 0.3 * outcome.relevance,
                ),
            )
        final = round(
            _clamp_confidence(step.confidence + lesson_adjustment + history_adjustment),
            6,
        )
        calibrated = TaskStep(step.step_id, step.description, final)
        evidence = Calibration(
            step_id=step.step_id,
            raw_confidence=step.confidence,
            lesson_adjustment=round(lesson_adjustment, 6),
            history_adjustment=round(history_adjustment, 6),
            final_confidence=round(final, 6),
            lesson_ids=[int(item["mistake_id"]) for item in lessons],
            outcome_attempts=outcome.attempts if outcome is not None else 0,
            outcome_success_rate=outcome.success_rate if outcome is not None else None,
        )
        return calibrated, evidence

    def plan(self, goal: str) -> Plan:
        """Decompose *goal* into steps and partition them by confidence.

        Args:
            goal: The high-level objective to plan.

        Returns:
            A :class:`Plan` with the full step tree plus ``approved`` and
            ``escalate`` partitions from the confidence gate.

        Raises:
            PlannerError: If *goal* is empty or the LLM output is unusable.
        """
        if not goal or not goal.strip():
            raise PlannerError("Goal must be a non-empty string.")

        prompt = PLAN_USER_TEMPLATE.format(goal=goal.strip())
        raw = self.llm.complete(prompt, system=PLAN_SYSTEM_PROMPT)
        raw_steps = _parse_steps(raw)
        calibrated = [self._calibrate(goal.strip(), step) for step in raw_steps]
        steps = [item[0] for item in calibrated]
        calibrations = [item[1] for item in calibrated]

        partition = filter_steps(steps, self.threshold)
        return Plan(
            goal=goal.strip(),
            steps=steps,
            approved=partition["approved"],
            escalate=partition["escalate"],
            calibrations=calibrations,
        )
