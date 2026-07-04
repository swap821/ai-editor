"""Tests for personalization deepening: fact extraction in /api/v1/chat,
confidence strengthening, and cortex bus observability.

Collaborators are overridden via FastAPI dependency injection so no real
LLM or embedder is loaded.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator, Optional
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from aios.api.main import (
    app,
    get_bedrock_client,
    get_gemini_client,
    get_ollama_client,
    get_semantic_facts,
    get_semantic_indexer,
)
from aios.memory.facts import SemanticFacts
from aios.memory.fact_extraction import extract_candidates


# ── Fakes ─────────────────────────────────────────────────────────────────────

class _DeterministicOllama:
    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b"]}

    def chat(self, messages, *, tools=None, model=None) -> dict:
        return {"role": "assistant", "content": "Sure thing!"}


class _FakeIndexer:
    def __init__(self) -> None:
        self.added: list[str] = []

    def add(self, text: str) -> int:
        self.added.append(text)
        return len(self.added)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_facts(tmp_path: Path) -> SemanticFacts:
    """SemanticFacts backed by a real temporary SQLite database."""
    return SemanticFacts(db_path=tmp_path / "test_facts.db")


@pytest.fixture()
def chat_client_with_facts(tmp_facts: SemanticFacts) -> Iterator[TestClient]:
    """Chat endpoint wired with real SemanticFacts on a temp DB."""
    ollama = _DeterministicOllama()
    indexer = _FakeIndexer()
    app.dependency_overrides[get_ollama_client] = lambda: ollama
    app.dependency_overrides[get_bedrock_client] = lambda: None
    app.dependency_overrides[get_gemini_client] = lambda: None
    app.dependency_overrides[get_semantic_indexer] = lambda: indexer
    app.dependency_overrides[get_semantic_facts] = lambda: tmp_facts
    with TestClient(app, client=("127.0.0.1", 12345)) as c:
        yield c
    app.dependency_overrides.clear()


# ── Tests: chat endpoint extracts facts ──────────────────────────────────────

def test_chat_endpoint_extracts_facts(
    chat_client_with_facts: TestClient, tmp_facts: SemanticFacts
) -> None:
    resp = chat_client_with_facts.post(
        "/api/v1/chat",
        json={"transcript": "I prefer dark mode for everything", "session_id": "s1"},
    )
    assert resp.status_code == 200
    proposals = tmp_facts.pending_proposals()
    assert len(proposals) >= 1
    found = any(
        str(row["object"]).lower().startswith("dark mode")
        for row in proposals
    )
    assert found, f"Expected 'dark mode' proposal, got: {proposals}"


def test_chat_extraction_disabled_when_flag_off(
    chat_client_with_facts: TestClient, tmp_facts: SemanticFacts
) -> None:
    with patch("aios.api.main.config.FACTS_AUTO_EXTRACT", False):
        resp = chat_client_with_facts.post(
            "/api/v1/chat",
            json={"transcript": "I prefer vim keybindings", "session_id": "s2"},
        )
    assert resp.status_code == 200
    proposals = tmp_facts.pending_proposals()
    assert len(proposals) == 0


# ── Tests: strengthen_or_propose ─────────────────────────────────────────────

def test_strengthen_bumps_confidence(tmp_facts: SemanticFacts) -> None:
    from aios.memory.db import init_memory_db
    init_memory_db(tmp_facts.db_path)
    tmp_facts.add_fact("operator", "prefers", "dark mode", approved_by="human", confidence=0.8)
    result = tmp_facts.strengthen_or_propose("operator", "prefers", "dark mode")
    assert result.reason == "strengthened"
    rows = tmp_facts.facts_for("operator", "prefers")
    assert len(rows) == 1
    assert float(rows[0]["confidence"]) == pytest.approx(0.85, abs=0.001)


def test_strengthen_proposes_new_fact(tmp_facts: SemanticFacts) -> None:
    result = tmp_facts.strengthen_or_propose("operator", "uses", "neovim")
    assert result.proposed is True
    assert result.reason == "proposed"
    proposals = tmp_facts.pending_proposals()
    assert len(proposals) == 1
    assert str(proposals[0]["object"]) == "neovim"


# ── Tests: cortex bus event ──────────────────────────────────────────────────

def test_cortex_bus_event_emitted_on_extraction(
    chat_client_with_facts: TestClient, tmp_path: Path
) -> None:
    from aios.runtime.cortex_bus import CortexBus

    bus = CortexBus(db_path=tmp_path / "bus.db")
    with patch("aios.api.main._cortex_bus", bus):
        resp = chat_client_with_facts.post(
            "/api/v1/chat",
            json={"transcript": "I use Python for everything", "session_id": "s3"},
        )
    assert resp.status_code == 200
    with bus._connect() as conn:
        rows = conn.execute(
            "SELECT * FROM cortex_events WHERE event_type = 'facts.proposed'"
        ).fetchall()
    assert len(rows) >= 1


# ── Tests: no double proposals ───────────────────────────────────────────────

def test_repeated_extraction_does_not_double_propose(tmp_facts: SemanticFacts) -> None:
    r1 = tmp_facts.strengthen_or_propose("operator", "likes", "coffee")
    assert r1.proposed is True
    r2 = tmp_facts.strengthen_or_propose("operator", "likes", "coffee")
    assert r2.proposed is False
    assert r2.reason == "already proposed"
    proposals = tmp_facts.pending_proposals()
    assert len(proposals) == 1
