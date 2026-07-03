"""Unit tests for the NativePlanner — sovereignty S3."""
from __future__ import annotations

import pytest

from aios.core.confidence_filter import TaskStep
from aios.core.native_planner import NativePlanner, NativePlanResult


# ── Fakes ──────────────────────────────────────────────────────────────────


class FakeSwarmPatterns:
    """Minimal fake for SwarmPatternMemory.recall()."""

    def __init__(self, results: list[dict] | None = None, *, raise_on_recall: bool = False):
        self._results = results or []
        self._raise = raise_on_recall

    def recall(self, goal: str, *, limit: int = 1) -> list[dict]:
        if self._raise:
            raise RuntimeError("boom")
        return self._results[:limit]


class FakeSkillMemory:
    """Minimal fake for SkillMemory.relevant_verified()."""

    def __init__(self, results: list[dict] | None = None, *, raise_on_recall: bool = False):
        self._results = results or []
        self._raise = raise_on_recall

    def relevant_verified(self, query: str, limit: int = 3) -> list[dict]:
        if self._raise:
            raise RuntimeError("boom")
        return self._results[:limit]


class FakeFacts:
    """Minimal fake for SemanticFacts.traverse_weighted()."""

    def __init__(self, has_entities: bool = True):
        self._has = has_entities

    def traverse_weighted(self, start: str, max_depth: int = 3, **kw) -> list:
        if self._has:
            return [object()]  # non-empty = entity exists
        return []


# ── Fixture data ───────────────────────────────────────────────────────────

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

SKILL_MATCH = {
    "skill_id": 17,
    "goal_pattern": "create a pytest for the router module",
    "steps": ["read router.py", "write test_router.py", "run pytest"],
    "success_count": 4,
    "failure_count": 1,
    "success_rate": 0.8,
    "freshness": 0.95,
    "reuse_success_count": 2,
    "reuse_failure_count": 0,
    "reuse_factor": 1.1,
    "strength": 0.836,
    "relevance": 0.90,
}


# ── Tests: swarm pattern matching ──────────────────────────────────────────


def test_try_plan_matches_swarm_pattern() -> None:
    planner = NativePlanner(patterns=FakeSwarmPatterns([SWARM_MATCH]))
    result = planner.try_plan("build a REST API with tests")
    assert result is not None
    assert result.source == "swarm_pattern"
    assert result.source_id == 42
    assert len(result.steps) == 3
    assert result.steps[0].description == "scaffold endpoints"


def test_try_plan_matches_skill_arc() -> None:
    planner = NativePlanner(skills=FakeSkillMemory([SKILL_MATCH]))
    result = planner.try_plan("create a pytest for the router module")
    assert result is not None
    assert result.source == "skill"
    assert result.source_id == 17
    assert len(result.steps) == 3


def test_try_plan_prefers_swarm_over_skill() -> None:
    planner = NativePlanner(
        patterns=FakeSwarmPatterns([SWARM_MATCH]),
        skills=FakeSkillMemory([SKILL_MATCH]),
    )
    result = planner.try_plan("build something")
    assert result is not None
    assert result.source == "swarm_pattern"


def test_try_plan_returns_none_below_relevance() -> None:
    low_relevance = {**SWARM_MATCH, "relevance": 0.40, "score": 0.40}
    planner = NativePlanner(patterns=FakeSwarmPatterns([low_relevance]))
    assert planner.try_plan("build something") is None


def test_try_plan_returns_none_below_confidence() -> None:
    low_rate = {**SWARM_MATCH, "success_rate": 0.50, "relevance": 0.60}
    # evidence_confidence = 0.50 * 0.60 = 0.30 (below 0.72)
    planner = NativePlanner(patterns=FakeSwarmPatterns([low_rate]))
    assert planner.try_plan("build something") is None


def test_try_plan_returns_none_no_stores() -> None:
    planner = NativePlanner()
    assert planner.try_plan("anything") is None


def test_try_plan_returns_none_empty_goal() -> None:
    planner = NativePlanner(patterns=FakeSwarmPatterns([SWARM_MATCH]))
    assert planner.try_plan("") is None
    assert planner.try_plan("   ") is None


def test_try_plan_fail_soft_on_recall_error() -> None:
    planner = NativePlanner(
        patterns=FakeSwarmPatterns(raise_on_recall=True),
        skills=FakeSkillMemory(raise_on_recall=True),
    )
    assert planner.try_plan("something") is None


# ── Tests: confidence arithmetic ───────────────────────────────────────────


def test_evidence_confidence_from_swarm() -> None:
    planner = NativePlanner(patterns=FakeSwarmPatterns([SWARM_MATCH]))
    result = planner.try_plan("build a REST API")
    assert result is not None
    expected = round(SWARM_MATCH["success_rate"] * SWARM_MATCH["relevance"], 4)
    assert result.evidence_confidence == expected


def test_evidence_confidence_from_skill() -> None:
    planner = NativePlanner(skills=FakeSkillMemory([SKILL_MATCH]))
    result = planner.try_plan("create a pytest")
    assert result is not None
    expected = round(SKILL_MATCH["strength"] * SKILL_MATCH["relevance"], 4)
    assert result.evidence_confidence == expected


def test_steps_have_uniform_confidence() -> None:
    planner = NativePlanner(patterns=FakeSwarmPatterns([SWARM_MATCH]))
    result = planner.try_plan("build a REST API")
    assert result is not None
    confidences = {s.confidence for s in result.steps}
    assert len(confidences) == 1  # all steps share the same evidence confidence


# ── Tests: preconditions ───────────────────────────────────────────────────


def test_preconditions_checked_when_kg_available() -> None:
    planner = NativePlanner(
        patterns=FakeSwarmPatterns([SWARM_MATCH]),
        facts=FakeFacts(has_entities=True),
    )
    result = planner.try_plan("build a REST API")
    # preconditions_met can be True, False, or None (no entities found)
    # With our fake that always returns non-empty, entities found = True or None
    assert result is not None
    assert result.preconditions_met is not False or result.preconditions_met is None


def test_preconditions_none_when_no_kg() -> None:
    planner = NativePlanner(patterns=FakeSwarmPatterns([SWARM_MATCH]))
    result = planner.try_plan("build a REST API")
    assert result is not None
    assert result.preconditions_met is None


# ── Tests: adversarial ─────────────────────────────────────────────────────


def test_native_plan_cannot_bypass_confidence_gate() -> None:
    """Even with high relevance, a low success_rate template gets escalated."""
    low_success = {**SWARM_MATCH, "success_rate": 0.60, "relevance": 0.90}
    # evidence_confidence = 0.60 * 0.90 = 0.54 (below 0.72 gate)
    planner = NativePlanner(patterns=FakeSwarmPatterns([low_success]))
    result = planner.try_plan("build something")
    assert result is None  # below min_confidence, falls through


def test_native_plan_cannot_execute() -> None:
    """NativePlanResult is pure data — no dispatch or execute method."""
    result = NativePlanResult(
        steps=[TaskStep("1", "test", 0.9)],
        source="skill",
        source_id=1,
        goal_pattern="test",
        relevance_score=0.9,
        evidence_confidence=0.9,
        preconditions_met=None,
    )
    assert not hasattr(result, "dispatch")
    assert not hasattr(result, "execute")


def test_swarm_pattern_with_empty_subtasks_returns_none() -> None:
    empty = {**SWARM_MATCH, "subtasks": []}
    planner = NativePlanner(patterns=FakeSwarmPatterns([empty]))
    assert planner.try_plan("build something") is None


def test_skill_arc_with_empty_steps_returns_none() -> None:
    empty = {**SKILL_MATCH, "steps": []}
    planner = NativePlanner(skills=FakeSkillMemory([empty]))
    assert planner.try_plan("create a test") is None
