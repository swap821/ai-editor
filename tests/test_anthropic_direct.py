"""Tests for the Anthropic direct API client."""
from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import patch

import pytest

from aios.core.anthropic_direct import AnthropicDirectClient, _to_anthropic_messages
from aios.core.llm import LLMError


class TestToAnthropicMessages:
    def test_system_extracted(self):
        msgs = [
            {"role": "system", "content": "Be helpful."},
            {"role": "user", "content": "Hi"},
        ]
        system, out = _to_anthropic_messages(msgs)
        assert system == "Be helpful."
        assert len(out) == 1
        assert out[0]["role"] == "user"

    def test_tool_calls_converted_to_content_blocks(self):
        msgs = [
            {"role": "assistant", "content": "Calling tool", "tool_calls": [
                {"function": {"name": "read_file", "arguments": {"path": "/x"}}}
            ]},
            {"role": "tool", "content": "file content"},
        ]
        system, out = _to_anthropic_messages(msgs)
        assert system == ""
        assistant_msg = out[0]
        assert assistant_msg["role"] == "assistant"
        blocks = assistant_msg["content"]
        tool_use_block = next(b for b in blocks if b["type"] == "tool_use")
        assert tool_use_block["name"] == "read_file"
        assert tool_use_block["input"] == {"path": "/x"}

        user_msg = out[1]
        assert user_msg["role"] == "user"
        result_block = next(b for b in user_msg["content"] if b["type"] == "tool_result")
        assert result_block["tool_use_id"] == tool_use_block["id"]


class TestAnthropicDirectClient:
    def test_complete_returns_text(self):
        response_body = {
            "content": [{"type": "text", "text": "Hello!"}],
            "role": "assistant",
            "stop_reason": "end_turn",
        }
        client = AnthropicDirectClient(api_key="test-key")

        class FakeResp:
            def read(self):
                return json.dumps(response_body).encode()
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        with patch("urllib.request.urlopen", return_value=FakeResp()):
            result = client.complete("Say hi")
        assert result == "Hello!"

    def test_chat_returns_ollama_shaped_message(self):
        response_body = {
            "content": [
                {"type": "text", "text": "I'll read that."},
                {"type": "tool_use", "id": "tu_1", "name": "read_file", "input": {"path": "/x"}}
            ],
            "role": "assistant",
            "stop_reason": "tool_use",
        }
        client = AnthropicDirectClient(api_key="k")

        class FakeResp:
            def read(self):
                return json.dumps(response_body).encode()
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        with patch("urllib.request.urlopen", return_value=FakeResp()):
            result = client.chat([{"role": "user", "content": "read /x"}])
        assert result["role"] == "assistant"
        assert result["tool_calls"][0]["function"]["name"] == "read_file"

    def test_chat_records_the_real_privacy_audit_when_a_tracker_is_supplied(self):
        """Organ 50 (second half): the real per-call redaction audit -- not
        just logged -- must reach an injected PrivacyAuditTracker."""
        from aios.application.models.privacy_audit import PrivacyAuditTracker

        raw_path = r"C:\Users\kumar\ai-editor\secrets.txt"
        response_body = {
            "content": [{"type": "text", "text": "ok"}],
            "role": "assistant",
            "stop_reason": "end_turn",
        }
        tracker = PrivacyAuditTracker()
        client = AnthropicDirectClient(api_key="k", privacy_audit_tracker=tracker)

        class FakeResp:
            def read(self):
                return json.dumps(response_body).encode()
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        with patch("urllib.request.urlopen", return_value=FakeResp()):
            client.chat([{"role": "user", "content": f"read {raw_path}"}])

        records = tracker.recent()
        assert len(records) == 1
        assert records[0].provider == "anthropic"
        assert records[0].audit["redacted_paths"] >= 1

    def test_http_error_raises_llm_error(self):
        import urllib.error
        client = AnthropicDirectClient(api_key="k")

        def raise_http(*a, **kw):
            raise urllib.error.HTTPError("url", 429, "Rate limit", {}, BytesIO(b"slow down"))

        with patch("urllib.request.urlopen", side_effect=raise_http):
            with pytest.raises(LLMError, match="429"):
                client.complete("hi")

    def test_network_error_raises_llm_error(self):
        import urllib.error
        client = AnthropicDirectClient(api_key="k")

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("conn refused")):
            with pytest.raises(LLMError):
                client.complete("hi")
