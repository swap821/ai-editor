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

    @property
    def requires_human(self) -> bool:
        """True if any step fell below the confidence threshold."""
        return len(self.escalate) > 0


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
    ) -> None:
        self.llm = llm
        self.threshold = threshold

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
        steps = _parse_steps(raw)

        partition = filter_steps(steps, self.threshold)
        return Plan(
            goal=goal.strip(),
            steps=steps,
            approved=partition["approved"],
            escalate=partition["escalate"],
        )
