"""Input-shield tests for the conversational endpoint (renovation P0-7).

The voice/chat path (`POST /api/v1/chat`) is the one endpoint that fans free-form
operator text straight at a (possibly cloud) provider with recalled facts
attached, so it gets two lightweight protections beyond the deterministic
security cage:

  * a per-turn SIZE cap (Pydantic ``max_length`` on ``transcript``) -> HTTP 422.
  * a per-session sliding-window flood THROTTLE -> HTTP 429.

Collaborators are overridden via dependency injection so the suite never calls
Ollama, loads an embedder, or touches the real store. The in-process throttle
dict is reset around each test so cases never contaminate each other.
"""
from __future__ import annotations

from typing import Iterator, Optional

import pytest
from fastapi.testclient import TestClient

import aios.api.main as main
from aios.api.main import (
    _CHAT_HITS,
    _CHAT_RATE_MAX,
    app,
    get_bedrock_client,
    get_gemini_client,
    get_ollama_client,
    get_semantic_facts,
    get_semantic_indexer,
)


class _StubOllama:
    """Minimal Ollama stand-in: a deterministic single-shot reply, no tools."""

    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b"]}

    def chat(
        self,
        messages: list,
        *,
        tools: Optional[list] = None,
        model: Optional[str] = None,
    ) -> dict:
        return {"role": "assistant", "content": "theek hai."}


class _FakeFacts:
    def facts_for(self, subject: str, predicate: Optional[str] = None) -> list[dict]:
        return []


@pytest.fixture()
def shield_client() -> Iterator[TestClient]:
    """Wire the chat endpoint with fakes and a clean throttle window."""
    _CHAT_HITS.clear()
    app.dependency_overrides[get_ollama_client] = lambda: _StubOllama()
    app.dependency_overrides[get_bedrock_client] = lambda: None
    app.dependency_overrides[get_gemini_client] = lambda: None
    app.dependency_overrides[get_semantic_indexer] = lambda: None
    app.dependency_overrides[get_semantic_facts] = lambda: _FakeFacts()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    _CHAT_HITS.clear()


def test_oversize_transcript_rejected_with_422(shield_client: TestClient) -> None:
    """A transcript past the 8000-char cap is refused by validation, not routed."""
    response = shield_client.post(
        "/api/v1/chat",
        json={"transcript": "x" * 8001, "sessionId": "shield-size"},
    )
    assert response.status_code == 422


def test_transcript_at_cap_is_accepted(shield_client: TestClient) -> None:
    """The boundary value (exactly the cap) still routes — the cap is inclusive."""
    response = shield_client.post(
        "/api/v1/chat",
        json={"transcript": "y" * 8000, "sessionId": "shield-cap"},
    )
    assert response.status_code == 200


def test_flood_throttled_with_429(shield_client: TestClient) -> None:
    """The first ``_CHAT_RATE_MAX`` turns in a window pass; the next is 429."""
    session = "shield-flood"
    for _ in range(_CHAT_RATE_MAX):
        ok = shield_client.post(
            "/api/v1/chat",
            json={"transcript": "hi", "sessionId": session},
        )
        assert ok.status_code == 200
    blocked = shield_client.post(
        "/api/v1/chat",
        json={"transcript": "hi", "sessionId": session},
    )
    assert blocked.status_code == 429
    assert "Too many chat turns" in blocked.text


def test_throttle_is_per_session(shield_client: TestClient) -> None:
    """One flooded session must not throttle a different session."""
    flooded = "shield-a"
    for _ in range(_CHAT_RATE_MAX):
        shield_client.post(
            "/api/v1/chat", json={"transcript": "hi", "sessionId": flooded}
        )
    # the flooded session is now blocked...
    assert (
        shield_client.post(
            "/api/v1/chat", json={"transcript": "hi", "sessionId": flooded}
        ).status_code
        == 429
    )
    # ...but a fresh session is unaffected.
    assert (
        shield_client.post(
            "/api/v1/chat", json={"transcript": "hi", "sessionId": "shield-b"}
        ).status_code
        == 200
    )


def test_throttle_window_expiry_lets_traffic_resume(
    shield_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Once the sliding window advances past old hits, traffic resumes (no 429)."""
    session = "shield-window"
    clock = {"t": 1000.0}
    monkeypatch.setattr(main.time, "monotonic", lambda: clock["t"])
    for _ in range(_CHAT_RATE_MAX):
        assert (
            shield_client.post(
                "/api/v1/chat", json={"transcript": "hi", "sessionId": session}
            ).status_code
            == 200
        )
    # still inside the window -> blocked.
    assert (
        shield_client.post(
            "/api/v1/chat", json={"transcript": "hi", "sessionId": session}
        ).status_code
        == 429
    )
    # advance past the window -> the old hits age out, traffic resumes.
    clock["t"] += main._CHAT_RATE_WINDOW_S + 1.0
    assert (
        shield_client.post(
            "/api/v1/chat", json={"transcript": "hi", "sessionId": session}
        ).status_code
        == 200
    )
