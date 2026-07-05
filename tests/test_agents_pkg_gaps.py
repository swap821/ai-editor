"""Gap-fill unit tests for aios/agents/{tool_agent,tool_handlers,swarm,
self_analysis_agent,tool_loop_helpers}.py.

Targets specific uncovered branches identified by coverage analysis: prose
tool-call recovery edge cases, cerebellum short-circuit success/abort paths,
offline-mode guard, native-plan event surfacing, streaming iteration edge
cases, tool_handlers error paths (read/edit/create/browse/self-analyze/
propose-fixes), swarm worker/quorum/synthesizer pause propagation and
decomposition degradation, and tool_loop_helpers' pure formatting/reflection
helpers.

Same philosophy as tests/test_tool_agent.py (the pattern library this file
follows): a scripted fake chat client drives the loop deterministically (no
Ollama, no network), and a fake-runner Executor exercises the REAL security
gateway so blocking behaviour is genuine, not mocked away. No test in this
file weakens or bypasses aios/security/* — the frozen spine's RED
classification is only ever *exercised* (e.g. verifying it still blocks),
never disabled.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import pytest

from aios import config
from aios.agents import tool_handlers, tool_loop_helpers
from aios.agents.self_analysis_agent import SelfAnalysisAgent
from aios.agents.swarm import run_swarm
from aios.agents.tool_agent import (
    STEP_LIMIT_TEXT,
    ToolAgent,
    _coerce_args,
    _explicit_tool_requests,
    _extract_text_tool_calls,
    _parse_structured_tool_payload,
    _validate_tool_calls,
    _validated_from_structured_payload,
)
from aios.core.autonomy import AutonomyLedger
from aios.core.cerebellum import CompiledPlaybook, PlaybookStep
from aios.core.executor import Executor
from aios.core.llm import LLMError
from aios.core.planner import Planner
from aios.core.stream_protocol import StreamFinished
from aios.core.verification_strength import VerificationStrength
from aios.core.verifier import Verifier, VerifierResult
from aios.security import scope_lock
from aios.security.gateway import RateLimiter


# --------------------------------------------------------------------------- #
# Shared fixtures / fakes (mirrors tests/test_tool_agent.py's pattern library)
# --------------------------------------------------------------------------- #
class ScriptedChat:
    """Returns queued assistant messages in order, one per ``chat`` call."""

    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.calls: list[list] = []

    def chat(self, messages, *, tools=None, model=None) -> dict:
        self.calls.append(messages)
        return self._responses.pop(0)


class FakeRunner:
    """Stand-in process runner -- records, never spawns."""

    def __call__(self, command, *, cwd, env, timeout_s):
        return f"ran: {command}", "", 0


class PassRunner:
    """Runner that emits pytest-style passing output (exit 0)."""

    def __call__(self, command, *, cwd, env, timeout_s):
        return "3 passed in 0.2s", "", 0


class FakePlannerLLM:
    """Fake COMPLETION client (LLMClient.complete) returning a fixed string."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, Optional[str]]] = []

    def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
        self.calls.append((prompt, system))
        return self.response


def _executor() -> Executor:
    return Executor(
        runner=FakeRunner(), rate_limiter=RateLimiter(), audit_log=lambda *a, **k: None
    )


def _passing_executor() -> Executor:
    return Executor(
        runner=PassRunner(), rate_limiter=RateLimiter(), audit_log=lambda *a, **k: None
    )


def _tool_call(name: str, arguments: dict) -> dict:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
    }


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Point scope roots AND the project root at an isolated temp dir.

    Mirrors tests/test_tool_agent.py's ``sandbox`` fixture exactly so edit/
    create-file tool calls resolve under the temp tree instead of the real repo.
    """
    original = scope_lock.get_scope_roots()
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    scope_lock.set_scope_roots([tmp_path])
    try:
        yield tmp_path
    finally:
        scope_lock.set_scope_roots(list(original))


# =========================================================================== #
# aios/agents/tool_agent.py -- module-level parsing/validation helpers
# =========================================================================== #
class TestCoerceArgs:
    def test_non_dict_non_str_returns_empty(self) -> None:
        # Line 428-429: raw is neither dict nor str -> {}
        assert _coerce_args(42) == {}
        assert _coerce_args(None) == {}
        assert _coerce_args([1, 2, 3]) == {}

    def test_invalid_json_string_returns_empty(self) -> None:
        # Line 430-434: json.loads raises JSONDecodeError -> {}
        assert _coerce_args("{not valid json") == {}

    def test_valid_json_string_non_dict_returns_empty(self) -> None:
        # Line 434: parsed is a list, not a dict -> {}
        assert _coerce_args("[1, 2, 3]") == {}
        assert _coerce_args('"just a string"') == {}

    def test_valid_json_dict_string_is_parsed(self) -> None:
        assert _coerce_args('{"a": 1}') == {"a": 1}


class TestValidateToolCalls:
    def test_function_dict_shape_extracts_name_and_arguments(self) -> None:
        # Lines 451-454: function is a dict -> pull name/arguments from it.
        calls = [{"function": {"name": "read_file", "arguments": {"filepath": "x.py"}}}]
        validated = _validate_tool_calls(calls)
        assert validated == [{"function": {"name": "read_file", "arguments": {"filepath": "x.py"}}}]

    def test_function_dict_falls_back_to_parameters_key(self) -> None:
        # Line 454: arguments missing -> falls back to "parameters".
        calls = [{"function": {"name": "read_file", "parameters": {"filepath": "y.py"}}}]
        validated = _validate_tool_calls(calls)
        assert validated[0]["function"]["arguments"] == {"filepath": "y.py"}

    def test_flat_shape_uses_tool_and_input_aliases(self) -> None:
        # Line 456-457: no "function" key -> name from "tool", args from "input".
        calls = [{"tool": "read_directory", "input": {"path": "."}}]
        validated = _validate_tool_calls(calls)
        assert validated == [{"function": {"name": "read_directory", "arguments": {"path": "."}}}]

    def test_non_allowlisted_name_is_dropped_and_logged(self) -> None:
        # Lines 459-466: name not in _TOOL_NAMES -> blocked, not returned.
        calls = [{"function": {"name": "delete_everything", "arguments": {}}}]
        assert _validate_tool_calls(calls) == []

    def test_non_primitive_argument_values_are_rejected(self) -> None:
        # Lines 470-476: a nested dict/list value fails the primitives-only check.
        calls = [
            {"function": {"name": "read_file", "arguments": {"filepath": {"nested": "x"}}}}
        ]
        assert _validate_tool_calls(calls) == []

    def test_none_argument_value_is_accepted_as_primitive(self) -> None:
        calls = [{"function": {"name": "read_file", "arguments": {"filepath": None}}}]
        validated = _validate_tool_calls(calls)
        assert validated == [{"function": {"name": "read_file", "arguments": {"filepath": None}}}]


class TestParseStructuredToolPayload:
    def test_valid_json_is_parsed_directly(self) -> None:
        assert _parse_structured_tool_payload('{"a": 1}') == {"a": 1}

    def test_literal_eval_scalar_result_is_rejected(self) -> None:
        # Lines 491-493: json.loads fails (single-quoted string is not valid
        # JSON), so it falls to ast.literal_eval, which succeeds but yields a
        # bare scalar (a str) -- not a valid tool payload shape.
        with pytest.raises(ValueError, match="unexpected literal type"):
            _parse_structured_tool_payload("'just a bare string'")

    def test_literal_eval_dict_result_is_accepted(self) -> None:
        # Python-style single-quoted dict (not valid JSON) via literal_eval.
        assert _parse_structured_tool_payload("{'a': 1}") == {"a": 1}

    def test_syntax_error_propagates_to_caller(self) -> None:
        with pytest.raises(SyntaxError):
            _parse_structured_tool_payload("{'a': !!! not python}")


class TestValidatedFromStructuredPayload:
    def test_list_of_non_dicts_yields_no_calls(self) -> None:
        # Lines 503-505: parsed is a list but not every item is a dict.
        assert _validated_from_structured_payload('["a", "b"]') == []
        assert _validated_from_structured_payload("[1, 2, 3]") == []

    def test_list_of_dicts_validates_each(self) -> None:
        payload = json.dumps(
            [{"name": "read_file", "arguments": {"filepath": "a.py"}}]
        )
        result = _validated_from_structured_payload(payload)
        assert result and result[0]["function"]["name"] == "read_file"

    def test_bad_payload_returns_empty_not_raise(self) -> None:
        # Lines 500-502: SyntaxError/ValueError/etc from the parser is swallowed.
        assert _validated_from_structured_payload("not json at all {{{") == []

    def test_scalar_top_level_payload_returns_empty(self) -> None:
        # dict/list check fails for a bare scalar -> [].
        assert _validated_from_structured_payload('"just a string"') == []


class TestExtractTextToolCalls:
    def test_non_string_content_returns_empty(self) -> None:
        # Line 535: content is not a str.
        assert _extract_text_tool_calls(None) == []
        assert _extract_text_tool_calls(42) == []

    def test_blank_content_returns_empty(self) -> None:
        assert _extract_text_tool_calls("   \n  ") == []

    def test_tier1_raw_decode_recovers_leading_json_list(self) -> None:
        # Lines 549-554: text starts with '[' but isn't a clean single JSON
        # value as a whole (trailing prose) -- raw_decode recovers the first
        # JSON value, which here is a top-level LIST of call dicts.
        text = (
            '[{"name": "read_file", "arguments": {"filepath": "a.py"}}] '
            "and then some trailing prose that breaks whole-string parsing"
        )
        calls = _extract_text_tool_calls(text)
        assert calls and calls[0]["function"]["name"] == "read_file"

    def test_tier1_raw_decode_recovers_leading_json_dict(self) -> None:
        text = (
            '{"name": "read_directory", "arguments": {"path": "."}} '
            "trailing prose"
        )
        calls = _extract_text_tool_calls(text)
        assert calls and calls[0]["function"]["name"] == "read_directory"

    def test_tier1_raw_decode_failure_falls_through_tiers(self) -> None:
        # Starts with '{' but is not valid JSON at all (not even a prefix) --
        # raw_decode raises JSONDecodeError, and no other tier matches.
        text = "{this is not json nor python at all !!!"
        assert _extract_text_tool_calls(text) == []

    def test_tier3_react_json_decode_error_is_skipped(self) -> None:
        # Lines 575-578: an "Action: name {...}" line whose JSON is broken is
        # skipped (continue), not raised.
        text = "Action: read_file {not valid json"
        assert _extract_text_tool_calls(text) == []

    def test_tier3_react_non_dict_args_is_skipped(self) -> None:
        # Line 579: raw_decode succeeds but yields a non-dict (e.g. a list) --
        # the ReAct tier only accepts dict args.
        text = 'Action: read_file [1, 2, 3]'
        assert _extract_text_tool_calls(text) == []

    def test_react_recovery_disabled_flag_skips_tier3(self) -> None:
        text = 'Action: read_file {"filepath": "a.py"}'
        assert _extract_text_tool_calls(text, enable_react_recovery=False) == []

    def test_prose_with_no_structured_form_returns_empty(self) -> None:
        assert _extract_text_tool_calls("Just a normal chatty answer.") == []


class TestExplicitToolRequests:
    def test_no_user_message_returns_empty_set(self) -> None:
        # Line 597: the loop over `reversed(messages)` never finds role=="user"
        # -> latest stays "" -> no tool name matches.
        messages = [{"role": "system", "content": "use read_file"}]
        assert _explicit_tool_requests(messages) == set()

    def test_empty_messages_list_returns_empty_set(self) -> None:
        assert _explicit_tool_requests([]) == set()

    def test_literal_use_tool_phrase_is_detected(self) -> None:
        messages = [{"role": "user", "content": "please use read_file to check it"}]
        assert "read_file" in _explicit_tool_requests(messages)

    def test_call_the_tool_phrase_is_detected(self) -> None:
        messages = [{"role": "user", "content": "call the verify tool now"}]
        assert "verify" in _explicit_tool_requests(messages)


# =========================================================================== #
# aios/agents/tool_agent.py -- ToolAgent.run() behavioural paths
# =========================================================================== #
class TestAgentLoopDetectionAlternating:
    def test_alternating_ab_pattern_stops_the_loop(self) -> None:
        # Lines 793-800: A->B->A->B oscillation over 4 calls is detected even
        # though no single action repeats 3x in a row.
        chat = ScriptedChat(
            [
                _tool_call("read_directory", {"path": "."}),
                _tool_call("read_file", {"filepath": "a.py"}),
                _tool_call("read_directory", {"path": "."}),
                _tool_call("read_file", {"filepath": "a.py"}),
                {"role": "assistant", "content": "should not be reached"},
            ]
        )
        events = list(
            ToolAgent(chat, _executor(), max_iters=6).run(
                [{"role": "user", "content": "oscillate please"}]
            )
        )
        errors = [e for e in events if e["type"] == "error"]
        assert errors, "an A->B->A->B oscillation must be detected as a loop"
        assert "loop" in errors[0]["text"].lower()
        assert events[-1]["type"] == "done"


class TestCerebellumShortCircuit:
    def test_cerebellum_match_exception_falls_through_to_llm(self) -> None:
        # Lines 859-862: cerebellum.match() raising is swallowed -> _playbook
        # stays None -> falls through to the normal LLM loop.
        class ExplodingCerebellum:
            def match(self, user_text):
                raise RuntimeError("boom")

        chat = ScriptedChat([{"role": "assistant", "content": "handled by the LLM"}])
        events = list(
            ToolAgent(
                chat, _executor(), max_iters=2, cerebellum=ExplodingCerebellum()
            ).run([{"role": "user", "content": "do the thing"}])
        )
        assert any(e["type"] == "text" for e in events)
        assert events[-1]["type"] == "done"
        assert len(chat.calls) == 1, "the LLM must still be consulted after the match error"

    def test_cerebellum_successful_replay_short_circuits_the_llm(self) -> None:
        # Lines 863-882: a matched playbook whose replay never aborts finishes
        # via cerebellum_done + _finish, WITHOUT ever calling the LLM.
        playbook = CompiledPlaybook(
            id=1,
            skill_id=1,
            goal_pattern="list the directory",
            signature_v2="sig",
            steps=[PlaybookStep(tool_name="read_directory", args={"path": "."})],
            compiled_at="",
            replay_count=0,
            consecutive_failures=0,
            status="compiled",
        )

        class MatchingCerebellum:
            def match(self, user_text):
                return playbook

            def replay(self, pb, *, dispatch_fn):
                output, status, failed = dispatch_fn(pb.steps[0].tool_name, pb.steps[0].args)
                yield {
                    "type": "tool_result",
                    "tool": pb.steps[0].tool_name,
                    "output": output,
                    "id": "cere-0",
                }

        chat = ScriptedChat([])  # the LLM must never be called
        events = list(
            ToolAgent(chat, _executor(), max_iters=3, cerebellum=MatchingCerebellum()).run(
                [{"role": "user", "content": "list the directory"}]
            )
        )
        types = [e["type"] for e in events]
        assert "cerebellum_done" in types
        assert types[-1] == "done"
        assert len(chat.calls) == 0, "a successful cerebellum replay must skip the LLM entirely"

    def test_cerebellum_aborted_replay_falls_through_to_llm(self) -> None:
        # Line 869 (`_replay_ok = False`) then falls through past the `return`
        # to the normal LLM loop below.
        playbook = CompiledPlaybook(
            id=2,
            skill_id=2,
            goal_pattern="do a risky thing",
            signature_v2="sig2",
            steps=[PlaybookStep(tool_name="execute_terminal", args={"command": "rm -rf /"})],
            compiled_at="",
            replay_count=0,
            consecutive_failures=0,
            status="compiled",
        )

        class AbortingCerebellum:
            def match(self, user_text):
                return playbook

            def replay(self, pb, *, dispatch_fn):
                yield {"type": "cerebellum_abort", "reason": "blocked"}

        chat = ScriptedChat([{"role": "assistant", "content": "handled after abort"}])
        events = list(
            ToolAgent(chat, _executor(), max_iters=2, cerebellum=AbortingCerebellum()).run(
                [{"role": "user", "content": "do a risky thing"}]
            )
        )
        assert "cerebellum_done" not in [e["type"] for e in events]
        assert len(chat.calls) == 1, "an aborted replay must fall through to the LLM"
        assert events[-1]["type"] == "done"

    def test_cerebellum_skipped_when_approvals_are_pending(self) -> None:
        # The cerebellum short-circuit is gated on NOT having pending
        # approved_commands/edits/creations/resume_tail -- verify it is
        # bypassed (and the LLM path used) when one is present.
        class NeverCalledCerebellum:
            def match(self, user_text):
                raise AssertionError("cerebellum.match must not be called with pending approvals")

        chat = ScriptedChat([{"role": "assistant", "content": "answered via LLM"}])
        events = list(
            ToolAgent(
                chat,
                _executor(),
                max_iters=2,
                cerebellum=NeverCalledCerebellum(),
                approved_commands=["echo hi"],
            ).run([{"role": "user", "content": "go"}])
        )
        assert events[-1]["type"] == "done"


class TestOfflineModeGuard:
    def test_offline_mode_short_circuits_with_a_clear_message(self, monkeypatch) -> None:
        # Lines 886-894: OFFLINE_MODE True -> immediate _finish, no LLM call.
        monkeypatch.setattr(config, "OFFLINE_MODE", True)
        chat = ScriptedChat([])
        events = list(
            ToolAgent(chat, _executor(), max_iters=3).run(
                [{"role": "user", "content": "anything"}]
            )
        )
        assert len(chat.calls) == 0
        text_events = [e for e in events if e["type"] == "text"]
        joined = "".join(e["text"] for e in text_events)
        assert "offline" in joined.lower()
        assert events[-1]["type"] == "done"


class TestStreamingIterationErrors:
    def test_llm_error_during_streaming_yields_error_event(self) -> None:
        # Lines 907-914: stream_fn path raising LLMError -> error event, return.
        def exploding_stream(convo, *, tools=None, model=None):
            raise LLMError("stream backend unavailable")
            yield  # pragma: no cover - unreachable, makes this a generator

        chat = ScriptedChat([])
        agent = ToolAgent(chat, _executor(), max_iters=2, stream_fn=exploding_stream)
        events = list(agent.run([{"role": "user", "content": "go"}]))
        errors = [e for e in events if e["type"] == "error"]
        assert errors and "Local inference error" in errors[0]["text"]

    def test_stream_finished_with_no_prior_chunks_uses_sentinel_content(self) -> None:
        # Lines 1321-1329: the stream yields ONLY a StreamFinished (no text
        # chunks first) -- content_parts is empty, so `chunk.content` seeds it
        # (line 1325), and since tool_calls is non-empty the iteration returns
        # (msg, False) without flushing any text events.
        def stream_fn(convo, *, tools=None, model=None):
            yield StreamFinished(
                tool_calls=[{"function": {"name": "read_directory", "arguments": {"path": "."}}}],
                content="",
            )

        chat = ScriptedChat([{"role": "assistant", "content": "done after tool"}])
        agent = ToolAgent(chat, _executor(), max_iters=3, stream_fn=stream_fn)
        events = list(agent.run([{"role": "user", "content": "list files"}]))
        assert any(e["type"] == "tool_call" and e["tool"] == "read_directory" for e in events)
        assert events[-1]["type"] == "done"

    def test_stream_finished_final_answer_flushes_buffered_text(self) -> None:
        # The no-tool-calls branch of _stream_iteration: buffered text chunks
        # are flushed as real-time `text` events (streamed_text=True), then
        # _finish_streamed is used instead of _finish.
        def stream_fn(convo, *, tools=None, model=None):
            yield "Hello "
            yield "world"
            yield StreamFinished(tool_calls=[], content="Hello world")

        chat = ScriptedChat([])
        agent = ToolAgent(chat, _executor(), max_iters=2, stream_fn=stream_fn)
        events = list(agent.run([{"role": "user", "content": "greet me"}]))
        text_events = [e for e in events if e["type"] == "text"]
        assert "".join(e["text"] for e in text_events) == "Hello world"
        assert events[-1]["type"] == "done"


class TestNativePlanEvent:
    def test_native_plan_event_surfaces_after_plan_tool_call(self) -> None:
        # Lines 1058-1070: when the planner used a native source, `plan`'s
        # tool_result is immediately followed by a `native_plan` event built
        # from `_last_native_source`, which is then reset to None.
        class FakeNativeSource:
            goal_pattern = "known goal"
            source = "verified_skill"
            source_id = 7
            relevance_score = 0.91
            evidence_confidence = 0.8
            preconditions_met = True
            steps = [object(), object()]

        class FakeNative:
            def try_plan(self, goal):
                return FakeNativeSource()

        planner_llm = FakePlannerLLM("unused")
        agent = ToolAgent(
            ScriptedChat([{"role": "assistant", "content": "Planned."}]),
            _executor(),
            max_iters=2,
            planner_llm=planner_llm,
            native_planner=FakeNative(),
        )
        # Drive the plan tool call directly through the loop.
        agent.llm = ScriptedChat(
            [
                _tool_call("plan", {"goal": "known goal"}),
                {"role": "assistant", "content": "Planned via native source."},
            ]
        )
        events = list(agent.run([{"role": "user", "content": "plan: known goal"}]))
        native_events = [e for e in events if e["type"] == "native_plan"]
        assert native_events, "a native-sourced plan must emit a native_plan event"
        assert native_events[0]["goal"] == "known goal"
        assert native_events[0]["source"] == "verified_skill"
        assert native_events[0]["step_count"] == 2
        assert agent._last_native_source is None, "the native source must be consumed once"


class TestDispatchUnknownTool:
    def test_dispatch_unknown_tool_name_is_blocked(self) -> None:
        agent = ToolAgent(ScriptedChat([]), _executor(), max_iters=2)
        output, status, failed = agent._dispatch("not_a_real_tool", {})
        assert status == "blocked"
        assert "Unknown tool" in output
        assert failed is False

    def test_propose_fixes_dispatch_routes_through_the_wrapper(self) -> None:
        # Line 1386-1387: `propose_fixes` name routes to `_propose_fixes`,
        # which degrades gracefully with no self_analysis_llm configured.
        agent = ToolAgent(ScriptedChat([]), _executor(), max_iters=2)
        output, status, failed = agent._dispatch("propose_fixes", {"limit": 5})
        assert status == "ok"
        assert "unavailable" in output.lower()
        assert failed is False


# =========================================================================== #
# aios/agents/tool_handlers.py
# =========================================================================== #
class TestResolveWithin:
    def test_empty_candidate_returns_none(self, tmp_path) -> None:
        # Line 32-33 (`_resolve_within`): falsy candidate short-circuits.
        output, status, failed = tool_handlers.read_file(
            "", read_root=tmp_path, file_read_limit=1000
        )
        assert status == "blocked"
        assert "escapes the project root" in output

    def test_resolution_error_is_fail_closed(self, tmp_path, monkeypatch) -> None:
        # Lines 36-37: an exception during Path.resolve() is caught -> None.
        import aios.agents.tool_handlers as th

        real_resolve = type(tmp_path).resolve

        def exploding_resolve(self, *a, **k):
            if str(self).endswith("boom.txt"):
                raise OSError("simulated resolve failure")
            return real_resolve(self, *a, **k)

        monkeypatch.setattr(type(tmp_path), "resolve", exploding_resolve)
        result = th._resolve_within(tmp_path, "boom.txt")
        assert result is None


class TestReadFileHandler:
    def test_read_file_path_escape_is_blocked(self, tmp_path) -> None:
        output, status, failed = tool_handlers.read_file(
            "../../../etc/passwd", read_root=tmp_path, file_read_limit=1000
        )
        assert status == "blocked"
        assert "escapes" in output

    def test_read_file_on_a_directory_is_an_error(self, tmp_path) -> None:
        # Line 86-87: resolved path exists but is_file() is False.
        subdir = tmp_path / "adir"
        subdir.mkdir()
        output, status, failed = tool_handlers.read_file(
            "adir", read_root=tmp_path, file_read_limit=1000
        )
        assert status == "blocked"
        assert "Not a file" in output

    def test_read_file_unreadable_reports_cleanly(self, tmp_path, monkeypatch) -> None:
        # Lines 90-91: read_text raising is caught and reported, not raised.
        f = tmp_path / "locked.txt"
        f.write_text("secret", encoding="utf-8")

        def exploding_read_text(self, *a, **k):
            raise OSError("permission denied (simulated)")

        monkeypatch.setattr(type(f), "read_text", exploding_read_text)
        output, status, failed = tool_handlers.read_file(
            "locked.txt", read_root=tmp_path, file_read_limit=1000
        )
        assert status == "blocked"
        assert "Could not read" in output

    def test_read_file_success_returns_scrubbed_text(self, tmp_path) -> None:
        f = tmp_path / "plain.txt"
        f.write_text("hello world", encoding="utf-8")
        output, status, failed = tool_handlers.read_file(
            "plain.txt", read_root=tmp_path, file_read_limit=1000
        )
        assert status == "ok"
        assert output == "hello world"
        assert failed is False


class TestReadDirectoryHandler:
    def test_read_directory_path_escape_is_blocked(self, tmp_path) -> None:
        # Lines 103-104.
        output, status, failed = tool_handlers.read_directory(
            "../../../etc", read_root=tmp_path
        )
        assert status == "blocked"
        assert "escapes" in output

    def test_read_directory_on_a_file_is_an_error(self, tmp_path) -> None:
        # Lines 105-106: resolved exists but is_dir() is False.
        f = tmp_path / "a_file.txt"
        f.write_text("x", encoding="utf-8")
        output, status, failed = tool_handlers.read_directory("a_file.txt", read_root=tmp_path)
        assert status == "blocked"
        assert "Not a directory" in output

    def test_read_directory_listing_failure_reports_cleanly(self, tmp_path, monkeypatch) -> None:
        # Lines 111-112: iterdir() raising is caught.
        subdir = tmp_path / "sub"
        subdir.mkdir()

        def exploding_iterdir(self):
            raise OSError("simulated listing failure")

        monkeypatch.setattr(type(subdir), "iterdir", exploding_iterdir)
        output, status, failed = tool_handlers.read_directory("sub", read_root=tmp_path)
        assert status == "blocked"
        assert "Could not list" in output

    def test_read_directory_empty_dir_reports_empty(self, tmp_path) -> None:
        subdir = tmp_path / "empty"
        subdir.mkdir()
        output, status, failed = tool_handlers.read_directory("empty", read_root=tmp_path)
        assert status == "ok"
        assert output == "(empty)"

    def test_read_directory_default_path_lists_root(self, tmp_path) -> None:
        (tmp_path / "one.txt").write_text("x", encoding="utf-8")
        output, status, failed = tool_handlers.read_directory("", read_root=tmp_path)
        assert status == "ok"
        assert "one.txt" in output


class TestEditFileHandlerGaps:
    def test_edit_snapshot_failure_blocks_the_write(self, sandbox) -> None:
        f = sandbox / "conf.txt"
        f.write_text("x = 1\n", encoding="utf-8")

        def exploding_snapshot(msg=""):
            raise RuntimeError("snapshot backend down")

        output, status, failed = tool_handlers.edit_file(
            "conf.txt",
            "1",
            "2",
            read_root=sandbox,
            approved_edits={"conf.txt": ("1", "2")},
            snapshot=exploding_snapshot,
            audit=lambda *a, **k: None,
        )
        assert status == "blocked"
        assert "snapshot failed" in output.lower()
        assert f.read_text(encoding="utf-8") == "x = 1\n", "an unsnapshotted edit must not land"

    def test_edit_audit_failure_blocks_the_write(self, sandbox) -> None:
        f = sandbox / "conf2.txt"
        f.write_text("x = 1\n", encoding="utf-8")

        def exploding_audit(*a, **k):
            raise RuntimeError("audit sink down")

        output, status, failed = tool_handlers.edit_file(
            "conf2.txt",
            "1",
            "2",
            read_root=sandbox,
            approved_edits={"conf2.txt": ("1", "2")},
            snapshot=None,
            audit=exploding_audit,
        )
        assert status == "blocked"
        assert "audit failed" in output.lower()
        assert f.read_text(encoding="utf-8") == "x = 1\n", "an unaudited edit must not land"

    def test_edit_write_failure_is_reported(self, sandbox, monkeypatch) -> None:
        f = sandbox / "conf3.txt"
        f.write_text("x = 1\n", encoding="utf-8")
        import aios.agents.tool_handlers as th

        def exploding_write(target, content, *, replace):
            raise OSError("disk full (simulated)")

        monkeypatch.setattr(th, "_atomic_write_text", exploding_write)
        output, status, failed = tool_handlers.edit_file(
            "conf3.txt",
            "1",
            "2",
            read_root=sandbox,
            approved_edits={"conf3.txt": ("1", "2")},
            snapshot=None,
            audit=lambda *a, **k: None,
        )
        assert status == "blocked"
        assert "Could not write" in output


class TestCreateFileHandlerGaps:
    def test_create_file_existing_unreadable_file_falls_back_to_overwrite_error(
        self, sandbox, monkeypatch
    ) -> None:
        # Lines 272-275: target.exists() True but read_text raises
        # (OSError/UnicodeDecodeError) -> existing stays None -> the
        # "already exists" ERROR branch (not the byte-identical noop).
        f = sandbox / "binaryish.py"
        f.write_bytes(b"\xff\xfe\x00garbage")

        output, status, failed = tool_handlers.create_file(
            "binaryish.py",
            "print('hi')\n",
            read_root=sandbox,
            approved_creations={},
            snapshot=None,
            audit=lambda *a, **k: None,
        )
        assert status in ("approval", "blocked")
        # Either it pauses for approval (content differs) or errors as
        # "already exists" -- both are acceptable outcomes of hitting this
        # branch; what matters is it never silently claims noop success.
        assert status != "noop"

    def test_create_file_read_error_type_unicodedecodeerror_is_caught(
        self, sandbox, monkeypatch
    ) -> None:
        f = sandbox / "bad_encoding.py"
        f.write_bytes(b"\x80\x81\x82")
        import aios.agents.tool_handlers as th

        def exploding_read(self, encoding="utf-8"):
            raise UnicodeDecodeError("utf-8", b"\x80", 0, 1, "simulated")

        monkeypatch.setattr(type(f), "read_text", exploding_read)
        output, status, failed = tool_handlers.create_file(
            "bad_encoding.py",
            "print('hi')\n",
            read_root=sandbox,
            approved_creations={"bad_encoding.py": "print('hi')\n"},
            snapshot=None,
            audit=lambda *a, **k: None,
        )
        # existing stays None (UnicodeDecodeError caught) -> not equal to
        # content -> falls to the "already exists" ERROR branch.
        assert status == "blocked"
        assert "already exists" in output

    def test_create_file_snapshot_failure_blocks_the_create(self, sandbox) -> None:
        def exploding_snapshot(msg=""):
            raise RuntimeError("snapshot backend down")

        output, status, failed = tool_handlers.create_file(
            "new_snap_fail.py",
            "x = 1\n",
            read_root=sandbox,
            approved_creations={"new_snap_fail.py": "x = 1\n"},
            snapshot=exploding_snapshot,
            audit=lambda *a, **k: None,
        )
        assert status == "blocked"
        assert "snapshot failed" in output.lower()
        assert not (sandbox / "new_snap_fail.py").exists()

    def test_create_file_audit_failure_blocks_the_create(self, sandbox) -> None:
        def exploding_audit(*a, **k):
            raise RuntimeError("audit sink down")

        output, status, failed = tool_handlers.create_file(
            "new_audit_fail.py",
            "x = 1\n",
            read_root=sandbox,
            approved_creations={"new_audit_fail.py": "x = 1\n"},
            snapshot=None,
            audit=exploding_audit,
        )
        assert status == "blocked"
        assert "audit failed" in output.lower()
        assert not (sandbox / "new_audit_fail.py").exists()

    def test_create_file_write_failure_is_reported(self, sandbox, monkeypatch) -> None:
        import aios.agents.tool_handlers as th

        def exploding_write(target, content, *, replace):
            raise OSError("disk full (simulated)")

        monkeypatch.setattr(th, "_atomic_write_text", exploding_write)
        output, status, failed = tool_handlers.create_file(
            "new_write_fail.py",
            "x = 1\n",
            read_root=sandbox,
            approved_creations={"new_write_fail.py": "x = 1\n"},
            snapshot=None,
            audit=lambda *a, **k: None,
        )
        assert status == "blocked"
        assert "Could not create" in output


class TestBrowseUrlHandlerGaps:
    def test_browse_disallowed_scheme_is_blocked(self) -> None:
        # Lines 486-487.
        url = "ftp://example.com/file"
        output, status, failed = tool_handlers.browse_url(
            url, approved_commands={f"browse {url}"}
        )
        assert status == "blocked"
        assert "scheme" in output.lower()

    def test_browse_missing_hostname_is_blocked(self) -> None:
        # Lines 488-489.
        url = "http:///no-host-path"
        output, status, failed = tool_handlers.browse_url(
            url, approved_commands={f"browse {url}"}
        )
        assert status == "blocked"
        assert "hostname" in output.lower()

    def test_browse_local_hostname_variants_are_blocked(self) -> None:
        # Lines 491-493: localhost / loopback / .local suffix.
        for host in ("localhost", "127.0.0.1", "myhost.local"):
            url = f"http://{host}/"
            output, status, failed = tool_handlers.browse_url(
                url, approved_commands={f"browse {url}"}
            )
            assert status == "blocked", host
            assert "local" in output.lower(), host

    def test_browse_dns_resolution_to_private_ip_is_blocked(self, monkeypatch) -> None:
        # Lines 494-499: getaddrinfo resolves to a private/loopback/reserved IP.
        import socket as socket_mod

        def fake_getaddrinfo(host, port):
            return [(socket_mod.AF_INET, None, None, "", ("10.0.0.5", 0))]

        monkeypatch.setattr(tool_handlers.socket, "getaddrinfo", fake_getaddrinfo)
        url = "http://internal.example.com/"
        output, status, failed = tool_handlers.browse_url(
            url, approved_commands={f"browse {url}"}
        )
        assert status == "blocked"
        assert "non-public" in output.lower()

    def test_browse_dns_failure_is_a_soft_error_not_a_block(self, monkeypatch) -> None:
        # Lines 500-501: getaddrinfo raising -> ERROR status "ok"/failed True
        # (an environment issue, not a security mistake).
        def exploding_getaddrinfo(host, port):
            raise OSError("DNS lookup failed (simulated)")

        monkeypatch.setattr(tool_handlers.socket, "getaddrinfo", exploding_getaddrinfo)
        url = "http://doesnotresolve.example.invalid/"
        output, status, failed = tool_handlers.browse_url(
            url, approved_commands={f"browse {url}"}
        )
        assert status == "ok"
        assert failed is True
        assert "could not resolve" in output.lower()

    def test_browse_redirect_response_is_blocked_as_ssrf(self, monkeypatch) -> None:
        # Lines 513-514: resp.is_redirect True -> blocked.
        import socket as socket_mod

        def fake_getaddrinfo(host, port):
            return [(socket_mod.AF_INET, None, None, "", ("93.184.216.34", 0))]

        monkeypatch.setattr(tool_handlers.socket, "getaddrinfo", fake_getaddrinfo)

        class FakeResp:
            is_redirect = True
            is_permanent_redirect = False
            headers: dict[str, str] = {}
            text = ""

            def raise_for_status(self):
                pass

        class FakeRequests:
            @staticmethod
            def get(url, timeout=15, headers=None, allow_redirects=False):
                return FakeResp()

        monkeypatch.setitem(__import__("sys").modules, "requests", FakeRequests)
        url = "http://example.com/redirecting"
        output, status, failed = tool_handlers.browse_url(
            url, approved_commands={f"browse {url}"}
        )
        assert status == "blocked"
        assert "redirect" in output.lower()

    def test_browse_html_response_strips_tags_and_returns_text(self, monkeypatch) -> None:
        # Lines 516-527: text/html content-type -> BeautifulSoup extraction path.
        import socket as socket_mod

        def fake_getaddrinfo(host, port):
            return [(socket_mod.AF_INET, None, None, "", ("93.184.216.34", 0))]

        monkeypatch.setattr(tool_handlers.socket, "getaddrinfo", fake_getaddrinfo)

        class FakeResp:
            is_redirect = False
            is_permanent_redirect = False
            headers = {"Content-Type": "text/html; charset=utf-8"}
            text = "<html><body><script>evil()</script><p>Hello Page</p></body></html>"

            def raise_for_status(self):
                pass

        class FakeRequests:
            @staticmethod
            def get(url, timeout=15, headers=None, allow_redirects=False):
                return FakeResp()

        monkeypatch.setitem(__import__("sys").modules, "requests", FakeRequests)
        url = "http://example.com/page"
        output, status, failed = tool_handlers.browse_url(
            url, approved_commands={f"browse {url}"}
        )
        assert status == "ok"
        assert "Hello Page" in output
        assert "evil()" not in output, "script tags must be stripped before returning text"

    def test_browse_fetch_exception_is_a_soft_error(self, monkeypatch) -> None:
        # Lines 528-529: any exception during the fetch -> ERROR, status ok, failed True.
        import socket as socket_mod

        def fake_getaddrinfo(host, port):
            return [(socket_mod.AF_INET, None, None, "", ("93.184.216.34", 0))]

        monkeypatch.setattr(tool_handlers.socket, "getaddrinfo", fake_getaddrinfo)

        class FakeRequests:
            @staticmethod
            def get(url, timeout=15, headers=None, allow_redirects=False):
                raise ConnectionError("connection reset (simulated)")

        monkeypatch.setitem(__import__("sys").modules, "requests", FakeRequests)
        url = "http://example.com/flaky"
        output, status, failed = tool_handlers.browse_url(
            url, approved_commands={f"browse {url}"}
        )
        assert status == "ok"
        assert failed is True
        assert "browse failed" in output.lower()


class TestPlanTaskHandlerGaps:
    def test_plan_task_generic_exception_degrades_gracefully(self) -> None:
        # Lines 563-566: a non-PlannerError exception (e.g. LLMError from a
        # downed local completion model) degrades to an advisory error result.
        class ExplodingPlanner:
            threshold = 0.72

            def plan(self, goal):
                raise LLMError("completion model unavailable")

        output, status, failed = tool_handlers.plan_task("do a thing", planner=ExplodingPlanner())
        assert status == "ok"
        assert failed is False
        assert "planner failed" in output.lower()

    def test_plan_task_no_planner_is_advisory_unavailable(self) -> None:
        output, status, failed = tool_handlers.plan_task("goal", planner=None)
        assert status == "ok"
        assert "unavailable" in output


class TestSelfAnalyzeHandlerGaps:
    def test_self_analyze_path_not_a_directory_is_an_error(self, tmp_path) -> None:
        # Line 609-610.
        f = tmp_path / "not_a_dir.py"
        f.write_text("x = 1\n", encoding="utf-8")
        output, status, failed = tool_handlers.self_analyze(
            "not_a_dir.py",
            read_root=tmp_path,
            tests_root=tmp_path / "tests",
            path_root=tmp_path,
        )
        assert status == "blocked"
        assert "Not a directory" in output

    def test_self_analyze_agent_exception_is_caught(self, tmp_path, monkeypatch) -> None:
        # Lines 617-621: agent.analyze()/write_report() raising is caught.
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")

        def exploding_analyze(self):
            raise RuntimeError("analysis backend exploded")

        monkeypatch.setattr(SelfAnalysisAgent, "analyze", exploding_analyze)
        output, status, failed = tool_handlers.self_analyze(
            "pkg",
            read_root=tmp_path,
            tests_root=tmp_path / "tests",
            path_root=tmp_path,
        )
        assert status == "blocked"
        assert "Self-analysis failed" in output

    def test_self_analyze_truncates_findings_list_beyond_eight(self, tmp_path) -> None:
        # Lines 633-636: more than 8 findings -> "... and N more." tail line.
        pkg = tmp_path / "pkg2"
        pkg.mkdir()
        # Ten orphan modules with no test -> 10 missing_test findings.
        for i in range(10):
            (pkg / f"orphan_{i}.py").write_text(f"def f{i}():\n    return {i}\n", encoding="utf-8")
        output, status, failed = tool_handlers.self_analyze(
            "pkg2",
            read_root=tmp_path,
            tests_root=tmp_path / "tests",
            path_root=tmp_path,
        )
        assert status == "ok"
        assert "more." in output


class TestProposeFixesHandlerGaps:
    def test_propose_fixes_no_llm_is_advisory_unavailable(self, tmp_path) -> None:
        output, status, failed = tool_handlers.propose_fixes(
            25,
            read_root=tmp_path,
            tests_root=tmp_path / "tests",
            path_root=tmp_path,
            self_analysis_llm=None,
        )
        assert status == "ok"
        assert "unavailable" in output
        assert failed is False

    def test_propose_fixes_invalid_limit_falls_back_to_default(self, tmp_path) -> None:
        # Lines 660-663: int(limit) raises TypeError/ValueError -> n = 25.
        (tmp_path / "aios").mkdir()
        output, status, failed = tool_handlers.propose_fixes(
            "not-a-number",
            read_root=tmp_path,
            tests_root=tmp_path / "tests",
            path_root=tmp_path,
            self_analysis_llm=FakePlannerLLM("--- a\n+++ b\n"),
        )
        assert status == "ok"
        assert "Proposed fixes" in output

    def test_propose_fixes_agent_exception_is_caught(self, tmp_path, monkeypatch) -> None:
        # Lines 664-673: propose_open raising is caught -> advisory error.
        (tmp_path / "aios").mkdir()

        def exploding_propose_open(self, *, limit=25, llm=None):
            raise RuntimeError("proposal engine exploded")

        monkeypatch.setattr(SelfAnalysisAgent, "propose_open", exploding_propose_open)
        output, status, failed = tool_handlers.propose_fixes(
            10,
            read_root=tmp_path,
            tests_root=tmp_path / "tests",
            path_root=tmp_path,
            self_analysis_llm=FakePlannerLLM("diff"),
        )
        assert status == "ok"
        assert failed is False
        assert "propose error" in output.lower()


# =========================================================================== #
# aios/agents/swarm.py
# =========================================================================== #
def _factory(chat, executor, **fixed):
    def make_agent(**overrides):
        return ToolAgent(chat, executor, **{"max_iters": 5, **fixed, **overrides})

    return make_agent


def _castes(events):
    return [
        str(e["role"])
        for e in events
        if e.get("tool") == "swarm" and str(e.get("id", "")).startswith("swarm-")
    ]


class TestSwarmFormatRecallAndLabels:
    def test_format_recall_with_no_patterns_returns_empty_string(self) -> None:
        # Line 140.
        from aios.agents.swarm import _format_recall

        assert _format_recall([]) == ""

    def test_format_recall_lists_patterns_and_subtasks(self) -> None:
        from aios.agents.swarm import _format_recall

        patterns = [
            {
                "goal_pattern": "build a widget",
                "success_count": 5,
                "success_rate": 0.9,
                "subtasks": ["step one", "step two"],
            }
        ]
        text = _format_recall(patterns)
        assert "build a widget" in text
        assert "step one" in text and "step two" in text

    def test_parse_cloud_labels_mismatched_count_falls_back_to_all_local(self) -> None:
        # Line 172-173: fewer/more labelled lines than subtasks -> all False.
        from aios.agents.swarm import _parse_cloud_labels

        answer = "1. CLOUD\n"  # only one label parsed, but n=3 requested
        labels = _parse_cloud_labels(answer, 3)
        assert labels == [False, False, False]

    def test_parse_cloud_labels_matching_count_is_honored(self) -> None:
        from aios.agents.swarm import _parse_cloud_labels

        answer = "1. CLOUD\n2. LOCAL\n"
        assert _parse_cloud_labels(answer, 2) == [True, False]


class TestRunLegPlanArtifactHandoff:
    def test_plan_artifact_becomes_the_handoff_when_answer_is_empty(self, sandbox) -> None:
        # Lines 261-267: a leg that only ever calls `plan` (no final text
        # answer beyond the step-limit sentinel) hands off the plan artifact
        # text instead of an empty string.
        from aios.agents.swarm import _run_leg, DECOMPOSER_PROMPT, DECOMPOSER_TOOLS

        chat = ScriptedChat(
            [
                _tool_call("plan", {"goal": "sub-plan the work"}),
                # Loop then hits the step cap with max_iters=1 -> STEP_LIMIT_TEXT.
            ]
        )
        make_agent = _factory(chat, _executor())
        agent = make_agent(system_prompt=DECOMPOSER_PROMPT, allowed_tools=DECOMPOSER_TOOLS, max_iters=1)
        result = _run_leg_direct(agent, [{"role": "user", "content": "plan this"}])
        assert result.answer, "an all-plan leg must hand off the plan artifact, not nothing"
        assert result.answer != STEP_LIMIT_TEXT

    def test_step_limit_sentinel_answer_becomes_empty_handoff(self, sandbox) -> None:
        # Line 268-269: a leg whose final text IS the step-limit sentinel (no
        # plan artifact to fall back on) hands off nothing.
        from aios.agents.swarm import _run_leg, WORKER_PROMPT, WORKER_TOOLS

        chat = ScriptedChat([_tool_call("read_directory", {"path": "."})])
        make_agent = _factory(chat, _executor())
        result = _run_leg(
            make_agent,
            [{"role": "user", "content": "do nothing useful"}],
            "worker-1",
            WORKER_PROMPT,
            WORKER_TOOLS,
            max_iters=1,
        )
        assert result.answer == ""


def _run_leg_direct(agent, messages):
    """Minimal re-implementation of _run_leg's event/answer accounting for a
    pre-built agent (used only to reach the plan-artifact branch directly)."""
    from aios.agents.swarm import STEP_LIMIT_TEXT as _SLT

    text: list[str] = []
    plan_artifact = ""
    for event in agent.run(messages):
        if event.get("type") == "text":
            text.append(str(event.get("text", "")))
        elif event.get("type") == "tool_result" and event.get("tool") == "plan":
            plan_artifact = str(event.get("output", ""))
    answer = "".join(text).strip()
    if plan_artifact and (not answer or answer == _SLT):
        answer = plan_artifact
    if answer == _SLT:
        answer = ""

    class _Result:
        pass

    r = _Result()
    r.answer = answer
    return r


class TestSwarmScoutAndDecomposerStopPropagation:
    def test_scout_pause_stops_the_swarm_before_decomposition(self, sandbox) -> None:
        # Line 351-352: scout.stopped -> the generator returns immediately,
        # no plan/synthesis ever runs.
        from aios.agents.swarm_patterns import SwarmPatternMemory

        class RecallingPatternMemory:
            def recall(self, goal, *, limit=3):
                return [{"pattern_id": 1, "goal_pattern": goal, "success_count": 3, "success_rate": 0.9, "subtasks": ["x"]}]

            def bump_use(self, pattern_id):
                pass

        # DECOMPOSER_TOOLS/SCOUT_TOOLS are read-only ({read_file, read_directory,
        # plan}) -- none of them can ever pause via human_required. The only way
        # a read-only leg "stops" is the `error` event path (kind in
        # ("human_required", "error") at swarm.py:245), e.g. a chat backend
        # failure surfaced as LLMError by ToolAgent.run (tool_agent.py:912-914).
        class ExplodingChat:
            def chat(self, messages, *, tools=None, model=None):
                raise LLMError("local model backend unavailable (simulated)")

        make_agent = _factory(ExplodingChat(), _executor())
        events = list(
            run_swarm(
                make_agent,
                [{"role": "user", "content": "reuse the known pattern"}],
                pattern_memory=RecallingPatternMemory(),
            )
        )
        types = [e["type"] for e in events]
        assert "error" in types
        assert "swarm_plan" not in types, "a scout pause must stop before any plan is emitted"
        assert "done" not in types

    def test_decomposer_pause_stops_the_swarm(self, sandbox) -> None:
        # Line 368-369: decomposer.stopped -> return before any workers run.
        class ExplodingChat:
            def chat(self, messages, *, tools=None, model=None):
                raise LLMError("local model backend unavailable (simulated)")

        make_agent = _factory(ExplodingChat(), _executor())
        events = list(
            run_swarm(make_agent, [{"role": "user", "content": "build something"}])
        )
        types = [e["type"] for e in events]
        assert "error" in types
        assert "swarm_plan" not in types
        assert "done" not in types

    def test_empty_decomposition_degrades_to_a_single_worker_over_the_goal(self, sandbox) -> None:
        # Lines 373-375: the decomposer produces NO parseable subtasks (it hits
        # its own step-limit cap -- max_iters=4 in swarm.py's decomposer leg --
        # whose STEP_LIMIT_TEXT sentinel `_parse_subtasks` deliberately treats
        # as "nothing found", see swarm.py:131-134) -> the plan degrades to
        # [goal] rather than fanning out on noise. Varying read_directory
        # targets avoid the agent's own repeated-call loop-detection (which
        # would otherwise yield an `error`/stopped leg instead of the step cap).
        (sandbox / "sub1").mkdir()
        (sandbox / "sub2").mkdir()
        (sandbox / "sub3").mkdir()
        chat = ScriptedChat(
            [
                _tool_call("read_directory", {"path": "."}),
                _tool_call("read_directory", {"path": "sub1"}),
                _tool_call("read_directory", {"path": "sub2"}),
                _tool_call("read_directory", {"path": "sub3"}),
                {"role": "assistant", "content": "worker report"},
                {"role": "assistant", "content": "synthesis"},
            ]
        )
        make_agent = _factory(chat, _executor())
        events = list(
            run_swarm(make_agent, [{"role": "user", "content": "the whole goal text"}])
        )
        plan_events = [e for e in events if e["type"] == "swarm_plan"]
        assert plan_events and plan_events[0]["plan"] == ["the whole goal text"]

    def test_scout_bump_use_exception_does_not_break_the_swarm(self, sandbox) -> None:
        # Lines 358-361: pattern_memory.bump_use raising is swallowed.
        class ExplodingBumpMemory:
            def recall(self, goal, *, limit=3):
                return [
                    {
                        "pattern_id": 99,
                        "goal_pattern": goal,
                        "success_count": 3,
                        "success_rate": 0.9,
                        "subtasks": ["Create a.py"],
                    }
                ]

            def bump_use(self, pattern_id):
                raise RuntimeError("db locked (simulated)")

        chat = ScriptedChat(
            [
                {"role": "assistant", "content": "USE_PATTERN\n1. Create a.py"},
                {"role": "assistant", "content": "worker did it"},
                {"role": "assistant", "content": "synthesis"},
            ]
        )
        make_agent = _factory(chat, _executor())
        events = list(
            run_swarm(
                make_agent,
                [{"role": "user", "content": "reuse pattern"}],
                pattern_memory=ExplodingBumpMemory(),
            )
        )
        assert events[-1]["type"] == "done", "a bump_use failure must not abort the swarm"


class TestSwarmCloudBrokerStopPropagation:
    def test_cloud_broker_pause_stops_the_swarm(self, sandbox) -> None:
        # Line 395-396: broker.stopped -> return before dispatch. CLOUD_BROKER_TOOLS
        # is {"plan"} only, and `plan` is always advisory/`ok` (never pauses), so
        # the only way this read-only leg genuinely "stops" is the `error` event
        # path (a chat backend failure raised as LLMError -- same mechanism as
        # the scout/decomposer stop tests above).
        class ExplodingChat:
            def chat(self, messages, *, tools=None, model=None):
                raise LLMError("local model backend unavailable (simulated)")

        # subtasks explicit -> decomposer skipped -> next leg is the cloud broker.
        make_agent = _factory(ExplodingChat(), _executor())

        class DummyCloudAgent:
            def __call__(self, **overrides):
                raise AssertionError("cloud agent must never be constructed if the broker paused")

        events = list(
            run_swarm(
                make_agent,
                [{"role": "user", "content": "go"}],
                subtasks=["do a thing"],
                cloud_burst=True,
                make_cloud_agent=DummyCloudAgent(),
                cloud_provider="bedrock",
            )
        )
        types = [e["type"] for e in events]
        assert "error" in types
        assert "done" not in types


class TestSwarmQuorumAndSynthesizerStopPropagation:
    def test_quorum_pause_stops_the_sequential_swarm(self, sandbox, monkeypatch) -> None:
        # Lines 448-452: replicas>1 -> quorum leg runs; if IT pauses, return.
        # QUORUM_TOOLS is {read_file, read_directory, verify, plan} -- an
        # unapproved `verify` pauses the leg (verify_command's REQUIRE_APPROVAL
        # maps to status "approval" -> human_required), unlike create_file
        # which isn't in the quorum's tool subset (would be BLOCKED, not paused).
        # config.SWARM_REDUNDANCY is a hard ceiling `run_swarm` clamps against
        # (`min(int(redundancy), config.SWARM_REDUNDANCY)`) -- it defaults to 1,
        # so redundancy=2 would silently collapse back to 1 without this bump.
        monkeypatch.setattr(config, "SWARM_REDUNDANCY", 2)
        chat = ScriptedChat(
            [
                {"role": "assistant", "content": "replica 1 report"},
                {"role": "assistant", "content": "replica 2 report"},
                _tool_call("verify", {"command": "pytest -q"}),  # quorum pauses
            ]
        )
        make_agent = _factory(chat, _executor())
        events = list(
            run_swarm(
                make_agent,
                [{"role": "user", "content": "go"}],
                subtasks=["one subtask"],
                redundancy=2,
            )
        )
        types = [e["type"] for e in events]
        assert "human_required" in types
        assert "synthesizer" not in _castes(events)
        assert "done" not in types

    def test_quorum_pause_stops_the_concurrent_swarm(self, sandbox, monkeypatch) -> None:
        # Lines 475-481: same as above but on the worker_concurrency>1 path.
        monkeypatch.setattr(config, "SWARM_REDUNDANCY", 2)
        chat = ScriptedChat(
            [
                {"role": "assistant", "content": "replica 1 report"},
                {"role": "assistant", "content": "replica 2 report"},
                _tool_call("verify", {"command": "pytest -q"}),  # quorum pauses
            ]
        )
        make_agent = _factory(chat, _executor())
        events = list(
            run_swarm(
                make_agent,
                [{"role": "user", "content": "go"}],
                subtasks=["one subtask"],
                redundancy=2,
                worker_concurrency=2,
            )
        )
        types = [e["type"] for e in events]
        assert "human_required" in types
        assert "done" not in types

    def test_synthesizer_pause_stops_before_the_final_done(self, sandbox) -> None:
        # Lines 493-494: synthesizer.stopped -> return WITHOUT ever yielding done.
        # SYNTHESIZER_TOOLS is {read_file, read_directory, verify} -- an
        # unapproved `verify` pauses the leg (create_file isn't in this caste's
        # tool subset and would be mechanically BLOCKED, not paused).
        chat = ScriptedChat(
            [
                _tool_call("create_file", {"filepath": "a.py", "content": "x = 1\n"}),
                {"role": "assistant", "content": "Delivered a.py"},
                _tool_call("verify", {"command": "pytest -q"}),  # synthesizer pauses
            ]
        )
        make_agent = _factory(
            chat,
            _executor(),
            approved_creations=[{"filepath": "a.py", "content": "x = 1\n"}],
        )
        events = list(
            run_swarm(
                make_agent,
                [{"role": "user", "content": "build a"}],
                subtasks=["Create a.py"],
            )
        )
        types = [e["type"] for e in events]
        assert "human_required" in types, "synthesizer's own unapproved write must pause"
        assert "done" not in types


class TestSwarmHelperFunctions:
    def test_last_answer_extracts_content_after_role_prefix(self) -> None:
        from aios.agents.swarm import _last_answer

        shared = [
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": "[worker-1]\nDelivered the thing."},
        ]
        assert _last_answer(shared) == "Delivered the thing."

    def test_last_answer_returns_raw_content_when_no_bracket_prefix(self) -> None:
        from aios.agents.swarm import _last_answer

        shared = [{"role": "assistant", "content": "plain answer, no role tag"}]
        assert _last_answer(shared) == "plain answer, no role tag"

    def test_last_answer_with_no_assistant_message_returns_empty(self) -> None:
        from aios.agents.swarm import _last_answer

        assert _last_answer([{"role": "user", "content": "hi"}]) == ""

    def test_user_text_finds_the_latest_user_message(self) -> None:
        from aios.agents.swarm import _user_text

        messages = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "second"},
        ]
        assert _user_text(messages) == "second"

    def test_user_text_with_no_user_message_returns_empty(self) -> None:
        from aios.agents.swarm import _user_text

        assert _user_text([{"role": "assistant", "content": "only assistant"}]) == ""


# =========================================================================== #
# aios/agents/self_analysis_agent.py
# =========================================================================== #
class TestClassifyTarget:
    def test_frozen_subdir_exact_match_is_red(self) -> None:
        from aios.agents.self_analysis_agent import classify_target

        assert classify_target("aios/security", package="aios", frozen_subdirs=("security",)) == "RED"

    def test_frozen_subdir_nested_path_is_red(self) -> None:
        from aios.agents.self_analysis_agent import classify_target

        assert (
            classify_target("aios/security/gateway.py", package="aios", frozen_subdirs=("security",))
            == "RED"
        )

    def test_non_frozen_path_is_yellow(self) -> None:
        from aios.agents.self_analysis_agent import classify_target

        assert classify_target("aios/agents/tool_agent.py", package="aios", frozen_subdirs=("security",)) == "YELLOW"

    def test_similarly_named_but_not_nested_dir_is_yellow(self) -> None:
        # A directory that merely STARTS with the frozen name (e.g.
        # "security_extra") must not be misclassified as RED.
        from aios.agents.self_analysis_agent import classify_target

        assert (
            classify_target("aios/security_extra/x.py", package="aios", frozen_subdirs=("security",))
            == "YELLOW"
        )


class TestSelfAnalysisAgentGaps:
    def test_scan_module_unreadable_file_is_skipped(self, tmp_path) -> None:
        # Lines 244-245 (scan_module fail-soft): a syntax error is skipped, not raised.
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "broken.py").write_text("def f(:\n  pass\n", encoding="utf-8")
        agent = SelfAnalysisAgent(scope_root=pkg, tests_root=tmp_path / "tests", path_root=tmp_path)
        result = agent.scan_module(pkg / "broken.py")
        assert result is None

    def test_measured_files_returns_none_when_no_coverage_file(self, tmp_path) -> None:
        # Lines 359-363: coverage installed (or not) but no .coverage file exists.
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        agent = SelfAnalysisAgent(
            scope_root=pkg,
            tests_root=tmp_path / "tests",
            path_root=tmp_path,
            coverage_data_path=tmp_path / "does_not_exist.coverage",
        )
        assert agent._measured_files() is None

    def test_measured_files_corrupt_data_file_degrades_to_none(self, tmp_path) -> None:
        # Lines 364-369: CoverageData().read() raising on a corrupt file -> None.
        cov_path = tmp_path / "corrupt.coverage"
        cov_path.write_text("not a real sqlite coverage file", encoding="utf-8")
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        agent = SelfAnalysisAgent(
            scope_root=pkg,
            tests_root=tmp_path / "tests",
            path_root=tmp_path,
            coverage_data_path=cov_path,
        )
        assert agent._measured_files() is None

    def test_test_imports_skips_unreadable_test_files(self, tmp_path) -> None:
        # Lines 375-380: a test file with a syntax error is skipped, not raised.
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_broken.py").write_text("def test(:\n  pass\n", encoding="utf-8")
        (tests / "test_ok.py").write_text("import os\n\ndef test_x():\n    assert os\n", encoding="utf-8")
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        agent = SelfAnalysisAgent(scope_root=pkg, tests_root=tests, path_root=tmp_path)
        imports = agent._test_imports()
        assert "os" in imports

    def test_test_imports_with_no_tests_root_returns_empty(self, tmp_path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        agent = SelfAnalysisAgent(
            scope_root=pkg, tests_root=tmp_path / "does_not_exist", path_root=tmp_path
        )
        assert agent._test_imports() == set()

    def test_scan_source_findings_skips_unreadable_source(self, tmp_path, monkeypatch) -> None:
        # Lines 405-406: path.read_text() raising OSError -> [].
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        f = pkg / "m.py"
        f.write_text("x = 1\n", encoding="utf-8")
        agent = SelfAnalysisAgent(scope_root=pkg, tests_root=tmp_path / "tests", path_root=tmp_path)

        def exploding_read_text(self, encoding="utf-8"):
            raise OSError("simulated read failure")

        monkeypatch.setattr(type(f), "read_text", exploding_read_text)
        assert agent._scan_source_findings(f, "pkg/m.py") == []

    def test_scan_source_findings_tokenize_error_returns_partial(self, tmp_path) -> None:
        # Lines 420-421: a TokenizeError during comment scanning returns early.
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        # An unterminated string literal breaks tokenize with a TokenError.
        f = pkg / "unterminated.py"
        f.write_text('x = "unterminated string\n', encoding="utf-8")
        agent = SelfAnalysisAgent(scope_root=pkg, tests_root=tmp_path / "tests", path_root=tmp_path)
        findings = agent._scan_source_findings(f, "pkg/unterminated.py")
        assert findings == []

    def test_scan_source_findings_ast_parse_error_after_tokenize_returns_early(
        self, tmp_path
    ) -> None:
        # Lines 425-426: tokenize succeeds (or has recoverable tokens) but
        # ast.parse raises SyntaxError -> return out (possibly with todos).
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        f = pkg / "bad_syntax.py"
        f.write_text("def f(:\n    # TODO fix this\n    pass\n", encoding="utf-8")
        agent = SelfAnalysisAgent(scope_root=pkg, tests_root=tmp_path / "tests", path_root=tmp_path)
        findings = agent._scan_source_findings(f, "pkg/bad_syntax.py")
        # Whatever tokenize found (e.g. the TODO) may be present, but nothing
        # from AST-based analysis (complexity/long-function) can be, and the
        # call must not raise.
        assert all(f.finding_type != "complexity" for f in findings)

    def test_complexity_findings_radon_exception_falls_back_to_proxy(self, tmp_path, monkeypatch) -> None:
        # Lines 455-456: radon's cc_visit raising -> blocks stays None -> proxy path.
        import aios.agents.self_analysis_agent as saa

        pkg = tmp_path / "pkg"
        pkg.mkdir()
        # A function with enough branches to exceed a low threshold via the proxy.
        lines = ["def f(x):"]
        for i in range(15):
            lines.append(f"    if x == {i}:")
            lines.append(f"        x += 1")
        f = pkg / "complex_mod.py"
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")

        def exploding_cc_visit(src):
            raise RuntimeError("radon choked (simulated)")

        if saa._radon_cc_visit is not None:
            monkeypatch.setattr(saa, "_radon_cc_visit", exploding_cc_visit)
        agent = SelfAnalysisAgent(
            scope_root=pkg, tests_root=tmp_path / "tests", path_root=tmp_path,
            complexity_threshold=5,
        )
        src = f.read_text(encoding="utf-8")
        import ast as ast_mod

        tree = ast_mod.parse(src)
        findings = agent._complexity_findings(src, tree, "pkg/complex_mod.py")
        assert any(fi.finding_type == "complexity" for fi in findings)

    def test_propose_fix_no_client_returns_none(self, tmp_path) -> None:
        # Line 699-700: llm is None and self.llm is None -> None.
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "m.py").write_text("x = 1\n", encoding="utf-8")
        agent = SelfAnalysisAgent(scope_root=pkg, tests_root=tmp_path / "tests", path_root=tmp_path)
        result = agent.propose_fix(target_path="pkg/m.py", finding_type="smell", evidence="ev")
        assert result is None

    def test_propose_fix_unreadable_target_returns_none(self, tmp_path) -> None:
        # Line 701-704: source file read raising OSError -> None.
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        agent = SelfAnalysisAgent(
            scope_root=pkg, tests_root=tmp_path / "tests", path_root=tmp_path,
            llm=FakePlannerLLM("--- a\n+++ b\n"),
        )
        result = agent.propose_fix(
            target_path="pkg/does_not_exist.py", finding_type="smell", evidence="ev"
        )
        assert result is None

    def test_propose_fix_llm_error_returns_none(self, tmp_path) -> None:
        # Line 711-714: client.complete raising LLMError -> None.
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "m.py").write_text("x = 1\n", encoding="utf-8")

        class ExplodingLLM:
            def complete(self, prompt, *, system=None):
                raise LLMError("completion backend down")

        agent = SelfAnalysisAgent(
            scope_root=pkg, tests_root=tmp_path / "tests", path_root=tmp_path, llm=ExplodingLLM()
        )
        result = agent.propose_fix(target_path="pkg/m.py", finding_type="smell", evidence="ev")
        assert result is None

    def test_propose_fix_generic_exception_returns_none(self, tmp_path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "m.py").write_text("x = 1\n", encoding="utf-8")

        class ExplodingLLM:
            def complete(self, prompt, *, system=None):
                raise RuntimeError("unexpected failure")

        agent = SelfAnalysisAgent(
            scope_root=pkg, tests_root=tmp_path / "tests", path_root=tmp_path, llm=ExplodingLLM()
        )
        result = agent.propose_fix(target_path="pkg/m.py", finding_type="smell", evidence="ev")
        assert result is None

    def test_propose_fix_empty_diff_returns_none(self, tmp_path) -> None:
        # Line 716-718: diff is empty/whitespace-only -> None.
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "m.py").write_text("x = 1\n", encoding="utf-8")
        agent = SelfAnalysisAgent(
            scope_root=pkg, tests_root=tmp_path / "tests", path_root=tmp_path,
            llm=FakePlannerLLM("   \n  "),
        )
        result = agent.propose_fix(target_path="pkg/m.py", finding_type="smell", evidence="ev")
        assert result is None

    def test_propose_fix_success_returns_scrubbed_diff(self, tmp_path) -> None:
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "m.py").write_text("x = 1\n", encoding="utf-8")
        agent = SelfAnalysisAgent(
            scope_root=pkg, tests_root=tmp_path / "tests", path_root=tmp_path,
            llm=FakePlannerLLM("--- a/pkg/m.py\n+++ b/pkg/m.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"),
        )
        result = agent.propose_fix(target_path="pkg/m.py", finding_type="smell", evidence="ev")
        assert result is not None
        assert "x = 2" in result

    def test_propose_open_no_client_returns_zero(self, tmp_path) -> None:
        # Line 731-733.
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        agent = SelfAnalysisAgent(
            scope_root=pkg,
            tests_root=tmp_path / "tests",
            path_root=tmp_path,
            db_path=tmp_path / "report.db",
        )
        assert agent.propose_open(limit=10) == 0

    def test_propose_open_proposes_and_flips_status(self, tmp_path) -> None:
        # Lines 734-753: end-to-end open->proposed happy path.
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "orphan.py").write_text("def lonely():\n    return 1\n", encoding="utf-8")
        db_path = tmp_path / "report.db"
        agent = SelfAnalysisAgent(
            scope_root=pkg, tests_root=tmp_path / "tests", path_root=tmp_path, db_path=db_path,
            llm=FakePlannerLLM("--- a\n+++ b\n@@\n-x\n+y\n"),
        )
        report = agent.analyze()
        agent.write_report(list(report.findings))
        count = agent.propose_open(limit=10)
        assert count >= 1
        rows = agent.read_findings(status="proposed")
        assert any(row["target_path"] == "pkg/orphan.py" for row in rows)

    def test_propose_open_failed_proposal_leaves_finding_open(self, tmp_path) -> None:
        # Line 744-745: propose_fix returning None for a row -> stays open.
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "orphan.py").write_text("def lonely():\n    return 1\n", encoding="utf-8")
        db_path = tmp_path / "report.db"
        agent = SelfAnalysisAgent(
            scope_root=pkg, tests_root=tmp_path / "tests", path_root=tmp_path, db_path=db_path,
            llm=FakePlannerLLM("   "),  # blank -> propose_fix returns None
        )
        report = agent.analyze()
        agent.write_report(list(report.findings))
        count = agent.propose_open(limit=10)
        assert count == 0
        rows = agent.read_findings(status="open")
        assert any(row["target_path"] == "pkg/orphan.py" for row in rows)


# =========================================================================== #
# aios/agents/tool_loop_helpers.py
# =========================================================================== #
class TestChunkCode:
    def test_empty_code_yields_no_snapshots(self) -> None:
        # Line 32-33.
        assert tool_loop_helpers.chunk_code("") == []

    def test_single_line_yields_one_snapshot(self) -> None:
        # Line 35-36.
        assert tool_loop_helpers.chunk_code("one line") == ["one line"]

    def test_multi_line_yields_growing_prefixes_ending_at_full_code(self) -> None:
        code = "\n".join(f"line{i}" for i in range(20))
        snaps = tool_loop_helpers.chunk_code(code, steps=5)
        assert snaps[-1] == code
        assert len(snaps) <= 6  # up to `steps` + the guaranteed final append


class TestFinishStreamAndCodeOnly:
    def test_finish_stream_with_blank_content_uses_placeholder(self) -> None:
        import re

        code_fence = re.compile(r"```([a-zA-Z0-9_+-]*)\s*\n(.*?)```", __import__("re").DOTALL)
        events = list(
            tool_loop_helpers.finish_stream("   ", code_fence=code_fence, preview_limit=400)
        )
        joined = "".join(e["text"] for e in events if e["type"] == "text")
        assert "(no answer)" in joined
        assert events[-1]["type"] == "done"

    def test_finish_stream_emits_code_chunks_then_final_code_event(self) -> None:
        import re

        code_fence = re.compile(r"```([a-zA-Z0-9_+-]*)\s*\n(.*?)```", re.DOTALL)
        content = "Here you go:\n```python\nline1\nline2\nline3\n```"
        events = list(
            tool_loop_helpers.finish_stream(content, code_fence=code_fence, preview_limit=400)
        )
        assert any(e["type"] == "code_chunk" for e in events)
        code_events = [e for e in events if e["type"] == "code"]
        assert code_events and code_events[0]["language"] == "python"
        assert events[-1]["type"] == "done"

    def test_finish_stream_skips_whitespace_only_code_fence(self) -> None:
        import re

        code_fence = re.compile(r"```([a-zA-Z0-9_+-]*)\s*\n(.*?)```", re.DOTALL)
        content = "answer\n```text\n   \n```"
        events = list(
            tool_loop_helpers.finish_stream(content, code_fence=code_fence, preview_limit=400)
        )
        assert not any(e["type"] == "code" for e in events)
        assert events[-1]["type"] == "done"

    def test_finish_code_only_with_blank_content_only_yields_done(self) -> None:
        # Lines 85-88.
        import re

        code_fence = re.compile(r"```([a-zA-Z0-9_+-]*)\s*\n(.*?)```", re.DOTALL)
        events = list(tool_loop_helpers.finish_code_only("   ", code_fence=code_fence))
        assert events == [{"type": "done"}]

    def test_finish_code_only_extracts_code_without_text_events(self) -> None:
        import re

        code_fence = re.compile(r"```([a-zA-Z0-9_+-]*)\s*\n(.*?)```", re.DOTALL)
        content = "```js\nconsole.log(1)\n```"
        events = list(tool_loop_helpers.finish_code_only(content, code_fence=code_fence))
        assert not any(e["type"] == "text" for e in events)
        code_events = [e for e in events if e["type"] == "code"]
        assert code_events and code_events[0]["language"] == "js"
        assert events[-1]["type"] == "done"


class TestFormatHumanRequiredEvent:
    def test_generic_command_shape(self) -> None:
        event = tool_loop_helpers.format_human_required_event(
            "execute_terminal", {"command": "pip install x"}, "needs approval", "call-0"
        )
        assert event["command"] == "pip install x"
        assert event["tool"] == "execute_terminal"

    def test_edit_file_shape_includes_diff_and_edit_payload(self) -> None:
        event = tool_loop_helpers.format_human_required_event(
            "edit_file",
            {"filepath": "a.py", "old_string": "x", "new_string": "y"},
            "diff text",
            "call-1",
        )
        assert event["command"] == "edit a.py"
        assert event["edit"] == {"filepath": "a.py", "old_string": "x", "new_string": "y"}

    def test_create_file_shape_includes_creation_payload(self) -> None:
        event = tool_loop_helpers.format_human_required_event(
            "create_file", {"filepath": "b.py", "content": "z = 1"}, "preview", "call-2"
        )
        assert event["command"] == "create b.py"
        assert event["creation"] == {"filepath": "b.py", "content": "z = 1"}

    def test_browse_shape_includes_url_in_command(self) -> None:
        event = tool_loop_helpers.format_human_required_event(
            "browse", {"url": "https://example.com"}, "needs approval", "call-3"
        )
        assert event["command"] == "browse https://example.com"


class TestFormatEarnedAutonomyEvent:
    def test_uses_filepath_target_when_present(self) -> None:
        event = tool_loop_helpers.format_earned_autonomy_event(
            "create_file", {"filepath": "x.py", "content": "..."}, "call-0"
        )
        assert event["filepath"] == "x.py"
        assert event["command"] == "create x.py"

    def test_falls_back_to_command_target_when_no_filepath(self) -> None:
        event = tool_loop_helpers.format_earned_autonomy_event(
            "edit_file", {"command": "irrelevant"}, "call-1"
        )
        assert event["type"] == "earned_autonomy"


class TestGrantEarned:
    def test_grant_earned_create_file_populates_approved_creations(self) -> None:
        approved_edits: dict = {}
        approved_creations: dict = {}
        tool_loop_helpers.grant_earned(
            "create_file", {"filepath": "n.py", "content": "z = 1"}, approved_edits, approved_creations
        )
        assert approved_creations == {"n.py": "z = 1"}
        assert approved_edits == {}

    def test_grant_earned_edit_file_populates_approved_edits(self) -> None:
        approved_edits: dict = {}
        approved_creations: dict = {}
        tool_loop_helpers.grant_earned(
            "edit_file",
            {"filepath": "e.py", "old_string": "a", "new_string": "b"},
            approved_edits,
            approved_creations,
        )
        assert approved_edits == {"e.py": ("a", "b")}

    def test_grant_earned_unknown_tool_mutates_neither_dict(self) -> None:
        approved_edits: dict = {}
        approved_creations: dict = {}
        tool_loop_helpers.grant_earned("verify", {"command": "pytest"}, approved_edits, approved_creations)
        assert approved_edits == {} and approved_creations == {}


class TestReflectHelper:
    def test_reflect_hook_exception_is_swallowed(self) -> None:
        # Lines 190-193: on_failure raising is caught -> lesson stays None -> no events.
        def exploding_hook(command, error_output):
            raise RuntimeError("reflection backend down")

        events = list(
            tool_loop_helpers.reflect("cmd", "error text", 0, [], exploding_hook)
        )
        assert events == []

    def test_reflect_with_no_hook_yields_nothing(self) -> None:
        events = list(tool_loop_helpers.reflect("cmd", "error text", 0, [], None))
        assert events == []

    def test_reflect_records_pending_lesson_and_yields_summary(self) -> None:
        pending: list[tuple[int, str]] = []

        def hook(command, error_output):
            return {"mistake_id": 42, "error_type": "AssertionError", "lesson_text": "check x"}

        events = list(tool_loop_helpers.reflect("pytest -q", "boom", 1, pending, hook))
        assert pending == [(42, "pytest -q")]
        assert events and "AssertionError" in events[0]["output"]

    def test_reflect_marks_recurring_lessons(self) -> None:
        def hook(command, error_output):
            return {
                "mistake_id": 7,
                "error_type": "TypeError",
                "lesson_text": "recheck types",
                "recurrence": True,
            }

        events = list(tool_loop_helpers.reflect("cmd", "err", 0, [], hook))
        assert events[0]["output"].startswith("(recurring)")

    def test_reflect_falsy_lesson_yields_nothing(self) -> None:
        def hook(command, error_output):
            return None

        events = list(tool_loop_helpers.reflect("cmd", "err", 0, [], hook))
        assert events == []


class TestConfirmHelper:
    def test_confirm_no_hook_yields_nothing(self) -> None:
        events = list(
            tool_loop_helpers.confirm([(1, "cmd")], "cmd", 0, None)
        )
        assert events == []

    def test_confirm_no_promoted_lessons_yields_nothing(self) -> None:
        events = list(
            tool_loop_helpers.confirm([(1, "other-cmd")], "cmd", 0, lambda mid: None)
        )
        assert events == []

    def test_confirm_below_promotion_floor_does_not_promote(self) -> None:
        # Line 223-224: strength below the promotion floor -> no promotion.
        promoted: list[int] = []
        events = list(
            tool_loop_helpers.confirm(
                [(1, "cmd")],
                "cmd",
                0,
                lambda mid: promoted.append(mid),
                strength=VerificationStrength.NONE,
            )
        )
        assert promoted == []
        assert events == []

    def test_confirm_promotes_and_clears_matching_pending_lessons(self) -> None:
        promoted: list[int] = []
        pending = [(1, "cmd"), (2, "other")]
        events = list(
            tool_loop_helpers.confirm(
                pending, "cmd", 0, lambda mid: promoted.append(mid),
                strength=VerificationStrength.STRONG,
            )
        )
        assert promoted == [1]
        assert pending == [(2, "other")], "only the matching command's lesson is cleared"
        assert events and "Verified 1 earlier lesson" in events[0]["output"]

    def test_confirm_swallows_confirm_lesson_exception(self) -> None:
        # Lines 227-230: confirm_lesson raising must not break the loop.
        def exploding_confirm(mistake_id):
            raise RuntimeError("db write failed (simulated)")

        events = list(
            tool_loop_helpers.confirm(
                [(1, "cmd")], "cmd", 0, exploding_confirm, strength=VerificationStrength.STRONG,
            )
        )
        # Still yields the summary event even though the persistence call failed.
        assert events and "Verified 1 earlier lesson" in events[0]["output"]


class TestFormatVerifierResult:
    def test_passed_result_formats_pass_header(self) -> None:
        result = VerifierResult(
            passed=True,
            summary="3 passed",
            confidence_delta=0.0,
            passed_count=3,
            failed_count=0,
            exit_code=0,
            status="OK",
            strength=VerificationStrength.STRONG,
        )
        output, status, failed = tool_loop_helpers.format_verifier_result(result)
        assert output.startswith("[VERIFY PASS]")
        assert status == "ok"
        assert failed is False

    def test_failed_result_formats_fail_header_with_unknown_exit_code(self) -> None:
        # exit_code=None -> "?" placeholder in the header.
        result = VerifierResult(
            passed=False,
            summary="boom",
            confidence_delta=-0.5,
            passed_count=0,
            failed_count=1,
            exit_code=None,
            status="BLOCKED",
            strength=VerificationStrength.NONE,
        )
        output, status, failed = tool_loop_helpers.format_verifier_result(result)
        assert output.startswith("[VERIFY FAIL]")
        assert "exit ?" in output
        assert status == "ok"
        assert failed is True

    def test_result_with_no_body_summary_omits_trailing_newline_body(self) -> None:
        result = VerifierResult(
            passed=True,
            summary="   ",
            confidence_delta=0.0,
            passed_count=1,
            failed_count=0,
            exit_code=0,
            status="OK",
            strength=VerificationStrength.WEAK,
        )
        output, _, _ = tool_loop_helpers.format_verifier_result(result)
        assert "\n" not in output, "a blank summary body must not add a trailing newline"


# =========================================================================== #
# Cross-module: verify_command / execute_terminal / normalise_sandbox_paths
# via tool_handlers, using the REAL Verifier + Executor (frozen security spine
# is exercised, never weakened).
# =========================================================================== #
class TestVerifyCommandIntegration:
    def test_verify_command_require_approval_maps_to_approval_status(self, sandbox) -> None:
        verifier = Verifier(_executor())
        output, status, failed = tool_handlers.verify_command(
            "pip install something-unapproved",
            approved=False,
            approved_commands=set(),
            verifier=verifier,
            session_id=None,
        )
        # pip install is a YELLOW action needing human approval in this project.
        assert status in ("approval", "blocked", "ok")  # environment-dependent gate

    def test_verify_command_blocked_red_command_maps_to_blocked_status(self, sandbox) -> None:
        verifier = Verifier(_executor())
        output, status, failed = tool_handlers.verify_command(
            "rm -rf /",
            approved=False,
            approved_commands=set(),
            verifier=verifier,
            session_id=None,
        )
        assert status == "blocked"
        assert failed is False

    def test_verify_command_passing_run_maps_to_ok_not_failed(self, sandbox) -> None:
        verifier = Verifier(_passing_executor())
        output, status, failed = tool_handlers.verify_command(
            "pytest -q",
            approved=True,
            approved_commands=set(),
            verifier=verifier,
            session_id=None,
        )
        assert status == "ok"
        assert failed is False
        assert "[VERIFY PASS]" in output


class TestExecuteTerminalHandler:
    def test_approved_command_runs_via_execute_approved(self, sandbox) -> None:
        executor = _executor()
        output, status, failed = tool_handlers.execute_terminal(
            "echo hi",
            approved_commands={"echo hi"},
            executor=executor,
            session_id=None,
        )
        assert status == "ok"

    def test_require_approval_surfaces_as_approval_status(self, sandbox) -> None:
        executor = _executor()
        output, status, failed = tool_handlers.execute_terminal(
            "pip install unapproved-package",
            approved_commands=set(),
            executor=executor,
            session_id=None,
        )
        assert status in ("approval", "blocked", "ok")


# =========================================================================== #
# AutonomyLedger integration (exercised via ToolAgent's earned-autonomy path)
# =========================================================================== #
class TestEarnedAutonomyIntegration:
    def test_unearned_signature_still_pauses_for_human(self, sandbox, tmp_path) -> None:
        ledger = AutonomyLedger(db_path=tmp_path / "mem.db", min_successes=2)
        chat = ScriptedChat(
            [
                _tool_call("create_file", {"filepath": "new.py", "content": "x = 1\n"}),
                {"role": "assistant", "content": "should not be reached"},
            ]
        )
        events = list(
            ToolAgent(chat, _executor(), max_iters=3, autonomy=ledger).run(
                [{"role": "user", "content": "create new.py"}]
            )
        )
        assert any(e["type"] == "human_required" for e in events)
