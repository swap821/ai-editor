"""Tests for the OpenAI-compatible LLM client."""
from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import patch

import pytest

from aios.core.openai_compat import OpenAICompatClient, _to_openai_messages
from aios.core.llm import LLMError


def _mock_response(body: dict) -> BytesIO:
    return BytesIO(json.dumps(body).encode())


class TestToOpenAIMessages:
    def test_system_and_user_passthrough(self):
        msgs = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
        ]
        out = _to_openai_messages(msgs)
        assert out[0]["role"] == "system"
        assert out[1]["role"] == "user"
        assert out[1]["content"] == "Hi"

    def test_tool_calls_get_ids_and_stringified_args(self):
        msgs = [
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "read_file", "arguments": {"path": "/x"}}}
            ]},
            {"role": "tool", "content": "file content"},
        ]
        out = _to_openai_messages(msgs)
        assistant_msg = out[0]
        assert assistant_msg["tool_calls"][0]["id"]
        assert isinstance(assistant_msg["tool_calls"][0]["function"]["arguments"], str)
        tool_msg = out[1]
        assert tool_msg["tool_call_id"] == assistant_msg["tool_calls"][0]["id"]


class TestOpenAICompatClient:
    def test_complete_returns_text(self):
        response_body = {
            "choices": [{"message": {"role": "assistant", "content": "Hello!"}}]
        }
        client = OpenAICompatClient(api_key="test-key", base_url="http://localhost:8000/v1")

        class FakeResp:
            def read(self):
                return json.dumps(response_body).encode()
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        with patch("urllib.request.urlopen", return_value=FakeResp()):
            result = client.complete("Say hello")
        assert result == "Hello!"

    def test_chat_with_tools(self):
        response_body = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path": "/x"}'}
                    }]
                }
            }]
        }
        client = OpenAICompatClient(api_key="k", base_url="http://localhost/v1")

        class FakeResp:
            def read(self):
                return json.dumps(response_body).encode()
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        with patch("urllib.request.urlopen", return_value=FakeResp()):
            result = client.chat(
                [{"role": "user", "content": "read /x"}],
                tools=[{"type": "function", "function": {"name": "read_file"}}],
            )
        assert result["tool_calls"][0]["function"]["name"] == "read_file"

    def test_chat_records_the_real_privacy_audit_when_a_tracker_is_supplied(self):
        """Organ 50 (second half): the real per-call redaction audit -- not
        just logged -- must reach an injected PrivacyAuditTracker."""
        from aios.application.models.privacy_audit import PrivacyAuditTracker

        raw_path = r"C:\Users\kumar\ai-editor\secrets.txt"
        response_body = {
            "choices": [{"message": {"role": "assistant", "content": "ok"}}]
        }
        tracker = PrivacyAuditTracker()
        client = OpenAICompatClient(
            api_key="k", base_url="http://localhost/v1", privacy_audit_tracker=tracker
        )

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
        assert records[0].provider == "openai"
        assert records[0].audit["redacted_paths"] >= 1

    def test_http_error_raises_llm_error(self):
        import urllib.error
        client = OpenAICompatClient(api_key="k", base_url="http://localhost/v1")

        def raise_http(*a, **kw):
            raise urllib.error.HTTPError("url", 500, "Internal", {}, BytesIO(b"oops"))

        with patch("urllib.request.urlopen", side_effect=raise_http):
            with pytest.raises(LLMError, match="500"):
                client.complete("hi")

    def test_network_error_raises_llm_error(self):
        import urllib.error
        client = OpenAICompatClient(api_key="k", base_url="http://localhost/v1")

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            with pytest.raises(LLMError):
                client.complete("hi")
