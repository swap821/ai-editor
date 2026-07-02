"""Facts auto-extraction — supervised memory formation (narrative's last organ).

The organism proposes semantic facts from the OPERATOR'S OWN statements only
(never file contents — that would be a memory-poisoning surface). Proposals
live in their own ``fact_proposals`` table: structurally quarantined, so no
recall path (search/facts_for/neighbors/traverse) can see them even in
principle. A human approval promotes a proposal THROUGH the existing
contradiction-aware ``add_fact``; contradictions stay pending for reconcile.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aios.api.main import app, get_semantic_facts
from aios.memory.db import init_memory_db
from aios.memory.fact_extraction import extract_candidates
from aios.memory.facts import SemanticFacts


# ── extractor: deterministic, statements-only, capped ────────────────────────

def test_operator_preference_statement_extracts() -> None:
    assert extract_candidates("I prefer dark mode.", max_candidates=3) == [
        ("operator", "prefers", "dark mode")
    ]


def test_project_usage_statement_extracts_and_trims_for_clause() -> None:
    assert extract_candidates(
        "We use FastAPI for the backend.", max_candidates=3
    ) == [("project", "uses", "FastAPI")]


def test_operator_attribute_statement_extracts() -> None:
    assert extract_candidates("my region is ap-south-1", max_candidates=3) == [
        ("operator.region", "is", "ap-south-1")
    ]


def test_questions_are_never_facts() -> None:
    assert extract_candidates("Do we use Redis?", max_candidates=3) == []


def test_unrelated_text_extracts_nothing() -> None:
    assert extract_candidates("Fix the login bug in auth.py", max_candidates=3) == []


def test_candidates_are_capped_and_deduplicated() -> None:
    text = (
        "I prefer dark mode. I use vim. I like coffee. "
        "I want fast builds. I prefer dark mode."
    )
    result = extract_candidates(text, max_candidates=3)
    assert len(result) == 3
    assert len(set(result)) == 3


# ── proposal store: structural quarantine + gated promotion ──────────────────

def _facts(tmp_path: Path) -> SemanticFacts:
    db_path = tmp_path / "mem.db"
    init_memory_db(db_path)
    return SemanticFacts(db_path=db_path)


def _client() -> TestClient:
    # The API is loopback-only; TestClient's default address is rejected.
    return TestClient(app, client=("127.0.0.1", 12345))


def test_proposal_is_quarantined_from_all_recall_paths(tmp_path: Path) -> None:
    facts = _facts(tmp_path)
    outcome = facts.propose("operator", "prefers", "dark mode")
    assert outcome.proposed and outcome.proposal_id is not None
    assert facts.search("operator prefers dark mode") == []
    assert facts.facts_for("operator") == []
    assert facts.neighbors("operator") == []
    assert facts.traverse("operator") == []
    pending = facts.pending_proposals()
    assert len(pending) == 1
    assert pending[0]["subject"] == "operator"


def test_duplicate_proposal_is_idempotent(tmp_path: Path) -> None:
    facts = _facts(tmp_path)
    first = facts.propose("operator", "prefers", "dark mode")
    second = facts.propose("operator", "prefers", "dark mode")
    assert second.proposed is False
    assert second.reason == "already proposed"
    assert second.proposal_id == first.proposal_id
    assert len(facts.pending_proposals()) == 1


def test_proposal_matching_active_fact_is_skipped(tmp_path: Path) -> None:
    facts = _facts(tmp_path)
    facts.add_fact("operator", "prefers", "dark mode", approved_by="operator")
    outcome = facts.propose("operator", "prefers", "dark mode")
    assert outcome.proposed is False
    assert outcome.reason == "already known"
    assert facts.pending_proposals() == []


def test_approval_promotes_through_contradiction_check(tmp_path: Path) -> None:
    facts = _facts(tmp_path)
    pid = facts.propose("operator", "prefers", "dark mode").proposal_id
    result = facts.approve_proposal(pid, approved_by="operator")
    assert result.committed and result.reason == "committed"
    rows = facts.facts_for("operator")
    assert len(rows) == 1
    assert rows[0]["approved_by"] == "operator"
    assert facts.pending_proposals() == []


def test_contradicting_approval_stays_pending(tmp_path: Path) -> None:
    facts = _facts(tmp_path)
    facts.add_fact("operator", "prefers", "light mode", approved_by="operator")
    pid = facts.propose("operator", "prefers", "dark mode").proposal_id
    result = facts.approve_proposal(pid, approved_by="operator")
    assert result.committed is False
    assert result.reason == "contradiction"
    assert len(facts.pending_proposals()) == 1  # awaits explicit reconcile


def test_approval_requires_a_named_approver(tmp_path: Path) -> None:
    facts = _facts(tmp_path)
    pid = facts.propose("operator", "prefers", "dark mode").proposal_id
    result = facts.approve_proposal(pid, approved_by="   ")
    assert result.committed is False
    assert result.reason == "approver required"
    assert len(facts.pending_proposals()) == 1


def test_reject_resolves_the_proposal(tmp_path: Path) -> None:
    facts = _facts(tmp_path)
    pid = facts.propose("operator", "prefers", "dark mode").proposal_id
    assert facts.reject_proposal(pid, rejected_by="operator") is True
    assert facts.pending_proposals() == []
    assert facts.facts_for("operator") == []


def test_resolving_a_non_pending_proposal_fails_closed(tmp_path: Path) -> None:
    facts = _facts(tmp_path)
    pid = facts.propose("operator", "prefers", "dark mode").proposal_id
    facts.reject_proposal(pid, rejected_by="operator")
    result = facts.approve_proposal(pid, approved_by="operator")
    assert result.committed is False
    assert result.reason == "not pending"


# ── endpoints: pending queue + human-gated resolution ─────────────────────────

def test_pending_facts_endpoints_roundtrip(tmp_path: Path) -> None:
    facts = _facts(tmp_path)
    app.dependency_overrides[get_semantic_facts] = lambda: facts
    try:
        client = _client()
        pid = facts.propose("operator", "prefers", "dark mode").proposal_id

        listed = client.get("/api/v1/memory/facts/pending")
        assert listed.status_code == 200
        proposals = listed.json()["proposals"]
        assert [p["id"] for p in proposals] == [pid]

        approved = client.post(
            f"/api/v1/memory/facts/pending/{pid}/approve",
            json={"resolvedBy": "operator"},
        )
        assert approved.status_code == 200
        assert approved.json()["reason"] == "committed"
        assert client.get("/api/v1/memory/facts/pending").json()["proposals"] == []
    finally:
        app.dependency_overrides.pop(get_semantic_facts, None)


def test_approve_endpoint_surfaces_contradiction_as_409(tmp_path: Path) -> None:
    facts = _facts(tmp_path)
    app.dependency_overrides[get_semantic_facts] = lambda: facts
    try:
        client = _client()
        facts.add_fact("operator", "prefers", "light mode", approved_by="operator")
        pid = facts.propose("operator", "prefers", "dark mode").proposal_id
        response = client.post(
            f"/api/v1/memory/facts/pending/{pid}/approve",
            json={"resolvedBy": "operator"},
        )
        assert response.status_code == 409
    finally:
        app.dependency_overrides.pop(get_semantic_facts, None)


def test_resolve_endpoints_404_on_unknown_proposal(tmp_path: Path) -> None:
    facts = _facts(tmp_path)
    app.dependency_overrides[get_semantic_facts] = lambda: facts
    try:
        client = _client()
        approve = client.post(
            "/api/v1/memory/facts/pending/999/approve", json={"resolvedBy": "op"}
        )
        reject = client.post(
            "/api/v1/memory/facts/pending/999/reject", json={"resolvedBy": "op"}
        )
        assert approve.status_code == 404
        assert reject.status_code == 404
    finally:
        app.dependency_overrides.pop(get_semantic_facts, None)
