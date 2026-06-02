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
