"""The emergency stop must halt the two highest-traffic model paths.

`tests/test_emergency_stop_boundaries.py` already proves the *gateway function*
refuses when the stop is engaged, and it passes. But `/api/v1/chat`'s anonymous
branch and `/api/generate` never enter that gateway, so that proof guarded
nothing on the live path. Measured before the fix: with the stop engaged, the
provider was still called and its reply still reached the client.

Chat is a GREEN action, so it never issues or consumes a capability -- and
`assert_operational()` was only reachable from `CapabilityAuthority.issue()` /
`.consume()`. That is why the gap existed despite the stop being "hard wired".

Each test here carries a CONTROL. Without one, a refusal from any unrelated
cause (origin protection, a 422, a missing session) reads as the stop working.
An earlier version of this probe did exactly that and nearly reported a real
finding as refuted.
"""

from __future__ import annotations

from typing import Iterator, Optional

import pytest
from fastapi.testclient import TestClient

from aios.api.deps import (
    get_bedrock_client,
    get_emergency_stop,
    get_gemini_client,
    get_ollama_client,
    get_optional_principal,
    get_semantic_facts,
    get_semantic_indexer,
)
from aios.api.main import app
from aios.domain.governance import EmergencyStopRequest

CALLS: list[str] = []


class ProviderSpy:
    """Records any reach for a provider. Never a real network call."""

    model = "fake-model"
    host = "http://127.0.0.1:11434"

    def stream_chat(self, messages, model=None, **kwargs):
        CALLS.append("stream_chat")
        yield "leaked reply"

    def chat(self, messages, model=None, **kwargs):
        CALLS.append("chat")
        return {"message": {"content": "leaked reply"}}


class FakeFacts:
    def facts_for(self, subject: str, predicate: Optional[str] = None) -> list[dict]:
        return []


@pytest.fixture()
def anonymous_chat() -> Iterator[TestClient]:
    CALLS.clear()
    app.dependency_overrides[get_optional_principal] = lambda: None
    app.dependency_overrides[get_ollama_client] = lambda: ProviderSpy()
    app.dependency_overrides[get_bedrock_client] = lambda: None
    app.dependency_overrides[get_gemini_client] = lambda: None
    app.dependency_overrides[get_semantic_indexer] = lambda: None
    app.dependency_overrides[get_semantic_facts] = lambda: FakeFacts()
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def engaged_stop() -> Iterator[None]:
    """Engage the REAL process controller.

    `aios/api/action_guard.py` calls `get_emergency_stop()` directly rather
    than through `Depends`, so a dependency override would not reach every
    consumer. Clearing needs a genuine one-use capability -- the ceremony is
    not bypassed here.
    """
    stop = get_emergency_stop()
    stop.engage(
        EmergencyStopRequest(
            operator_id="op-estop-test",
            authentication_event_id="auth-estop-1",
            reason="test: every model path must stop",
        )
    )
    assert stop.is_engaged() is True
    try:
        yield
    finally:
        token = stop.issue_clear_capability(
            operator_id="op-estop-test",
            authentication_event_id="auth-estop-2",
            session_id="estop-session",
        )
        stop.clear(
            operator_id="op-estop-test",
            authentication_event_id="auth-estop-2",
            session_id="estop-session",
            clear_capability=token,
        )
        assert stop.is_engaged() is False


def test_control_anonymous_chat_reaches_the_provider_when_not_stopped(
    anonymous_chat: TestClient,
) -> None:
    """CONTROL. Without this, a refusal from any other cause would be
    misread as the emergency stop working."""
    response = anonymous_chat.post(
        "/api/v1/chat", json={"transcript": "hello", "sessionId": "estop-control"}
    )

    assert response.status_code == 200, response.text
    assert CALLS, "control is meaningless if the provider was never reached"


def test_engaged_stop_halts_anonymous_chat_before_any_provider_call(
    anonymous_chat: TestClient, engaged_stop: None
) -> None:
    response = anonymous_chat.post(
        "/api/v1/chat",
        json={"transcript": "hello while stopped", "sessionId": "estop-1"},
    )

    assert CALLS == [], "provider was reached while the emergency stop was engaged"
    assert response.status_code == 503, response.text
    assert "leaked reply" not in response.text
