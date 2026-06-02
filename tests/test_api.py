"""FastAPI integration tests using Starlette's TestClient.

Collaborators are overridden via dependency injection so the suite never calls
Ollama, spawns a shell, or touches the real sandbox/ledger.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Iterator, Optional

import pytest
from fastapi.testclient import TestClient

from aios.api.main import (
    app,
    get_executor,
    get_llm_client,
    get_ollama_client,
    get_rollback_engine,
    get_semantic_indexer,
)
from aios.core.executor import Executor
from aios.memory.episodic import EpisodicMemory
from aios.security.gateway import RateLimiter


class FakeLLM:
    """Deterministic LLM stand-in for reflect + plan endpoints."""

    def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
        if "planning module" in (system or ""):
            return json.dumps(
                {"steps": [
                    {"step_id": "1", "description": "scaffold project", "confidence": 0.9},
                    {"step_id": "2", "description": "risky migration", "confidence": 0.4},
                ]}
            )
        return json.dumps(
            {
                "error_type": "Timeout",
                "root_cause": "the operation exceeded its time budget",
                "fix_applied": "increased the timeout and retried",
                "lesson_text": "set explicit timeouts on network calls",
                "confidence_delta": -0.1,
            }
        )


class FakeOllama:
    """Deterministic Ollama stand-in for model discovery + agentic chat."""

    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b", "nomic-embed-text:latest"]}

    def chat(
        self,
        messages: list,
        *,
        tools: Optional[list] = None,
        model: Optional[str] = None,
    ) -> dict:
        # No tool call: answer immediately with a fenced code block.
        return {
            "role": "assistant",
            "content": "Here is a button:\n```html\n<button>Hi</button>\n```",
        }


class FakeRunner:
    """Stand-in process runner — records, never spawns."""

    def __call__(self, command, *, cwd, env, timeout_s):
        return f"ran: {command}", "", 0


class RecordingAudit:
    def __call__(self, actor, payload, zone, **kwargs):
        return None


class FakeIndexer:
    """Stand-in L3 writer — records indexed text, never loads an embedder."""

    def __init__(self) -> None:
        self.added: list[str] = []

    def add(self, text: str) -> int:
        self.added.append(text)
        return len(self.added)


def _fake_executor() -> Executor:
    return Executor(runner=FakeRunner(), rate_limiter=RateLimiter(), audit_log=RecordingAudit())


@pytest.fixture()
def client() -> Iterator[TestClient]:
    fake_indexer = FakeIndexer()
    app.dependency_overrides[get_llm_client] = FakeLLM
    app.dependency_overrides[get_ollama_client] = FakeOllama
    app.dependency_overrides[get_executor] = _fake_executor
    app.dependency_overrides[get_semantic_indexer] = lambda: fake_indexer
    with TestClient(app) as test_client:
        test_client.fake_indexer = fake_indexer  # exposed for indexing assertions
        yield test_client
    app.dependency_overrides.clear()


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_classify_red_and_yellow(client: TestClient) -> None:
    red = client.post("/api/v1/security/classify", json={"command": "rm -rf /"})
    assert red.status_code == 200
    assert red.json()["zone"] == "RED"

    yellow = client.post("/api/v1/security/classify", json={"command": "pip install flask"})
    assert yellow.json()["zone"] == "YELLOW"


def test_memory_search_returns_list(client: TestClient) -> None:
    response = client.post("/api/v1/memory/search", json={"query": "anything", "top_k": 3})
    assert response.status_code == 200
    assert isinstance(response.json()["results"], list)


def test_audit_verify_responds(client: TestClient) -> None:
    response = client.get("/api/v1/audit/verify")
    assert response.status_code == 200
    assert "valid" in response.json()


def test_reflect_with_injected_fake_llm(client: TestClient) -> None:
    response = client.post(
        "/api/v1/reflect",
        json={"command": "fetch url", "error_output": "timed out", "task_id": "api-test"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error_type"] == "Timeout"
    assert body["mistake_id"] >= 1


def test_models_local_lists_installed(client: TestClient) -> None:
    response = client.get("/api/v1/models/local")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert "llama3.2:3b" in body["models"]


def test_generate_streams_text_code_and_done(client: TestClient) -> None:
    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "make a button"}]}],
            "modelId": "ollama.llama3.2:3b",
        },
    )
    assert response.status_code == 200
    body = response.text
    # streamed prose, the extracted code event, and a terminal done frame
    assert "event: text_chunk" in body
    assert "event: code" in body
    assert "<button>Hi</button>" in body
    assert "event: done" in body


def test_generate_without_user_message_emits_error(client: TestClient) -> None:
    response = client.post("/api/generate", json={"messages": []})
    assert response.status_code == 200
    assert "event: error" in response.text


def test_terminal_green_runs_in_sandbox(client: TestClient) -> None:
    response = client.post("/api/terminal", json={"command": "echo hello"})
    assert response.status_code == 200
    body = response.json()
    assert body["isError"] is False
    assert "ran: echo hello" in body["output"]


def test_terminal_red_command_is_blocked(client: TestClient) -> None:
    response = client.post("/api/terminal", json={"command": "rm -rf /"})
    assert response.status_code == 200
    body = response.json()
    assert body["isError"] is True
    assert "BLOCKED" in body["output"]


def test_generate_persists_episodic_turns(client: TestClient) -> None:
    session_id = "test-episodic-persist"
    before = EpisodicMemory().count(session_id)
    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "make a button"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": session_id,
        },
    )
    assert response.status_code == 200
    assert "event: done" in response.text
    # The user turn and the assistant answer are both recorded.
    assert EpisodicMemory().count(session_id) - before >= 2


def test_generate_recalls_memory_as_step(client: TestClient, monkeypatch) -> None:
    recalled = [SimpleNamespace(text="The project serves the API on port 8000.")]
    monkeypatch.setattr("aios.api.main.hybrid_search", lambda q, top_k=3: recalled)

    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "what port?"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": "test-recall-step",
        },
    )
    assert response.status_code == 200
    body = response.text
    assert "query_knowledge" in body          # the recall step is surfaced
    assert "serves the API on port 8000" in body


def test_generate_indexes_completed_turn_into_semantic(client: TestClient) -> None:
    client.fake_indexer.added.clear()
    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "make a button"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": "test-index-turn",
        },
    )
    assert response.status_code == 200
    assert "event: done" in response.text
    assert client.fake_indexer.added, "the completed turn should be indexed into L3"
    entry = client.fake_indexer.added[-1]
    assert "User:" in entry and "Assistant:" in entry
