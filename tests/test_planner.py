"""Planner tests — confidence-gated decomposition with an injected fake LLM."""
from __future__ import annotations

import json
from typing import Optional

import pytest

from aios.core.planner import Planner, PlannerError


class StepLLM:
    """Returns a fixed steps payload, optionally wrapped in noise/fences."""

    def __init__(self, payload: str) -> None:
        self.payload = payload

    def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
        return self.payload


def _steps_json(*confidences: float) -> str:
    steps = [
        {"step_id": str(i + 1), "description": f"step {i + 1}", "confidence": c}
        for i, c in enumerate(confidences)
    ]
    return json.dumps({"steps": steps})


def test_plan_partitions_by_confidence() -> None:
    llm = StepLLM(_steps_json(0.95, 0.5, 0.72))
    plan = Planner(llm).plan("build a todo app")
    assert len(plan.steps) == 3
    assert len(plan.approved) == 2          # 0.95 and 0.72 (>= threshold)
    assert len(plan.escalate) == 1          # 0.5 is below
    assert plan.requires_human is True
    assert plan.escalate[0]["step"].confidence == 0.5


def test_plan_all_confident_needs_no_human() -> None:
    plan = Planner(StepLLM(_steps_json(0.9, 0.85))).plan("safe goal")
    assert plan.requires_human is False
    assert len(plan.approved) == 2


def test_plan_handles_code_fences_and_noise() -> None:
    raw = "Sure! Here is the plan:\n```json\n" + _steps_json(0.8) + "\n```"
    plan = Planner(StepLLM(raw)).plan("anything")
    assert len(plan.steps) == 1


def test_plan_clamps_out_of_range_confidence() -> None:
    plan = Planner(StepLLM(_steps_json(1.7, -0.4))).plan("clamp me")
    confidences = sorted(s.confidence for s in plan.steps)
    assert confidences == [0.0, 1.0]


def test_empty_goal_raises() -> None:
    with pytest.raises(PlannerError):
        Planner(StepLLM(_steps_json(0.9))).plan("   ")


def test_malformed_llm_output_raises() -> None:
    with pytest.raises(PlannerError):
        Planner(StepLLM("not json at all")).plan("goal")


def test_empty_steps_array_raises() -> None:
    with pytest.raises(PlannerError):
        Planner(StepLLM(json.dumps({"steps": []}))).plan("goal")
