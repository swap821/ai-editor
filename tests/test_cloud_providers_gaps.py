"""Gap-closing tests for aios/core/{bedrock,gemini,openai_compat,failover}.py.

Targets specific uncovered lines/branches in the four cloud-provider adapters:
tool-schema conversion edge cases, streaming-chunk parsing (including tool-use
accumulation), error-mapping, and the failover ladder's streaming/H9 paths.

All network/SDK boundaries are faked — no boto3, no google-genai, no real HTTP.
Follows the established patterns in tests/test_bedrock.py, tests/test_gemini.py,
tests/test_openai_compat.py, tests/test_failover.py, tests/test_failover_stream_tools.py,
and tests/test_anthropic_direct_coverage.py.
"""
from __future__ import annotations

import json
import urllib.error
from io import BytesIO
from typing import Any, Iterator, Optional
from unittest.mock import patch

import pytest

from aios.core.bedrock import (
    BedrockClient,
    _finish_tool,
    _parse_output as _bedrock_parse_output,
    _stream_from_converse,
    _stream_text_from_converse,
    _to_converse,
)
from aios.core.failover import FailoverChatClient
from aios.core.gemini import (
    GeminiClient,
    _coerce_args,
    _parse_output as _gemini_parse_output,
    _stream_from_gemini,
    _stream_text_from_gemini,
    _to_gemini,
)
from aios.core.llm import LLMError
from aios.core.openai_compat import OpenAICompatClient, _parse_output as _openai_parse_output
from aios.core.stream_protocol import StreamFinished

pytestmark = [pytest.mark.cloud]


# =====================================================================
# aios/core/bedrock.py
# =====================================================================


class FakeBedrock:
    """Stub bedrock-runtime: records converse kwargs, returns canned replies."""

    def __init__(self, reply: dict, *, stream_reply: dict | None = None) -> None:
        self.reply = reply
        self.stream_reply = stream_reply or {"stream": []}
        self.last: dict | None = None
        self.stream_last: dict | None = None

    def converse(self, **kwargs):
        self.last = kwargs
        return self.reply

    def converse_stream(self, **kwargs):
        self.stream_last = kwargs
        return self.stream_reply


class TestBedrockToConverse:
    def test_bad_json_tool_arguments_default_to_empty_dict(self) -> None:
        # Lines 84-88: string arguments that fail json.loads fall back to {}.
        _, conv = _to_converse(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"function": {"name": "read_file", "arguments": "not-json"}}],
                },
            ]
        )
        assert conv[0]["content"][0]["toolUse"]["input"] == {}

    def test_assistant_with_no_text_and_no_tool_calls_gets_empty_text_block(self) -> None:
        # Line 92-93: Converse rejects empty content -> synthesize {"text": ""}.
        _, conv = _to_converse([{"role": "assistant", "content": ""}])
        assert conv[0] == {"role": "assistant", "content": [{"text": ""}]}

    def test_orphan_tool_result_folds_in_as_text(self) -> None:
        # A `role: tool` message with no pending toolUse id (e.g. ToolAgent's
        # forced _auto_verify check) no longer manufactures a synthetic
        # toolResult -- that produced an EXTRA toolResult with no matching
        # toolUse, which Bedrock's Converse API hard-rejects. It now folds in
        # as a plain text block instead (fixed 2026-07-05, see bedrock.py's
        # _to_converse docstring).
        _, conv = _to_converse([{"role": "tool", "content": "orphan result"}])
        assert conv[0]["content"][0] == {"text": "orphan result"}


class TestBedrockParseOutput:
    def test_non_dict_blocks_are_skipped(self) -> None:
        # Line 134-135: `if not isinstance(block, dict): continue`.
        parsed = _bedrock_parse_output({"content": ["not-a-dict", {"text": "hi"}]})
        assert parsed == {"role": "assistant", "content": "hi"}

    def test_missing_content_key_yields_empty_message(self) -> None:
        parsed = _bedrock_parse_output({})
        assert parsed == {"role": "assistant", "content": ""}


class TestBedrockStreamTextFromConverse:
    def test_non_dict_stream_events_are_skipped(self) -> None:
        # Lines 156-157: `if not isinstance(event, dict): continue`.
        response = {"stream": ["garbage", {"contentBlockDelta": {"delta": {"text": "ok"}}}]}
        assert list(_stream_text_from_converse(response)) == ["ok"]

    def test_response_without_stream_key_iterates_the_object_directly(self) -> None:
        # Line 154: `response.get("stream") if isinstance(response, dict) else response`.
        events = [{"contentBlockDelta": {"delta": {"text": "raw"}}}]
        assert list(_stream_text_from_converse(events)) == ["raw"]

    def test_missing_text_delta_yields_nothing(self) -> None:
        response = {"stream": [{"contentBlockDelta": {"delta": {}}}]}
        assert list(_stream_text_from_converse(response)) == []


class TestBedrockStreamFromConverse:
    def test_full_tool_use_accumulation_across_events(self) -> None:
        # Lines 170-210: text deltas, tool_use start/delta/stop, StreamFinished.
        response = {
            "stream": [
                "garbage-non-dict",
                {"contentBlockDelta": {"delta": {"text": "Let "}}},
                {"contentBlockDelta": {"delta": {"text": "me check."}}},
                {"contentBlockStart": {"start": {"toolUse": {"toolUseId": "t1", "name": "read_file"}}}},
                {"contentBlockDelta": {"delta": {"toolUse": {"input": '{"path"'}}}},
                {"contentBlockDelta": {"delta": {"toolUse": {"input": ': "a.py"}'}}}},
                {"contentBlockStop": {}},
            ]
        }
        items = list(_stream_from_converse(response))
        text_items = [i for i in items if isinstance(i, str)]
        finished = [i for i in items if isinstance(i, StreamFinished)]
        assert text_items == ["Let ", "me check."]
        assert len(finished) == 1
        assert finished[0].tool_calls == [
            {"id": "t1", "function": {"name": "read_file", "arguments": {"path": "a.py"}}}
        ]
        assert finished[0].content == "Let me check."

    def test_second_tool_start_finalizes_the_first_in_progress_tool(self) -> None:
        # Lines 194-199: a new contentBlockStart while current_tool is set finishes it first.
        response = {
            "stream": [
                {"contentBlockStart": {"start": {"toolUse": {"toolUseId": "a", "name": "one"}}}},
                {"contentBlockDelta": {"delta": {"toolUse": {"input": "{}"}}}},
                {"contentBlockStart": {"start": {"toolUse": {"toolUseId": "b", "name": "two"}}}},
                {"contentBlockStop": {}},
            ]
        }
        items = list(_stream_from_converse(response))
        finished = [i for i in items if isinstance(i, StreamFinished)][0]
        names = [tc["function"]["name"] for tc in finished.tool_calls]
        assert names == ["one", "two"]

    def test_trailing_unfinished_tool_is_finalized_defensively(self) -> None:
        # Lines 207-208: no contentBlockStop ever arrives; the trailing tool is
        # still finalized after the stream ends.
        response = {
            "stream": [
                {"contentBlockStart": {"start": {"toolUse": {"toolUseId": "x", "name": "run"}}}},
                {"contentBlockDelta": {"delta": {"toolUse": {"input": '{"a": 1}'}}}},
            ]
        }
        items = list(_stream_from_converse(response))
        finished = [i for i in items if isinstance(i, StreamFinished)][0]
        assert finished.tool_calls == [{"id": "x", "function": {"name": "run", "arguments": {"a": 1}}}]

    def test_empty_stream_yields_only_stream_finished_with_no_content(self) -> None:
        items = list(_stream_from_converse({"stream": []}))
        assert len(items) == 1
        assert isinstance(items[0], StreamFinished)
        assert items[0].tool_calls == []
        assert items[0].content == ""


class TestFinishTool:
    def test_bad_json_input_fragments_default_to_empty_args(self) -> None:
        # Lines 219-223: json.loads failure -> {}.
        out: list[dict[str, Any]] = []
        _finish_tool({"toolUseId": "z", "name": "n"}, ["{not valid"], out)
        assert out == [{"id": "z", "function": {"name": "n", "arguments": {}}}]

    def test_empty_input_fragments_yield_empty_args_without_calling_json_loads(self) -> None:
        out: list[dict[str, Any]] = []
        _finish_tool({"toolUseId": "z2", "name": "n2"}, [], out)
        assert out == [{"id": "z2", "function": {"name": "n2", "arguments": {}}}]


class TestBedrockClientChat:
    def test_chat_logs_privacy_filter_when_redaction_occurred(self, caplog) -> None:
        # Lines 280-285: audit dict has a redacted_* key that is truthy -> info log.
        fake = FakeBedrock({"output": {"message": {"content": [{"text": "ok"}]}}})
        client = BedrockClient(model="m", region="r", client=fake)
        with caplog.at_level("INFO"):
            client.chat([{"role": "user", "content": r"C:\Users\kumar\secrets.txt"}])
        assert any("privacy filter applied" in rec.message for rec in caplog.records)

    def test_chat_includes_system_block_when_present(self) -> None:
        # Line 293-294: `if system: kwargs["system"] = system`.
        fake = FakeBedrock({"output": {"message": {"content": [{"text": "ok"}]}}})
        client = BedrockClient(model="m", region="r", client=fake)
        client.chat([{"role": "system", "content": "be terse"}, {"role": "user", "content": "hi"}])
        assert fake.last["system"] == [{"text": "be terse"}]

    def test_chat_omits_system_key_when_absent(self) -> None:
        fake = FakeBedrock({"output": {"message": {"content": [{"text": "ok"}]}}})
        client = BedrockClient(model="m", region="r", client=fake)
        client.chat([{"role": "user", "content": "hi"}])
        assert "system" not in fake.last

    def test_chat_returns_empty_assistant_when_message_is_not_a_dict(self) -> None:
        # Line 314-316: `if not isinstance(message, dict): return {...}`.
        fake = FakeBedrock({"output": {"message": ["not-a-dict"]}})
        client = BedrockClient(model="m", region="r", client=fake)
        out = client.chat([{"role": "user", "content": "hi"}])
        assert out == {"role": "assistant", "content": ""}

    def test_chat_returns_empty_assistant_when_output_missing_entirely(self) -> None:
        fake = FakeBedrock({})
        client = BedrockClient(model="m", region="r", client=fake)
        out = client.chat([{"role": "user", "content": "hi"}])
        assert out == {"role": "assistant", "content": ""}


class TestBedrockClientStreamChat:
    def test_stream_chat_includes_system_when_present(self) -> None:
        # Line 346-347.
        fake = FakeBedrock({}, stream_reply={"stream": []})
        client = BedrockClient(model="m", region="r", client=fake)
        list(client.stream_chat([{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]))
        assert fake.stream_last["system"] == [{"text": "sys"}]

    def test_stream_chat_logs_privacy_filter_when_redaction_occurred(self, caplog) -> None:
        # Line 337-338.
        fake = FakeBedrock({}, stream_reply={"stream": []})
        client = BedrockClient(model="m", region="r", client=fake)
        with caplog.at_level("INFO"):
            list(client.stream_chat([{"role": "user", "content": r"C:\Users\kumar\secrets.txt"}]))
        assert any("privacy filter applied" in rec.message for rec in caplog.records)

    def test_stream_chat_wraps_provider_failure_as_llm_error(self) -> None:
        # Lines 352-365: converse_stream raising is wrapped + scrubbed + re-raised.
        class Boom:
            def converse_stream(self, **kwargs):
                raise RuntimeError("ThrottlingException: rate exceeded")

        client = BedrockClient(model="m", region="r", client=Boom())
        with pytest.raises(LLMError, match="ConverseStream failed"):
            list(client.stream_chat([{"role": "user", "content": "hi"}]))


class TestBedrockClientStreamChatWithTools:
    def test_stream_chat_with_tools_happy_path_includes_system_and_tools(self) -> None:
        # Lines 381-399: full happy path through stream_chat_with_tools.
        fake = FakeBedrock(
            {},
            stream_reply={
                "stream": [
                    {"contentBlockDelta": {"delta": {"text": "hi"}}},
                ]
            },
        )
        client = BedrockClient(model="m", region="r", client=fake)
        items = list(
            client.stream_chat_with_tools(
                [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
                tools=[{"function": {"name": "t", "description": "d", "parameters": {}}}],
            )
        )
        assert "hi" in items
        assert isinstance(items[-1], StreamFinished)
        assert fake.stream_last["system"] == [{"text": "sys"}]
        assert "toolConfig" in fake.stream_last

    def test_stream_chat_with_tools_logs_privacy_filter_when_redaction_occurred(self, caplog) -> None:
        # Line 382-383.
        fake = FakeBedrock({}, stream_reply={"stream": []})
        client = BedrockClient(model="m", region="r", client=fake)
        with caplog.at_level("INFO"):
            list(client.stream_chat_with_tools([{"role": "user", "content": r"C:\Users\kumar\secrets.txt"}]))
        assert any("privacy filter applied" in rec.message for rec in caplog.records)

    def test_stream_chat_with_tools_wraps_provider_failure_as_llm_error(self) -> None:
        # Lines 397-409.
        class Boom:
            def converse_stream(self, **kwargs):
                raise RuntimeError("AccessDenied")

        client = BedrockClient(model="m", region="r", client=Boom())
        with pytest.raises(LLMError, match="stream_chat_with_tools failed"):
            list(client.stream_chat_with_tools([{"role": "user", "content": "hi"}]))


class FakeCtrl:
    def __init__(self, summaries: list) -> None:
        self.summaries = summaries

    def list_foundation_models(self, **kwargs):
        return {"modelSummaries": self.summaries}


class TestBedrockDiscoverModels:
    def test_discover_models_falls_back_when_ctrl_client_creation_fails(self) -> None:
        # Lines 425-432: ctrl is None and boto3.client(...) raises -> [].
        with patch("boto3.client", side_effect=RuntimeError("no boto3 creds")):
            client = BedrockClient(model="m", region="r", client=FakeBedrock({}), ctrl_client=None)
            models = client._discover_models()
        assert models == []

    def test_list_foundation_models_call_failure_falls_back_to_curated(self) -> None:
        # Line 434-437 + list_models() combining with CURATED_MODELS.
        from aios.core.bedrock import CURATED_MODELS

        class Boom:
            def list_foundation_models(self, **kwargs):
                raise RuntimeError("AccessDeniedException")

        client = BedrockClient(model="m", region="r", client=FakeBedrock({}), ctrl_client=Boom())
        assert client.list_models() == CURATED_MODELS

    def test_discover_models_skips_non_dict_summaries_and_missing_ids(self) -> None:
        # Lines 442-446: `if not isinstance(summary, dict): continue` and missing modelId.
        ctrl = FakeCtrl(["not-a-dict", {"providerName": "X"}, {"modelId": "", "providerName": "Y"}])
        client = BedrockClient(model="m", region="r", client=FakeBedrock({}), ctrl_client=ctrl)
        assert client._discover_models() == []


# =====================================================================
# aios/core/gemini.py
# =====================================================================


class _FnCall:
    def __init__(self, name: str, args: dict) -> None:
        self.name = name
        self.args = args


class _Part:
    def __init__(self, *, text=None, function_call=None) -> None:
        self.text = text
        self.function_call = function_call


class _Content:
    def __init__(self, parts: list) -> None:
        self.parts = parts


class _Candidate:
    def __init__(self, content: _Content) -> None:
        self.content = content


class _Response:
    def __init__(self, candidates: list) -> None:
        self.candidates = candidates


class _Model:
    def __init__(self, name: str, display_name=None) -> None:
        self.name = name
        self.display_name = display_name


class _FakeModels:
    def __init__(self, response, listing, stream=None) -> None:
        self._response = response
        self._listing = listing
        self._stream = stream or []
        self.last: dict | None = None
        self.stream_last: dict | None = None

    def generate_content(self, **kwargs):
        self.last = kwargs
        return self._response

    def generate_content_stream(self, **kwargs):
        self.stream_last = kwargs
        return self._stream

    def list(self):
        return self._listing


class FakeGemini:
    def __init__(self, response, listing=None, stream=None) -> None:
        self.models = _FakeModels(response, listing or [], stream=stream)


class TestGeminiToGemini:
    def test_bad_json_tool_arguments_default_to_empty_dict(self) -> None:
        # Lines 86-90.
        _, contents = _to_gemini(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"function": {"name": "read_file", "arguments": "not-json"}}],
                }
            ]
        )
        assert contents[0]["parts"][0]["function_call"]["args"] == {}

    def test_assistant_with_no_text_and_no_tool_calls_gets_empty_text_part(self) -> None:
        # Lines 92-93: Gemini rejects empty content -> synthesize {"text": ""}.
        _, contents = _to_gemini([{"role": "assistant", "content": ""}])
        assert contents[0] == {"role": "model", "parts": [{"text": ""}]}

    def test_orphan_tool_result_defaults_name_to_tool(self) -> None:
        # Line 96: pending_names empty -> "tool".
        _, contents = _to_gemini([{"role": "tool", "content": "orphan"}])
        fr = contents[0]["parts"][0]["function_response"]
        assert fr["name"] == "tool"
        assert fr["response"] == {"result": "orphan"}


class TestGeminiCoerceArgs:
    def test_falsy_raw_returns_empty_dict(self) -> None:
        # Line 131-132.
        assert _coerce_args(None) == {}
        assert _coerce_args({}) == {}
        assert _coerce_args("") == {}

    def test_uncoercible_raw_returns_empty_dict(self) -> None:
        # Lines 133-136: dict(raw) raises TypeError/ValueError -> {}.
        assert _coerce_args(42) == {}
        assert _coerce_args("not-a-mapping") == {}

    def test_valid_mapping_like_object_is_coerced(self) -> None:
        assert _coerce_args({"a": 1}) == {"a": 1}
        assert _coerce_args([("a", 1), ("b", 2)]) == {"a": 1, "b": 2}


class TestGeminiParseOutput:
    def test_empty_candidates_returns_empty_assistant(self) -> None:
        assert _gemini_parse_output(_Response([])) == {"role": "assistant", "content": ""}

    def test_none_content_yields_no_parts(self) -> None:
        candidate = _Candidate(None)
        assert _gemini_parse_output(_Response([candidate])) == {"role": "assistant", "content": ""}


class TestGeminiStreamTextFromGemini:
    def test_chunk_without_text_attr_falls_back_to_parse_output(self) -> None:
        # Lines 176-182: `_stream_text_from_gemini` falls back to parsing the
        # whole chunk via `_parse_output` when `.text` is falsy but the chunk
        # carries function_call-free text content nested in candidates.
        chunk = _Response([_Candidate(_Content([_Part(text="fallback-text")]))])
        # Force `.text` attribute lookup on the top-level chunk to be absent by
        # using an object that has no `text` attribute at all (only candidates).
        assert not hasattr(chunk, "text")
        assert list(_stream_text_from_gemini([chunk])) == ["fallback-text"]

    def test_chunk_with_neither_text_nor_content_yields_nothing(self) -> None:
        chunk = _Response([])
        assert list(_stream_text_from_gemini([chunk])) == []

    def test_none_chunks_iterable_yields_nothing(self) -> None:
        assert list(_stream_text_from_gemini(None)) == []


class TestGeminiStreamFromGemini:
    def test_full_tool_call_accumulation_via_candidates_path(self) -> None:
        # Lines 192-224: chunks with no top-level `.text` but candidates/parts
        # carrying both text and function_call parts.
        chunk1 = _Response([_Candidate(_Content([_Part(text="Let me "), _Part(text="check.")]))])
        chunk2 = _Response(
            [_Candidate(_Content([_Part(function_call=_FnCall("read_file", {"path": "a.py"}))]))]
        )
        items = list(_stream_from_gemini([chunk1, chunk2]))
        text_items = [i for i in items if isinstance(i, str)]
        finished = [i for i in items if isinstance(i, StreamFinished)]
        assert text_items == ["Let me ", "check."]
        assert len(finished) == 1
        assert finished[0].tool_calls == [
            {"id": None, "function": {"name": "read_file", "arguments": {"path": "a.py"}}}
        ]
        assert finished[0].content == "Let me check."

    def test_chunk_with_top_level_text_attribute_short_circuits_candidate_parsing(self) -> None:
        # Lines 195-199: `.text` truthy on the chunk itself -> yields and `continue`s
        # (skips candidate/function_call parsing for that chunk).
        class _TextChunk:
            text = "direct"

        items = list(_stream_from_gemini([_TextChunk()]))
        text_items = [i for i in items if isinstance(i, str)]
        assert text_items == ["direct"]

    def test_chunk_with_no_candidates_is_skipped(self) -> None:
        # Lines 201-203: `if not candidates: continue`.
        empty_chunk = _Response([])
        items = list(_stream_from_gemini([empty_chunk]))
        assert len(items) == 1
        assert isinstance(items[0], StreamFinished)
        assert items[0].content == ""

    def test_none_chunks_iterable_yields_only_stream_finished(self) -> None:
        items = list(_stream_from_gemini(None))
        assert len(items) == 1
        assert isinstance(items[0], StreamFinished)
        assert items[0].tool_calls == []
        assert items[0].content == ""


class TestGeminiClientChat:
    def test_chat_logs_privacy_filter_when_redaction_occurred(self, caplog) -> None:
        # Line 282-286.
        fake = FakeGemini(_Response([_Candidate(_Content([_Part(text="ok")]))]))
        client = GeminiClient(project="p", client=fake)
        with caplog.at_level("INFO"):
            client.chat([{"role": "user", "content": r"C:\Users\kumar\secrets.txt"}])
        assert any("privacy filter applied" in rec.message for rec in caplog.records)


class TestGeminiClientStreamChat:
    def test_stream_chat_includes_system_instruction_and_tools(self) -> None:
        # Line 349-355.
        fake = FakeGemini(None, stream=[])
        client = GeminiClient(project="p", client=fake)
        list(
            client.stream_chat(
                [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
                tools=[{"function": {"name": "t", "description": "d", "parameters": {}}}],
            )
        )
        assert fake.models.stream_last["config"]["system_instruction"] == "sys"
        assert "tools" in fake.models.stream_last["config"]

    def test_stream_chat_logs_privacy_filter_when_redaction_occurred(self, caplog) -> None:
        # Line 341-342.
        fake = FakeGemini(None, stream=[])
        client = GeminiClient(project="p", client=fake)
        with caplog.at_level("INFO"):
            list(client.stream_chat([{"role": "user", "content": r"C:\Users\kumar\secrets.txt"}]))
        assert any("privacy filter applied" in rec.message for rec in caplog.records)

    def test_stream_chat_wraps_provider_failure_as_llm_error(self) -> None:
        # Lines 357-374.
        class _BoomModels:
            def generate_content_stream(self, **kwargs):
                raise RuntimeError("ResourceExhausted")

        class _BoomClient:
            def __init__(self) -> None:
                self.models = _BoomModels()

        client = GeminiClient(model="m", project="p", client=_BoomClient())
        with pytest.raises(LLMError, match="generate_content_stream failed"):
            list(client.stream_chat([{"role": "user", "content": "hi"}]))


class TestGeminiClientStreamChatWithTools:
    def test_stream_chat_with_tools_happy_path(self) -> None:
        # Lines 389-412: full happy path.
        fake = FakeGemini(
            None,
            stream=[
                _Response([_Candidate(_Content([_Part(text="hi")]))]),
            ],
        )
        client = GeminiClient(project="p", client=fake)
        items = list(
            client.stream_chat_with_tools(
                [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
                tools=[{"function": {"name": "t", "description": "d", "parameters": {}}}],
            )
        )
        assert "hi" in items
        assert isinstance(items[-1], StreamFinished)
        assert fake.models.stream_last["config"]["system_instruction"] == "sys"
        assert "tools" in fake.models.stream_last["config"]

    def test_stream_chat_with_tools_logs_privacy_filter_when_redaction_occurred(self, caplog) -> None:
        # Line 390-391.
        fake = FakeGemini(None, stream=[])
        client = GeminiClient(project="p", client=fake)
        with caplog.at_level("INFO"):
            list(
                client.stream_chat_with_tools(
                    [{"role": "user", "content": r"C:\Users\kumar\secrets.txt"}]
                )
            )
        assert any("privacy filter applied" in rec.message for rec in caplog.records)

    def test_stream_chat_with_tools_wraps_provider_failure_as_llm_error(self) -> None:
        # Lines 406-423.
        class _BoomModels:
            def generate_content_stream(self, **kwargs):
                raise RuntimeError("PermissionDenied")

        class _BoomClient:
            def __init__(self) -> None:
                self.models = _BoomModels()

        client = GeminiClient(model="m", project="p", client=_BoomClient())
        with pytest.raises(LLMError, match="stream_chat_with_tools failed"):
            list(client.stream_chat_with_tools([{"role": "user", "content": "hi"}]))


class TestGeminiListModelsEmpty:
    def test_list_models_empty_listing_falls_back_to_curated(self) -> None:
        # Line 421 + 433-434: discovery returns [] -> CURATED_MODELS.
        from aios.core.gemini import CURATED_MODELS

        client = GeminiClient(project="p", client=FakeGemini(None, listing=[]))
        assert client.list_models() == CURATED_MODELS


class TestGeminiDiscoverModels:
    def test_discover_models_reads_name_from_dict_entries(self) -> None:
        # Lines 445-447: `if name is None and isinstance(m, dict): name = m.get("name")`.
        listing = [{"name": "publishers/google/models/gemini-2.0-flash"}]
        client = GeminiClient(project="p", client=FakeGemini(None, listing=listing))
        ids = [m["id"] for m in client.list_models()]
        assert "gemini-2.0-flash" in ids

    def test_discover_models_skips_entries_with_no_name_at_all(self) -> None:
        listing = [{"no_name_key": "x"}]
        client = GeminiClient(project="p", client=FakeGemini(None, listing=listing))
        from aios.core.gemini import CURATED_MODELS

        assert client.list_models() == CURATED_MODELS

    def test_discover_models_dedups_repeated_ids(self) -> None:
        # Line 449-453: `if ... mid in seen: continue` + seen.add(mid).
        listing = [
            _Model("publishers/google/models/gemini-2.0-flash", "Flash"),
            _Model("publishers/google/models/gemini-2.0-flash", "Flash Dup"),
        ]
        client = GeminiClient(project="p", client=FakeGemini(None, listing=listing))
        ids = [m["id"] for m in client.list_models()]
        assert ids.count("gemini-2.0-flash") == 1

    def test_discover_models_uses_fallback_display_when_no_display_name(self) -> None:
        listing = [_Model("publishers/google/models/gemini-2.0-flash", None)]
        client = GeminiClient(project="p", client=FakeGemini(None, listing=listing))
        names = [m["name"] for m in client.list_models()]
        assert "Google gemini-2.0-flash" in names


# =====================================================================
# aios/core/openai_compat.py
# =====================================================================


class _FakeHTTPResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _json_response(body: dict) -> _FakeHTTPResponse:
    return _FakeHTTPResponse(json.dumps(body).encode("utf-8"))


class TestOpenAIParseOutput:
    def test_bad_json_tool_call_arguments_default_to_empty_dict(self) -> None:
        # Lines 100-105: json.loads raises JSONDecodeError -> args = {}.
        message = {
            "content": "",
            "tool_calls": [
                {"id": "c1", "function": {"name": "read_file", "arguments": "not-json"}}
            ],
        }
        parsed = _openai_parse_output(message)
        assert parsed["tool_calls"][0]["function"]["arguments"] == {}

    def test_non_dict_tool_call_entries_are_skipped(self) -> None:
        message = {"content": "hi", "tool_calls": ["not-a-dict"]}
        parsed = _openai_parse_output(message)
        assert parsed == {"role": "assistant", "content": "hi"}

    def test_empty_string_arguments_becomes_empty_dict_without_json_loads_error(self) -> None:
        message = {
            "content": "",
            "tool_calls": [{"id": "c2", "function": {"name": "f", "arguments": ""}}],
        }
        parsed = _openai_parse_output(message)
        assert parsed["tool_calls"][0]["function"]["arguments"] == {}


class TestOpenAICompatPostErrorPaths:
    def test_http_error_with_unreadable_body_still_raises_llm_error(self) -> None:
        # Lines 158-163: exc.read() raising is swallowed -> detail stays "".
        class _ExplodingHTTPError(urllib.error.HTTPError):
            def read(self):
                raise RuntimeError("body unavailable")

        client = OpenAICompatClient(api_key="k", base_url="http://localhost/v1")
        err = _ExplodingHTTPError("url", 500, "boom", {}, BytesIO(b""))
        with patch("urllib.request.urlopen", side_effect=err):
            with pytest.raises(LLMError, match="HTTP 500"):
                client.complete("hi")

    def test_non_json_response_raises_llm_error(self) -> None:
        # Lines 171-172.
        client = OpenAICompatClient(api_key="k", base_url="http://localhost/v1")
        with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(b"<html>oops</html>")):
            with pytest.raises(LLMError, match="non-JSON"):
                client.complete("hi")


class TestOpenAICompatComplete:
    def test_complete_includes_system_message_when_given(self) -> None:
        # Line 181-182.
        captured: dict = {}

        def fake_urlopen(request, timeout=None):
            captured["payload"] = json.loads(request.data.decode())
            return _json_response({"choices": [{"message": {"content": "hi"}}]})

        client = OpenAICompatClient(api_key="k", base_url="http://localhost/v1")
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.complete("prompt", system="be brief")
        assert captured["payload"]["messages"][0] == {"role": "system", "content": "be brief"}

    def test_complete_returns_empty_string_when_no_choices(self) -> None:
        # Line 194-195.
        client = OpenAICompatClient(api_key="k", base_url="http://localhost/v1")
        with patch("urllib.request.urlopen", return_value=_json_response({"choices": []})):
            assert client.complete("hi") == ""


class TestOpenAICompatClientChat:
    def test_chat_logs_privacy_filter_when_redaction_occurred(self, caplog) -> None:
        # Line 216-217.
        client = OpenAICompatClient(api_key="k", base_url="http://localhost/v1")
        with patch(
            "urllib.request.urlopen",
            return_value=_json_response({"choices": [{"message": {"content": "ok"}}]}),
        ):
            with caplog.at_level("INFO"):
                client.chat([{"role": "user", "content": r"C:\Users\kumar\secrets.txt"}])
        assert any("privacy filter applied" in rec.message for rec in caplog.records)

    def test_chat_returns_empty_assistant_when_no_choices(self) -> None:
        # Line 231-232.
        client = OpenAICompatClient(api_key="k", base_url="http://localhost/v1")
        with patch("urllib.request.urlopen", return_value=_json_response({"choices": []})):
            out = client.chat([{"role": "user", "content": "hi"}])
        assert out == {"role": "assistant", "content": ""}

    def test_chat_returns_empty_assistant_when_message_is_not_a_dict(self) -> None:
        # Line 234-235.
        client = OpenAICompatClient(api_key="k", base_url="http://localhost/v1")
        with patch(
            "urllib.request.urlopen",
            return_value=_json_response({"choices": [{"message": ["not-a-dict"]}]}),
        ):
            out = client.chat([{"role": "user", "content": "hi"}])
        assert out == {"role": "assistant", "content": ""}


class TestOpenAICompatStreamChat:
    def _sse_lines_response(self, lines: list[str]):
        class _Stream:
            def __init__(self, encoded: list[bytes]) -> None:
                self._lines = encoded

            def __iter__(self):
                return iter(self._lines)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return _Stream([line.encode("utf-8") for line in lines])

    def test_stream_chat_full_sse_loop_parses_and_ignores_noise(self) -> None:
        # Lines 255-294: the entire SSE parsing body — blank lines, non-data
        # lines, malformed JSON, empty-choices chunks, missing delta content,
        # and the [DONE] sentinel.
        lines = [
            "",
            "event: ping",
            "data:",
            "data: not-json",
            'data: {"choices": []}',
            'data: {"choices": [{"delta": {}}]}',
            'data: {"choices": [{"delta": {"content": "Hel"}}]}',
            'data: {"choices": [{"delta": {"content": ""}}]}',
            'data: {"choices": [{"delta": {"content": "lo"}}]}',
            "data: [DONE]",
            'data: {"choices": [{"delta": {"content": "unreachable"}}]}',
        ]
        captured: dict = {}

        def fake_urlopen(request, timeout=None):
            captured["payload"] = json.loads(request.data.decode())
            return self._sse_lines_response(lines)

        client = OpenAICompatClient(api_key="k", base_url="http://localhost/v1")
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            chunks = list(
                client.stream_chat(
                    [{"role": "user", "content": "hi"}],
                    tools=[{"type": "function", "function": {"name": "t"}}],
                )
            )
        assert chunks == ["Hel", "lo"]
        assert captured["payload"]["stream"] is True
        assert captured["payload"]["tools"][0]["function"]["name"] == "t"

    def test_stream_chat_logs_privacy_filter_when_redaction_occurred(self, caplog) -> None:
        # Line 256-257.
        client = OpenAICompatClient(api_key="k", base_url="http://localhost/v1")
        with patch("urllib.request.urlopen", return_value=self._sse_lines_response([])):
            with caplog.at_level("INFO"):
                list(client.stream_chat([{"role": "user", "content": r"C:\Users\kumar\secrets.txt"}]))
        assert any("privacy filter applied" in rec.message for rec in caplog.records)

    def test_stream_chat_omits_tools_key_when_not_given(self) -> None:
        captured: dict = {}

        def fake_urlopen(request, timeout=None):
            captured["payload"] = json.loads(request.data.decode())
            return self._sse_lines_response([])

        client = OpenAICompatClient(api_key="k", base_url="http://localhost/v1")
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            list(client.stream_chat([{"role": "user", "content": "hi"}]))
        assert "tools" not in captured["payload"]

    def test_stream_chat_http_error_maps_to_llm_error(self) -> None:
        # Lines 295-305.
        client = OpenAICompatClient(api_key="k", base_url="http://localhost/v1")
        err = urllib.error.HTTPError("url", 429, "slow", {}, BytesIO(b"rate limited"))
        with patch("urllib.request.urlopen", side_effect=err):
            with pytest.raises(LLMError, match="HTTP 429"):
                list(client.stream_chat([{"role": "user", "content": "hi"}]))

    def test_stream_chat_http_error_with_unreadable_body(self) -> None:
        class _ExplodingHTTPError(urllib.error.HTTPError):
            def read(self):
                raise RuntimeError("body unavailable")

        client = OpenAICompatClient(api_key="k", base_url="http://localhost/v1")
        err = _ExplodingHTTPError("url", 503, "down", {}, BytesIO(b""))
        with patch("urllib.request.urlopen", side_effect=err):
            with pytest.raises(LLMError, match="HTTP 503"):
                list(client.stream_chat([{"role": "user", "content": "hi"}]))

    def test_stream_chat_network_error_maps_to_llm_error(self) -> None:
        # Lines 306-308.
        client = OpenAICompatClient(api_key="k", base_url="http://localhost/v1")
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            with pytest.raises(LLMError, match="stream to"):
                list(client.stream_chat([{"role": "user", "content": "hi"}]))


# =====================================================================
# aios/core/failover.py
# =====================================================================


class OK:
    """A client that succeeds and echoes the model/messages it was handed."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = 0
        self.seen_messages: list[Any] = []

    def chat(self, messages, *, tools=None, model=None):
        self.calls += 1
        self.seen_messages.append(messages)
        return {"role": "assistant", "content": self.reply, "_model": model}


class Boom:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, *, tools=None, model=None):
        self.calls += 1
        raise LLMError("provider down")


MSG = [{"role": "user", "content": "hi"}]
SECRET_MSG = [{"role": "user", "content": r"C:\Users\kumar\secrets.txt"}]


class TestFailoverChatUnknownProviderAndPrivacyLog:
    def test_unknown_provider_name_is_treated_as_local(self) -> None:
        # Line 130-132: an unrecognized provider name falls into local_indices,
        # which means it will NOT be skipped for H9 purposes and no privacy
        # filtering is applied to the messages it receives.
        weird = OK("served-by-weird")
        fc = FailoverChatClient([(weird, "m1", "some-custom-provider")])
        out = fc.chat(MSG)
        assert out["content"] == "served-by-weird"
        # No cloud candidate present -> raw messages passed through untouched.
        assert weird.seen_messages[0] is MSG

    def test_chat_logs_privacy_filter_when_cloud_candidate_and_redaction_occurred(self, caplog) -> None:
        # Line 138-144.
        cloud = OK("cloud-reply")
        fc = FailoverChatClient([(cloud, "m1", "bedrock")])
        with caplog.at_level("INFO"):
            fc.chat(SECRET_MSG)
        assert any("Failover privacy filter applied" in rec.message for rec in caplog.records)

    def test_cloud_candidate_receives_filtered_messages_not_raw(self) -> None:
        # Line 171: `use_messages = filtered_messages if i in cloud_indices else messages`.
        cloud = OK("cloud-reply")
        fc = FailoverChatClient([(cloud, "m1", "bedrock")])
        fc.chat(SECRET_MSG)
        sent = cloud.seen_messages[0]
        assert sent is not SECRET_MSG
        assert r"C:\Users\kumar\secrets.txt" not in sent[0]["content"]


class TestFailoverChatOnFailoverHookSwallowsExceptions:
    def test_hook_exception_does_not_propagate_and_does_not_block_success(self) -> None:
        # Lines 181-187: `on_failover` raising is caught and ignored.
        def bad_hook(fp, fm, np, nm, e):
            raise RuntimeError("hook bug")

        bad, good = Boom(), OK("served")
        fc = FailoverChatClient([(bad, "m1", "gemini"), (good, "m2", "bedrock")], on_failover=bad_hook)
        out = fc.chat(MSG)  # must not raise despite the hook's RuntimeError
        assert out["content"] == "served"
        assert fc.active_provider == "bedrock"


class TestFailoverStreamChatToolsDelegatesToChat:
    def test_stream_chat_with_tools_argument_delegates_to_chat_and_yields_content(self) -> None:
        # Lines 213-218: `if tools: result = self.chat(...); yield content`.
        good = OK("tool-delegated-reply")
        fc = FailoverChatClient([(good, "m1", "ollama")])
        chunks = list(fc.stream_chat(MSG, tools=[{"function": {"name": "t"}}]))
        assert chunks == ["tool-delegated-reply"]
        assert good.calls == 1

    def test_stream_chat_with_tools_argument_and_empty_content_yields_nothing(self) -> None:
        empty = OK("")
        fc = FailoverChatClient([(empty, "m1", "ollama")])
        chunks = list(fc.stream_chat(MSG, tools=[{"function": {"name": "t"}}]))
        assert chunks == []


class StreamOK:
    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks
        self.calls = 0
        self.models: list[str | None] = []
        self.seen_messages: list[Any] = []

    def stream_chat(self, messages, *, tools=None, model=None):
        self.calls += 1
        self.models.append(model)
        self.seen_messages.append(messages)
        yield from self.chunks

    def chat(self, messages, *, tools=None, model=None):
        raise AssertionError("streaming path should not call chat")


class StreamBoom:
    def __init__(self) -> None:
        self.calls = 0

    def stream_chat(self, messages, *, tools=None, model=None):
        self.calls += 1
        raise LLMError("stream provider down")


class NonStreamingOK:
    """A candidate with only `chat()` — no `stream_chat` method at all."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = 0

    def chat(self, messages, *, tools=None, model=None):
        self.calls += 1
        return {"role": "assistant", "content": self.reply}


class TestFailoverStreamChatNoToolsPath:
    def test_provider_classification_and_privacy_log_for_no_tools_stream(self, caplog) -> None:
        # Lines 223-241: classification loop + privacy pre-filter + info log.
        cloud = StreamOK(["cloud", "-stream"])
        fc = FailoverChatClient([(cloud, "m1", "gemini")])
        with caplog.at_level("INFO"):
            chunks = list(fc.stream_chat(SECRET_MSG))
        assert chunks == ["cloud", "-stream"]
        assert any("Failover privacy filter applied" in rec.message for rec in caplog.records)
        sent = cloud.seen_messages[0]
        assert r"C:\Users\kumar\secrets.txt" not in sent[0]["content"]

    def test_h9_skips_second_cloud_provider_when_local_fallback_exists(self) -> None:
        # Lines 246-253: different cloud provider skipped in favor of local.
        bad_cloud = StreamBoom()
        other_cloud = StreamOK(["should-not-run"])
        local = StreamOK(["local-served"])
        fc = FailoverChatClient(
            [(bad_cloud, "g1", "gemini"), (other_cloud, "b1", "bedrock"), (local, "l1", "ollama")]
        )
        chunks = list(fc.stream_chat(MSG))
        assert chunks == ["local-served"]
        assert other_cloud.calls == 0
        assert local.calls == 1

    def test_no_local_fallback_logs_warning_and_tries_additional_cloud_provider(self, caplog) -> None:
        # Line 254-257 (the warning branch when has_local_fallback is False).
        bad_cloud = StreamBoom()
        other_cloud = StreamOK(["desperate-cloud-served"])
        fc = FailoverChatClient([(bad_cloud, "g1", "gemini"), (other_cloud, "b1", "bedrock")])
        with caplog.at_level("WARNING"):
            chunks = list(fc.stream_chat(MSG))
        assert chunks == ["desperate-cloud-served"]
        assert any("no local fallback available" in rec.message for rec in caplog.records)

    def test_streaming_candidate_success_fires_failover_hook_and_yields_all_chunks(self) -> None:
        # Lines 264-288: streaming candidate branch — first chunk + hook + remaining chunks.
        events: list[tuple[str, str, str, str]] = []
        bad = StreamBoom()
        good = StreamOK(["a", "b", "c"])
        fc = FailoverChatClient(
            [(bad, "m1", "bedrock"), (good, "m2", "ollama")],
            on_failover=lambda fp, fm, np, nm, e: events.append((fp, fm, np, nm)),
        )
        chunks = list(fc.stream_chat(MSG))
        assert chunks == ["a", "b", "c"]
        assert events == [("bedrock", "m1", "ollama", "m2")]
        assert fc.active_provider == "ollama" and fc.active_model == "m2"

    def test_streaming_candidate_with_falsy_first_chunk_is_not_yielded(self) -> None:
        # Line 283: `if first: yield str(first)` — falsy first chunk skipped.
        good = StreamOK(["", "real-chunk"])
        fc = FailoverChatClient([(good, "m1", "ollama")])
        chunks = list(fc.stream_chat(MSG))
        assert chunks == ["real-chunk"]

    def test_streaming_candidate_with_no_chunks_at_all_yields_nothing(self) -> None:
        good = StreamOK([])
        fc = FailoverChatClient([(good, "m1", "ollama")])
        assert list(fc.stream_chat(MSG)) == []

    def test_non_streaming_candidate_falls_back_to_chat_and_yields_content(self) -> None:
        # Lines 290-305: candidate has no `stream_chat` -> falls back to `.chat()`.
        good = NonStreamingOK("fallback-content")
        fc = FailoverChatClient([(good, "m1", "ollama")])
        chunks = list(fc.stream_chat(MSG))
        assert chunks == ["fallback-content"]
        assert good.calls == 1

    def test_non_streaming_candidate_fallback_fires_failover_hook(self) -> None:
        events: list[tuple[str, str, str, str]] = []
        bad = StreamBoom()
        good = NonStreamingOK("fallback-after-failover")
        fc = FailoverChatClient(
            [(bad, "m1", "gemini"), (good, "m2", "ollama")],
            on_failover=lambda fp, fm, np, nm, e: events.append((fp, fm, np, nm)),
        )
        chunks = list(fc.stream_chat(MSG))
        assert chunks == ["fallback-after-failover"]
        assert events == [("gemini", "m1", "ollama", "m2")]

    def test_non_streaming_candidate_with_empty_content_yields_nothing(self) -> None:
        good = NonStreamingOK("")
        fc = FailoverChatClient([(good, "m1", "ollama")])
        assert list(fc.stream_chat(MSG)) == []

    def test_stream_chat_llmerror_advances_index_and_records_error(self) -> None:
        # Lines 306-308.
        bad, good = StreamBoom(), StreamOK(["ok"])
        fc = FailoverChatClient([(bad, "m1", "bedrock"), (good, "m2", "ollama")])
        list(fc.stream_chat(MSG))
        assert bad.calls == 1

    def test_stream_chat_all_candidates_failing_raises_llmerror(self) -> None:
        # Lines 310-311.
        fc = FailoverChatClient([(StreamBoom(), "a", "gemini"), (StreamBoom(), "b", "bedrock")])
        with pytest.raises(LLMError, match="all 2 model candidate"):
            list(fc.stream_chat(MSG))


class FakeStreamingWithToolsClient:
    def __init__(
        self,
        chunks: list[str | StreamFinished],
        *,
        raise_on: Optional[Exception] = None,
    ) -> None:
        self._chunks = chunks
        self._raise_on = raise_on
        self.seen_messages: list[Any] = []

    def chat(self, messages, *, tools=None, model=None):
        if self._raise_on:
            raise self._raise_on
        return {"role": "assistant", "content": "fallback", "tool_calls": []}

    def stream_chat_with_tools(self, messages, *, tools=None, model=None):
        self.seen_messages.append(messages)
        if self._raise_on:
            raise self._raise_on
        yield from self._chunks


class NonStreamingToolsClient:
    """No `stream_chat_with_tools` — forces the chat() fallback branch."""

    def __init__(self, response: dict) -> None:
        self._response = response
        self.calls = 0

    def chat(self, messages, *, tools=None, model=None):
        self.calls += 1
        return self._response


class TestFailoverStreamChatWithToolsGaps:
    def test_privacy_log_for_stream_chat_with_tools(self, caplog) -> None:
        # Line 344-350.
        cloud = FakeStreamingWithToolsClient([StreamFinished(tool_calls=[], content="")])
        fc = FailoverChatClient([(cloud, "m1", "bedrock")])
        with caplog.at_level("INFO"):
            list(fc.stream_chat_with_tools(SECRET_MSG))
        assert any("Failover privacy filter applied" in rec.message for rec in caplog.records)
        sent = cloud.seen_messages[0]
        assert r"C:\Users\kumar\secrets.txt" not in sent[0]["content"]

    def test_h9_skip_and_warning_in_stream_chat_with_tools_no_local_fallback(self, caplog) -> None:
        # Lines 357-366: H9 skip logic + warning when no local fallback exists.
        bad_cloud = FakeStreamingWithToolsClient([], raise_on=LLMError("gemini down"))
        other_cloud = FakeStreamingWithToolsClient(
            [StreamFinished(tool_calls=[], content="served")]
        )
        fc = FailoverChatClient([(bad_cloud, "g1", "gemini"), (other_cloud, "b1", "bedrock")])
        with caplog.at_level("WARNING"):
            result = list(fc.stream_chat_with_tools(MSG))
        finished = [r for r in result if isinstance(r, StreamFinished)]
        assert finished[0].content == "served"
        assert any("no local fallback available" in rec.message for rec in caplog.records)

    def test_h9_skips_different_cloud_provider_when_local_exists_stream_with_tools(self) -> None:
        bad_cloud = FakeStreamingWithToolsClient([], raise_on=LLMError("gemini down"))
        other_cloud = FakeStreamingWithToolsClient([StreamFinished(tool_calls=[], content="never")])
        local = FakeStreamingWithToolsClient([StreamFinished(tool_calls=[], content="local-served")])
        fc = FailoverChatClient(
            [(bad_cloud, "g1", "gemini"), (other_cloud, "b1", "bedrock"), (local, "l1", "ollama")]
        )
        result = list(fc.stream_chat_with_tools(MSG))
        finished = [r for r in result if isinstance(r, StreamFinished)][0]
        assert finished.content == "local-served"

    def test_streaming_candidate_yields_none_first_chunk_without_erroring(self) -> None:
        # Line 392-393: `if first is not None: yield first` — falsy-but-not-None
        # first item (e.g. empty string) IS yielded here (unlike stream_chat's
        # `if first:` check), and None-sentinel items are filtered downstream.
        chunks: list[str | StreamFinished] = ["", StreamFinished(tool_calls=[], content="")]
        client = FakeStreamingWithToolsClient(chunks)
        fc = FailoverChatClient([(client, "m1", "bedrock")])
        result = list(fc.stream_chat_with_tools(MSG))
        text_items = [r for r in result if isinstance(r, str)]
        assert text_items == [""]

    def test_streaming_candidate_skips_none_chunks_in_remainder(self) -> None:
        # Line 394-396: `for chunk in iterator: if chunk is not None: yield chunk`.
        chunks: list[Any] = ["first", None, "third", StreamFinished(tool_calls=[], content="x")]
        client = FakeStreamingWithToolsClient(chunks)
        fc = FailoverChatClient([(client, "m1", "bedrock")])
        result = list(fc.stream_chat_with_tools(MSG))
        text_items = [r for r in result if isinstance(r, str)]
        assert text_items == ["first", "third"]

    def test_non_streaming_fallback_yields_content_then_stream_finished(self) -> None:
        # Lines 399-417: no `stream_chat_with_tools` -> use `chat()`.
        response = {"role": "assistant", "content": "chat-fallback", "tool_calls": []}
        client = NonStreamingToolsClient(response)
        fc = FailoverChatClient([(client, "m1", "ollama")])
        result = list(fc.stream_chat_with_tools(MSG))
        text_items = [r for r in result if isinstance(r, str)]
        finished = [r for r in result if isinstance(r, StreamFinished)]
        assert text_items == ["chat-fallback"]
        assert len(finished) == 1
        assert finished[0].content == "chat-fallback"
        assert client.calls == 1

    def test_non_streaming_fallback_with_tool_calls_does_not_yield_content_text(self) -> None:
        # Line 414: `if content and not tool_calls: yield content` — when
        # tool_calls are present, content text is NOT yielded as a chunk (only
        # inside StreamFinished), avoiding double-delivery to the agent loop.
        tool_calls = [{"id": "x", "function": {"name": "read_file", "arguments": {}}}]
        response = {"role": "assistant", "content": "text-plus-tools", "tool_calls": tool_calls}
        client = NonStreamingToolsClient(response)
        fc = FailoverChatClient([(client, "m1", "ollama")])
        result = list(fc.stream_chat_with_tools(MSG))
        text_items = [r for r in result if isinstance(r, str)]
        finished = [r for r in result if isinstance(r, StreamFinished)]
        assert text_items == []
        assert finished[0].tool_calls == tool_calls
        assert finished[0].content == "text-plus-tools"

    def test_non_streaming_fallback_fires_failover_hook_on_provider_switch(self) -> None:
        events: list[tuple[str, str, str, str]] = []
        bad = FakeStreamingWithToolsClient([], raise_on=LLMError("down"))
        good = NonStreamingToolsClient({"role": "assistant", "content": "ok", "tool_calls": []})
        fc = FailoverChatClient(
            [(bad, "m1", "gemini"), (good, "m2", "ollama")],
            on_failover=lambda fp, fm, np, nm, e: events.append((fp, fm, np, nm)),
        )
        list(fc.stream_chat_with_tools(MSG))
        assert events == [("gemini", "m1", "ollama", "m2")]

    def test_all_candidates_fail_raises_llmerror_with_stream_with_tools_label(self) -> None:
        bad1 = FakeStreamingWithToolsClient([], raise_on=LLMError("err1"))
        bad2 = FakeStreamingWithToolsClient([], raise_on=LLMError("err2"))
        fc = FailoverChatClient([(bad1, "m1", "bedrock"), (bad2, "m2", "ollama")])
        with pytest.raises(LLMError, match="stream_with_tools"):
            list(fc.stream_chat_with_tools(MSG))


class TestFailoverListModels:
    def test_list_models_delegates_to_primary_candidate(self) -> None:
        # Line 425-427.
        class ListingClient:
            def list_models(self):
                return [{"id": "m1", "name": "Model One"}]

            def chat(self, *a, **kw):  # pragma: no cover - unused in this test
                raise AssertionError

        fc = FailoverChatClient([(ListingClient(), "m1", "ollama"), (OK("x"), "m2", "bedrock")])
        assert fc.list_models() == [{"id": "m1", "name": "Model One"}]
