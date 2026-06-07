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
        return "ok", "", 0


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
            on_failure=lambda c, o: reflected.append((c, o)),
        ).run([{"role": "user", "content": "verify the tests pass"}])
    )

    results = [e for e in events if e["type"] == "tool_result" and e.get("tool") == "verify"]
    assert results, "a verify must surface its result to the stream"
    assert "VERIFY PASS" in results[0]["output"]
    assert "3 passed" in results[0]["output"]          # parsed pass count is shown
    assert reflected == [], "a passing verification must not trigger reflection"
    assert events[-1]["type"] == "done"


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
        ToolAgent(chat, _failing_executor(), max_iters=3, on_failure=hook).run(
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
