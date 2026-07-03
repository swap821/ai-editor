"""Tests for S2 knowledge graph: confidence-weighted facts and traversal."""
from pathlib import Path

import pytest

from aios.memory.facts import SemanticFacts, WeightedEdge
from aios.memory.db import init_memory_db


@pytest.fixture
def facts(tmp_path: Path) -> SemanticFacts:
    db = tmp_path / "kg.db"
    init_memory_db(db)
    return SemanticFacts(db)


# ── add_fact confidence tests ────────────────────────────────────────────────

def test_add_fact_with_confidence(facts: SemanticFacts) -> None:
    result = facts.add_fact("project", "uses", "FastAPI", confidence=0.7)
    assert result.committed is True
    row = facts.get(result.fact_id)
    assert float(row["confidence"]) == pytest.approx(0.7)


def test_add_fact_confidence_default(facts: SemanticFacts) -> None:
    result = facts.add_fact("project", "uses", "FastAPI")
    assert result.committed is True
    row = facts.get(result.fact_id)
    assert float(row["confidence"]) == pytest.approx(1.0)


def test_add_fact_confidence_clamped(facts: SemanticFacts) -> None:
    r1 = facts.add_fact("a", "p", "high", confidence=1.5)
    row1 = facts.get(r1.fact_id)
    assert float(row1["confidence"]) == pytest.approx(1.0)

    r2 = facts.add_fact("a", "p2", "low", confidence=-0.3)
    row2 = facts.get(r2.fact_id)
    assert float(row2["confidence"]) == pytest.approx(0.0)


def test_add_fact_idempotent_takes_max_confidence(facts: SemanticFacts) -> None:
    facts.add_fact("project", "uses", "FastAPI", approved_by="op", confidence=0.5)
    r2 = facts.add_fact("project", "uses", "FastAPI", approved_by="op", confidence=0.9)
    assert r2.reason == "already present"
    row = facts.get(r2.fact_id)
    assert float(row["confidence"]) == pytest.approx(0.9)


# ── traverse_weighted tests ─────────────────────────────────────────────────

def test_traverse_weighted_no_decay_at_depth_1(facts: SemanticFacts) -> None:
    facts.add_fact("project", "uses", "FastAPI", confidence=1.0)
    edges = facts.traverse_weighted("project", max_depth=1)
    assert len(edges) == 1
    assert edges[0].path_confidence == pytest.approx(1.0)
    assert edges[0].depth == 1


def test_traverse_weighted_decays_at_depth_2(facts: SemanticFacts) -> None:
    facts.add_fact("project", "uses", "FastAPI", confidence=1.0)
    facts.add_fact("FastAPI", "needs", "uvicorn", confidence=1.0)
    edges = facts.traverse_weighted("project", max_depth=2, decay=0.85)
    depth_2 = [e for e in edges if e.depth == 2]
    assert len(depth_2) == 1
    assert depth_2[0].path_confidence == pytest.approx(0.85, abs=0.01)


def test_traverse_weighted_decays_at_depth_3(facts: SemanticFacts) -> None:
    facts.add_fact("a", "to", "b", confidence=1.0)
    facts.add_fact("b", "to", "c", confidence=1.0)
    facts.add_fact("c", "to", "d", confidence=1.0)
    edges = facts.traverse_weighted("a", max_depth=3, decay=0.85)
    depth_3 = [e for e in edges if e.depth == 3]
    assert len(depth_3) == 1
    assert depth_3[0].path_confidence == pytest.approx(0.7225, abs=0.01)


def test_traverse_weighted_prunes_below_min(facts: SemanticFacts) -> None:
    facts.add_fact("a", "to", "b", confidence=0.3)
    facts.add_fact("b", "to", "c", confidence=0.3)
    facts.add_fact("c", "to", "d", confidence=0.3)
    edges = facts.traverse_weighted("a", max_depth=3, min_path_confidence=0.1, decay=0.85)
    for e in edges:
        assert e.path_confidence >= 0.1


def test_traverse_weighted_cycle_safe(facts: SemanticFacts) -> None:
    facts.add_fact("a", "to", "b")
    facts.add_fact("b", "to", "a")
    edges = facts.traverse_weighted("a", max_depth=3)
    assert len(edges) == 1
    assert edges[0].subject == "a" and edges[0].object == "b"


def test_traverse_weighted_orders_by_confidence(facts: SemanticFacts) -> None:
    facts.add_fact("root", "high", "a", confidence=1.0)
    facts.add_fact("root", "low", "b", confidence=0.5)
    edges = facts.traverse_weighted("root", max_depth=1)
    assert len(edges) == 2
    assert edges[0].path_confidence >= edges[1].path_confidence


def test_traverse_weighted_with_explicit_confidence(facts: SemanticFacts) -> None:
    facts.add_fact("root", "strong", "a", confidence=1.0)
    facts.add_fact("a", "to", "x", confidence=1.0)
    facts.add_fact("root", "weak", "b", confidence=0.5)
    facts.add_fact("b", "to", "y", confidence=0.5)
    edges = facts.traverse_weighted("root", max_depth=2, decay=0.85)
    depth_2 = [e for e in edges if e.depth == 2]
    strong = [e for e in depth_2 if e.object == "x"]
    weak = [e for e in depth_2 if e.object == "y"]
    assert len(strong) == 1 and len(weak) == 1
    assert strong[0].path_confidence > weak[0].path_confidence


def test_traverse_weighted_clamps_depth(facts: SemanticFacts) -> None:
    facts.add_fact("a", "to", "b")
    facts.add_fact("b", "to", "c")
    facts.add_fact("c", "to", "d")
    facts.add_fact("d", "to", "e")
    facts.add_fact("e", "to", "f")
    edges = facts.traverse_weighted("a", max_depth=99)
    assert all(e.depth <= 4 for e in edges)


# ── cross-store ingestion integration tests ─────────────────────────────────

def test_confidence_survives_roundtrip(facts: SemanticFacts) -> None:
    facts.add_fact("error", "caused_by", "null_check", confidence=0.8)
    edges = facts.traverse_weighted("error", max_depth=1)
    assert len(edges) == 1
    assert edges[0].confidence == pytest.approx(0.8)
