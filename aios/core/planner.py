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
from dataclasses import asdict, dataclass, field
from typing import Any, Optional, TYPE_CHECKING

from aios import config

if TYPE_CHECKING:
    from aios.core.native_planner import NativePlanner
from aios.core.confidence_filter import TaskStep, filter_steps
from aios.core.llm import LLMClient
from aios.memory.development import DevelopmentTracker
from aios.memory.mistake import MistakeMemory
from aios.memory.skills import SkillMemory

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
    native_source: Optional[Any] = None

    @property
    def requires_human(self) -> bool:
        """True if any step fell below the confidence threshold."""
        return len(self.escalate) > 0


def serialize_plan(plan: "Plan") -> dict[str, Any]:
    """Flatten a :class:`Plan` (with TaskStep dataclasses) into JSON-safe primitives.

    Shared by the standalone ``POST /api/v1/plan`` endpoint and the in-loop
    plan stage's ``plan`` SSE event, so both surfaces speak ONE shape —
    including the ``native`` flag (the raw ``native_source`` template object
    stays internal; the boolean is the serializable fact callers need).
    """
    return {
        "goal": plan.goal,
        "requires_human": plan.requires_human,
        "native": plan.native_source is not None,
        "steps": [asdict(s) for s in plan.steps],
        "approved": [asdict(s) for s in plan.approved],
        "escalate": [
            {"step": asdict(e["step"]), "reason": e["reason"], "action": e["action"]}
            for e in plan.escalate
        ],
        "calibrations": [asdict(c) for c in plan.calibrations],
    }


def plan_to_prompt_block(plan: "Plan") -> str:
    """Render a :class:`Plan` as the advisory context block the agent reads.

    Lives next to :func:`serialize_plan` for the same reason: the escalate
    entries' internal shape is encapsulated here, not at each consumer. The
    block states its own authority honestly (advisory; approval still happens
    per-action at execution time) and tells the model NOT to re-plan the same
    goal with the ``plan`` tool — the stage already paid that consultation.
    """
    lines = [
        f"{step.step_id}. {step.description} (confidence {step.confidence:.2f})"
        for step in plan.steps
    ]
    if plan.escalate:
        lines.append(
            "Steps requiring human sign-off before risky execution: "
            + ", ".join(str(e["step"].step_id) for e in plan.escalate)
        )
    return (
        "TASK PLAN (advisory, confidence-gated; escalated steps pause for "
        "approval at execution time; already computed — do not call the plan "
        "tool again for this same goal):\n" + "\n".join(lines)
    )


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
    skill_adjustment: float = 0.0
    skill_ids: list[int] = field(default_factory=list)


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
        skills: Optional[SkillMemory] = None,
        native: Optional["NativePlanner"] = None,
    ) -> None:
        self.llm = llm
        self.threshold = threshold
        self.mistakes = mistakes or MistakeMemory()
        self.development = development or DevelopmentTracker()
        self.skills = skills or SkillMemory()
        self._native = native
        self._last_native_source: Optional[Any] = None

    def _calibrate(self, goal: str, step: TaskStep) -> tuple[TaskStep, Calibration]:
        """Adjust self-reported confidence using only verified external evidence."""
        query = f"{goal} {step.description}"
        lessons: list[dict[str, Any]] = []
        outcome = None
        verified_skills: list[dict[str, Any]] = []
        try:
            lessons = self.mistakes.relevant_verified(query, limit=5)
        except Exception:  # noqa: BLE001 - planning remains available if memory is down
            pass
        try:
            outcome = self.development.relevant_success_rate(query)
        except Exception:  # noqa: BLE001 - planning remains available if metrics are down
            pass
        try:
            verified_skills = self.skills.relevant_verified(query, limit=3)
        except Exception:  # noqa: BLE001 - planning remains available if memory is down
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
        # Foraging reward: a step matching strong, fresh verified workflows is
        # encouraged upward. Bounded by SKILL_CONFIDENCE_BONUS_MAX so a trail
        # can never single-handedly clear the human-review gate, and gated on
        # verification (SkillMemory counts only verification-backed successes)
        # so mere repetition cannot manufacture confidence.
        skill_adjustment = min(
            config.SKILL_CONFIDENCE_BONUS_MAX,
            sum(
                float(item["strength"]) * float(item["relevance"])
                for item in verified_skills
            ),
        )
        final = round(
            _clamp_confidence(
                step.confidence
                + lesson_adjustment
                + history_adjustment
                + skill_adjustment
            ),
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
            skill_adjustment=round(skill_adjustment, 6),
            skill_ids=[int(item["skill_id"]) for item in verified_skills],
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

        self._last_native_source = None

        # ── Sovereignty S3: native planning from verified experience ──
        if self._native is not None:
            native_result = self._native.try_plan(goal.strip())
            if native_result is not None:
                self._last_native_source = native_result
                partition = filter_steps(native_result.steps, self.threshold)
                return Plan(
                    goal=goal.strip(),
                    steps=native_result.steps,
                    approved=partition["approved"],
                    escalate=partition["escalate"],
                    calibrations=[],
                    native_source=native_result,
                )

        # -- Offline guard (sovereignty S4) -----------------------------------
        if config.OFFLINE_MODE:
            raise PlannerError(
                "Offline mode: no native plan matched this goal. "
                "LLM planning is unavailable."
            )

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
