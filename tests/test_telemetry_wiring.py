"""Integration tests proving ``aios.core.telemetry.record_run()`` is wired into
the live dispatch path (``POST /api/generate`` and ``POST /api/v1/chat``).

Before this wiring landed, ``record_run`` existed (see ``tests/test_telemetry.py``,
unit tests only) but nothing under ``aios/`` ever imported ``aios.core.telemetry``
-- the lap counter never actually counted a lap. These tests drive REAL requests
through the FastAPI app (fakes only at the provider/executor boundary, per house
style -- see ``tests/test_api.py``/``tests/test_chat.py``) and assert a row lands
in the real (test-isolated, see ``tests/conftest.py``) ``run_telemetry`` table with
honest field values -- not placeholders.
"""
from __future__ import annotations

from typing import Iterator, Optional

import pytest
from fastapi.testclient import TestClient

from aios.api.main import (
    app,
    get_approval_store,
    get_bedrock_client,
    get_executor,
    get_gemini_client,
    get_ollama_client,
    get_semantic_facts,
    get_semantic_indexer,
)
from aios.core import telemetry
from aios.core.executor import Executor
from aios.security.gateway import RateLimiter


class FakeIndexer:
    """Stand-in L3 writer -- records indexed text, never loads an embedder."""

    def __init__(self) -> None:
        self.added: list[str] = []

    def add(self, text: str) -> int:
        self.added.append(text)
        return len(self.added)


class FakeRunner:
    """Stand-in process runner -- records, never spawns."""

    def __call__(self, command, *, cwd, env, timeout_s):
        return f"ran: {command}", "", 0


class RecordingAudit:
    def __call__(self, actor, payload, zone, **kwargs):
        return None


def _fake_executor() -> Executor:
    return Executor(runner=FakeRunner(), rate_limiter=RateLimiter(), audit_log=RecordingAudit())


def _rows_for(session_id: str) -> list:
    """Telemetry rows for one session, from the real (test-isolated) DB."""
    return [r for r in telemetry.fetch_rows() if r["session_id"] == session_id]


class PlainOllama:
    """No tool calls, no verify -- the baseline LLM dispatch path."""

    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b"]}

    def chat(
        self,
        messages: list,
        *,
        tools: Optional[list] = None,
        model: Optional[str] = None,
    ) -> dict:
        return {"role": "assistant", "content": "just an answer, no tools involved"}


class YellowOllama:
    """First turn calls a YELLOW (needs-approval) command -- the turn pauses."""

    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b"]}

    def chat(
        self,
        messages: list,
        *,
        tools: Optional[list] = None,
        model: Optional[str] = None,
    ) -> dict:
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "execute_terminal",
                        "arguments": {"command": "pip install flask"},
                    }
                }
            ],
        }


@pytest.fixture()
def generate_client() -> Iterator[TestClient]:
    ollama = PlainOllama()
    fake_indexer = FakeIndexer()
    app.dependency_overrides[get_ollama_client] = lambda: ollama
    app.dependency_overrides[get_executor] = _fake_executor
    app.dependency_overrides[get_semantic_indexer] = lambda: fake_indexer
    get_approval_store().clear()
    with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_generate_plain_llm_turn_records_telemetry_row(generate_client: TestClient) -> None:
    """A plain no-tool-call turn lands exactly one telemetry row: dispatch_path
    'llm' (no playbook/native-plan matched), unverified (nothing was verified),
    with the REAL serving provider/model and a real measured latency."""
    session_id = "telemetry-wiring-llm"
    response = generate_client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "just chat, no tools"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": session_id,
        },
    )
    assert response.status_code == 200
    assert "event: done" in response.text

    rows = _rows_for(session_id)
    assert len(rows) == 1
    row = rows[0]
    assert row["dispatch_path"] == telemetry.DISPATCH_LLM
    assert row["provider"] == "ollama"
    assert row["model"]  # a real model string, not a placeholder/None
    assert row["verified_outcome"] == telemetry.OUTCOME_UNVERIFIED
    assert isinstance(row["latency_ms"], int) and row["latency_ms"] >= 0


def test_generate_paused_turn_records_aborted_telemetry_row() -> None:
    """A turn that pauses for YELLOW approval and is never resumed must still
    land ONE telemetry row -- pre-wiring, this (very common) case left ZERO
    rows, silently undercounting real traffic."""
    ollama = YellowOllama()
    fake_indexer = FakeIndexer()
    app.dependency_overrides[get_ollama_client] = lambda: ollama
    app.dependency_overrides[get_executor] = _fake_executor
    app.dependency_overrides[get_semantic_indexer] = lambda: fake_indexer
    get_approval_store().clear()
    session_id = "telemetry-wiring-paused"
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            response = client.post(
                "/api/generate",
                json={
                    "messages": [{"role": "user", "content": [{"text": "pip install flask"}]}],
                    "modelId": "ollama.llama3.2:3b",
                    "sessionId": session_id,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "event: human_required" in response.text

    rows = _rows_for(session_id)
    assert len(rows) == 1
    assert rows[0]["verified_outcome"] == telemetry.OUTCOME_ABORTED
    assert rows[0]["dispatch_path"] == telemetry.DISPATCH_LLM
    # The pause is a YELLOW-classified command -- the coarse max_zone
    # approximation must reflect that (see scoping report SS5.2).
    assert rows[0]["max_zone"] == "YELLOW"


class CapturingChatOllama:
    """Deterministic Ollama stand-in that records every chat() it receives."""

    def __init__(self) -> None:
        self.calls: list[list] = []

    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b"]}

    def chat(
        self,
        messages: list,
        *,
        tools: Optional[list] = None,
        model: Optional[str] = None,
    ) -> dict:
        self.calls.append(messages)
        return {"role": "assistant", "content": "Arre haan bhai, ho jayega!"}


class FakeFacts:
    """Personalization-facts stand-in returning zero rows (dormant)."""

    def facts_for(self, subject: str, predicate: Optional[str] = None) -> list[dict]:
        return []


@pytest.fixture()
def chat_client_fixture() -> Iterator[tuple[TestClient, CapturingChatOllama]]:
    ollama = CapturingChatOllama()
    indexer = FakeIndexer()
    app.dependency_overrides[get_ollama_client] = lambda: ollama
    app.dependency_overrides[get_bedrock_client] = lambda: None
    app.dependency_overrides[get_gemini_client] = lambda: None
    app.dependency_overrides[get_semantic_indexer] = lambda: indexer
    app.dependency_overrides[get_semantic_facts] = lambda: FakeFacts()
    with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
        yield test_client, ollama
    app.dependency_overrides.clear()


def test_chat_turn_records_telemetry_row(
    chat_client_fixture: tuple[TestClient, CapturingChatOllama],
) -> None:
    """/api/v1/chat has no tool loop -- dispatch_path is always 'llm' and
    verified_outcome is always 'unverified' (nothing is ever verified here)."""
    client, _ = chat_client_fixture
    session_id = "telemetry-wiring-chat"
    response = client.post(
        "/api/v1/chat",
        json={"transcript": "kaise ho?", "sessionId": session_id},
    )
    assert response.status_code == 200
    assert "event: done" in response.text

    rows = _rows_for(session_id)
    assert len(rows) == 1
    row = rows[0]
    assert row["dispatch_path"] == telemetry.DISPATCH_LLM
    assert row["provider"] == "ollama"
    assert row["model"]
    assert row["verified_outcome"] == telemetry.OUTCOME_UNVERIFIED
    assert isinstance(row["latency_ms"], int) and row["latency_ms"] >= 0


def test_chat_without_transcript_records_aborted_telemetry_row(
    chat_client_fixture: tuple[TestClient, CapturingChatOllama],
) -> None:
    """An empty transcript never reaches the model -- still counted, as aborted."""
    client, ollama = chat_client_fixture
    session_id = "telemetry-wiring-chat-empty"
    response = client.post(
        "/api/v1/chat",
        json={"transcript": "   ", "sessionId": session_id},
    )
    assert response.status_code == 200
    assert "event: error" in response.text
    assert ollama.calls == []  # no model call when there's nothing to say

    rows = _rows_for(session_id)
    assert len(rows) == 1
    assert rows[0]["verified_outcome"] == telemetry.OUTCOME_ABORTED
