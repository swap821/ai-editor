"""FastAPI integration tests using Starlette's TestClient.

The LLM dependency is overridden with a fake so ``/reflect`` runs without
Ollama. Other endpoints exercise the real (empty) databases created at startup.
"""
from __future__ import annotations

import json
from typing import Iterator, Optional

import pytest
from fastapi.testclient import TestClient

from aios.api.main import app, get_llm_client


class FakeLLM:
    """Deterministic LLM stand-in for the reflect endpoint."""

    def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
        return json.dumps(
            {
                "error_type": "Timeout",
                "root_cause": "the operation exceeded its time budget",
                "fix_applied": "increased the timeout and retried",
                "lesson_text": "set explicit timeouts on network calls",
                "confidence_delta": -0.1,
            }
        )


@pytest.fixture()
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_llm_client] = FakeLLM
    with TestClient(app) as test_client:
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
