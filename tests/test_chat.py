"""Tests for the lean Hinglish conversational endpoint (POST /api/v1/chat).

The Jarvis voice mind, Slice 1: a conversation-only endpoint that reuses the
router + memory + REAL personalization facts and streams a reply, running NO
file-write/coding tools. Collaborators are overridden via dependency injection
so the suite never calls Ollama, loads an embedder, or touches the real store.
"""
from __future__ import annotations

from typing import Iterator, Optional

import pytest
from fastapi.testclient import TestClient

from aios.api.main import (
    CHAT_SYSTEM_PROMPT,
    app,
    get_bedrock_client,
    get_gemini_client,
    get_ollama_client,
    get_semantic_facts,
    get_semantic_indexer,
)


class CapturingChatOllama:
    """Deterministic Ollama stand-in that records every chat() it receives.

    Exposes ``calls`` (the messages lists) and ``tools_seen`` so a test can
    assert the system prompt content AND that the conversational path never
    passes tools (no file-write/coding loop).
    """

    def __init__(self) -> None:
        self.calls: list[list] = []
        self.tools_seen: list[Optional[list]] = []

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
        self.tools_seen.append(tools)
        return {"role": "assistant", "content": "Arre haan bhai, ho jayega!"}


class FakeFacts:
    """Personalization-facts stand-in returning sqlite-Row-like dict rows."""

    def __init__(self, rows: Optional[list[dict]] = None) -> None:
        self._rows = rows or []

    def facts_for(self, subject: str, predicate: Optional[str] = None) -> list[dict]:
        return self._rows


class FakeIndexer:
    """Stand-in L3 writer — records indexed text, never loads an embedder."""

    def __init__(self) -> None:
        self.added: list[str] = []

    def add(self, text: str) -> int:
        self.added.append(text)
        return len(self.added)


@pytest.fixture()
def chat_setup() -> Iterator[tuple[TestClient, CapturingChatOllama]]:
    """Wire the chat endpoint with fakes; default = no operator facts (dormant)."""
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


def test_chat_streams_text_chunk_then_done(
    chat_setup: tuple[TestClient, CapturingChatOllama],
) -> None:
    client, _ = chat_setup
    response = client.post(
        "/api/v1/chat",
        json={"transcript": "kaise ho?", "sessionId": "voice-1"},
    )
    assert response.status_code == 200
    body = response.text
    # route announced, the reply streamed as text_chunk(s), terminal done.
    assert "event: route" in body
    assert "event: text_chunk" in body
    assert "event: done" in body
    # local-first respected: provider is the router's local pick, privacy local.
    assert '"provider": "ollama"' in body
    assert '"privacy": "local"' in body
    # the reply text actually reached the wire.
    assert "ho" in body and "jayega" in body
    # text_chunk precedes done.
    assert body.index("event: text_chunk") < body.index("event: done")


def test_chat_system_prompt_is_hinglish_conversational(
    chat_setup: tuple[TestClient, CapturingChatOllama],
) -> None:
    client, ollama = chat_setup
    response = client.post(
        "/api/v1/chat",
        json={"transcript": "thoda baat karein"},
    )
    assert response.status_code == 200
    # the system prompt is the first message and is the Hinglish persona.
    system = ollama.calls[0][0]
    assert system["role"] == "system"
    assert CHAT_SYSTEM_PROMPT in system["content"]
    # Hinglish + conversational, NOT the coding forge.
    assert "HINGLISH" in system["content"]
    assert "forge NAHI" in system["content"]
    # the operator's turn is carried as the user message.
    user = ollama.calls[0][1]
    assert user == {"role": "user", "content": "thoda baat karein"}


def test_chat_injects_operator_facts_when_present() -> None:
    """REAL approved operator facts are injected into the system prompt."""
    ollama = CapturingChatOllama()
    facts = FakeFacts(
        rows=[
            {"subject": "operator", "predicate": "prefers", "object": "concise Hinglish"},
            {"subject": "operator", "predicate": "is", "object": "an independent developer"},
        ]
    )
    app.dependency_overrides[get_ollama_client] = lambda: ollama
    app.dependency_overrides[get_bedrock_client] = lambda: None
    app.dependency_overrides[get_gemini_client] = lambda: None
    app.dependency_overrides[get_semantic_indexer] = lambda: None
    app.dependency_overrides[get_semantic_facts] = lambda: facts
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            response = client.post("/api/v1/chat", json={"transcript": "yaad hai mujhe?"})
        assert response.status_code == 200
        system_content = ollama.calls[0][0]["content"]
        assert "KNOWN FACTS ABOUT THE OPERATOR" in system_content
        assert "operator prefers concise Hinglish" in system_content
        assert "operator is an independent developer" in system_content
    finally:
        app.dependency_overrides.clear()


def test_chat_omits_facts_block_when_dormant(
    chat_setup: tuple[TestClient, CapturingChatOllama],
) -> None:
    """Honesty law: no facts -> no invented personalization block."""
    client, ollama = chat_setup  # default fixture has zero facts
    response = client.post("/api/v1/chat", json={"transcript": "hi"})
    assert response.status_code == 200
    system_content = ollama.calls[0][0]["content"]
    assert "KNOWN FACTS ABOUT THE OPERATOR" not in system_content


def test_chat_runs_no_file_write_tools(
    chat_setup: tuple[TestClient, CapturingChatOllama],
) -> None:
    """Conversation, not the forge: the chat client is called with tools=None
    (no tool loop) and the stream carries NO step/code/file-write frames."""
    client, ollama = chat_setup
    response = client.post("/api/v1/chat", json={"transcript": "kuch likhna mat, bas baat kar"})
    assert response.status_code == 200
    # exactly one model call, and it advertised NO tools.
    assert len(ollama.tools_seen) == 1
    assert ollama.tools_seen[0] is None
    # the conversational wire never emits agentic/coding frames.
    body = response.text
    assert "event: step" not in body
    assert "event: code" not in body
    assert "tool_call" not in body
    assert "edit_file" not in body
    assert "event: human_required" not in body


def test_chat_without_transcript_emits_error(
    chat_setup: tuple[TestClient, CapturingChatOllama],
) -> None:
    client, ollama = chat_setup
    response = client.post("/api/v1/chat", json={"transcript": "   "})
    assert response.status_code == 200
    assert "event: error" in response.text
    # no model call when there's nothing to say.
    assert ollama.calls == []
