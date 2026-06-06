"""Unit tests for the agentic tool loop (aios.agents.tool_agent).

A scripted fake chat client drives the loop deterministically — no Ollama, no
shell — while a fake-runner Executor exercises the real security gateway so the
blocking behaviour under test is genuine, not mocked away.
"""
from __future__ import annotations

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
