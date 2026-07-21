"""Unit tests for aios.core.failover (FailoverChatClient)."""

from unittest.mock import MagicMock
import pytest

from aios.core.failover import FailoverChatClient, _is_cloud_provider, _is_local_provider
from aios.core.llm import LLMError
from aios.core.stream_protocol import StreamFinished


def test_provider_classification():
    assert _is_cloud_provider("bedrock") is True
    assert _is_cloud_provider("gemini") is True
    assert _is_cloud_provider("ollama") is False

    assert _is_local_provider("ollama") is True
    assert _is_local_provider("local") is True
    assert _is_local_provider("bedrock") is False


def test_failover_chat_client_init_empty():
    with pytest.raises(ValueError, match="requires at least one candidate"):
        FailoverChatClient([])


def test_failover_chat_success_first_candidate():
    client1 = MagicMock()
    client1.chat.return_value = {"content": "response 1"}

    client2 = MagicMock()

    candidates = [
        (client1, "model-1", "ollama"),
        (client2, "model-2", "ollama"),
    ]

    fc = FailoverChatClient(candidates)
    assert fc.active_provider == "ollama"
    assert fc.active_model == "model-1"

    result = fc.chat([{"role": "user", "content": "hi"}])
    assert result == {"content": "response 1"}
    client1.chat.assert_called_once()
    client2.chat.assert_not_called()


def test_failover_chat_fallback_on_llm_error():
    client1 = MagicMock()
    client1.chat.side_effect = LLMError("Outage on model 1")

    client2 = MagicMock()
    client2.chat.return_value = {"content": "response 2"}

    hook_calls = []
    def on_failover(failed_p, failed_m, next_p, next_m, exc):
        hook_calls.append((failed_p, failed_m, next_p, next_m, str(exc)))

    candidates = [
        (client1, "model-1", "ollama"),
        (client2, "model-2", "ollama"),
    ]

    fc = FailoverChatClient(candidates, on_failover=on_failover)
    result = fc.chat([{"role": "user", "content": "hello"}])
    assert result == {"content": "response 2"}
    assert fc.active_model == "model-2"
    assert len(hook_calls) == 1
    assert hook_calls[0][0] == "ollama"
    assert hook_calls[0][1] == "model-1"
    assert hook_calls[0][3] == "model-2"


def test_failover_chat_all_fail_raises():
    client1 = MagicMock()
    client1.chat.side_effect = LLMError("Error 1")

    client2 = MagicMock()
    client2.chat.side_effect = LLMError("Error 2")

    candidates = [
        (client1, "m1", "ollama"),
        (client2, "m2", "ollama"),
    ]

    fc = FailoverChatClient(candidates)
    with pytest.raises(LLMError, match="all 2 model candidate\(s\) failed"):
        fc.chat([{"role": "user", "content": "test"}])


def test_failover_stream_chat():
    client1 = MagicMock()
    client1.stream_chat.side_effect = LLMError("Stream failed")

    client2 = MagicMock()
    client2.stream_chat.return_value = iter(["chunk 1", "chunk 2"])

    candidates = [
        (client1, "m1", "ollama"),
        (client2, "m2", "ollama"),
    ]

    fc = FailoverChatClient(candidates)
    chunks = list(fc.stream_chat([{"role": "user", "content": "hi"}]))
    assert chunks == ["chunk 1", "chunk 2"]
    assert fc.active_model == "m2"


def test_failover_stream_chat_with_tools():
    client1 = MagicMock()
    client1.stream_chat_with_tools.return_value = iter([
        "text",
        StreamFinished(tool_calls=[], content="text")
    ])

    candidates = [
        (client1, "m1", "ollama")
    ]

    fc = FailoverChatClient(candidates)
    items = list(fc.stream_chat_with_tools([{"role": "user", "content": "hi"}]))
    assert len(items) == 2
    assert items[0] == "text"
    assert isinstance(items[1], StreamFinished)
