"""Tests for the streaming protocol types (C4)."""
from aios.core.stream_protocol import StreamFinished


def test_stream_finished_default_fields() -> None:
    sf = StreamFinished()
    assert sf.tool_calls == []
    assert sf.content == ""


def test_stream_finished_with_tool_calls() -> None:
    calls = [{"id": "1", "function": {"name": "read_file", "arguments": {"path": "a.py"}}}]
    sf = StreamFinished(tool_calls=calls, content="thinking...")
    assert sf.tool_calls == calls
    assert sf.content == "thinking..."


def test_stream_finished_is_frozen() -> None:
    sf = StreamFinished(content="hello")
    try:
        sf.content = "changed"  # type: ignore[misc]
        assert False, "should be frozen"
    except AttributeError:
        pass
