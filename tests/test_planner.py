"""Planner tests — confidence-gated decomposition with an injected fake LLM."""
from __future__ import annotations

import json
from typing import Optional

import pytest

from aios.core.planner import (
    Plan,
    Planner,
    PlannerError,
    plan_to_prompt_block,
    serialize_plan,
)


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


class _EmptyMemory:
    def relevant_verified(self, query: str, limit: int = 5) -> list[dict]:
        return []

    def relevant_success_rate(self, query: str):
        return None


def _planner(llm: StepLLM, **kwargs) -> Planner:
    return Planner(llm, mistakes=_EmptyMemory(), **kwargs)


def test_planner_refuses_implicit_legacy_memory_stores() -> None:
    with pytest.raises(
        RuntimeError,
        match="MemoryAuthority or explicit memory stores are required",
    ):
        Planner(StepLLM(_steps_json(0.9)))


def test_plan_partitions_by_confidence() -> None:
    llm = StepLLM(_steps_json(0.95, 0.5, 0.72))
    plan = _planner(llm).plan("build a todo app")
    assert len(plan.steps) == 3
    assert len(plan.approved) == 2          # 0.95 and 0.72 (>= threshold)
    assert len(plan.escalate) == 1          # 0.5 is below
    assert plan.requires_human is True
    assert plan.escalate[0]["step"].confidence == 0.5


def test_plan_all_confident_needs_no_human() -> None:
    plan = _planner(StepLLM(_steps_json(0.9, 0.85))).plan("safe goal")
    assert plan.requires_human is False
    assert len(plan.approved) == 2


def test_plan_handles_code_fences_and_noise() -> None:
    raw = "Sure! Here is the plan:\n```json\n" + _steps_json(0.8) + "\n```"
    plan = _planner(StepLLM(raw)).plan("anything")
    assert len(plan.steps) == 1


def test_plan_clamps_out_of_range_confidence() -> None:
    plan = _planner(StepLLM(_steps_json(1.7, -0.4))).plan("clamp me")
    confidences = sorted(s.confidence for s in plan.steps)
    assert confidences == [0.0, 1.0]


def test_empty_goal_raises() -> None:
    with pytest.raises(PlannerError):
        _planner(StepLLM(_steps_json(0.9))).plan("   ")


def test_malformed_llm_output_raises() -> None:
    with pytest.raises(PlannerError):
        _planner(StepLLM("not json at all")).plan("goal")


def test_empty_steps_array_raises() -> None:
    with pytest.raises(PlannerError):
        _planner(StepLLM(json.dumps({"steps": []}))).plan("goal")


# ── serialize_plan / plan_to_prompt_block — pure-unit coverage ──────────────
# The B2 close-out flagged these two shared helpers (used by both the standalone
# /api/v1/plan endpoint and the in-loop plan-stage SSE) as untested in isolation.


def test_serialize_plan_is_json_safe_and_complete() -> None:
    plan = _planner(StepLLM(_steps_json(0.95, 0.4))).plan("ship a feature")
    data = serialize_plan(plan)
    # Round-trips through JSON with no dataclass leaking through.
    assert json.loads(json.dumps(data)) == data
    assert data["goal"] == "ship a feature"
    assert data["requires_human"] is True
    assert data["native"] is False
    assert len(data["steps"]) == 2
    # Escalate entries carry the flattened step plus reason/action.
    assert len(data["escalate"]) == 1
    esc = data["escalate"][0]
    assert set(esc) == {"step", "reason", "action"}
    assert isinstance(esc["step"], dict)
    assert esc["step"]["confidence"] == 0.4


def test_serialize_plan_native_flag_reflects_native_source() -> None:
    native = Plan(
        goal="g",
        steps=[],
        approved=[],
        escalate=[],
        calibrations=[],
        native_source=object(),
    )
    assert serialize_plan(native)["native"] is True
    plain = Plan(goal="g", steps=[], approved=[], escalate=[], calibrations=[])
    assert serialize_plan(plain)["native"] is False


def test_plan_to_prompt_block_renders_steps_and_escalations() -> None:
    plan = _planner(StepLLM(_steps_json(0.95, 0.4))).plan("do the thing")
    block = plan_to_prompt_block(plan)
    assert block.startswith("TASK PLAN (advisory")
    # Every step's description and 2-dp confidence is present.
    assert "step 1" in block and "0.95" in block
    assert "step 2" in block and "0.40" in block
    # The below-threshold step is called out for sign-off.
    assert "human sign-off" in block
    # And the model is told not to re-plan the same goal.
    assert "do not call the plan" in block


def test_plan_to_prompt_block_omits_escalation_line_when_all_confident() -> None:
    plan = _planner(StepLLM(_steps_json(0.9, 0.88))).plan("all good")
    block = plan_to_prompt_block(plan)
    assert "human sign-off" not in block
    assert "step 1" in block and "step 2" in block
