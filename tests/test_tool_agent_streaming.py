"""Tests for ToolAgent streaming integration (C4).

Verifies that:
- When stream_fn is provided, text tokens are yielded from the final answer
- When stream_fn yields tool_calls, they are dispatched normally
- When stream_fn is None, existing behavior is unchanged (word-split)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator
from unittest.mock import MagicMock

import pytest

from aios.agents.tool_agent import ToolAgent
from aios.core.stream_protocol import StreamFinished


class FakeChatClient:
    """Minimal ChatClient for testing."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self._call_count = 0

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Any = None,
        model: Any = None,
    ) -> dict[str, Any]:
        resp = self._responses[min(self._call_count, len(self._responses) - 1)]
        self._call_count += 1
        return resp


class FakeExecutor:
    """Minimal executor that never runs anything."""

    project_root = Path("/tmp/fake-project")
    sandbox_roots = [Path("/tmp/fake-project")]

    def run(self, command: str, **kwargs: Any) -> dict[str, Any]:
        return {"exit_code": 0, "stdout": "ok", "stderr": ""}


def _make_stream_fn(chunks: list[str | StreamFinished]):
    """Create a stream_fn that yields the given chunks."""

    def stream_fn(messages: Any, *, tools: Any = None, model: Any = None) -> Iterator[Any]:
        yield from chunks

    return stream_fn


@pytest.fixture
def executor() -> FakeExecutor:
    return FakeExecutor()


class TestStreamingFinalAnswer:
    def test_text_tokens_yielded_from_stream(self, executor: FakeExecutor) -> None:
        """When stream_fn yields text chunks (no tool_calls), they become text events."""
        chunks: list[str | StreamFinished] = [
            "Hello ",
            "world!",
            StreamFinished(tool_calls=[], content="Hello world!"),
        ]
        agent = ToolAgent(
            FakeChatClient([]),
            executor,
            stream_fn=_make_stream_fn(chunks),
        )
        events = list(agent.run([{"role": "user", "content": "hi"}]))
        text_events = [e for e in events if e["type"] == "text"]
        assert len(text_events) == 2
        assert text_events[0]["text"] == "Hello "
        assert text_events[1]["text"] == "world!"
        assert any(e["type"] == "done" for e in events)

    def test_no_word_split_when_streamed(self, executor: FakeExecutor) -> None:
        """Streamed text should not be re-split into words."""
        content = "This is a multi-word sentence."
        chunks: list[str | StreamFinished] = [
            content,
            StreamFinished(tool_calls=[], content=content),
        ]
        agent = ToolAgent(
            FakeChatClient([]),
            executor,
            stream_fn=_make_stream_fn(chunks),
        )
        events = list(agent.run([{"role": "user", "content": "hi"}]))
        text_events = [e for e in events if e["type"] == "text"]
        # Should be exactly 1 text event (the full chunk), not word-split
        assert len(text_events) == 1
        assert text_events[0]["text"] == content


class TestStreamingWithToolCalls:
    def test_tool_calls_dispatched_after_stream(self, executor: FakeExecutor) -> None:
        """When stream yields tool_calls, they are processed normally."""
        tool_calls = [
            {"id": "tc-0", "function": {"name": "read_file", "arguments": {"filepath": "test.py"}}}
        ]
        # First iteration: streaming returns tool_calls
        first_chunks: list[str | StreamFinished] = [
            "Let me read that file.",
            StreamFinished(tool_calls=tool_calls, content="Let me read that file."),
        ]
        # Second iteration: streaming returns final answer
        second_chunks: list[str | StreamFinished] = [
            "Done!",
            StreamFinished(tool_calls=[], content="Done!"),
        ]

        call_count = [0]

        def stream_fn(messages: Any, *, tools: Any = None, model: Any = None) -> Iterator[Any]:
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                yield from first_chunks
            else:
                yield from second_chunks

        agent = ToolAgent(
            FakeChatClient([]),
            executor,
            stream_fn=stream_fn,
        )
        events = list(agent.run([{"role": "user", "content": "read test.py"}]))

        # Should have tool_call event
        tool_call_events = [e for e in events if e["type"] == "tool_call"]
        assert len(tool_call_events) == 1
        assert tool_call_events[0]["tool"] == "read_file"

        # Intermediate thinking text should NOT be yielded as text events
        text_events = [e for e in events if e["type"] == "text"]
        texts = [e["text"] for e in text_events]
        assert "Let me read that file." not in texts
        # Final answer should be yielded
        assert "Done!" in texts

    def test_intermediate_text_not_leaked(self, executor: FakeExecutor) -> None:
        """Text from iterations with tool_calls must not become text events."""
        chunks_with_tools: list[str | StreamFinished] = [
            "Thinking about tools...",
            StreamFinished(
                tool_calls=[{"id": "t1", "function": {"name": "read_file", "arguments": {"filepath": "x.py"}}}],
                content="Thinking about tools...",
            ),
        ]
        chunks_final: list[str | StreamFinished] = [
            "Final answer.",
            StreamFinished(tool_calls=[], content="Final answer."),
        ]

        call_count = [0]

        def stream_fn(messages: Any, *, tools: Any = None, model: Any = None) -> Iterator[Any]:
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                yield from chunks_with_tools
            else:
                yield from chunks_final

        agent = ToolAgent(
            FakeChatClient([]),
            executor,
            stream_fn=stream_fn,
        )
        events = list(agent.run([{"role": "user", "content": "hi"}]))
        text_events = [e for e in events if e["type"] == "text"]
        all_text = "".join(e["text"] for e in text_events)
        assert "Thinking about tools" not in all_text
        assert "Final answer." in all_text


class TestNonStreamingFallback:
    def test_no_stream_fn_uses_word_split(self, executor: FakeExecutor) -> None:
        """When stream_fn is None, existing word-split behavior is used."""
        agent = ToolAgent(
            FakeChatClient([{"role": "assistant", "content": "hello world"}]),
            executor,
            stream_fn=None,
        )
        events = list(agent.run([{"role": "user", "content": "hi"}]))
        text_events = [e for e in events if e["type"] == "text"]
        # Word-split produces one event per word
        assert len(text_events) == 2
        assert text_events[0]["text"].strip() == "hello"
        assert text_events[1]["text"].strip() == "world"


class TestStreamCodeBlockExtraction:
    def test_code_block_extracted_after_streaming(self, executor: FakeExecutor) -> None:
        """Code blocks in streamed content should still produce code events."""
        content = "Here is code:\n```python\nprint('hi')\n```"
        chunks: list[str | StreamFinished] = [
            content,
            StreamFinished(tool_calls=[], content=content),
        ]
        agent = ToolAgent(
            FakeChatClient([]),
            executor,
            stream_fn=_make_stream_fn(chunks),
        )
        events = list(agent.run([{"role": "user", "content": "show code"}]))
        code_events = [e for e in events if e["type"] == "code"]
        assert len(code_events) == 1
        assert "print('hi')" in code_events[0]["code"]
