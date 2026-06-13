"""Behavioral tests for the evidence-gated Brain Growth Loop v1."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pytest

from aios import config
from aios.core.planner import Planner
from aios.memory.consolidation import MemoryConsolidator
from aios.memory.curriculum import CurriculumManager
from aios.memory.db import get_connection, init_memory_db
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


def test_model_task_success_rates_aggregates_by_provider_model_task(
    tmp_path: Path,
) -> None:
    tracker = DevelopmentTracker(_db(tmp_path))
    md = lambda p, m, t: {"provider": p, "model": m, "task": t}  # noqa: E731
    # gemini on reasoning: 2 of 3 verified -> 0.667
    tracker.record("analyze x", "verified_success", metadata=md("gemini", "gemini-2.5-flash", "reasoning"))
    tracker.record("analyze y", "verified_failure", metadata=md("gemini", "gemini-2.5-flash", "reasoning"))
    tracker.record("analyze z", "verified_success", metadata=md("gemini", "gemini-2.5-flash", "reasoning"))
    # local coder on coding: 1 verified attempt -> below min_attempts, excluded
    tracker.record("fix bug", "verified_success", metadata=md("ollama", "qwen2.5-coder:7b", "coding"))
    # unverified outcomes never calibrate
    tracker.record("analyze q", "unverified", metadata=md("gemini", "gemini-2.5-flash", "reasoning"))

    rates = tracker.model_task_success_rates(min_attempts=3)
    assert rates == {("gemini", "gemini-2.5-flash", "reasoning"): pytest.approx(2 / 3, abs=1e-6)}
    # a lower bar surfaces the single-attempt local key too
    low = tracker.model_task_success_rates(min_attempts=1)
    assert low[("ollama", "qwen2.5-coder:7b", "coding")] == 1.0


def test_model_task_success_rates_skips_events_missing_provider(tmp_path: Path) -> None:
    tracker = DevelopmentTracker(_db(tmp_path))
    # legacy events recorded before provider tagging (model+task only) are ignored.
    tracker.record("t", "verified_success", metadata={"model": "m", "task": "coding"})
    tracker.record("t", "verified_success", metadata={"model": "m", "task": "coding"})
    tracker.record("t", "verified_success", metadata={"model": "m", "task": "coding"})
    assert tracker.model_task_success_rates(min_attempts=1) == {}


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


# --------------------------------------------------------------------------- #
# Trail mechanics: reinforcement-on-reuse, negative pheromone, consolidation
# --------------------------------------------------------------------------- #

_OLD_SKILLS_DDL = """
CREATE TABLE procedural_skills (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    signature       TEXT NOT NULL UNIQUE,
    goal_pattern    TEXT NOT NULL,
    steps_json      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'candidate'
                    CHECK (status IN ('candidate','verified','superseded')),
    success_count   INTEGER NOT NULL DEFAULT 0,
    failure_count   INTEGER NOT NULL DEFAULT 0
);
"""


def _old_schema_db(tmp_path: Path) -> Path:
    """A pre-trail-mechanics database, as a live deployment would have it."""
    path = tmp_path / "old.db"
    conn = sqlite3.connect(str(path))
    conn.executescript(_OLD_SKILLS_DDL)
    conn.commit()
    conn.close()
    return path


def _insert_old_skill(
    path: Path,
    signature: str,
    goal: str,
    steps: list[str],
    *,
    status: str,
    successes: int,
    failures: int,
) -> int:
    conn = sqlite3.connect(str(path))
    cur = conn.execute(
        "INSERT INTO procedural_skills "
        "(signature, goal_pattern, steps_json, status, success_count, failure_count) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (signature, goal, json.dumps(steps), status, successes, failures),
    )
    conn.commit()
    row_id = int(cur.lastrowid)
    conn.close()
    return row_id


def _verified_trail(skills: SkillMemory, goal: str, steps: list[str]) -> int:
    for _ in range(3):
        skill_id = skills.record_attempt(goal, steps, success=True)
    return skill_id


def test_reuse_success_reinforces_recalled_trail(tmp_path: Path) -> None:
    skills = SkillMemory(_db(tmp_path))
    steps = ["read_file: a", "edit_file: b", "verify: pytest"]
    for _ in range(4):
        skill_id = skills.record_attempt("fix parser bug", steps, success=True)
    skills.record_attempt("fix parser bug", steps, success=False)  # 4/1, rate 0.8

    baseline = skills.relevant_verified("fix parser bug")[0]
    assert baseline["strength"] == pytest.approx(0.8, abs=1e-2)

    later = datetime.now(timezone.utc) + timedelta(hours=1)
    assert skills.record_reuse([skill_id], success=True, now=later) == [skill_id]
    assert skills.record_reuse([skill_id], success=True, now=later) == [skill_id]

    after = skills.relevant_verified("fix parser bug", now=later)[0]
    assert after["reuse_success_count"] == 2
    assert after["success_count"] == 4 and after["failure_count"] == 1  # direct untouched
    expected = min(1.0, 0.8 * SkillMemory._reuse_factor(2, 0))
    assert after["strength"] == pytest.approx(expected, abs=2e-6)
    assert after["strength"] > baseline["strength"]


def test_reuse_factor_exact_asymmetry() -> None:
    assert SkillMemory._reuse_factor(0, 1) == pytest.approx(0.70805, abs=1e-4)
    assert SkillMemory._reuse_factor(1, 0) == pytest.approx(1.04252, abs=1e-4)
    # One failure bites more than six successes' worth of reward.
    assert (1 - SkillMemory._reuse_factor(0, 1)) > 6 * (SkillMemory._reuse_factor(1, 0) - 1)


def test_reuse_credit_cannot_promote_candidate(tmp_path: Path) -> None:
    skills = SkillMemory(_db(tmp_path))
    steps = ["read_file: a", "verify: pytest"]
    skill_id = skills.record_attempt("tune cache", steps, success=True)
    skills.record_attempt("tune cache", steps, success=True)  # candidate 2/0

    for _ in range(10):
        assert skills.record_reuse([skill_id], success=True) == []

    row = skills.list()[0]
    assert row["status"] == "candidate"
    assert row["success_count"] == 2
    assert row["reuse_success_count"] == 0
    assert skills.relevant_verified("tune cache") == []


def test_reuse_failures_quarantine_verified_trail(tmp_path: Path) -> None:
    skills = SkillMemory(_db(tmp_path))
    skill_id = _verified_trail(skills, "fix parser bug", ["read_file: a", "verify: p"])
    moment = datetime.now(timezone.utc)

    for _ in range(3):
        skills.record_reuse([skill_id], success=False, now=moment)

    row = skills.list()[0]
    assert row["status"] == "candidate"          # quarantined
    assert row["success_count"] == 3 and row["failure_count"] == 0  # direct untouched
    assert row["reuse_failure_count"] == 3
    assert skills.relevant_verified("fix parser bug") == []


def test_direct_success_restores_quarantined_trail(tmp_path: Path) -> None:
    skills = SkillMemory(_db(tmp_path))
    steps = ["read_file: a", "verify: p"]
    skill_id = _verified_trail(skills, "fix parser bug", steps)
    for _ in range(3):
        skills.record_reuse([skill_id], success=False)
    assert skills.list()[0]["status"] == "candidate"

    skills.record_attempt("fix parser bug", steps, success=True)  # fresh DIRECT evidence

    recalled = skills.relevant_verified("fix parser bug")
    assert recalled and recalled[0]["skill_id"] == skill_id
    assert recalled[0]["success_count"] == 4
    assert recalled[0]["reuse_failure_count"] == 3              # the stain persists
    assert recalled[0]["reuse_factor"] == pytest.approx(
        SkillMemory._reuse_factor(0, 3), abs=1e-6
    )


def test_reuse_factor_bounds(monkeypatch) -> None:
    assert SkillMemory._reuse_factor(100, 0) == pytest.approx(1.15, abs=1e-6)
    # Default-constants asymptote is 1 - PENALTY_MAX = 0.40; the floor only
    # binds when env tuning pushes the penalty deeper.
    assert SkillMemory._reuse_factor(0, 100) == pytest.approx(0.40, abs=1e-3)
    monkeypatch.setattr(config, "SKILL_REUSE_PENALTY_MAX", 1.0)
    assert SkillMemory._reuse_factor(0, 100) == pytest.approx(
        config.SKILL_REUSE_FACTOR_FLOOR, abs=1e-6
    )


def test_reuse_success_refreshes_clock_failure_does_not(tmp_path: Path) -> None:
    skills = SkillMemory(_db(tmp_path))
    skill_id = _verified_trail(skills, "fix parser bug", ["read_file: a", "verify: p"])
    created_at = skills.list()[0]["updated_at"]
    far = datetime.fromisoformat(created_at) + timedelta(hours=1000)

    skills.record_reuse([skill_id], success=False, now=far)
    row = skills.list()[0]
    assert row["updated_at"] == created_at                      # keeps evaporating
    assert row["last_reused_at"] == far.strftime("%Y-%m-%d %H:%M:%S")

    skills.record_reuse([skill_id], success=True, now=far)
    assert skills.list()[0]["updated_at"] == far.strftime("%Y-%m-%d %H:%M:%S")


def test_redaction_noise_consolidates_to_one_signature(tmp_path: Path) -> None:
    skills = SkillMemory(_db(tmp_path))
    noisy = [
        "create_file: filepath=<REDACTED:HIGH_ENTROPY:00000000>.py",
        "create_file: filepath=beta.py",
    ]
    clean = [
        "create_file: filepath=alpha.py",
        "create_file: filepath=beta.py",
    ]
    skills.record_attempt("create the shout helper", noisy, success=True)
    skills.record_attempt("create the shout helper", clean, success=True)
    skills.record_attempt("create the shout helper", clean, success=True)

    active = [row for row in skills.list() if row["status"] != "superseded"]
    assert len(active) == 1
    assert active[0]["success_count"] == 3
    assert active[0]["status"] == "verified"
    assert "<REDACTED:" not in active[0]["steps_json"]          # recipe refreshed


def test_different_length_arcs_stay_distinct(tmp_path: Path) -> None:
    skills = SkillMemory(_db(tmp_path))
    clean_arc = ["create_file: a", "create_file: b"]
    flail_arc = clean_arc + ["edit_file: c", "edit_file: c", "edit_file: c"]
    verified_id = _verified_trail(skills, "create the shout helper", clean_arc)
    skills.record_attempt("create the shout helper", flail_arc, success=False)

    rows = {row["id"]: row for row in skills.list()}
    assert len(rows) == 2                                       # arcs stay distinct
    assert rows[verified_id]["status"] == "verified"
    assert rows[verified_id]["success_count"] == 3
    assert rows[verified_id]["failure_count"] == 0              # failure never bleeds over


def test_migration_backfills_live_shape_as_noop(tmp_path: Path) -> None:
    path = _old_schema_db(tmp_path)
    _insert_old_skill(path, "s1", "create the shout helper",
                      ["create_file: a", "create_file: b"],
                      status="verified", successes=3, failures=0)
    _insert_old_skill(path, "s2", "create the shout helper",
                      ["create_file: a", "create_file: b", "edit_file: c"],
                      status="candidate", successes=0, failures=1)
    _insert_old_skill(path, "s3", "create the clamp helper",
                      ["create_file: a", "create_file: b"],
                      status="candidate", successes=1, failures=0)

    init_memory_db(path)

    with get_connection(path) as conn:
        rows = conn.execute("SELECT * FROM procedural_skills ORDER BY id").fetchall()
    assert all(row["signature_v2"] for row in rows)             # backfilled
    assert [row["status"] for row in rows] == ["verified", "candidate", "candidate"]
    assert [(row["success_count"], row["failure_count"]) for row in rows] == [
        (3, 0), (0, 1), (1, 0)
    ]                                                            # byte-identical counts
    assert all(row["superseded_by"] is None for row in rows)     # zero merges

    init_memory_db(path)                                         # idempotent
    with get_connection(path) as conn:
        again = conn.execute("SELECT * FROM procedural_skills ORDER BY id").fetchall()
    assert [dict(row) for row in again] == [dict(row) for row in rows]


def test_migration_merges_true_duplicates_preserving_rows(tmp_path: Path) -> None:
    path = _old_schema_db(tmp_path)
    keeper_id = _insert_old_skill(path, "s1", "create the shout helper",
                                  ["create_file: noisy-arg", "create_file: b"],
                                  status="candidate", successes=2, failures=0)
    dupe_id = _insert_old_skill(path, "s2", "create the shout helper",
                                ["create_file: clean-arg", "create_file: b"],
                                status="candidate", successes=1, failures=0)
    other_id = _insert_old_skill(path, "s3", "create the clamp helper",
                                 ["create_file: a", "create_file: b"],
                                 status="verified", successes=3, failures=0)

    init_memory_db(path)

    with get_connection(path) as conn:
        rows = {int(r["id"]): dict(r) for r in conn.execute(
            "SELECT * FROM procedural_skills"
        ).fetchall()}
    assert len(rows) == 3                                        # nothing deleted
    assert rows[keeper_id]["status"] == "verified"               # 3/0 direct sums
    assert rows[keeper_id]["success_count"] == 3
    assert rows[dupe_id]["status"] == "superseded"
    assert rows[dupe_id]["superseded_by"] == keeper_id
    assert rows[dupe_id]["success_count"] == 1                   # provenance intact
    assert rows[other_id]["status"] == "verified"                # untouched


def test_migration_prefers_verified_keeper(tmp_path: Path) -> None:
    path = _old_schema_db(tmp_path)
    fragment_id = _insert_old_skill(path, "s1", "create the shout helper",
                                    ["create_file: x", "create_file: y"],
                                    status="candidate", successes=0, failures=2)
    verified_id = _insert_old_skill(path, "s2", "create the shout helper",
                                    ["create_file: p", "create_file: q"],
                                    status="verified", successes=3, failures=0)

    init_memory_db(path)

    with get_connection(path) as conn:
        rows = {int(r["id"]): dict(r) for r in conn.execute(
            "SELECT * FROM procedural_skills"
        ).fetchall()}
    assert rows[verified_id]["superseded_by"] is None            # verified row is keeper
    assert rows[fragment_id]["status"] == "superseded"
    assert rows[fragment_id]["superseded_by"] == verified_id
    # Absorbing the sibling's failures recomputes honestly: 3/2 -> candidate.
    assert rows[verified_id]["success_count"] == 3
    assert rows[verified_id]["failure_count"] == 2
    assert rows[verified_id]["status"] == "candidate"


def test_record_reuse_skips_superseded_ids(tmp_path: Path) -> None:
    skills = SkillMemory(_db(tmp_path))
    skill_id = _verified_trail(skills, "fix parser bug", ["read_file: a", "verify: p"])
    with get_connection(skills.db_path) as conn:
        conn.execute(
            "UPDATE procedural_skills SET status = 'superseded' WHERE id = ?",
            (skill_id,),
        )

    assert skills.record_reuse([skill_id], success=True) == []
    row = skills.list()[0]
    assert row["reuse_success_count"] == 0 and row["status"] == "superseded"


def test_weakened_trail_outcompeted_not_deleted(tmp_path: Path) -> None:
    skills = SkillMemory(_db(tmp_path))
    stained = _verified_trail(skills, "fix parser bug alpha", ["read_file: a", "verify: p"])
    _verified_trail(skills, "fix parser bug beta", ["edit_file: b", "verify: p"])

    moment = datetime.now(timezone.utc)
    skills.record_reuse([stained], success=False, now=moment)
    skills.record_reuse([stained], success=False, now=moment)   # net 2: below quarantine

    recalled = skills.relevant_verified("fix parser bug", now=moment)
    assert len(recalled) == 2                                    # still recallable
    assert recalled[-1]["skill_id"] == stained                   # but ranks last
    assert recalled[-1]["reuse_factor"] == pytest.approx(
        SkillMemory._reuse_factor(0, 2), abs=1e-6
    )
    assert len(skills.list()) == 2                               # never deleted


def test_trail_map_reports_computed_field_and_quarantine(tmp_path: Path) -> None:
    skills = SkillMemory(_db(tmp_path))
    healthy = _verified_trail(skills, "fix parser bug", ["read_file: a", "verify: p"])
    quarantined = _verified_trail(skills, "tune the cache", ["edit_file: b", "verify: p"])
    moment = datetime.now(timezone.utc)
    skills.record_reuse([healthy], success=True, now=moment)
    for _ in range(3):
        skills.record_reuse([quarantined], success=False, now=moment)

    trail_map = skills.trail_map(now=moment)

    by_id = {t["skill_id"]: t for t in trail_map["trails"]}
    assert by_id[healthy]["status"] == "verified"
    assert by_id[healthy]["quarantined"] is False
    assert by_id[healthy]["strength"] == pytest.approx(
        min(1.0, 1.0 * by_id[healthy]["freshness"] * SkillMemory._reuse_factor(1, 0)),
        abs=2e-6,
    )
    assert by_id[quarantined]["status"] == "candidate"
    assert by_id[quarantined]["quarantined"] is True        # demoted by reuse, not evidence
    assert trail_map["summary"]["quarantined"] == 1
    assert trail_map["summary"]["verified"] == 1
    assert trail_map["constants"]["reuse_demote_net_failures"] == (
        config.SKILL_REUSE_DEMOTE_NET_FAILURES
    )
    # Strength-sorted: the healthy reinforced trail ranks first.
    assert trail_map["trails"][0]["skill_id"] == healthy


def test_trail_map_lists_superseded_fragments_with_lineage(tmp_path: Path) -> None:
    path = _old_schema_db(tmp_path)
    keeper = _insert_old_skill(path, "s1", "create the shout helper",
                               ["create_file: noisy", "create_file: b"],
                               status="candidate", successes=2, failures=0)
    dupe = _insert_old_skill(path, "s2", "create the shout helper",
                             ["create_file: clean", "create_file: b"],
                             status="candidate", successes=1, failures=0)
    init_memory_db(path)

    trail_map = SkillMemory(path).trail_map()

    assert [t["skill_id"] for t in trail_map["trails"]] == [keeper]
    assert trail_map["superseded_fragments"] == [{
        "skill_id": dupe,
        "goal_pattern": "create the shout helper",
        "superseded_by": keeper,
        "success_count": 1,
        "failure_count": 0,
    }]
