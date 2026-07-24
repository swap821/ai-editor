"""Organ 30: real ground-truth correction for classify_human_state()'s guess.

POST /api/v1/chat/human-state/correct and GET /api/v1/chat/human-state/accuracy
close the organ's own named gap ("not measured against real production
traffic") by giving a human a real place to correct a guess, and a real
report measuring the classifier against whatever corrections exist.
"""

from __future__ import annotations

import json
from typing import Iterator, Optional

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


class _FakeOllama:
    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b"]}

    def chat(self, messages: list, *, tools: Optional[list] = None, model=None) -> dict:
        return {"role": "assistant", "content": "sab badhiya hai"}


class _FakeFacts:
    def facts_for(self, subject: str, predicate: Optional[str] = None) -> list[dict]:
        return []


class _FakeIndexer:
    def add(self, text: str) -> int:
        return 1


@pytest.fixture()
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_ollama_client] = lambda: _FakeOllama()
    app.dependency_overrides[get_bedrock_client] = lambda: None
    app.dependency_overrides[get_gemini_client] = lambda: None
    app.dependency_overrides[get_semantic_indexer] = lambda: _FakeIndexer()
    app.dependency_overrides[get_semantic_facts] = lambda: _FakeFacts()
    with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _human_state_frame(sse_body: str) -> dict:
    marker = "event: human_state\ndata: "
    start = sse_body.index(marker) + len(marker)
    end = sse_body.index("\n\n", start)
    return json.loads(sse_body[start:end])


def _real_turn(client: TestClient, session_id: str, transcript: str) -> tuple[str, str]:
    """Drive one real chat turn and return (turn_id, session_id)."""
    response = client.post(
        "/api/v1/chat",
        json={"transcript": transcript, "sessionId": session_id},
    )
    assert response.status_code == 200
    frame = _human_state_frame(response.text)
    return str(frame["turn_id"]), session_id


def test_correct_human_state_happy_path_then_visible_in_accuracy(
    client: TestClient,
) -> None:
    turn_id, session_id = _real_turn(client, "session-correct-1", "ugh still broken")

    resp = client.post(
        "/api/v1/chat/human-state/correct",
        json={
            "turnId": turn_id,
            "correctedState": "neutral",
            "sessionId": session_id,
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["turnId"] == turn_id
    assert body["correctedState"] == "neutral"
    assert body["recorded"] is True

    accuracy = client.get("/api/v1/chat/human-state/accuracy")
    assert accuracy.status_code == 200
    report = accuracy.json()
    assert report["total_corrected"] >= 1


def test_correct_human_state_unknown_turn_is_404(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/chat/human-state/correct",
        json={
            "turnId": "no-such-turn",
            "correctedState": "neutral",
            "sessionId": "session-x",
        },
    )
    assert resp.status_code == 404


def test_correct_human_state_invalid_state_is_422(client: TestClient) -> None:
    turn_id, session_id = _real_turn(client, "session-correct-2", "just do it now")

    resp = client.post(
        "/api/v1/chat/human-state/correct",
        json={
            "turnId": turn_id,
            "correctedState": "angry",  # not one of the 6 real states
            "sessionId": session_id,
        },
    )
    assert resp.status_code == 422


def test_human_state_accuracy_report_shape_is_stable(client: TestClient) -> None:
    resp = client.get("/api/v1/chat/human-state/accuracy")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"total_corrected", "agreements", "accuracy", "by_state"}
