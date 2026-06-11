"""Behavioral tests for the evidence-gated Brain Growth Loop v1."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pytest

from aios import config
from aios.core.planner import Planner
from aios.memory.consolidation import MemoryConsolidator
from aios.memory.curriculum import CurriculumManager
from aios.memory.db import init_memory_db
from aios.memory.development import DevelopmentTracker, OutcomeEvidence
from aios.memory.facts import SemanticFacts
from aios.memory.mistake import MistakeMemory
from aios.memory.semantic import SemanticMemory
from aios.memory.skills import SkillMemory


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "memory.db"
    init_memory_db(path)
    return path


class PlanningLLM:
    def __init__(self, confidence: float = 0.9) -> None:
        self.confidence = confidence

    def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
        return json.dumps(
            {
                "steps": [
                    {
                        "step_id": "1",
                        "description": "deploy the api safely",
                        "confidence": self.confidence,
                    }
                ]
            }
        )


def test_verified_lessons_recall_cross_session_but_pending_do_not(tmp_path: Path) -> None:
    mistakes = MistakeMemory(_db(tmp_path))
    pending = mistakes.record(
        "old-session", "Timeout", "api deploy timed out", "retry", "set deploy timeout", -0.2
    )
    verified = mistakes.record(
        "other-session", "DeployFailure", "api deploy failed", "rollback", "verify api deploy", -0.3
    )
    mistakes.promote(verified)

    recalled = mistakes.relevant_verified("deploy the api")

    assert [item["mistake_id"] for item in recalled] == [verified]
    assert pending not in [item["mistake_id"] for item in recalled]


def test_planner_calibrates_with_verified_lessons_and_explains_adjustment() -> None:
    class Lessons:
        def relevant_verified(self, query: str, limit: int = 5):
            return [
                {
                    "mistake_id": 9,
                    "confidence_delta": -0.3,
                    "relevance": 1.0,
                }
            ]

    class NoHistory:
        def relevant_success_rate(self, query: str):
            return None

    plan = Planner(
        PlanningLLM(), mistakes=Lessons(), development=NoHistory()
    ).plan("deploy the api")

    assert plan.steps[0].confidence == 0.6
    assert plan.requires_human is True
    assert plan.calibrations[0].lesson_ids == [9]
    assert plan.calibrations[0].raw_confidence == 0.9


def test_planner_uses_verified_historical_outcomes_only() -> None:
    class NoLessons:
        def relevant_verified(self, query: str, limit: int = 5):
            return []

    class StrongHistory:
        def relevant_success_rate(self, query: str):
            return OutcomeEvidence(attempts=5, success_rate=1.0, relevance=1.0)

    plan = Planner(
        PlanningLLM(0.7), mistakes=NoLessons(), development=StrongHistory()
    ).plan("deploy the api")

    assert plan.steps[0].confidence == 0.85
    assert plan.requires_human is False
    assert plan.calibrations[0].outcome_attempts == 5


def test_planner_scales_historical_adjustment_by_relevance() -> None:
    class NoLessons:
        def relevant_verified(self, query: str, limit: int = 5):
            return []

    class WeakHistory:
        def relevant_success_rate(self, query: str):
            return OutcomeEvidence(attempts=5, success_rate=1.0, relevance=0.2)

    plan = Planner(
        PlanningLLM(0.7), mistakes=NoLessons(), development=WeakHistory()
    ).plan("deploy the api")

    assert plan.steps[0].confidence == 0.73
    assert plan.calibrations[0].history_adjustment == 0.03


def test_semantic_memory_consolidates_exact_duplicates_without_new_vector(
    tmp_path: Path,
) -> None:
    path = _db(tmp_path)

    class Embedder:
        def encode(self, text: str):
            return [[0.0, 1.0]]

    class Index:
        path = tmp_path / "index.faiss"

        def __init__(self) -> None:
            self.added: list[int] = []

        def reload(self) -> None:
            pass

        def add(self, vector_id: int, vector) -> None:
            self.added.append(vector_id)

        def persist(self) -> None:
            pass

    index = Index()
    memory = SemanticMemory(path, index=index, embedder=Embedder())
    first = memory.add("  Same   Knowledge ")
    second = memory.add("same knowledge")

    assert second == first
    assert memory.count() == 1
    assert index.added == [first]
    assert memory.get(first)["occurrence_count"] == 2
    assert memory.get(first)["verification_status"] == "unverified"
    memory.add("same knowledge", count_occurrence=False)
    assert memory.get(first)["occurrence_count"] == 2


def test_semantic_memory_refuses_empty_content(tmp_path: Path) -> None:
    path = _db(tmp_path)
    memory = SemanticMemory(path, index=object(), embedder=object())

    with pytest.raises(ValueError, match="non-empty"):
        memory.add("   ")


def test_consolidator_promotes_only_verified_lessons_and_approved_facts(
    tmp_path: Path,
) -> None:
    path = _db(tmp_path)
    mistakes = MistakeMemory(path)
    facts = SemanticFacts(path)

    class SemanticRecorder:
        def __init__(self) -> None:
            self.rows: list[tuple[str, str, str]] = []
            self.superseded: list[str] = []

        def add(
            self,
            text: str,
            *,
            memory_type: str,
            verification_status: str,
            count_occurrence: bool = True,
        ) -> int:
            self.rows.append((text, memory_type, verification_status))
            return len(self.rows)

        def supersede_text(self, text: str) -> int:
            self.superseded.append(text)
            return 1

        def promote(self, mem_id: int) -> None:
            pass

    semantic = SemanticRecorder()
    consolidator = MemoryConsolidator(
        path, semantic=semantic, mistakes=mistakes, facts=facts
    )
    lesson_id = mistakes.record("t", "Timeout", "slow", "retry", "set timeout", -0.2)

    assert consolidator.consolidate_lesson(lesson_id) is None
    mistakes.promote(lesson_id)
    assert consolidator.consolidate_lesson(lesson_id) == 1

    facts.add_fact("service", "port", "7000")
    promoted = consolidator.promote_fact(
        "service", "host", "localhost", approved_by="operator"
    )
    assert promoted.committed is True
    result = consolidator.run()
    assert result["active_facts_consolidated"] == 1
    assert all(row[2] == "verified" for row in semantic.rows)

    conflict = consolidator.promote_fact(
        "service", "host", "remote", approved_by="operator"
    )
    assert conflict.reason == "contradiction"
    reconciled = consolidator.reconcile_fact(
        "service", "host", "remote", approved_by="operator"
    )
    assert reconciled.reason == "reconciled"
    assert any("localhost" in text for text in semantic.superseded)
    assert facts.facts_for("service", "host")[0]["object"] == "remote"


def test_development_tracker_counts_only_verified_outcomes_for_calibration(
    tmp_path: Path,
) -> None:
    tracker = DevelopmentTracker(_db(tmp_path))
    tracker.record("deploy api", "verified_success", tool_calls=2)
    tracker.record("deploy api", "verified_failure", blocked_actions=1)
    tracker.record("deploy api", "verified_success", human_interventions=1)
    tracker.record("deploy api", "unverified")

    evidence = tracker.relevant_success_rate("deploy api")
    summary = tracker.summary()

    assert evidence is not None
    assert evidence.attempts == 3
    assert evidence.success_rate == pytest.approx(2 / 3, abs=1e-6)
    assert summary["verification_coverage"] == 0.75
    assert summary["verified_success_rate"] == pytest.approx(2 / 3, abs=1e-6)


def test_skill_memory_promotes_after_repeated_verified_success_and_regresses(
    tmp_path: Path,
) -> None:
    skills = SkillMemory(_db(tmp_path))
    steps = ["read_file", "edit_file", "verify"]
    for _ in range(3):
        skills.record_attempt("fix parser bug", steps, success=True)

    recalled = skills.relevant_verified("fix parser bug")
    assert recalled and recalled[0]["success_count"] == 3

    skills.record_attempt("fix parser bug", steps, success=False)
    assert skills.relevant_verified("fix parser bug") == []
    assert skills.list()[0]["status"] == "candidate"


def test_skill_trail_evaporates_with_disuse(tmp_path: Path) -> None:
    skills = SkillMemory(_db(tmp_path))
    steps = ["read_file", "edit_file", "verify"]
    for _ in range(3):
        skills.record_attempt("fix parser bug", steps, success=True)

    fresh = skills.relevant_verified("fix parser bug")
    assert fresh and fresh[0]["freshness"] >= 0.99
    assert fresh[0]["strength"] == pytest.approx(fresh[0]["success_rate"], abs=1e-2)

    last_used = datetime.fromisoformat(skills.list()[0]["updated_at"])
    stale = skills.relevant_verified(
        "fix parser bug", now=last_used + timedelta(hours=2000)
    )
    # Disuse evaporates the trail's pull but never deletes the verified skill.
    assert stale and stale[0]["freshness"] < 0.05
    assert stale[0]["strength"] < stale[0]["success_rate"]
    assert stale[0]["skill_id"] == fresh[0]["skill_id"]


def test_planner_rewards_matching_verified_skill() -> None:
    class NoLessons:
        def relevant_verified(self, query: str, limit: int = 5):
            return []

    class NoHistory:
        def relevant_success_rate(self, query: str):
            return None

    class TrustedTrail:
        def relevant_verified(self, query: str, limit: int = 3):
            return [{"skill_id": 4, "strength": 0.9, "relevance": 1.0}]

    plan = Planner(
        PlanningLLM(0.6),
        mistakes=NoLessons(),
        development=NoHistory(),
        skills=TrustedTrail(),
    ).plan("deploy the api")

    # 0.6 raw + min(0.2, 0.9 * 1.0) -> 0.8, lifting the step over the gate.
    assert plan.calibrations[0].skill_ids == [4]
    assert plan.calibrations[0].skill_adjustment == pytest.approx(0.2, abs=1e-6)
    assert plan.steps[0].confidence == pytest.approx(0.8, abs=1e-6)
    assert plan.requires_human is False


def test_planner_skill_reward_is_bounded() -> None:
    class NoLessons:
        def relevant_verified(self, query: str, limit: int = 5):
            return []

    class NoHistory:
        def relevant_success_rate(self, query: str):
            return None

    class ManyStrongTrails:
        def relevant_verified(self, query: str, limit: int = 3):
            return [
                {"skill_id": 1, "strength": 1.0, "relevance": 1.0},
                {"skill_id": 2, "strength": 1.0, "relevance": 1.0},
            ]

    plan = Planner(
        PlanningLLM(0.7),
        mistakes=NoLessons(),
        development=NoHistory(),
        skills=ManyStrongTrails(),
    ).plan("deploy the api")

    # sum(strength * relevance) = 2.0, capped at SKILL_CONFIDENCE_BONUS_MAX.
    assert plan.calibrations[0].skill_adjustment == pytest.approx(
        config.SKILL_CONFIDENCE_BONUS_MAX, abs=1e-6
    )
    assert plan.steps[0].confidence == pytest.approx(0.9, abs=1e-6)


def test_curriculum_requires_training_and_held_out_verifier_evidence(
    tmp_path: Path,
) -> None:
    curriculum = CurriculumManager(_db(tmp_path), training_passes_required=2)
    curriculum.add_task("python", 1, "training task")
    curriculum.add_task("python", 1, "held out task", held_out=True)
    next_id = curriculum.add_task("python", 2, "advanced task")

    curriculum.record_matching(
        "training task", passed=True, evidence="[VERIFY PASS] 1 passed"
    )
    curriculum.record_matching(
        "training task", passed=True, evidence="[VERIFY PASS] 1 passed"
    )
    assert next(item for item in curriculum.list() if item["id"] == next_id)["status"] == "locked"

    curriculum.record_matching(
        "held out task", passed=True, evidence="[VERIFY PASS] 1 passed"
    )
    rows = curriculum.list()
    assert all(item["status"] == "mastered" for item in rows if item["level"] == 1)
    assert next(item for item in rows if item["id"] == next_id)["status"] == "available"


def test_curriculum_locks_missing_prerequisites_and_refuses_ambiguous_evidence(
    tmp_path: Path,
) -> None:
    curriculum = CurriculumManager(_db(tmp_path))
    advanced = curriculum.add_task("python", 2, "advanced first")
    assert curriculum.list()[0]["status"] == "locked"
    assert curriculum.add_task("python", 2, "advanced first") == advanced

    curriculum.add_task("python", 1, "shared prompt")
    curriculum.add_task("javascript", 1, "shared prompt")
    with pytest.raises(ValueError, match="ambiguous"):
        curriculum.record_matching(
            "shared prompt", passed=True, evidence="[VERIFY PASS] 1 passed"
        )


def test_curriculum_requires_coverage_of_every_defined_task(tmp_path: Path) -> None:
    curriculum = CurriculumManager(_db(tmp_path), training_passes_required=2)
    curriculum.add_task("python", 1, "training one")
    curriculum.add_task("python", 1, "training two")
    curriculum.add_task("python", 1, "held out", held_out=True)

    for _ in range(2):
        curriculum.record_matching(
            "training one", passed=True, evidence="[VERIFY PASS] 1 passed"
        )
    curriculum.record_matching(
        "held out", passed=True, evidence="[VERIFY PASS] 1 passed"
    )
    assert any(item["status"] == "available" for item in curriculum.list())

    curriculum.record_matching(
        "training two", passed=True, evidence="[VERIFY PASS] 1 passed"
    )
    assert all(item["status"] == "mastered" for item in curriculum.list())
