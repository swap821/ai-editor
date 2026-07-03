"""Integration tests for S2 cross-store knowledge graph ingestion hooks.

Verifies that promoting a skill/mistake or recording a verified outcome
actually inserts edges into the knowledge graph, and that the hooks are
fail-soft (exceptions in ingestion never crash the caller).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from aios.memory.db import init_memory_db
from aios.memory.development import DevelopmentTracker
from aios.memory.facts import SemanticFacts
from aios.memory.mistake import MistakeMemory
from aios.memory.skills import SkillMemory
from aios.core.verification_strength import VerificationStrength


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "integration.db"
    init_memory_db(path)
    return path


@pytest.fixture
def facts(db: Path) -> SemanticFacts:
    return SemanticFacts(db)


def _fact_rows(facts: SemanticFacts) -> list[dict]:
    """Read all active facts from the store."""
    from aios.memory.db import get_connection

    with get_connection(facts.db_path) as conn:
        rows = conn.execute(
            "SELECT subject, predicate, object, confidence "
            "FROM semantic_facts WHERE status = 'active'"
        ).fetchall()
    return [dict(r) for r in rows]


class TestSkillIngestion:
    def test_ingestion_hook_fires_on_skill_promotion(self, db: Path, facts: SemanticFacts) -> None:
        skills = SkillMemory(db, min_successes=3, min_success_rate=0.8, facts=facts)
        steps = ["read_file: src/main.py", "execute_terminal: pytest tests/"]
        for _ in range(3):
            skills.record_attempt("Fix bug in src/main.py", steps, success=True)
        rows = _fact_rows(facts)
        assert len(rows) > 0, "promotion should ingest edges"
        subjects = {r["subject"] for r in rows}
        predicates = {r["predicate"] for r in rows}
        assert subjects, "at least one entity extracted"
        assert predicates & {"read_in_workflow", "verified_by", "associated_with"}

    def test_candidate_skill_produces_no_edges(self, db: Path, facts: SemanticFacts) -> None:
        skills = SkillMemory(db, min_successes=3, min_success_rate=0.8, facts=facts)
        steps = ["read_file: src/app.py"]
        skills.record_attempt("Deploy app", steps, success=True)
        rows = _fact_rows(facts)
        assert len(rows) == 0, "candidate (1 success < 3 min) must not ingest"


class TestMistakeIngestion:
    def test_ingestion_hook_fires_on_mistake_promotion(self, db: Path, facts: SemanticFacts) -> None:
        mistakes = MistakeMemory(db, facts=facts)
        mid = mistakes.record(
            "task-1", "TypeError", "missing null check in 'parser.py'",
            "added guard clause", "always validate input before parsing", -0.2,
        )
        mistakes.promote(mid, strength=VerificationStrength.STRONG)
        rows = _fact_rows(facts)
        assert len(rows) > 0, "verified mistake should ingest edges"
        assert any(r["predicate"] == "caused_by" for r in rows)
        assert all(0 < r["confidence"] <= 1.0 for r in rows)

    def test_pending_mistake_produces_no_edges(self, db: Path, facts: SemanticFacts) -> None:
        mistakes = MistakeMemory(db, facts=facts)
        mistakes.record(
            "task-2", "KeyError", "missing key", "added default", "check keys", -0.1,
        )
        rows = _fact_rows(facts)
        assert len(rows) == 0, "unverified mistake must not ingest"


class TestOutcomeIngestion:
    def test_ingestion_hook_fires_on_outcome_record(self, db: Path, facts: SemanticFacts) -> None:
        tracker = DevelopmentTracker(db, facts=facts)
        tracker.record("Deploy 'auth-service.py' to staging", "verified_success", tool_calls=5)
        rows = _fact_rows(facts)
        assert len(rows) > 0, "verified_success should ingest edges"
        assert any(r["predicate"] == "has_verified_success" for r in rows)

    def test_unverified_outcome_produces_no_edges(self, db: Path, facts: SemanticFacts) -> None:
        tracker = DevelopmentTracker(db, facts=facts)
        tracker.record("Run linter on utils.py", "unverified", tool_calls=1)
        rows = _fact_rows(facts)
        assert len(rows) == 0, "unverified outcome must not ingest"


class TestFailSoft:
    def test_skill_ingestion_is_fail_soft(self, db: Path, facts: SemanticFacts) -> None:
        skills = SkillMemory(db, min_successes=1, min_success_rate=0.0, facts=facts)
        with patch.object(facts, "add_fact", side_effect=RuntimeError("boom")):
            skill_id = skills.record_attempt(
                "Fix 'routes.py'", ["read_file: routes.py"], success=True,
            )
        assert isinstance(skill_id, int), "record_attempt must succeed despite ingestion failure"

    def test_mistake_ingestion_is_fail_soft(self, db: Path, facts: SemanticFacts) -> None:
        mistakes = MistakeMemory(db, facts=facts)
        mid = mistakes.record(
            "task-3", "ImportError", "wrong module in 'cli.py'",
            "fixed import", "verify imports", -0.1,
        )
        with patch.object(facts, "add_fact", side_effect=RuntimeError("boom")):
            mistakes.promote(mid, strength=VerificationStrength.STRONG)
        row = mistakes.get(mid)
        assert row["verification_status"] == "verified", "promote must succeed despite ingestion failure"

    def test_outcome_ingestion_is_fail_soft(self, db: Path, facts: SemanticFacts) -> None:
        tracker = DevelopmentTracker(db, facts=facts)
        with patch.object(facts, "add_fact", side_effect=RuntimeError("boom")):
            row_id = tracker.record("Fix 'api.py' endpoint", "verified_success", tool_calls=2)
        assert isinstance(row_id, int), "record must succeed despite ingestion failure"


class TestConfidenceRoundtrip:
    def test_confidence_survives_roundtrip(self, facts: SemanticFacts) -> None:
        facts.add_fact("error", "caused_by", "null_check", confidence=0.8)
        edges = facts.traverse_weighted("error", max_depth=1)
        assert len(edges) == 1
        assert edges[0].confidence == pytest.approx(0.8)
