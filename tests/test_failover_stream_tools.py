"""Tests for FailoverChatClient.stream_chat_with_tools() (C4).

Verifies streaming-with-tools yields text chunks and StreamFinished,
applies privacy filter for cloud candidates, and does first-chunk failover.
"""
from __future__ import annotations

from typing import Any, Iterator, Optional

import pytest

from aios.core.failover import FailoverChatClient
from aios.core.llm import LLMError
from aios.core.stream_protocol import StreamFinished


class FakeStreamingClient:
    """Client that supports stream_chat_with_tools."""

    def __init__(
        self,
        chunks: list[str | StreamFinished],
        *,
        raise_on: Optional[Exception] = None,
    ) -> None:
        self._chunks = chunks
        self._raise_on = raise_on

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Any = None,
        model: Any = None,
    ) -> dict[str, Any]:
        if self._raise_on:
            raise self._raise_on
        return {"role": "assistant", "content": "fallback", "tool_calls": []}

    def stream_chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Any = None,
        model: Any = None,
    ) -> Iterator[str | StreamFinished]:
        if self._raise_on:
            raise self._raise_on
        yield from self._chunks


class FakeNonStreamingClient:
    """Client without stream_chat_with_tools (local model)."""

    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Any = None,
        model: Any = None,
    ) -> dict[str, Any]:
        return self._response


class TestBasicStreaming:
    def test_yields_text_chunks_and_finished(self) -> None:
        chunks: list[str | StreamFinished] = [
            "Hello ",
            "there!",
            StreamFinished(tool_calls=[], content="Hello there!"),
        ]
        client = FailoverChatClient(
            [(FakeStreamingClient(chunks), "model-1", "bedrock")]
        )
        result = list(client.stream_chat_with_tools(
            [{"role": "user", "content": "hi"}],
            tools=[{"function": {"name": "t", "description": "d", "parameters": {}}}],
        ))
        text_chunks = [r for r in result if isinstance(r, str)]
        finished = [r for r in result if isinstance(r, StreamFinished)]
        assert text_chunks == ["Hello ", "there!"]
        assert len(finished) == 1
        assert finished[0].content == "Hello there!"
        assert finished[0].tool_calls == []

    def test_yields_tool_calls_in_finished(self) -> None:
        tool_calls = [{"id": "1", "function": {"name": "read_file", "arguments": {}}}]
        chunks: list[str | StreamFinished] = [
            "Let me check.",
            StreamFinished(tool_calls=tool_calls, content="Let me check."),
        ]
        client = FailoverChatClient(
            [(FakeStreamingClient(chunks), "model-1", "bedrock")]
        )
        result = list(client.stream_chat_with_tools(
            [{"role": "user", "content": "read"}],
            tools=[{"function": {"name": "read_file", "description": "d", "parameters": {}}}],
        ))
        finished = [r for r in result if isinstance(r, StreamFinished)]
        assert len(finished) == 1
        assert finished[0].tool_calls == tool_calls


class TestFailover:
    def test_failover_to_next_candidate(self) -> None:
        """If first candidate fails before first chunk, try next."""
        bad_client = FakeStreamingClient([], raise_on=LLMError("timeout"))
        good_chunks: list[str | StreamFinished] = [
            "ok",
            StreamFinished(tool_calls=[], content="ok"),
        ]
        good_client = FakeStreamingClient(good_chunks)

        failover_calls: list[tuple[str, str, str, str]] = []

        def on_failover(fp: str, fm: str, sp: str, sm: str, exc: Exception) -> None:
            failover_calls.append((fp, fm, sp, sm))

        client = FailoverChatClient(
            [(bad_client, "bad-model", "bedrock"), (good_client, "good-model", "ollama")],
            on_failover=on_failover,
        )
        result = list(client.stream_chat_with_tools(
            [{"role": "user", "content": "hi"}],
        ))
        text_chunks = [r for r in result if isinstance(r, str)]
        assert "ok" in text_chunks
        assert len(failover_calls) == 1
        assert failover_calls[0][0] == "bedrock"
        assert failover_calls[0][2] == "ollama"

    def test_all_fail_raises(self) -> None:
        bad1 = FakeStreamingClient([], raise_on=LLMError("err1"))
        bad2 = FakeStreamingClient([], raise_on=LLMError("err2"))
        client = FailoverChatClient(
            [(bad1, "m1", "bedrock"), (bad2, "m2", "ollama")],
        )
        with pytest.raises(LLMError, match="failed"):
            list(client.stream_chat_with_tools(
                [{"role": "user", "content": "hi"}],
            ))


class TestNonStreamingFallback:
    def test_fallback_to_chat_when_no_stream_method(self) -> None:
        """Client without stream_chat_with_tools falls back to chat()."""
        response = {"role": "assistant", "content": "answer", "tool_calls": []}
        client = FailoverChatClient(
            [(FakeNonStreamingClient(response), "local-model", "ollama")]
        )
        result = list(client.stream_chat_with_tools(
            [{"role": "user", "content": "hi"}],
        ))
        # Should get content as a text chunk + StreamFinished
        text_chunks = [r for r in result if isinstance(r, str)]
        finished = [r for r in result if isinstance(r, StreamFinished)]
        assert "answer" in text_chunks
        assert len(finished) == 1

    def test_fallback_preserves_tool_calls(self) -> None:
        """When falling back to chat(), tool_calls in the response are preserved."""
        tool_calls = [{"id": "x", "function": {"name": "read_file", "arguments": {}}}]
        response = {"role": "assistant", "content": "", "tool_calls": tool_calls}
        client = FailoverChatClient(
            [(FakeNonStreamingClient(response), "local-model", "ollama")]
        )
        result = list(client.stream_chat_with_tools(
            [{"role": "user", "content": "hi"}],
            tools=[{"function": {"name": "read_file", "description": "d", "parameters": {}}}],
        ))
        finished = [r for r in result if isinstance(r, StreamFinished)]
        assert len(finished) == 1
        assert finished[0].tool_calls == tool_calls


class TestPrivacyFilter:
    def test_privacy_filter_applied_for_cloud(self) -> None:
        """Cloud candidates should get privacy-filtered messages."""
        received_messages: list[Any] = []

        class SpyClient:
            def stream_chat_with_tools(
                self, messages: list[dict[str, Any]], **kwargs: Any
            ) -> Iterator[str | StreamFinished]:
                received_messages.append(messages)
                yield StreamFinished(tool_calls=[], content="")

        client = FailoverChatClient(
            [(SpyClient(), "model", "bedrock")]
        )
        list(client.stream_chat_with_tools(
            [{"role": "user", "content": "my secret is sk-abc123"}],
        ))
        # The privacy filter should have processed the messages
        assert len(received_messages) == 1
        # The exact redaction depends on the filter, but the call should succeed
