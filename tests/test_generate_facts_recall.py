"""Tests that the agentic forge recalls semantic facts into memory_context."""
from pathlib import Path

import pytest

from aios.api.main import _recall_facts
from aios.memory.facts import SemanticFacts
from aios.memory.db import init_memory_db


@pytest.fixture
def facts(tmp_path: Path) -> SemanticFacts:
    db = tmp_path / "facts.db"
    init_memory_db(db)
    return SemanticFacts(db)


def test_recall_facts_returns_none_when_no_match(facts: SemanticFacts) -> None:
    facts.add_fact("project", "uses", "FastAPI")
    block = _recall_facts(facts, "tell me about deployments")
    assert block is None


def test_recall_facts_includes_matched_triple(facts: SemanticFacts) -> None:
    facts.add_fact("project", "uses", "FastAPI")
    block = _recall_facts(facts, "how is FastAPI used")
    assert block is not None
    assert "project uses FastAPI" in block


def test_recall_facts_includes_neighbors(facts: SemanticFacts) -> None:
    facts.add_fact("project", "uses", "FastAPI")
    facts.add_fact("FastAPI", "needs", "uvicorn")
    block = _recall_facts(facts, "project")
    assert block is not None
    assert "project uses FastAPI" in block
    assert "FastAPI needs uvicorn" in block


def test_recall_facts_ignores_superseded_facts(facts: SemanticFacts) -> None:
    facts.add_fact("project", "uses", "FastAPI")
    facts.reconcile("project", "uses", "Django")
    block = _recall_facts(facts, "project")
    assert block is not None
    assert "FastAPI" not in block
    assert "project uses Django" in block


def test_recall_facts_degrades_gracefully_on_store_error(facts: SemanticFacts) -> None:
    # Point at a non-existent / invalid path so the store raises.
    bad_facts = SemanticFacts(Path("/nonexistent/aios/facts.db"))
    block = _recall_facts(bad_facts, "project")
    assert block is None
