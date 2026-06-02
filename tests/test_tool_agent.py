"""Unit tests for the agentic tool loop (aios.agents.tool_agent).

A scripted fake chat client drives the loop deterministically — no Ollama, no
shell — while a fake-runner Executor exercises the real security gateway so the
blocking behaviour under test is genuine, not mocked away.
"""
from __future__ import annotations

from typing import Optional

from aios.agents.tool_agent import ToolAgent
from aios.core.executor import Executor
from aios.core.llm import LLMError
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
        return "ok", "", 0


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
        _tool_call("execute_terminal", {"command": "pytest"}),
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

    assert seen and seen[0][0] == "pytest"          # the hook saw the failed command
    reflect_steps = [e for e in events if e.get("tool") == "reflect"]
    assert reflect_steps and "add a guard clause" in reflect_steps[0]["output"]


def test_agent_promotes_lesson_after_corrective_success() -> None:
    # Fail a command (records lesson 7), then succeed on the retry -> verify it.
    chat = ScriptedChat([
        _tool_call("execute_terminal", {"command": "pytest"}),
        _tool_call("execute_terminal", {"command": "pytest --fixed"}),
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

    assert confirmed == [7], "the lesson should be promoted after the corrective success"
    verify_steps = [e for e in events if e.get("tool") == "reflect" and "Verified" in e.get("output", "")]
    assert verify_steps, "a 'lesson verified' step should be surfaced"


def test_agent_verifies_prior_session_lesson_on_success() -> None:
    # A lesson carried in from an earlier turn is verified when a command now
    # succeeds — no failure needed this run.
    chat = ScriptedChat([
        _tool_call("execute_terminal", {"command": "echo ok"}),
        {"role": "assistant", "content": "looks good"},
    ])
    confirmed: list[int] = []
    list(
        ToolAgent(
            chat, _executor(), max_iters=3,
            confirm_lesson=confirmed.append, prior_lesson_ids=[42],
        ).run([{"role": "user", "content": "continue"}])
    )
    assert confirmed == [42], "a recalled prior-session lesson should verify on a success"


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
