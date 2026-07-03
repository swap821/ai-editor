"""Tests for aios.core.graph_ingestion — entity extraction and edge generation."""
import pytest

from aios.core.graph_ingestion import (
    edges_from_mistake,
    edges_from_outcome,
    edges_from_skill,
    find_entities,
)


# ── find_entities tests ──────────────────────────────────────────────────────

def test_find_entities_path() -> None:
    entities = find_entities("read_file: aios/core/router.py")
    assert "aios/core/router.py" in entities
    assert "router" in entities


def test_find_entities_quoted() -> None:
    entities = find_entities('check the "router handler" module')
    assert "router handler" in entities


def test_find_entities_preposition() -> None:
    entities = find_entities("create a test for the router module")
    assert "router" in entities


def test_find_entities_multiple_patterns() -> None:
    text = 'fix the "config parser" in aios/core/router.py for the session module'
    entities = find_entities(text)
    assert "aios/core/router.py" in entities
    assert "config parser" in entities
    assert "router" in entities
    assert len(entities) == len(set(e.lower() for e in entities))


def test_find_entities_short_tokens_ignored() -> None:
    assert find_entities("") == []
    assert find_entities("a") == []
    assert find_entities("   ") == []


# ── edges_from_skill tests ──────────────────────────────────────────────────

def test_edges_from_skill_extracts_tool_target() -> None:
    edges = edges_from_skill(
        "fix the router",
        ["read_file: aios/core/router.py", "edit_file: aios/core/router.py"],
    )
    read_edges = [(s, p, o) for s, p, o, _ in edges if p == "read_in_workflow"]
    assert any("router" in s for s, _, _ in read_edges)


def test_edges_from_skill_scales_by_success_rate() -> None:
    edges = edges_from_skill(
        "test flow",
        ["read_file: main.py"],
        success_rate=0.8,
    )
    assert all(c == pytest.approx(0.8) for _, _, _, c in edges)


def test_edges_from_skill_clamps_confidence_floor() -> None:
    edges = edges_from_skill(
        "test flow",
        ["read_file: main.py"],
        success_rate=0.4,
    )
    assert all(c == pytest.approx(0.5) for _, _, _, c in edges)


def test_edges_from_skill_crosslinks_goal_to_steps() -> None:
    edges = edges_from_skill(
        "create a test for the router module",
        ["read_file: aios/core/executor.py"],
    )
    assoc = [(s, p, o) for s, p, o, _ in edges if p == "associated_with"]
    assert len(assoc) > 0


# ── edges_from_mistake tests ────────────────────────────────────────────────

def test_edges_from_mistake_extracts_cause() -> None:
    edges = edges_from_mistake(
        "FileNotFoundError",
        'missing file at "config.yaml"',
        'add existence check for "config.yaml"',
    )
    cause_edges = [(s, p, o) for s, p, o, _ in edges if p == "caused_by"]
    assert len(cause_edges) > 0
    assert all(s == "FileNotFoundError" for s, _, _ in cause_edges)
    assert all(c == pytest.approx(0.8) for _, _, _, c in edges)


def test_edges_from_mistake_empty_error_type() -> None:
    assert edges_from_mistake("", "some cause", "some lesson") == []
    assert edges_from_mistake("   ", "some cause", "some lesson") == []


# ── edges_from_outcome tests ────────────────────────────────────────────────

def test_edges_from_outcome_verified_success() -> None:
    edges = edges_from_outcome("fix aios/core/router.py", "verified_success", 5)
    assert len(edges) > 0
    assert all(c == pytest.approx(1.0) for _, _, _, c in edges)
    assert all(p == "has_verified_success" for _, p, _, _ in edges)


def test_edges_from_outcome_verified_failure() -> None:
    edges = edges_from_outcome("fix aios/core/router.py", "verified_failure", 5)
    assert len(edges) > 0
    assert all(c == pytest.approx(0.7) for _, _, _, c in edges)
    assert all(p == "has_verified_failure" for _, p, _, _ in edges)


def test_edges_from_outcome_unverified_ignored() -> None:
    assert edges_from_outcome("task", "unverified", 5) == []
    assert edges_from_outcome("task", "paused", 5) == []
