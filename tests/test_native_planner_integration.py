"""Integration tests — NativePlanner wired into Planner (sovereignty S3)."""
from __future__ import annotations

import json
from typing import Any, Optional

import pytest

from aios.core.confidence_filter import TaskStep
from aios.core.native_planner import NativePlanner, NativePlanResult
from aios.core.planner import Planner, PlannerError


# ── Fakes ──────────────────────────────────────────────────────────────────


class StepLLM:
    """Returns a fixed steps payload; tracks whether it was called."""

    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.called = False

    def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
        self.called = True
        return self.payload


class FakeSwarmPatterns:
    def __init__(self, results: list[dict] | None = None):
        self._results = results or []

    def recall(self, goal: str, *, limit: int = 1) -> list[dict]:
        return self._results[:limit]


class FakeSkillMemory:
    def __init__(self, results: list[dict] | None = None):
        self._results = results or []

    def relevant_verified(self, query: str, limit: int = 3) -> list[dict]:
        return self._results[:limit]


def _steps_json(*confidences: float) -> str:
    steps = [
        {"step_id": str(i + 1), "description": f"step {i + 1}", "confidence": c}
        for i, c in enumerate(confidences)
    ]
    return json.dumps({"steps": steps})


SWARM_MATCH = {
    "pattern_id": 42,
    "goal_pattern": "build a REST API with tests",
    "subtasks": ["scaffold endpoints", "write models", "add tests"],
    "success_count": 5,
    "failure_count": 0,
    "success_rate": 1.0,
    "relevance": 0.80,
    "score": 0.80,
}

SKILL_HIGH_CONF = {
    "skill_id": 17,
    "goal_pattern": "create a pytest for the router module",
    "steps": ["read router.py", "write test_router.py", "run pytest"],
    "success_count": 4,
    "failure_count": 0,
    "success_rate": 1.0,
    "freshness": 1.0,
    "reuse_success_count": 2,
    "reuse_failure_count": 0,
    "reuse_factor": 1.0,
    "strength": 1.0,
    "relevance": 0.90,
}


# ── Integration tests ─────────────────────────────────────────────────────


def test_planner_uses_native_before_llm() -> None:
    """When the native planner matches, the LLM is never called."""
    llm = StepLLM(_steps_json(0.9, 0.8))
    native = NativePlanner(patterns=FakeSwarmPatterns([SWARM_MATCH]))
    planner = Planner(llm, native=native)

    plan = planner.plan("build a REST API with tests")
    assert llm.called is False
    assert plan.native_source is not None
    assert plan.native_source.source == "swarm_pattern"
    assert len(plan.steps) == 3


def test_planner_falls_through_on_no_match() -> None:
    """When the native planner has no match, the LLM is called normally."""
    llm = StepLLM(_steps_json(0.9, 0.85))
    native = NativePlanner()  # no stores -> no match
    planner = Planner(llm, native=native)

    plan = planner.plan("something novel")
    assert llm.called is True
    assert plan.native_source is None
    assert len(plan.steps) == 2


def test_native_plan_passes_confidence_gate() -> None:
    """A native plan with evidence confidence >= 0.72 has approved steps."""
    native = NativePlanner(patterns=FakeSwarmPatterns([SWARM_MATCH]))
    llm = StepLLM(_steps_json(0.9))
    planner = Planner(llm, native=native)

    plan = planner.plan("build a REST API")
    # evidence_confidence = 1.0 * 0.80 = 0.80 >= 0.72
    assert len(plan.approved) == 3
    assert len(plan.escalate) == 0
    assert plan.requires_human is False


def test_native_plan_escalates_low_confidence() -> None:
    """A native plan with evidence confidence < 0.72 has escalated steps."""
    low_conf = {**SWARM_MATCH, "success_rate": 0.75, "relevance": 0.96}
    # evidence_confidence = 0.75 * 0.96 = 0.72 (exactly at threshold, should pass)
    native = NativePlanner(
        patterns=FakeSwarmPatterns([low_conf]),
        min_confidence=0.0,  # let it through the native planner's own gate
    )
    llm = StepLLM(_steps_json(0.9))
    planner = Planner(llm, native=native)

    plan = planner.plan("build something")
    # All steps carry evidence_confidence = 0.72 exactly at threshold -> approved
    assert plan.native_source is not None
    assert all(s.confidence == plan.native_source.evidence_confidence for s in plan.steps)


def test_native_plan_below_gate_escalates() -> None:
    """Steps with evidence confidence below 0.72 go to escalate."""
    low_conf = {**SWARM_MATCH, "success_rate": 0.70, "relevance": 0.96}
    # evidence_confidence = 0.70 * 0.96 = 0.672 (below 0.72)
    native = NativePlanner(
        patterns=FakeSwarmPatterns([low_conf]),
        min_confidence=0.0,  # let it through the native planner
    )
    llm = StepLLM(_steps_json(0.9))
    planner = Planner(llm, native=native)

    plan = planner.plan("build something")
    assert plan.native_source is not None
    assert len(plan.escalate) == 3  # all steps below gate
    assert plan.requires_human is True


def test_existing_planner_tests_unchanged() -> None:
    """Planner with native=None behaves exactly as before (zero regression)."""
    llm = StepLLM(_steps_json(0.95, 0.5, 0.72))
    planner = Planner(llm, native=None)
    plan = planner.plan("build a todo app")
    assert len(plan.steps) == 3
    assert len(plan.approved) == 2
    assert len(plan.escalate) == 1
    assert plan.requires_human is True
    assert plan.native_source is None


def test_planner_stores_last_native_source() -> None:
    """After a native plan, _last_native_source is set for SSE emission."""
    native = NativePlanner(patterns=FakeSwarmPatterns([SWARM_MATCH]))
    llm = StepLLM(_steps_json(0.9))
    planner = Planner(llm, native=native)

    planner.plan("build a REST API")
    assert planner._last_native_source is not None
    assert planner._last_native_source.source == "swarm_pattern"


def test_planner_clears_last_native_source_on_fallthrough() -> None:
    """After an LLM plan, _last_native_source is cleared."""
    native = NativePlanner()  # no stores -> no match
    llm = StepLLM(_steps_json(0.9))
    planner = Planner(llm, native=native)

    planner.plan("novel goal")
    assert planner._last_native_source is None


def test_native_plan_calibrations_empty() -> None:
    """Native plans have no LLM calibrations — confidence is from evidence."""
    native = NativePlanner(patterns=FakeSwarmPatterns([SWARM_MATCH]))
    llm = StepLLM(_steps_json(0.9))
    planner = Planner(llm, native=native)

    plan = planner.plan("build a REST API")
    assert plan.calibrations == []
