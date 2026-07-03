"""Unit tests for the agentic tool loop (aios.agents.tool_agent).

A scripted fake chat client drives the loop deterministically — no Ollama, no
shell — while a fake-runner Executor exercises the real security gateway so the
blocking behaviour under test is genuine, not mocked away.
"""
from __future__ import annotations

import json
from typing import Optional

import pytest

from aios import config
from aios.agents.tool_agent import ToolAgent
from aios.core.executor import Executor
from aios.core.llm import LLMError
from aios.security import scope_lock
from aios.security.gateway import RateLimiter


class ScriptedChat:
    """Returns queued assistant messages in order, one per ``chat`` call."""

    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.calls: list[list] = []

    def chat(self, messages, *, tools=None, model=None) -> dict:
        self.calls.append(messages)
        return self._responses.pop(0)


class FakeRunner:
    """Stand-in process runner — records, never spawns."""

    def __call__(self, command, *, cwd, env, timeout_s):
        return f"ran: {command}", "", 0


class FailRunner:
    """Runner that always reports a non-zero exit (a genuine command failure)."""

    def __call__(self, command, *, cwd, env, timeout_s):
        return "", "boom: assertion failed", 1


class FlakyRunner:
    """Fails the first command, then succeeds — models a fix being applied."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, command, *, cwd, env, timeout_s):
        self.calls += 1
        if self.calls == 1:
            return "", "boom: assertion failed", 1
        return "3 passed in 0.2s", "", 0


class PassRunner:
    """Runner that emits pytest-style passing output (exit 0)."""

    def __call__(self, command, *, cwd, env, timeout_s):
        return "3 passed in 0.2s", "", 0


class RecordingRunner:
    """Runner that records every command it is asked to run, but spawns nothing.

    Lets a test prove a *blocked* command never reaches execution at all.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, command, *, cwd, env, timeout_s):
        self.calls.append(command)
        return "should-not-run", "", 0


class FakePlannerLLM:
    """Fake COMPLETION client (LLMClient.complete) returning a fixed plan string.

    Distinct from ScriptedChat (a .chat() client): the Planner needs .complete(),
    which the loop's chat client may not have (it can be cloud Bedrock).
    """

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, Optional[str]]] = []

    def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
        self.calls.append((prompt, system))
        return self.response


#: A fixed 3-step plan with one step (step 2) below the 0.72 confidence gate.
_PLAN_JSON = json.dumps(
    {
        "steps": [
            {"step_id": "1", "description": "Read config", "confidence": 0.9},
            {"step_id": "2", "description": "Refactor parser", "confidence": 0.4},
            {"step_id": "3", "description": "Run tests", "confidence": 0.85},
        ]
    }
)


def _executor() -> Executor:
    return Executor(
        runner=FakeRunner(),
        rate_limiter=RateLimiter(),
        audit_log=lambda *a, **k: None,
    )


def _failing_executor() -> Executor:
    return Executor(
        runner=FailRunner(),
        rate_limiter=RateLimiter(),
        audit_log=lambda *a, **k: None,
    )


def _flaky_executor() -> Executor:
    return Executor(
        runner=FlakyRunner(),
        rate_limiter=RateLimiter(),
        audit_log=lambda *a, **k: None,
    )


def _passing_executor() -> Executor:
    return Executor(
        runner=PassRunner(),
        rate_limiter=RateLimiter(),
        audit_log=lambda *a, **k: None,
    )


def _tool_call(name: str, arguments: dict) -> dict:
    return {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": name, "arguments": arguments}}
    ]}


def test_agent_runs_tool_then_answers() -> None:
    chat = ScriptedChat([
        _tool_call("read_directory", {"path": "."}),
        {"role": "assistant", "content": "All set.\n```text\nok\n```"},
    ])
    events = list(ToolAgent(chat, _executor(), max_iters=3).run(
        [{"role": "user", "content": "list the files then summarise"}]
    ))
    types = [e["type"] for e in events]

    assert "tool_call" in types
    assert "tool_result" in types          # listing the project root succeeds
    assert any(e["type"] == "text" for e in events)
    assert any(e["type"] == "code" for e in events)
    assert types[-1] == "done"


def test_agent_recovers_allowlisted_tool_call_emitted_as_json_text() -> None:
    chat = ScriptedChat([
        {
            "role": "assistant",
            "content": (
                "```json\n"
                '{"name":"read_file","arguments":{"filepath":"training_ground/greeter.py"}}'
                "\n```"
            ),
        },
        {"role": "assistant", "content": "The file was inspected."},
    ])

    events = list(ToolAgent(chat, _executor(), max_iters=3).run(
        [{"role": "user", "content": "inspect greeter.py"}]
    ))

    assert any(e.get("tool") == "read_file" and e["type"] == "tool_call" for e in events)
    assert any(e.get("tool") == "read_file" and e["type"] == "tool_result" for e in events)
    assert events[-1]["type"] == "done"


def test_agent_recovers_python_style_mapping_tool_call_from_local_model() -> None:
    chat = ScriptedChat([
        {
            "role": "assistant",
            "content": (
                "```json\n"
                "{'name': 'read_file', 'arguments': "
                "{'filepath': 'training_ground/greeter.py'}}"
                "\n```"
            ),
        },
        {"role": "assistant", "content": "The file was inspected."},
    ])

    events = list(ToolAgent(chat, _executor(), max_iters=3).run(
        [{"role": "user", "content": "inspect greeter.py"}]
    ))

    assert any(e.get("tool") == "read_file" and e["type"] == "tool_call" for e in events)
    assert events[-1]["type"] == "done"


def test_agent_recovers_first_of_multiple_fenced_json_tool_calls() -> None:
    # Local models often narrate EVERY step of a multi-step task as a series of
    # fenced JSON calls in one message. Only the first allowlisted call may run;
    # its tool result re-anchors the model before it continues.
    chat = ScriptedChat([
        {
            "role": "assistant",
            "content": (
                "I'll do both steps now.\n"
                "```json\n"
                '{"name":"read_directory","arguments":{"path":"."}}'
                "\n```\n\n"
                "```json\n"
                '{"name":"read_file","arguments":{"filepath":"training_ground/greeter.py"}}'
                "\n```"
            ),
        },
        {"role": "assistant", "content": "Both inspected."},
    ])

    events = list(ToolAgent(chat, _executor(), max_iters=3).run(
        [{"role": "user", "content": "list the directory then read greeter.py"}]
    ))

    calls = [e for e in events if e["type"] == "tool_call"]
    assert len(calls) == 1, "only the FIRST fenced call may be recovered per message"
    assert calls[0]["tool"] == "read_directory"
    assert events[-1]["type"] == "done"


def test_agent_recovers_first_of_multiple_bare_json_tool_calls() -> None:
    # No fences at all: some models emit several raw JSON objects back-to-back.
    # A message BEGINNING with a JSON object is a call, not prose — recover the
    # first allowlisted one only.
    chat = ScriptedChat([
        {
            "role": "assistant",
            "content": (
                '{"name": "read_directory", "arguments": {"path": "."}}\n\n'
                '{"name": "read_file", "arguments": {"filepath": "training_ground/greeter.py"}}'
            ),
        },
        {"role": "assistant", "content": "Both inspected."},
    ])

    events = list(ToolAgent(chat, _executor(), max_iters=3).run(
        [{"role": "user", "content": "list then read"}]
    ))

    calls = [e for e in events if e["type"] == "tool_call"]
    assert len(calls) == 1
    assert calls[0]["tool"] == "read_directory"
    assert events[-1]["type"] == "done"


def test_agent_recovers_react_style_action_line() -> None:
    # ReAct narration ("Thought: ... Action: tool {json}") — recover the call.
    chat = ScriptedChat([
        {
            "role": "assistant",
            "content": (
                "Thought: I should inspect the file first.\n"
                'Action: read_file {"filepath": "training_ground/greeter.py"}'
            ),
        },
        {"role": "assistant", "content": "The file was inspected."},
    ])

    events = list(ToolAgent(chat, _executor(), max_iters=3).run(
        [{"role": "user", "content": "inspect greeter.py"}]
    ))

    assert any(e.get("tool") == "read_file" and e["type"] == "tool_call" for e in events)
    assert any(e.get("tool") == "read_file" and e["type"] == "tool_result" for e in events)
    assert events[-1]["type"] == "done"


def test_agent_recovers_parameters_keyed_json_tool_call() -> None:
    # llama3.1-style prose call: arguments keyed as "parameters".
    chat = ScriptedChat([
        {
            "role": "assistant",
            "content": (
                "```json\n"
                '{"name": "read_file", "parameters": '
                '{"filepath": "training_ground/greeter.py"}}'
                "\n```"
            ),
        },
        {"role": "assistant", "content": "The file was inspected."},
    ])

    events = list(ToolAgent(chat, _executor(), max_iters=3).run(
        [{"role": "user", "content": "inspect greeter.py"}]
    ))

    assert any(e.get("tool") == "read_file" and e["type"] == "tool_call" for e in events)
    assert any(e.get("tool") == "read_file" and e["type"] == "tool_result" for e in events)
    assert events[-1]["type"] == "done"


def test_agent_never_executes_python_expression_in_text_tool_fallback() -> None:
    chat = ScriptedChat([
        {
            "role": "assistant",
            "content": (
                "{'name': 'read_file', 'arguments': "
                "__import__('os').system('echo unsafe')}"
            ),
        },
    ])

    events = list(ToolAgent(chat, _executor(), max_iters=2).run(
        [{"role": "user", "content": "show this text"}]
    ))

    assert not any(e["type"] == "tool_call" for e in events)
    assert events[-1]["type"] == "done"


def test_agent_does_not_execute_unknown_json_text_as_a_tool() -> None:
    chat = ScriptedChat([
        {"role": "assistant", "content": '{"name":"delete_everything","arguments":{}}'},
    ])

    events = list(ToolAgent(chat, _executor(), max_iters=2).run(
        [{"role": "user", "content": "show JSON"}]
    ))

    assert not any(e["type"] == "tool_call" for e in events)
    assert events[-1]["type"] == "done"


def test_agent_retries_once_when_user_explicitly_requests_a_tool() -> None:
    chat = ScriptedChat([
        {"role": "assistant", "content": "I can answer without reading it."},
        _tool_call("read_file", {"filepath": "training_ground/greeter.py"}),
        {"role": "assistant", "content": "I inspected the file."},
    ])

    events = list(ToolAgent(chat, _executor(), max_iters=4).run(
        [{"role": "user", "content": "Use the read_file tool to inspect greeter.py"}]
    ))

    assert any(e.get("tool") == "read_file" and e["type"] == "tool_call" for e in events)
    assert any(
        "explicitly requested tool" in str(msg.get("content", ""))
        for msg in chat.calls[1]
    )
    assert events[-1]["type"] == "done"


def test_agent_does_not_force_tools_for_normal_chat() -> None:
    chat = ScriptedChat([
        {"role": "assistant", "content": "A direct answer."},
    ])

    events = list(ToolAgent(chat, _executor(), max_iters=3).run(
        [{"role": "user", "content": "What does read_file do?"}]
    ))

    assert len(chat.calls) == 1
    assert not any(e["type"] == "tool_call" for e in events)
    assert events[-1]["type"] == "done"


def test_agent_blocks_red_command() -> None:
    chat = ScriptedChat([
        _tool_call("execute_terminal", {"command": "rm -rf /"}),
        {"role": "assistant", "content": "I could not run that — it was blocked."},
    ])
    events = list(ToolAgent(chat, _executor(), max_iters=3).run(
        [{"role": "user", "content": "delete everything"}]
    ))

    blocked = [e for e in events if e["type"] == "tool_blocked"]
    assert blocked, "a RED command must surface a tool_blocked event"
    assert "BLOCK" in blocked[0]["reason"].upper()
    # The model still gets to answer after the block.
    assert events[-1]["type"] == "done"


def test_agent_blocks_path_escape_on_read() -> None:
    chat = ScriptedChat([
        _tool_call("read_file", {"filepath": "../../../../etc/passwd"}),
        {"role": "assistant", "content": "blocked"},
    ])
    events = list(ToolAgent(chat, _executor(), max_iters=3).run(
        [{"role": "user", "content": "read the password file"}]
    ))

    blocked = [e for e in events if e["type"] == "tool_blocked"]
    assert blocked and "escapes the project root" in blocked[0]["reason"]


def test_agent_green_command_runs_in_sandbox() -> None:
    chat = ScriptedChat([
        _tool_call("execute_terminal", {"command": "echo hello"}),
        {"role": "assistant", "content": "Printed hello."},
    ])
    events = list(ToolAgent(chat, _executor(), max_iters=3).run(
        [{"role": "user", "content": "print hello"}]
    ))

    results = [e for e in events if e["type"] == "tool_result"]
    assert results and "ran: echo hello" in results[0]["output"]


def test_agent_surfaces_llm_error() -> None:
    class Boom:
        def chat(self, messages, *, tools=None, model: Optional[str] = None) -> dict:
            raise LLMError("ollama is down")

    events = list(ToolAgent(Boom(), _executor(), max_iters=3).run(
        [{"role": "user", "content": "hi"}]
    ))
    assert events[-1]["type"] == "error"
    assert "ollama is down" in events[-1]["text"]


def test_agent_injects_memory_context_into_system_prompt() -> None:
    chat = ScriptedChat([{"role": "assistant", "content": "ok"}])
    agent = ToolAgent(
        chat, _executor(), max_iters=2,
        memory_context="RELEVANT PROJECT MEMORY:\n- the answer is 42",
    )
    list(agent.run([{"role": "user", "content": "what is the answer?"}]))

    system_msg = chat.calls[0][0]
    assert system_msg["role"] == "system"
    assert "the answer is 42" in system_msg["content"]


def test_agent_reflects_on_command_failure() -> None:
    chat = ScriptedChat([
        _tool_call("execute_terminal", {"command": "echo tests"}),
        {"role": "assistant", "content": "The tests failed; noted."},
    ])
    seen: list[tuple[str, str]] = []

    def hook(command: str, error_output: str):
        seen.append((command, error_output))
        return {"error_type": "AssertionError", "lesson_text": "add a guard clause",
                "recurrence": False, "mistake_id": 7}

    events = list(ToolAgent(chat, _failing_executor(), max_iters=3, on_failure=hook).run(
        [{"role": "user", "content": "run the tests"}]
    ))

    assert seen and seen[0][0] == "echo tests"          # the hook saw the failed command
    reflect_steps = [e for e in events if e.get("tool") == "reflect"]
    assert reflect_steps and "add a guard clause" in reflect_steps[0]["output"]


def test_agent_promotes_lesson_after_corrective_success() -> None:
    # Fail a test command (records lesson 7), then succeed on the retry with
    # behavior-asserting output -> verify it.
    chat = ScriptedChat([
        _tool_call("execute_terminal", {"command": "pytest -q"}),
        _tool_call("execute_terminal", {"command": "pytest -q"}),
        {"role": "assistant", "content": "Fixed and passing."},
    ])

    def on_failure(command: str, error_output: str):
        return {"error_type": "AssertionError", "lesson_text": "guard the input",
                "recurrence": False, "mistake_id": 7}

    confirmed: list[int] = []
    events = list(
        ToolAgent(
            chat, _flaky_executor(), max_iters=4,
            on_failure=on_failure, confirm_lesson=confirmed.append,
            approved_commands=["pytest -q"],
        ).run([{"role": "user", "content": "make the tests pass"}])
    )

    assert confirmed == [7], "the lesson should be promoted after the corrective success"
    verify_steps = [e for e in events if e.get("tool") == "reflect" and "Verified" in e.get("output", "")]
    assert verify_steps, "a 'lesson verified' step should be surfaced"


def test_agent_does_not_promote_lesson_after_weak_corrective_success() -> None:
    # The same failed command succeeds on retry, but it is a weak GREEN command
    # ("echo" with no assertions), so it cannot turn a mistake into planner-visible
    # verified lesson evidence.
    chat = ScriptedChat([
        _tool_call("execute_terminal", {"command": "echo tests"}),
        _tool_call("execute_terminal", {"command": "echo tests"}),
        {"role": "assistant", "content": "Fixed and passing."},
    ])

    def on_failure(command: str, error_output: str):
        return {"error_type": "AssertionError", "lesson_text": "guard the input",
                "recurrence": False, "mistake_id": 7}

    confirmed: list[int] = []
    events = list(
        ToolAgent(
            chat, _flaky_executor(), max_iters=4,
            on_failure=on_failure, confirm_lesson=confirmed.append,
        ).run([{"role": "user", "content": "make the tests pass"}])
    )

    assert confirmed == []
    verify_steps = [e for e in events if e.get("tool") == "reflect" and "Verified" in e.get("output", "")]
    assert verify_steps == []


def test_agent_does_not_verify_failed_command_lesson_on_unrelated_success() -> None:
    # Even in the same run, an unrelated success is not evidence that the failed
    # command was corrected.
    chat = ScriptedChat([
        _tool_call("execute_terminal", {"command": "echo tests"}),
        _tool_call("execute_terminal", {"command": "echo unrelated"}),
        {"role": "assistant", "content": "looks good"},
    ])

    def on_failure(command: str, error_output: str):
        return {"error_type": "AssertionError", "lesson_text": "guard the input",
                "recurrence": False, "mistake_id": 42}

    confirmed: list[int] = []
    list(
        ToolAgent(
            chat, _flaky_executor(), max_iters=4,
            on_failure=on_failure, confirm_lesson=confirmed.append,
        ).run([{"role": "user", "content": "continue"}])
    )
    assert confirmed == [], "unrelated success must not verify the failed-command lesson"


def test_agent_does_not_promote_without_prior_failure() -> None:
    # A clean success with no earlier failure must not promote anything.
    chat = ScriptedChat([
        _tool_call("execute_terminal", {"command": "echo hi"}),
        {"role": "assistant", "content": "done"},
    ])
    confirmed: list[int] = []
    list(
        ToolAgent(
            chat, _executor(), max_iters=3,
            on_failure=lambda c, e: {"mistake_id": 1, "error_type": "X", "lesson_text": "y", "recurrence": False},
            confirm_lesson=confirmed.append,
        ).run([{"role": "user", "content": "say hi"}])
    )
    assert confirmed == [], "no failure occurred, so nothing should be confirmed"


def test_agent_does_not_reflect_on_security_block() -> None:
    chat = ScriptedChat([
        _tool_call("execute_terminal", {"command": "rm -rf /"}),
        {"role": "assistant", "content": "blocked"},
    ])
    seen: list[tuple[str, str]] = []

    def hook(command: str, error_output: str):
        seen.append((command, error_output))
        return {"error_type": "X", "lesson_text": "y", "recurrence": False, "mistake_id": 1}

    events = list(ToolAgent(chat, _executor(), max_iters=3, on_failure=hook).run(
        [{"role": "user", "content": "delete everything"}]
    ))

    assert not seen, "a security block is correct behaviour, not a mistake to reflect on"
    assert not any(e.get("tool") == "reflect" for e in events)


def test_agent_stops_at_step_cap() -> None:
    # Always asks for another tool call -> never finishes on its own.
    looping = ScriptedChat([_tool_call("read_directory", {"path": "."}) for _ in range(10)])
    events = list(ToolAgent(looping, _executor(), max_iters=2).run(
        [{"role": "user", "content": "loop forever"}]
    ))
    assert events[-1]["type"] == "done"
    assert any("step limit" in e.get("text", "") for e in events if e["type"] == "text")


def test_agent_pauses_on_unapproved_yellow_command() -> None:
    # A YELLOW command the human hasn't authorised pauses the turn for approval
    # instead of running it or dead-ending with "not run".
    chat = ScriptedChat([
        _tool_call("execute_terminal", {"command": "pip install flask"}),
        {"role": "assistant", "content": "should not be reached"},
    ])
    events = list(ToolAgent(chat, _executor(), max_iters=3).run(
        [{"role": "user", "content": "install flask"}]
    ))
    types = [e["type"] for e in events]

    assert "human_required" in types, "an unapproved YELLOW command must ask the human"
    hr = next(e for e in events if e["type"] == "human_required")
    assert hr["command"] == "pip install flask"
    # The turn pauses cleanly: nothing ran, no answer, and the loop stopped before
    # consuming the next scripted response.
    assert "tool_result" not in types
    assert "done" not in types
    assert chat._responses, "the loop must stop before requesting another turn"


def test_agent_runs_approved_yellow_command() -> None:
    # The same YELLOW command, now whitelisted, runs via execute_approved instead
    # of pausing again — this is what makes in-chat approval resumable.
    chat = ScriptedChat([
        _tool_call("execute_terminal", {"command": "pip install flask"}),
        {"role": "assistant", "content": "Installed."},
    ])
    events = list(
        ToolAgent(
            chat, _executor(), max_iters=3,
            approved_commands=["pip install flask"],
        ).run([{"role": "user", "content": "install flask"}])
    )
    types = [e["type"] for e in events]

    assert "human_required" not in types, "an authorised command must not pause again"
    results = [e for e in events if e["type"] == "tool_result"]
    assert results and "ran: pip install flask" in results[0]["output"]
    assert types[-1] == "done"


def test_agent_refuses_red_even_if_approved() -> None:
    # Approval cannot authorise a RED action: execute_approved refuses it, so it
    # surfaces as blocked, never runs, and does not pause for re-approval.
    chat = ScriptedChat([
        _tool_call("execute_terminal", {"command": "rm -rf /"}),
        {"role": "assistant", "content": "could not run that."},
    ])
    events = list(
        ToolAgent(
            chat, _executor(), max_iters=3,
            approved_commands=["rm -rf /"],
        ).run([{"role": "user", "content": "delete everything"}])
    )
    types = [e["type"] for e in events]

    assert "human_required" not in types
    blocked = [e for e in events if e["type"] == "tool_blocked"]
    assert blocked, "a RED command must stay blocked even when 'approved'"
    assert "RED action" in blocked[0]["reason"]
    assert events[-1]["type"] == "done"


# --------------------------------------------------------------------------- #
# edit_file — patch-style edits with diff preview + approval (Slice 2)
# --------------------------------------------------------------------------- #
@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Point scope roots AND the project root at an isolated temp dir for edit tests.

    read_root defaults to config.PROJECT_ROOT, and edit_file resolves the model's path
    under read_root before the scope check, so the project root must match the sandbox
    for bare in-scope names to resolve. monkeypatch auto-reverts after the test.
    """
    original = scope_lock.get_scope_roots()
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    scope_lock.set_scope_roots([tmp_path])
    try:
        yield tmp_path
    finally:
        scope_lock.set_scope_roots(list(original))


def test_agent_edit_resolves_project_relative_sandbox_path(tmp_path, monkeypatch) -> None:
    # Regression: a project-relative path that *names* the sandbox dir must resolve to
    # the real file, not double-join onto the scope root. This is the "file is empty"
    # bug — edit_file("training_ground/data.json") used to become
    # .../training_ground/training_ground/data.json (nonexistent) -> "no such file".
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    sand = tmp_path / "training_ground"
    sand.mkdir()
    (sand / "data.json").write_text('{ "greeting": "hello" }\n', encoding="utf-8")
    original = scope_lock.get_scope_roots()
    scope_lock.set_scope_roots([sand])
    try:
        chat = ScriptedChat([
            _tool_call("edit_file", {"filepath": "training_ground/data.json",
                                     "old_string": "hello", "new_string": "hi"}),
            {"role": "assistant", "content": "should not be reached"},
        ])
        events = list(ToolAgent(chat, _executor(), max_iters=3).run(
            [{"role": "user", "content": "change hello to hi"}]
        ))
        types = [e["type"] for e in events]
        assert "human_required" in types, "a project-relative sandbox path must resolve, not 404"
        hr = next(e for e in events if e["type"] == "human_required")
        assert "training_ground/data.json" in hr["command"]
        assert '-{ "greeting": "hello" }' in hr["diff"]
        assert '+{ "greeting": "hi" }' in hr["diff"]
        # Unapproved edit: nothing written yet.
        assert (sand / "data.json").read_text(encoding="utf-8") == '{ "greeting": "hello" }\n'
    finally:
        scope_lock.set_scope_roots(list(original))


def test_agent_edit_blocks_out_of_scope_path(sandbox) -> None:
    chat = ScriptedChat([
        _tool_call("edit_file", {"filepath": "../../../../etc/hosts",
                                 "old_string": "a", "new_string": "b"}),
        {"role": "assistant", "content": "blocked"},
    ])
    events = list(ToolAgent(chat, _executor(), max_iters=3).run(
        [{"role": "user", "content": "edit hosts"}]
    ))
    blocked = [e for e in events if e["type"] == "tool_blocked"]
    assert blocked and "scope" in blocked[0]["reason"].lower()


def test_agent_edit_pauses_with_diff(sandbox) -> None:
    f = sandbox / "greeting.txt"
    f.write_text("hello world\n", encoding="utf-8")
    chat = ScriptedChat([
        _tool_call("edit_file", {"filepath": "greeting.txt",
                                 "old_string": "world", "new_string": "there"}),
        {"role": "assistant", "content": "should not be reached"},
    ])
    events = list(ToolAgent(chat, _executor(), max_iters=3).run(
        [{"role": "user", "content": "change world to there"}]
    ))
    types = [e["type"] for e in events]

    assert "human_required" in types, "an unapproved edit must ask the human"
    hr = next(e for e in events if e["type"] == "human_required")
    assert "greeting.txt" in hr["command"]
    assert "-hello world" in hr["diff"] and "+hello there" in hr["diff"]
    # Nothing written, turn paused, loop stopped before the next scripted turn.
    assert f.read_text(encoding="utf-8") == "hello world\n"
    assert "done" not in types
    assert chat._responses


def test_agent_edit_applies_when_approved_and_snapshots(sandbox) -> None:
    f = sandbox / "greeting.txt"
    f.write_text("hello world\n", encoding="utf-8")
    snaps: list[str] = []
    chat = ScriptedChat([
        _tool_call("edit_file", {"filepath": "greeting.txt",
                                 "old_string": "world", "new_string": "there"}),
        {"role": "assistant", "content": "Done."},
    ])
    agent = ToolAgent(
        chat, _executor(), max_iters=3,
        approved_edits=[{"filepath": "greeting.txt",
                         "old_string": "world", "new_string": "there"}],
        snapshot=lambda msg="": snaps.append(msg),
    )
    events = list(agent.run([{"role": "user", "content": "change world to there"}]))
    types = [e["type"] for e in events]

    assert "human_required" not in types
    assert f.read_text(encoding="utf-8") == "hello there\n"   # written
    assert snaps, "a pre-write snapshot must be taken before applying the edit"
    results = [e for e in events if e["type"] == "tool_result"]
    assert results and "greeting.txt" in results[0]["output"]
    assert types[-1] == "done"


def test_agent_edit_audits_applied_write(sandbox) -> None:
    f = sandbox / "conf.txt"
    f.write_text("x = 1\n", encoding="utf-8")
    audited: list[tuple] = []
    chat = ScriptedChat([
        _tool_call("edit_file", {"filepath": "conf.txt",
                                 "old_string": "1", "new_string": "2"}),
        {"role": "assistant", "content": "done"},
    ])
    agent = ToolAgent(
        chat, _executor(), max_iters=3,
        approved_edits=[{"filepath": "conf.txt", "old_string": "1", "new_string": "2"}],
        audit_log=lambda *a, **k: audited.append(a),
    )
    list(agent.run([{"role": "user", "content": "bump"}]))
    assert f.read_text(encoding="utf-8") == "x = 2\n"
    assert audited, "the applied edit must be audited"


def test_agent_edit_rejects_nonunique_old_string(sandbox) -> None:
    f = sandbox / "dup.txt"
    f.write_text("a\na\n", encoding="utf-8")
    chat = ScriptedChat([
        _tool_call("edit_file", {"filepath": "dup.txt",
                                 "old_string": "a", "new_string": "b"}),
        {"role": "assistant", "content": "ambiguous"},
    ])
    events = list(ToolAgent(
        chat, _executor(), max_iters=3,
        approved_edits=[{"filepath": "dup.txt", "old_string": "a", "new_string": "b"}],
    ).run([{"role": "user", "content": "edit"}]))

    blocked = [e for e in events if e["type"] == "tool_blocked"]
    assert blocked and "unique" in blocked[0]["reason"].lower()
    assert f.read_text(encoding="utf-8") == "a\na\n"   # untouched (not unique)


def test_agent_edit_applies_approved_despite_model_arg_drift(sandbox) -> None:
    # On resume the model regenerates *different* args; the APPROVED edit (keyed
    # by filepath) is applied, not the model's drifted one.
    f = sandbox / "greeting.txt"
    f.write_text("hello world\n", encoding="utf-8")
    chat = ScriptedChat([
        _tool_call("edit_file", {"filepath": "greeting.txt",
                                 "old_string": "HELLO", "new_string": "zzz"}),
        {"role": "assistant", "content": "done"},
    ])
    agent = ToolAgent(
        chat, _executor(), max_iters=3,
        approved_edits=[{"filepath": "greeting.txt", "old_string": "world", "new_string": "there"}],
        snapshot=lambda msg="": None, audit_log=lambda *a, **k: None,
    )
    list(agent.run([{"role": "user", "content": "edit"}]))
    assert f.read_text(encoding="utf-8") == "hello there\n"   # the APPROVED edit, not the drift


def test_agent_edit_blocked_when_snapshot_fails(sandbox) -> None:
    # Fail-closed: a snapshot failure must NOT apply the edit.
    f = sandbox / "greeting.txt"
    f.write_text("hello world\n", encoding="utf-8")

    def boom(msg=""):
        raise RuntimeError("git down")

    chat = ScriptedChat([
        _tool_call("edit_file", {"filepath": "greeting.txt",
                                 "old_string": "world", "new_string": "there"}),
        {"role": "assistant", "content": "x"},
    ])
    events = list(ToolAgent(
        chat, _executor(), max_iters=3,
        approved_edits=[{"filepath": "greeting.txt", "old_string": "world", "new_string": "there"}],
        snapshot=boom, audit_log=lambda *a, **k: None,
    ).run([{"role": "user", "content": "edit"}]))
    blocked = [e for e in events if e["type"] == "tool_blocked"]
    assert blocked and "snapshot failed" in blocked[0]["reason"].lower()
    assert f.read_text(encoding="utf-8") == "hello world\n"   # not applied


def test_agent_edit_blocked_when_audit_fails(sandbox) -> None:
    # Fail-closed: an audit failure must NOT apply the edit.
    f = sandbox / "greeting.txt"
    f.write_text("hello world\n", encoding="utf-8")

    def boom_audit(*a, **k):
        raise RuntimeError("audit db locked")

    chat = ScriptedChat([
        _tool_call("edit_file", {"filepath": "greeting.txt",
                                 "old_string": "world", "new_string": "there"}),
        {"role": "assistant", "content": "x"},
    ])
    events = list(ToolAgent(
        chat, _executor(), max_iters=3,
        approved_edits=[{"filepath": "greeting.txt", "old_string": "world", "new_string": "there"}],
        snapshot=lambda msg="": None, audit_log=boom_audit,
    ).run([{"role": "user", "content": "edit"}]))
    blocked = [e for e in events if e["type"] == "tool_blocked"]
    assert blocked and "audit failed" in blocked[0]["reason"].lower()
    assert f.read_text(encoding="utf-8") == "hello world\n"   # not applied


def test_agent_edit_atomic_publish_failure_preserves_original(sandbox, monkeypatch) -> None:
    f = sandbox / "greeting.txt"
    f.write_text("hello world\n", encoding="utf-8")

    def fail_replace(*args, **kwargs):
        raise OSError("disk publication failed")

    monkeypatch.setattr("aios.agents.tool_handlers.os.replace", fail_replace)
    chat = ScriptedChat([
        _tool_call("edit_file", {"filepath": "greeting.txt",
                                 "old_string": "world", "new_string": "there"}),
        {"role": "assistant", "content": "x"},
    ])
    events = list(ToolAgent(
        chat, _executor(), max_iters=3,
        approved_edits=[{"filepath": "greeting.txt", "old_string": "world", "new_string": "there"}],
        snapshot=lambda msg="": None, audit_log=lambda *a, **k: None,
    ).run([{"role": "user", "content": "edit"}]))

    blocked = [e for e in events if e["type"] == "tool_blocked"]
    assert blocked and "could not write" in blocked[0]["reason"].lower()
    assert f.read_text(encoding="utf-8") == "hello world\n"
    assert not list(sandbox.glob(".greeting.txt.*.tmp"))


# --------------------------------------------------------------------------- #
# create_file — author a NEW file in the sandbox, behind the same human gate
# --------------------------------------------------------------------------- #
def test_agent_create_pauses_with_preview(sandbox) -> None:
    # An unapproved create_file must pause for the human, showing an all-additions
    # preview, and write nothing.
    chat = ScriptedChat([
        _tool_call("create_file", {"filepath": "new.py", "content": "print('hi')\n"}),
        {"role": "assistant", "content": "should not be reached"},
    ])
    events = list(ToolAgent(chat, _executor(), max_iters=3).run(
        [{"role": "user", "content": "make a new file"}]
    ))
    types = [e["type"] for e in events]

    assert "human_required" in types, "an unapproved create must ask the human"
    hr = next(e for e in events if e["type"] == "human_required")
    assert "new.py" in hr["command"]
    assert "+print('hi')" in hr["diff"]          # all-additions preview
    assert hr["creation"] == {"filepath": "new.py", "content": "print('hi')\n"}
    assert not (sandbox / "new.py").exists()     # nothing written
    assert "done" not in types
    assert chat._responses                       # paused before the next scripted turn


def test_agent_create_applies_approved_and_snapshots_despite_drift(sandbox) -> None:
    # On resume the model regenerates *different* content; the APPROVED creation
    # (keyed by filepath) is written, snapshotted first.
    snaps: list[str] = []
    chat = ScriptedChat([
        _tool_call("create_file", {"filepath": "sub/new.py", "content": "WRONG DRIFT\n"}),
        {"role": "assistant", "content": "Done."},
    ])
    agent = ToolAgent(
        chat, _executor(), max_iters=3,
        approved_creations=[{"filepath": "sub/new.py", "content": "print('hi')\n"}],
        snapshot=lambda msg="": snaps.append(msg),
    )
    events = list(agent.run([{"role": "user", "content": "create it"}]))
    types = [e["type"] for e in events]

    assert "human_required" not in types
    created = sandbox / "sub" / "new.py"
    assert created.read_text(encoding="utf-8") == "print('hi')\n"   # APPROVED, not drift
    assert snaps, "a pre-create snapshot must be taken before writing the new file"
    results = [e for e in events if e["type"] == "tool_result"]
    assert results and "sub/new.py" in results[0]["output"]
    assert types[-1] == "done"


def test_agent_create_audits_applied_write(sandbox) -> None:
    audited: list[tuple] = []
    chat = ScriptedChat([
        _tool_call("create_file", {"filepath": "note.txt", "content": "hello\n"}),
        {"role": "assistant", "content": "done"},
    ])
    agent = ToolAgent(
        chat, _executor(), max_iters=3,
        approved_creations=[{"filepath": "note.txt", "content": "hello\n"}],
        audit_log=lambda *a, **k: audited.append(a),
    )
    list(agent.run([{"role": "user", "content": "create note"}]))
    assert (sandbox / "note.txt").read_text(encoding="utf-8") == "hello\n"
    assert audited, "the applied creation must be audited"


def test_agent_create_refuses_existing_file(sandbox) -> None:
    # create_file is for NEW files only — an existing path is refused (use edit_file).
    f = sandbox / "exists.txt"
    f.write_text("original\n", encoding="utf-8")
    chat = ScriptedChat([
        _tool_call("create_file", {"filepath": "exists.txt", "content": "clobbered\n"}),
        {"role": "assistant", "content": "blocked"},
    ])
    events = list(ToolAgent(
        chat, _executor(), max_iters=3,
        approved_creations=[{"filepath": "exists.txt", "content": "clobbered\n"}],
    ).run([{"role": "user", "content": "create over existing"}]))

    blocked = [e for e in events if e["type"] == "tool_blocked"]
    assert blocked and "already exists" in blocked[0]["reason"].lower()
    assert "edit_file" in blocked[0]["reason"]
    assert f.read_text(encoding="utf-8") == "original\n"   # not overwritten


def test_agent_create_is_noop_for_existing_identical_content(sandbox) -> None:
    # Replay tolerance: the resumable approval flow re-runs the whole turn, so the
    # model legitimately re-issues a create for a file an earlier replay already
    # wrote. Byte-identical content writes nothing and needs no approval — the
    # loop continues to the task's remaining steps instead of dead-ending.
    f = sandbox / "made.py"
    f.write_text("x = 1\n", encoding="utf-8")
    chat = ScriptedChat([
        _tool_call("create_file", {"filepath": "made.py", "content": "x = 1\n"}),
        {"role": "assistant", "content": "continuing"},
    ])
    events = list(ToolAgent(chat, _executor(), max_iters=3).run(
        [{"role": "user", "content": "create made.py"}]
    ))
    types = [e["type"] for e in events]

    assert "human_required" not in types, "no write happens, so nothing needs approval"
    assert "tool_blocked" not in types
    results = [
        e for e in events
        if e["type"] == "tool_result" and e.get("tool") == "create_file"
    ]
    assert results and "nothing to write" in results[0]["output"]
    assert f.read_text(encoding="utf-8") == "x = 1\n"   # untouched
    assert types[-1] == "done"


def test_agent_pre_applies_granted_creation_when_model_ignores_it(sandbox) -> None:
    # The dropped-grant bug: a human-approved write must land even when the
    # replayed model takes a different path and never re-issues the call.
    chat = ScriptedChat([
        {"role": "assistant", "content": "Everything is already in order."},
    ])
    agent = ToolAgent(
        chat, _executor(), max_iters=2,
        approved_creations=[{"filepath": "granted.py", "content": "x = 1\n"}],
    )
    events = list(agent.run([{"role": "user", "content": "create granted.py"}]))
    types = [e["type"] for e in events]

    assert (sandbox / "granted.py").read_text(encoding="utf-8") == "x = 1\n"
    pre_applied = [
        e for e in events
        if e["type"] == "tool_result" and str(e.get("id", "")).startswith("grant-create")
    ]
    assert pre_applied and "granted.py" in pre_applied[0]["output"]
    assert "human_required" not in types
    assert types[-1] == "done"


def test_agent_pre_applies_all_grants_before_verifying(sandbox) -> None:
    # Ordering fix: a module AND its test are granted together (the TEST listed
    # first on purpose). Every write must land BEFORE any verify runs — otherwise
    # the test verifies against a not-yet-applied module and records a FALSE failure
    # even though the finished files are correct.
    chat = ScriptedChat([{"role": "assistant", "content": "Done."}])
    agent = ToolAgent(
        chat, _executor(), max_iters=2,
        approved_creations=[
            {"filepath": "test_thing.py", "content": "from thing import f\n\ndef test_f():\n    assert f() == 1\n"},
            {"filepath": "thing.py", "content": "def f():\n    return 1\n"},
        ],
    )
    events = list(agent.run([{"role": "user", "content": "make thing + its test"}]))
    assert (sandbox / "thing.py").is_file() and (sandbox / "test_thing.py").is_file()
    last_write = max(
        i for i, e in enumerate(events)
        if e.get("type") == "tool_result" and str(e.get("id", "")).startswith("grant-create")
    )
    verifies = [i for i, e in enumerate(events) if str(e.get("id", "")).startswith("autoverify")]
    assert verifies, "the test write should trigger a verify"
    assert min(verifies) > last_write  # every verify runs only after every write landed


def test_agent_pre_applies_granted_edit_and_skips_when_landed(sandbox) -> None:
    f = sandbox / "mod.py"
    f.write_text("value = 1\n", encoding="utf-8")
    grant = [{"filepath": "mod.py", "old_string": "value = 1", "new_string": "value = 2"}]
    chat = ScriptedChat([
        {"role": "assistant", "content": "Nothing further to do."},
    ])
    events = list(ToolAgent(
        chat, _executor(), max_iters=2, approved_edits=grant,
    ).run([{"role": "user", "content": "bump the value"}]))

    assert f.read_text(encoding="utf-8") == "value = 2\n"
    assert any(str(e.get("id", "")).startswith("grant-edit") for e in events)

    # Second replay with the same grant: the edit already landed — no re-apply
    # (no grant-edit tool_result) and no block; but the RECIPE still carries
    # the write (exactly one tool_call), the workflow-steps analog of the
    # noop-verify queueing: the final done-replay's workflow_steps — and any
    # skill it mints — must include every write of the approval chain.
    chat2 = ScriptedChat([
        {"role": "assistant", "content": "Confirmed."},
    ])
    events2 = list(ToolAgent(
        chat2, _executor(), max_iters=2, approved_edits=grant,
    ).run([{"role": "user", "content": "bump the value"}]))

    assert f.read_text(encoding="utf-8") == "value = 2\n"
    grant_frames = [e for e in events2 if str(e.get("id", "")).startswith("grant-edit")]
    assert [e["type"] for e in grant_frames] == ["tool_call"], (
        f"a landed grant replays as one recipe tool_call, nothing else; got "
        f"{[e['type'] for e in grant_frames]}"
    )
    assert not any(e["type"] == "tool_blocked" for e in events2)


def test_agent_edit_is_noop_when_replacement_already_present(sandbox) -> None:
    # Replay tolerance, edit analog of the create no-op: the model re-issues
    # an edit an earlier replay already applied; the replacement being present
    # is success, not a dead end.
    f = sandbox / "done.py"
    f.write_text("value = 2\n", encoding="utf-8")
    chat = ScriptedChat([
        _tool_call("edit_file", {
            "filepath": "done.py", "old_string": "value = 1", "new_string": "value = 2",
        }),
        {"role": "assistant", "content": "continuing"},
    ])
    events = list(ToolAgent(
        chat, _executor(), max_iters=3,
        approved_edits=[{"filepath": "done.py", "old_string": "value = 1", "new_string": "value = 2"}],
    ).run([{"role": "user", "content": "bump the value"}]))
    types = [e["type"] for e in events]

    assert "human_required" not in types
    results = [
        e for e in events
        if e["type"] == "tool_result" and e.get("tool") == "edit_file"
        and "nothing to change" in e.get("output", "")
    ]
    assert results, "an already-applied edit must report success, not block"
    assert f.read_text(encoding="utf-8") == "value = 2\n"
    assert types[-1] == "done"


def test_agent_create_blocked_out_of_scope(tmp_path, monkeypatch) -> None:
    # A path inside the project but OUTSIDE the sandbox scope is refused, even when
    # an approval is supplied (out-of-sandbox writes are blocked, never written).
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    sand = tmp_path / "training_ground"
    sand.mkdir()
    original = scope_lock.get_scope_roots()
    scope_lock.set_scope_roots([sand])
    try:
        chat = ScriptedChat([
            _tool_call("create_file", {"filepath": "aios/x.py", "content": "x = 1\n"}),
            {"role": "assistant", "content": "blocked"},
        ])
        events = list(ToolAgent(
            chat, _executor(), max_iters=3, read_root=tmp_path,
            approved_creations=[{"filepath": "aios/x.py", "content": "x = 1\n"}],
        ).run([{"role": "user", "content": "create out of scope"}]))
        blocked = [e for e in events if e["type"] == "tool_blocked"]
        assert blocked and "scope" in blocked[0]["reason"].lower()
        assert not (tmp_path / "aios" / "x.py").exists()
    finally:
        scope_lock.set_scope_roots(list(original))


def test_agent_create_blocked_path_escape(sandbox) -> None:
    chat = ScriptedChat([
        _tool_call("create_file", {"filepath": "../../../../etc/evil", "content": "x"}),
        {"role": "assistant", "content": "blocked"},
    ])
    events = list(ToolAgent(
        chat, _executor(), max_iters=3,
        approved_creations=[{"filepath": "../../../../etc/evil", "content": "x"}],
    ).run([{"role": "user", "content": "escape"}]))
    blocked = [e for e in events if e["type"] == "tool_blocked"]
    assert blocked and (
        "escapes the project root" in blocked[0]["reason"]
        or "scope" in blocked[0]["reason"].lower()
    )


def test_agent_create_blocked_when_audit_fails(sandbox) -> None:
    # Fail-closed: an audit failure must NOT create the file.
    def boom_audit(*a, **k):
        raise RuntimeError("audit db locked")

    chat = ScriptedChat([
        _tool_call("create_file", {"filepath": "new.py", "content": "x = 1\n"}),
        {"role": "assistant", "content": "x"},
    ])
    events = list(ToolAgent(
        chat, _executor(), max_iters=3,
        approved_creations=[{"filepath": "new.py", "content": "x = 1\n"}],
        snapshot=lambda msg="": None, audit_log=boom_audit,
    ).run([{"role": "user", "content": "create"}]))
    blocked = [e for e in events if e["type"] == "tool_blocked"]
    assert blocked and "audit failed" in blocked[0]["reason"].lower()
    assert not (sandbox / "new.py").exists()   # not created


def test_agent_create_blocked_when_snapshot_fails(sandbox) -> None:
    # Fail-closed: a snapshot failure must NOT create the file.
    def boom(msg=""):
        raise RuntimeError("git down")

    chat = ScriptedChat([
        _tool_call("create_file", {"filepath": "new.py", "content": "x = 1\n"}),
        {"role": "assistant", "content": "x"},
    ])
    events = list(ToolAgent(
        chat, _executor(), max_iters=3,
        approved_creations=[{"filepath": "new.py", "content": "x = 1\n"}],
        snapshot=boom, audit_log=lambda *a, **k: None,
    ).run([{"role": "user", "content": "create"}]))
    blocked = [e for e in events if e["type"] == "tool_blocked"]
    assert blocked and "snapshot failed" in blocked[0]["reason"].lower()
    assert not (sandbox / "new.py").exists()   # not created


def test_agent_create_atomic_publish_failure_leaves_target_absent(sandbox, monkeypatch) -> None:
    def fail_link(*args, **kwargs):
        raise OSError("disk publication failed")

    monkeypatch.setattr("aios.agents.tool_handlers.os.link", fail_link)
    chat = ScriptedChat([
        _tool_call("create_file", {"filepath": "sub/new.py", "content": "x = 1\n"}),
        {"role": "assistant", "content": "x"},
    ])
    events = list(ToolAgent(
        chat, _executor(), max_iters=3,
        approved_creations=[{"filepath": "sub/new.py", "content": "x = 1\n"}],
        snapshot=lambda msg="": None, audit_log=lambda *a, **k: None,
    ).run([{"role": "user", "content": "create"}]))

    blocked = [e for e in events if e["type"] == "tool_blocked"]
    assert blocked and "could not create" in blocked[0]["reason"].lower()
    assert not (sandbox / "sub" / "new.py").exists()
    assert not list((sandbox / "sub").glob(".new.py.*.tmp"))


# --------------------------------------------------------------------------- #
# verify — run a check through the gated Verifier to PROVE a change worked
# (Slice 5 / blueprint stage 8, now wired into the live loop)
# --------------------------------------------------------------------------- #
def test_agent_verify_reports_pass_and_does_not_reflect() -> None:
    # The agent verifies a passing command: the result reports PASS with counts,
    # and a PASS must never fire the reflection hook (nothing to learn from).
    chat = ScriptedChat([
        _tool_call("verify", {"command": "pytest"}),
        {"role": "assistant", "content": "Verified — all green."},
    ])
    reflected: list[tuple[str, str]] = []
    events = list(
        ToolAgent(
            chat, _passing_executor(), max_iters=3,
            approved_commands=["pytest"],
            on_failure=lambda c, o: reflected.append((c, o)),
        ).run([{"role": "user", "content": "verify the tests pass"}])
    )

    results = [e for e in events if e["type"] == "tool_result" and e.get("tool") == "verify"]
    assert results, "a verify must surface its result to the stream"
    assert "VERIFY PASS" in results[0]["output"]
    assert "3 passed" in results[0]["output"]          # parsed pass count is shown
    assert reflected == [], "a passing verification must not trigger reflection"
    assert events[-1]["type"] == "done"


@pytest.mark.parametrize(
    "raw, expected",
    [
        # repo-relative path the model commonly writes -> stripped to sandbox-relative
        ("pytest training_ground/test_x.py", "pytest test_x.py"),
        ('pytest "training_ground/test_x.py" -q', 'pytest "test_x.py" -q'),
        ("python -m pytest ./training_ground/test_x.py", "python -m pytest test_x.py"),
        ("pytest training_ground/sub/test_x.py", "pytest sub/test_x.py"),
        # already-correct / unrelated commands are untouched (idempotent no-ops)
        ("pytest test_x.py", "pytest test_x.py"),
        ("pytest -q", "pytest -q"),
        ('pytest "test_x.py" -q', 'pytest "test_x.py" -q'),
        # a token that merely CONTAINS the name but is not a path segment is left alone
        ("pytest mytraining_ground/test_x.py", "pytest mytraining_ground/test_x.py"),
    ],
)
def test_normalise_sandbox_paths_strips_redundant_root_prefix(raw, expected) -> None:
    # The verify tool runs FROM the sandbox cwd, so a repo-relative path would
    # double-nest and collect 0 tests (exit 4 -> spurious FAIL). The normaliser
    # strips ONLY the exact sandbox-root segment, leaving everything else intact.
    assert config.SCOPE_ROOTS[0].name == "training_ground"  # guards the fixtures above
    agent = ToolAgent(ScriptedChat([]), _executor(), max_iters=1)
    assert agent._normalise_sandbox_paths(raw) == expected


def test_verify_runs_mispathed_model_command_after_normalisation() -> None:
    # End-to-end: the model verifies with a repo-relative path; the normaliser
    # makes it sandbox-relative so the check actually runs (PASS), instead of a
    # spurious FAIL from a 0-tests-collected double-nest.
    chat = ScriptedChat([
        _tool_call("verify", {"command": "pytest training_ground/test_x.py"}),
        {"role": "assistant", "content": "Verified — all green."},
    ])
    events = list(
        ToolAgent(
            chat, _passing_executor(), max_iters=3,
            approved_commands=["pytest test_x.py"],  # the NORMALISED form is what runs
        ).run([{"role": "user", "content": "verify it"}])
    )
    results = [e for e in events if e["type"] == "tool_result" and e.get("tool") == "verify"]
    assert results and "VERIFY PASS" in results[0]["output"]


def test_agent_verify_requires_human_approval() -> None:
    chat = ScriptedChat([_tool_call("verify", {"command": "pytest"})])
    events = list(ToolAgent(chat, _passing_executor(), max_iters=2).run(
        [{"role": "user", "content": "verify the tests"}]
    ))

    required = [e for e in events if e["type"] == "human_required"]
    assert required and required[0]["command"] == "pytest"


def test_agent_verify_reports_fail_and_reflects_once() -> None:
    # A failing verification reports FAIL AND fires the on_failure reflection hook
    # (the Verifier fires it) — but the dispatch path must NOT double-reflect, so
    # no separate 'reflect' step is surfaced from the verify path.
    chat = ScriptedChat([
        _tool_call("verify", {"command": "pytest"}),
        {"role": "assistant", "content": "Verification failed; noted."},
    ])
    reflected: list[tuple[str, str]] = []

    def hook(command: str, error_output: str):
        reflected.append((command, error_output))
        return {"error_type": "AssertionError", "lesson_text": "fix the broken case",
                "recurrence": False, "mistake_id": 11}

    events = list(
        ToolAgent(
            chat, _failing_executor(), max_iters=3,
            approved_commands=["pytest"], on_failure=hook,
        ).run(
            [{"role": "user", "content": "verify the change"}]
        )
    )

    results = [e for e in events if e["type"] == "tool_result" and e.get("tool") == "verify"]
    assert results and "VERIFY FAIL" in results[0]["output"]
    # The SAME reflection hook fired, once, with the failed command + its output.
    assert reflected and reflected[0][0] == "pytest"
    assert "boom" in reflected[0][1]
    # ...and the verify path did not also emit a 'reflect' step (no double-reflect).
    assert not any(e.get("tool") == "reflect" for e in events)
    assert events[-1]["type"] == "done"


def test_agent_verify_red_command_is_refused_by_gateway_not_run() -> None:
    # An out-of-scope / RED verify command is refused by the security gateway:
    # it surfaces as blocked, never reaches the runner, and is not a "mistake"
    # to reflect on (a refusal is correct behaviour).
    runner = RecordingRunner()
    ex = Executor(runner=runner, rate_limiter=RateLimiter(), audit_log=lambda *a, **k: None)
    chat = ScriptedChat([
        _tool_call("verify", {"command": "rm -rf /"}),
        {"role": "assistant", "content": "Could not verify — that command was blocked."},
    ])
    reflected: list[str] = []
    events = list(
        ToolAgent(chat, ex, max_iters=3, on_failure=lambda c, o: reflected.append(c)).run(
            [{"role": "user", "content": "verify by wiping the disk"}]
        )
    )

    blocked = [e for e in events if e["type"] == "tool_blocked" and e.get("tool") == "verify"]
    assert blocked, "a RED verify command must be refused by the gateway (blocked)"
    assert "BLOCK" in blocked[0]["reason"].upper()
    assert runner.calls == [], "a blocked verify command must never reach the runner"
    assert reflected == [], "a security block is correct behaviour, not a mistake to reflect on"
    assert events[-1]["type"] == "done"


# --------------------------------------------------------------------------- #
# plan — decompose a goal into a confidence-gated plan BEFORE acting
# (Slice 5 Planner + the 0.72 confidence gate, now wired into the live loop)
# --------------------------------------------------------------------------- #
def test_agent_plan_lists_ordered_steps() -> None:
    # plan over the injected completion client surfaces an ordered, confidence-
    # scored summary as a normal tool_result (tool == "plan").
    planner_llm = FakePlannerLLM(_PLAN_JSON)
    chat = ScriptedChat([
        _tool_call("plan", {"goal": "refactor the parser safely"}),
        {"role": "assistant", "content": "Here is my plan."},
    ])
    events = list(
        ToolAgent(chat, _executor(), max_iters=3, planner_llm=planner_llm).run(
            [{"role": "user", "content": "refactor the parser safely"}]
        )
    )

    results = [e for e in events if e["type"] == "tool_result" and e.get("tool") == "plan"]
    assert results, "plan must surface a tool_result"
    out = results[0]["output"]
    assert "Read config" in out and "Refactor parser" in out and "Run tests" in out
    # ordered: step 1 appears before step 3 in the summary
    assert out.index("Read config") < out.index("Run tests")
    assert planner_llm.calls, "the planner's COMPLETION client (.complete) must be called"
    assert events[-1]["type"] == "done"


def test_agent_plan_flags_low_confidence_step_for_human_review() -> None:
    # The 0.40 step is below the 0.72 gate -> surfaced as needing human review.
    planner_llm = FakePlannerLLM(_PLAN_JSON)
    chat = ScriptedChat([
        _tool_call("plan", {"goal": "do the risky thing"}),
        {"role": "assistant", "content": "One step needs review."},
    ])
    events = list(
        ToolAgent(chat, _executor(), max_iters=3, planner_llm=planner_llm).run(
            [{"role": "user", "content": "do the risky thing"}]
        )
    )

    out = next(
        e["output"] for e in events
        if e["type"] == "tool_result" and e.get("tool") == "plan"
    )
    assert "human review" in out.lower()
    assert "Refactor parser" in out          # the 0.40 step is the escalated one
    assert "0.72" in out                      # the confidence threshold is named


def test_agent_plan_surfaces_planner_error_cleanly() -> None:
    # Junk LLM output -> PlannerError -> a clean advisory result (status ok), NOT a
    # security block and NOT a reflectable failure (no reflect step, hook untouched).
    planner_llm = FakePlannerLLM("not json at all")
    chat = ScriptedChat([
        _tool_call("plan", {"goal": "whatever"}),
        {"role": "assistant", "content": "Could not plan."},
    ])
    reflected: list[str] = []
    events = list(
        ToolAgent(
            chat, _executor(), max_iters=3, planner_llm=planner_llm,
            on_failure=lambda c, o: reflected.append(c),
        ).run([{"role": "user", "content": "whatever"}])
    )

    results = [e for e in events if e["type"] in ("tool_result", "tool_blocked") and e.get("tool") == "plan"]
    assert results and results[0]["type"] == "tool_result"   # surfaced cleanly, not blocked
    assert "[plan error]" in results[0]["output"]
    assert not any(e.get("tool") == "reflect" for e in events)
    assert reflected == [], "a planning error is advisory, not a reflectable failure"
    assert events[-1]["type"] == "done"


def test_agent_plan_degrades_gracefully_without_planner() -> None:
    # No planner_llm injected -> the plan tool returns a graceful "unavailable"
    # result and the loop still completes normally.
    chat = ScriptedChat([
        _tool_call("plan", {"goal": "anything"}),
        {"role": "assistant", "content": "No planner available, proceeding."},
    ])
    events = list(
        ToolAgent(chat, _executor(), max_iters=3).run(
            [{"role": "user", "content": "anything"}]
        )
    )

    results = [e for e in events if e["type"] in ("tool_result", "tool_blocked") and e.get("tool") == "plan"]
    assert results and results[0]["type"] == "tool_result"
    assert "[plan unavailable]" in results[0]["output"]
    assert events[-1]["type"] == "done"


def test_agent_plan_survives_planner_llm_error() -> None:
    # If the planner's completion LLM fails (e.g. Ollama down while chatting on Bedrock),
    # the plan tool must degrade to a graceful advisory result, NOT abort the turn —
    # run() does not wrap _dispatch in try/except, so _plan must catch it itself.
    class _BoomPlannerLLM:
        def complete(self, prompt, *, system=None):
            raise LLMError("ollama is down")

    chat = ScriptedChat([
        _tool_call("plan", {"goal": "do the thing"}),
        {"role": "assistant", "content": "Planner was unavailable; proceeding."},
    ])
    reflected: list[str] = []
    events = list(
        ToolAgent(
            chat, _executor(), max_iters=3, planner_llm=_BoomPlannerLLM(),
            on_failure=lambda c, o: reflected.append(c),
        ).run([{"role": "user", "content": "do the thing"}])
    )

    results = [
        e for e in events
        if e["type"] in ("tool_result", "tool_blocked") and e.get("tool") == "plan"
    ]
    assert results and results[0]["type"] == "tool_result"   # graceful, not a crash
    assert "[plan error]" in results[0]["output"]
    assert not any(e.get("tool") == "reflect" for e in events)
    assert reflected == [], "a planner failure is advisory, not a reflectable mistake"
    assert events[-1]["type"] == "done"


# --------------------------------------------------------------------------- #
# force verify-after-write — a successful sandbox write AUTO-runs its sibling
# test so PASS/FAIL (not the model's narration) is the authoritative signal.
# --------------------------------------------------------------------------- #
def test_agent_auto_verifies_after_edit_and_reports_pass(sandbox, monkeypatch) -> None:
    # The model never calls verify; the loop forces it after the approved write.
    monkeypatch.setattr(config, "SCOPE_ROOTS", [sandbox])
    (sandbox / "greeter.py").write_text(
        'def greet(name):\n    return "Hello, !"\n', encoding="utf-8"
    )
    (sandbox / "test_greeter.py").write_text(
        'from greeter import greet\n\n\ndef test_greet():\n'
        '    assert greet("Ada") == "Hello, Ada!"\n',
        encoding="utf-8",
    )
    approved = {"filepath": "greeter.py",
                "old_string": 'return "Hello, !"',
                "new_string": 'return f"Hello, {name}!"'}
    chat = ScriptedChat([
        _tool_call("edit_file", dict(approved)),
        {"role": "assistant", "content": "I fixed greet()."},
    ])
    agent = ToolAgent(
        chat, _passing_executor(), max_iters=3,
        approved_edits=[approved],
        snapshot=lambda msg="": None, audit_log=lambda *a, **k: None,
    )
    events = list(agent.run([{"role": "user", "content": "fix greet"}]))

    verify = [e for e in events if e.get("tool") == "verify" and e["type"] == "tool_result"]
    assert verify, "an approved .py edit must AUTO-run its sibling test"
    assert "VERIFY PASS" in verify[0]["output"]
    assert verify[0]["id"].startswith("autoverify-"), "the verify was forced by the loop, not the model"
    assert (sandbox / "greeter.py").read_text(encoding="utf-8") == (
        'def greet(name):\n    return f"Hello, {name}!"\n'
    )


def test_agent_auto_verify_fail_overrides_false_success_and_reflects_once(sandbox, monkeypatch) -> None:
    # Even when the model NARRATES success, the forced verify reports FAIL — and a
    # genuine failure reflects exactly once (inside the Verifier), with no separate
    # 'reflect' step from the write path (no double-reflect).
    monkeypatch.setattr(config, "SCOPE_ROOTS", [sandbox])
    (sandbox / "greeter.py").write_text(
        'def greet(name):\n    return "Hello, !"\n', encoding="utf-8"
    )
    (sandbox / "test_greeter.py").write_text(
        'from greeter import greet\n\n\ndef test_greet():\n'
        '    assert greet("Ada") == "Hello, Ada!"\n',
        encoding="utf-8",
    )
    approved = {"filepath": "greeter.py",
                "old_string": 'return "Hello, !"', "new_string": 'return "Hi, !"'}
    chat = ScriptedChat([
        _tool_call("edit_file", dict(approved)),
        {"role": "assistant", "content": "Done — the bug is fixed and it passes now."},
    ])
    reflected: list[tuple[str, str]] = []

    def hook(command: str, error_output: str):
        reflected.append((command, error_output))
        return {"error_type": "AssertionError", "lesson_text": "greet still drops the name",
                "recurrence": False, "mistake_id": 5}

    agent = ToolAgent(
        chat, _failing_executor(), max_iters=3,
        approved_edits=[approved],
        snapshot=lambda msg="": None, audit_log=lambda *a, **k: None,
        on_failure=hook,
    )
    events = list(agent.run([{"role": "user", "content": "fix greet"}]))

    verify = [e for e in events if e.get("tool") == "verify" and e["type"] == "tool_result"]
    assert verify and "VERIFY FAIL" in verify[0]["output"], "the forced verify must contradict the model's prose"
    assert len(reflected) == 1, "a genuine verify FAIL must reflect exactly once"
    assert "pytest" in reflected[0][0]
    assert not any(e.get("tool") == "reflect" for e in events), "no double-reflect from the write path"


def test_agent_auto_verify_reports_unverified_when_no_test(sandbox, monkeypatch) -> None:
    # A .py change with no sibling test is reported UNVERIFIED — never a false pass.
    monkeypatch.setattr(config, "SCOPE_ROOTS", [sandbox])
    (sandbox / "lonely.py").write_text("x = 1\n", encoding="utf-8")
    approved = {"filepath": "lonely.py", "old_string": "x = 1", "new_string": "x = 2"}
    chat = ScriptedChat([
        _tool_call("edit_file", dict(approved)),
        {"role": "assistant", "content": "Changed it."},
    ])
    agent = ToolAgent(
        chat, _executor(), max_iters=3, approved_edits=[approved],
        snapshot=lambda msg="": None, audit_log=lambda *a, **k: None,
    )
    events = list(agent.run([{"role": "user", "content": "bump"}]))

    verify = [e for e in events if e.get("tool") == "verify"]
    assert verify and "UNVERIFIED" in verify[0]["output"] and "SKIPPED" in verify[0]["output"]


def test_agent_no_auto_verify_for_non_python_write(sandbox, monkeypatch) -> None:
    # Non-code writes (.txt/.json/config) aren't pytest-verifiable — the loop is
    # left exactly as it was for them (no verify step).
    monkeypatch.setattr(config, "SCOPE_ROOTS", [sandbox])
    (sandbox / "notes.txt").write_text("hello world\n", encoding="utf-8")
    approved = {"filepath": "notes.txt", "old_string": "world", "new_string": "there"}
    chat = ScriptedChat([
        _tool_call("edit_file", dict(approved)),
        {"role": "assistant", "content": "Done."},
    ])
    agent = ToolAgent(
        chat, _executor(), max_iters=3, approved_edits=[approved],
        snapshot=lambda msg="": None, audit_log=lambda *a, **k: None,
    )
    events = list(agent.run([{"role": "user", "content": "edit notes"}]))

    assert (sandbox / "notes.txt").read_text(encoding="utf-8") == "hello there\n"
    assert not any(e.get("tool") == "verify" for e in events), "text edits aren't auto-verified"


# --------------------------------------------------------------------------- #
# browse — public-internet fetch tool (Slice 6)
# --------------------------------------------------------------------------- #

class FakeResponse:
    def __init__(self, text, headers=None, status_code=200):
        self.text = text
        self.headers = headers or {"Content-Type": "text/html"}
        self.status_code = status_code
        self.is_redirect = False
        self.is_permanent_redirect = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


def test_browse_pauses_for_approval_without_pre_approval() -> None:
    chat = ScriptedChat([
        _tool_call("browse", {"url": "https://example.com"}),
        {"role": "assistant", "content": "I can fetch after approval."},
    ])
    events = list(ToolAgent(chat, _executor(), max_iters=3).run(
        [{"role": "user", "content": "read example.com"}]
    ))
    hr = [e for e in events if e["type"] == "human_required"]
    assert len(hr) == 1
    assert hr[0]["command"] == "browse https://example.com"
    # No tool_result for browse because it paused before fetching.
    assert not any(e.get("tool") == "browse" and e["type"] == "tool_result" for e in events)


def test_browse_blocks_local_and_private_urls() -> None:
    chat = ScriptedChat([
        _tool_call("browse", {"url": "http://localhost:8000"}),
        {"role": "assistant", "content": "blocked"},
    ])
    events = list(ToolAgent(
        chat, _executor(), max_iters=3, approved_commands=["browse http://localhost:8000"]
    ).run([{"role": "user", "content": "read localhost"}]))
    blocked = [e for e in events if e["type"] == "tool_blocked"]
    assert blocked and "local target" in blocked[0]["reason"].lower()


def test_browse_fetches_and_extracts_text(monkeypatch) -> None:
    def fake_get(url, *, timeout, headers, **kwargs):
        return FakeResponse("<html><body><p>Hello world</p></body></html>")

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("socket.getaddrinfo", lambda host, port: [(None, None, None, None, ("93.184.216.34", 0))])

    chat = ScriptedChat([
        _tool_call("browse", {"url": "https://example.com"}),
        {"role": "assistant", "content": "Fetched."},
    ])
    events = list(ToolAgent(
        chat, _executor(), max_iters=3, approved_commands=["browse https://example.com"]
    ).run([{"role": "user", "content": "read example.com"}]))
    result = [e for e in events if e.get("tool") == "browse" and e["type"] == "tool_result"]
    assert result and "Hello world" in result[0]["output"]
