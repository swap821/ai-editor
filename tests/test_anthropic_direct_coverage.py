"""Characterization tests for uncovered regions of ``aios/core/anthropic_direct.py``.

Complements ``tests/test_anthropic_direct.py``: message-converter edge cases,
tool-spec mapping, error-detail extraction, and the entire ``stream_chat``
SSE path. All transport is faked by patching ``urllib.request.urlopen`` —
no network, model, shell, or file side effects (conftest.py isolates
``AIOS_DATA_DIR``).
"""
from __future__ import annotations

import json
import urllib.error
from io import BytesIO
from unittest.mock import patch

import pytest

from aios.core.anthropic_direct import (
    AnthropicDirectClient,
    _parse_output,
    _to_anthropic_messages,
    _to_tools,
)
from aios.core.llm import LLMError


class _FakeResponse:
    def __init__(self, body: dict) -> None:
        self._data = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


class _RawResponse(_FakeResponse):
    def __init__(self, raw: bytes) -> None:
        self._data = raw


class _FakeStream:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = lines

    def __iter__(self):
        return iter(self._lines)

    def __enter__(self) -> "_FakeStream":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


class _ExplodingHTTPError(urllib.error.HTTPError):
    def read(self) -> bytes:  # type: ignore[override]
        raise RuntimeError("body unavailable")


class _RedactingFilter:
    """Deterministic stand-in that reports a redaction so the log branch runs."""

    def filter(self, messages):
        return messages, {"redacted_secrets": 1}

    def validate_response(self, result):
        return None


def _client() -> AnthropicDirectClient:
    return AnthropicDirectClient(api_key="test-key", model="claude-test")


# --- converter edge cases -------------------------------------------------


def test_converter_skips_blank_system_and_pads_empty_assistant():
    system, out = _to_anthropic_messages(
        [
            {"role": "system", "content": "   "},
            {"role": "assistant", "content": ""},
        ]
    )
    assert system == ""
    assert out == [{"role": "assistant", "content": [{"type": "text", "text": ""}]}]


def test_converter_parses_string_arguments_and_defaults_bad_json():
    msgs = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "a", "arguments": '{"x": 1}'}},
                {"function": {"name": "b", "arguments": "not-json"}},
            ],
        }
    ]
    _, out = _to_anthropic_messages(msgs)
    blocks = [b for b in out[0]["content"] if b["type"] == "tool_use"]
    assert blocks[0]["input"] == {"x": 1}
    assert blocks[1]["input"] == {}


def test_converter_orphan_tool_result_gets_synthetic_id():
    _, out = _to_anthropic_messages([{"role": "tool", "content": "orphan"}])
    block = out[0]["content"][0]
    assert block["type"] == "tool_result"
    assert block["tool_use_id"].startswith("toolu_orphan_")


def test_to_tools_maps_openai_specs_and_defaults_schema():
    assert _to_tools(None) is None
    specs = _to_tools(
        [
            {"function": {"name": "f", "description": "d", "parameters": {"type": "object"}}},
            {"function": {"name": "g"}},
        ]
    )
    assert specs[0] == {"name": "f", "description": "d", "input_schema": {"type": "object"}}
    assert specs[1]["input_schema"] == {"type": "object", "properties": {}}


def test_parse_output_skips_non_dict_blocks_and_omits_empty_tool_calls():
    result = _parse_output({"content": ["junk", {"type": "text", "text": "ok"}]})
    assert result == {"role": "assistant", "content": "ok"}
    assert "tool_calls" not in result


# --- complete / chat payload shaping ---------------------------------------


def test_complete_sends_system_and_skips_non_dict_blocks():
    captured: dict = {}

    def fake_urlopen(request, timeout=None):
        captured["payload"] = json.loads(request.data.decode())
        return _FakeResponse({"content": ["junk", {"type": "text", "text": "hi"}]})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        text = _client().complete("prompt", system="be brief")
    assert text == "hi"
    assert captured["payload"]["system"] == "be brief"


def test_chat_sends_system_and_tools_and_logs_redaction():
    captured: dict = {}

    def fake_urlopen(request, timeout=None):
        captured["payload"] = json.loads(request.data.decode())
        return _FakeResponse({"content": [{"type": "text", "text": "done"}]})

    client = _client()
    client._privacy_filter = _RedactingFilter()
    tools = [{"function": {"name": "read_file", "parameters": {"type": "object"}}}]
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = client.chat(
            [
                {"role": "system", "content": "rules"},
                {"role": "user", "content": "go"},
            ],
            tools=tools,
            model="claude-override",
        )
    assert result["content"] == "done"
    assert captured["payload"]["system"] == "rules"
    assert captured["payload"]["model"] == "claude-override"
    assert captured["payload"]["tools"][0]["name"] == "read_file"


# --- _post error mapping ----------------------------------------------------


def test_post_http_error_with_unreadable_body_still_raises_llm_error():
    err = _ExplodingHTTPError("url", 500, "boom", {}, BytesIO(b""))
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(LLMError, match="HTTP 500"):
            _client().complete("hi")


def test_post_non_json_response_raises_llm_error():
    with patch("urllib.request.urlopen", return_value=_RawResponse(b"<html>oops</html>")):
        with pytest.raises(LLMError, match="non-JSON"):
            _client().complete("hi")


# --- stream_chat ------------------------------------------------------------


def _sse(lines: list[str]) -> _FakeStream:
    return _FakeStream([line.encode("utf-8") for line in lines])


def test_stream_chat_yields_text_deltas_and_ignores_noise():
    stream = _sse(
        [
            "",
            ": keepalive",
            "event: message_start",
            "data:",
            "data: not-json",
            'data: {"type": "message_start"}',
            'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hel"}}',
            'data: {"type": "content_block_delta", "delta": {"type": "input_json_delta", "partial_json": "{}"}}',
            'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "lo"}}',
            'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": ""}}',
            "data: [DONE]",
        ]
    )
    captured: dict = {}

    def fake_urlopen(request, timeout=None):
        captured["payload"] = json.loads(request.data.decode())
        return stream

    client = _client()
    client._privacy_filter = _RedactingFilter()
    tools = [{"function": {"name": "t"}}]
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        chunks = list(
            client.stream_chat(
                [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
                tools=tools,
            )
        )
    assert chunks == ["Hel", "lo"]
    assert captured["payload"]["stream"] is True
    assert captured["payload"]["system"] == "sys"
    assert captured["payload"]["tools"][0]["name"] == "t"


def test_stream_chat_http_error_maps_to_llm_error():
    err = urllib.error.HTTPError("url", 429, "slow", {}, BytesIO(b"rate limited"))
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(LLMError, match="HTTP 429"):
            list(_client().stream_chat([{"role": "user", "content": "hi"}]))


def test_stream_chat_http_error_with_unreadable_body():
    err = _ExplodingHTTPError("url", 503, "down", {}, BytesIO(b""))
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(LLMError, match="HTTP 503"):
            list(_client().stream_chat([{"role": "user", "content": "hi"}]))


def test_stream_chat_network_error_maps_to_llm_error():
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
        with pytest.raises(LLMError, match="stream failed"):
            list(_client().stream_chat([{"role": "user", "content": "hi"}]))
