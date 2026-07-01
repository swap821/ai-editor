"""Tests for aios.memory.facts — semantic fact CRUD, contradiction, and graph walk."""
from pathlib import Path

import pytest

from aios.memory.facts import FactWriteResult, SemanticFacts
from aios.memory.db import init_memory_db


@pytest.fixture
def facts(tmp_path: Path) -> SemanticFacts:
    db = tmp_path / "facts.db"
    init_memory_db(db)
    return SemanticFacts(db)


def test_add_fact_commits_and_returns_id(facts: SemanticFacts) -> None:
    result = facts.add_fact("project", "uses", "FastAPI")
    assert result.committed is True
    assert result.fact_id is not None
    assert result.reason == "committed"


def test_add_fact_idempotent_exact_duplicate(facts: SemanticFacts) -> None:
    r1 = facts.add_fact("project", "uses", "FastAPI")
    r2 = facts.add_fact("project", "uses", "FastAPI")
    assert r1.fact_id == r2.fact_id
    assert r2.reason == "already present"


def test_add_fact_detects_contradiction(facts: SemanticFacts) -> None:
    facts.add_fact("project", "uses", "FastAPI")
    result = facts.add_fact("project", "uses", "Django")
    assert result.committed is False
    assert result.reason == "contradiction"
    assert result.conflict_object == "FastAPI"


def test_reconcile_supersedes_old_fact(facts: SemanticFacts) -> None:
    facts.add_fact("project", "uses", "FastAPI", approved_by="op")
    result = facts.reconcile("project", "uses", "Django", approved_by="op")
    assert result.committed is True
    assert result.reason == "reconciled"
    active = facts.facts_for("project", "uses")
    assert len(active) == 1
    assert active[0]["object"] == "Django"


def test_facts_for_filters_by_predicate(facts: SemanticFacts) -> None:
    facts.add_fact("project", "uses", "FastAPI")
    facts.add_fact("project", "needs", "uvicorn")
    assert len(facts.facts_for("project", "uses")) == 1
    assert len(facts.facts_for("project")) == 2


def test_search_matches_subject_or_object(facts: SemanticFacts) -> None:
    facts.add_fact("FastAPI", "needs", "uvicorn")
    facts.add_fact("project", "uses", "FastAPI")
    facts.add_fact("operator", "prefers", "dark-mode")
    hits = facts.search("FastAPI")
    assert len(hits) == 2


def test_search_empty_query_returns_empty(facts: SemanticFacts) -> None:
    facts.add_fact("project", "uses", "FastAPI")
    assert facts.search("") == []
    assert facts.search("   ") == []


def test_neighbors_returns_incoming_and_outgoing(facts: SemanticFacts) -> None:
    facts.add_fact("alice", "likes", "tea")
    facts.add_fact("bob", "knows", "alice")
    facts.add_fact("alice", "works-on", "project")
    neighbors = facts.neighbors("alice")
    directions = {row["direction"] for row in neighbors}
    assert directions == {"in", "out"}
    assert len(neighbors) == 3


def test_neighbors_empty_subject_returns_empty(facts: SemanticFacts) -> None:
    assert facts.neighbors("") == []


def test_traverse_follows_object_to_subject_edges(facts: SemanticFacts) -> None:
    facts.add_fact("project", "uses", "FastAPI")
    facts.add_fact("FastAPI", "needs", "uvicorn")
    path = facts.traverse("project", max_depth=2)
    assert len(path) == 2
    depths = {row["depth"] for row in path}
    assert depths == {1, 2}


def test_traverse_clamps_max_depth(facts: SemanticFacts) -> None:
    facts.add_fact("a", "links", "b")
    facts.add_fact("b", "links", "c")
    facts.add_fact("c", "links", "d")
    facts.add_fact("d", "links", "e")
    # max_depth > 4 should clamp to 4
    path = facts.traverse("a", max_depth=99)
    assert max(row["depth"] for row in path) == 4


def test_traverse_avoids_cycles(facts: SemanticFacts) -> None:
    facts.add_fact("a", "links", "b")
    facts.add_fact("b", "links", "a")
    path = facts.traverse("a", max_depth=3)
    # a->b is emitted at depth 1; b->a is blocked because 'a' is already in the
    # path. The recursion terminates instead of looping forever.
    assert len(path) == 1
    assert path[0]["subject"] == "a" and path[0]["object"] == "b"


def test_traverse_caps_pathological_fanout(facts: SemanticFacts) -> None:
    for i in range(300):
        facts.add_fact("root", f"p{i:03d}", f"node{i:03d}")
    path = facts.traverse("root", max_depth=1)
    assert len(path) == 256
    assert path[-1]["predicate"] == "p255"
