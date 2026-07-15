"""Native symbolic planner — plans known task shapes without an LLM.

A composition layer over SkillMemory (single-task templates) and
SwarmPatternMemory (multi-task decompositions). The NativePlanner
checks these stores BEFORE the LLM planner. A match produces a
deterministic plan with evidence-derived confidence (not LLM-reported).
A miss falls through to the LLM planner — no degradation.

The native planner never executes anything. It produces the same
Plan/TaskStep structures the LLM planner produces, so the downstream
pipeline (confidence gate, tool agent, security gateway) treats native
and LLM plans identically. The difference is the source of the plan
and the source of the confidence — verified evidence vs. LLM guess.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from aios import config
from aios.core.confidence_filter import TaskStep

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NativePlanResult:
    """A plan produced from verified experience, not an LLM.

    ``source`` identifies which store produced the plan:
    - "skill" — a single verified skill arc (SkillMemory)
    - "swarm_pattern" — a verified multi-task decomposition (SwarmPatternMemory)

    ``evidence_confidence`` is derived entirely from verification history
    (success rate, freshness, relevance) — never from an LLM's self-report.
    """

    steps: list[TaskStep]
    source: str
    source_id: int
    goal_pattern: str
    relevance_score: float
    evidence_confidence: float
    preconditions_met: bool | None


MIN_RELEVANCE: float = 0.55

MIN_EVIDENCE_CONFIDENCE: float = config.CONFIDENCE_THRESHOLD


class NativePlanner:
    """Plans known task shapes from verified experience without an LLM.

    Injected into the existing Planner (optional, default None). When
    present, Planner.plan() checks the NativePlanner FIRST. A match
    returns a Plan with evidence-derived confidence. A miss falls
    through to the LLM decomposition.

    The NativePlanner NEVER:
    - Calls an LLM
    - Executes any action
    - Bypasses the confidence gate
    - Creates or modifies any store entry
    """

    def __init__(
        self,
        *,
        skills: Optional[Any] = None,
        patterns: Optional[Any] = None,
        facts: Optional[Any] = None,
        min_relevance: float = MIN_RELEVANCE,
        min_confidence: float = MIN_EVIDENCE_CONFIDENCE,
        memory_authority: Optional[Any] = None,
    ) -> None:
        self._skills = skills
        self._patterns = patterns
        self._facts = facts
        self.min_relevance = min_relevance
        self.min_confidence = min_confidence
        self.memory_authority = memory_authority

    def try_plan(self, goal: str) -> NativePlanResult | None:
        """Attempt to plan *goal* from verified experience.

        Returns NativePlanResult with TaskStep list, or None (fall through to LLM).
        """
        if not goal or not goal.strip():
            return None
        goal = goal.strip()

        result = self._try_swarm_patterns(goal)
        if result is not None:
            return result

        result = self._try_skill_arcs(goal)
        if result is not None:
            return result

        return None

    def _try_swarm_patterns(self, goal: str) -> NativePlanResult | None:
        """Match against SwarmPatternMemory verified decompositions."""
        if self._patterns is None:
            return None
        try:
            matches = self._patterns.recall(goal, limit=1)
        except Exception:
            logger.warning("swarm pattern recall failed", exc_info=True)
            return None
        if not matches:
            return None

        match = matches[0]
        if match["relevance"] < self.min_relevance:
            return None

        subtasks: list[str] = match.get("subtasks", [])
        if not subtasks:
            return None

        evidence_conf = round(match["success_rate"] * match["relevance"], 4)
        if evidence_conf < self.min_confidence:
            return None

        steps = [
            TaskStep(
                step_id=str(i + 1),
                description=desc,
                confidence=evidence_conf,
            )
            for i, desc in enumerate(subtasks)
        ]

        preconditions = self._check_preconditions(subtasks)

        return NativePlanResult(
            steps=steps,
            source="swarm_pattern",
            source_id=match["pattern_id"],
            goal_pattern=match["goal_pattern"],
            relevance_score=match["relevance"],
            evidence_confidence=evidence_conf,
            preconditions_met=preconditions,
        )

    def _try_skill_arcs(self, goal: str) -> NativePlanResult | None:
        """Match against SkillMemory verified single-task arcs."""
        if self._skills is None:
            return None
        try:
            matches = (
                self.memory_authority.recall_skills(goal, 1)
                if self.memory_authority is not None
                and self.memory_authority.owns_store("skills", self._skills)
                else self._skills.relevant_verified(goal, limit=1)
            )
        except Exception:
            logger.warning("skill recall failed", exc_info=True)
            return None
        if not matches:
            return None

        match = matches[0]
        if match["relevance"] < self.min_relevance:
            return None

        arc_steps: list[str] = match.get("steps", [])
        if not arc_steps:
            return None

        evidence_conf = round(match["strength"] * match["relevance"], 4)
        if evidence_conf < self.min_confidence:
            return None

        steps = [
            TaskStep(
                step_id=str(i + 1),
                description=desc,
                confidence=evidence_conf,
            )
            for i, desc in enumerate(arc_steps)
        ]

        preconditions = self._check_preconditions(arc_steps)

        return NativePlanResult(
            steps=steps,
            source="skill",
            source_id=match["skill_id"],
            goal_pattern=match["goal_pattern"],
            relevance_score=match["relevance"],
            evidence_confidence=evidence_conf,
            preconditions_met=preconditions,
        )

    def _check_preconditions(self, steps: list[str]) -> bool | None:
        """Check whether entities referenced in steps exist in the knowledge graph."""
        if self._facts is None:
            return None
        try:
            from aios.core.graph_ingestion import find_entities

            all_entities: list[str] = []
            for step in steps:
                all_entities.extend(find_entities(step))
            if not all_entities:
                return None

            for entity in all_entities[:5]:
                edges = (
                    self.memory_authority.facts_traverse_weighted(entity, max_depth=1)
                    if self.memory_authority is not None
                    and self.memory_authority.owns_store("facts", self._facts)
                    else self._facts.traverse_weighted(entity, max_depth=1)
                )
                if not edges:
                    return False
            return True
        except Exception:
            logger.warning("precondition check failed", exc_info=True)
            return None
