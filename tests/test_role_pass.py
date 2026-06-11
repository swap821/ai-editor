"""Behavioral tests for the sequential role-pass castes (aios.agents.role_pass).

Same testing philosophy as test_tool_agent.py: a scripted fake chat client
drives the legs deterministically while a fake-runner Executor exercises the
REAL security gateway, so the caste enforcement under test is genuine.
"""
from __future__ import annotations

import pytest

from aios import config
from aios.agents.role_pass import run_role_pass
from aios.agents.tool_agent import ToolAgent
from aios.core.executor import Executor
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
    def __call__(self, command, *, cwd, env, timeout_s):
        return f"ran: {command}", "", 0


class FailRunner:
    def __call__(self, command, *, cwd, env, timeout_s):
        return "", "boom: assertion failed", 1


def _executor(runner=None) -> Executor:
    return Executor(
        runner=runner or FakeRunner(),
        rate_limiter=RateLimiter(),
        audit_log=lambda *a, **k: None,
    )


def _tool_call(name: str, arguments: dict) -> dict:
    return {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": name, "arguments": arguments}}
    ]}


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    original = scope_lock.get_scope_roots()
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    scope_lock.set_scope_roots([tmp_path])
    yield tmp_path
    scope_lock.set_scope_roots(original)


def _factory(chat, executor, **fixed):
    def make_agent(**overrides):
        params = {"max_iters": 5, **fixed, **overrides}   # conductor overrides win
        return ToolAgent(chat, executor, **params)
    return make_agent


def _castes(events: list[dict]) -> list[str]:
    return [
        str(e["role"]) for e in events
        if e.get("tool") == "role_pass" and str(e.get("id", "")).startswith("role-")
    ]


def test_role_pass_runs_castes_sequentially_with_handoff(sandbox) -> None:
    chat = ScriptedChat([
        {"role": "assistant", "content": "1. Create alpha.py with x = 1. 2. Verify."},
        _tool_call("create_file", {"filepath": "alpha.py", "content": "x = 1\n"}),
        {"role": "assistant", "content": "Created alpha.py as planned."},
        _tool_call("verify", {"command": "pytest -q"}),
        {"role": "assistant", "content": "Verdict: the work verifies green."},
    ])
    make_agent = _factory(
        chat, _executor(),
        approved_creations=[{"filepath": "alpha.py", "content": "x = 1\n"}],
        approved_commands=["pytest -q"],
    )
    events = list(run_role_pass(make_agent, [{"role": "user", "content": "make alpha"}]))

    assert _castes(events) == ["planner", "coder", "reviewer"]
    assert (sandbox / "alpha.py").read_text(encoding="utf-8") == "x = 1\n"
    assert [e["type"] for e in events].count("done") == 1
    assert events[-1]["type"] == "done"
    verifies = [
        e for e in events
        if e.get("tool") == "verify" and e["type"] == "tool_result"
        and "VERIFY PASS" in e.get("output", "")
    ]
    assert any(e.get("role") == "reviewer" for e in verifies)
    # Stigmergic handoff: the coder's leg opened with the planner's labelled
    # answer in the shared conversation.
    coder_first_messages = chat.calls[1]
    assert any(
        str(m.get("content", "")).startswith("[planner]")
        for m in coder_first_messages
    ), "the planner's final answer must cross the leg boundary"


def test_role_pass_reviewer_cannot_write(sandbox) -> None:
    f = sandbox / "alpha.py"
    chat = ScriptedChat([
        {"role": "assistant", "content": "Plan: create alpha.py, then verify."},
        _tool_call("create_file", {"filepath": "alpha.py", "content": "x = 1\n"}),
        {"role": "assistant", "content": "Done."},
        _tool_call("edit_file", {
            "filepath": "alpha.py", "old_string": "x = 1", "new_string": "x = 2",
        }),
        {"role": "assistant", "content": "Verdict: I tried to fix it myself."},
    ])
    make_agent = _factory(
        chat, _executor(),
        approved_creations=[{"filepath": "alpha.py", "content": "x = 1\n"}],
    )
    events = list(run_role_pass(make_agent, [{"role": "user", "content": "make alpha"}]))

    denied = [
        e for e in events
        if e["type"] == "tool_blocked" and e.get("role") == "reviewer"
    ]
    assert denied and "not permitted" in denied[0]["reason"]
    assert f.read_text(encoding="utf-8") == "x = 1\n"   # reviewer changed nothing


def test_role_pass_denies_prose_rescued_out_of_caste_call(sandbox) -> None:
    # The planner emits a bare-JSON create_file: the rescue parser recovers it,
    # and the dispatch-level caste enforcement still denies it.
    chat = ScriptedChat([
        {"role": "assistant",
         "content": '{"name": "create_file", "arguments": {"filepath": "evil.py", "content": "x"}}'},
        {"role": "assistant", "content": "Plan: nothing further."},
        {"role": "assistant", "content": "No work to do."},
    ])
    events = list(run_role_pass(
        _factory(chat, _executor()), [{"role": "user", "content": "assess the request"}]
    ))

    denied = [
        e for e in events
        if e["type"] == "tool_blocked" and e.get("role") == "planner"
    ]
    assert denied and "not permitted" in denied[0]["reason"]
    assert not (sandbox / "evil.py").exists()


def test_role_pass_pause_ends_whole_turn(sandbox) -> None:
    chat = ScriptedChat([
        {"role": "assistant", "content": "Plan: create alpha.py."},
        _tool_call("create_file", {"filepath": "alpha.py", "content": "x = 1\n"}),
    ])
    events = list(run_role_pass(
        _factory(chat, _executor()), [{"role": "user", "content": "make alpha"}]
    ))

    assert events[-1]["type"] == "human_required"
    assert events[-1]["role"] == "coder"
    assert not any(e["type"] == "done" for e in events)
    assert "reviewer" not in _castes(events)
    assert not (sandbox / "alpha.py").exists()           # nothing written unapproved


def test_role_pass_reviewer_fail_buys_exactly_one_retry(sandbox) -> None:
    chat = ScriptedChat([
        {"role": "assistant", "content": "Plan: create alpha.py, verify."},
        _tool_call("create_file", {"filepath": "alpha.py", "content": "x = 1\n"}),
        {"role": "assistant", "content": "Created."},
        _tool_call("verify", {"command": "pytest -q"}),
        {"role": "assistant", "content": "Verdict: the tests fail."},
        {"role": "assistant", "content": "I could not improve it further."},
        _tool_call("verify", {"command": "pytest -q"}),
        {"role": "assistant", "content": "Verdict: still failing."},
    ])
    make_agent = _factory(
        chat, _executor(FailRunner()),
        approved_creations=[{"filepath": "alpha.py", "content": "x = 1\n"}],
        approved_commands=["pytest -q"],
    )
    events = list(run_role_pass(make_agent, [{"role": "user", "content": "make alpha"}]))

    assert _castes(events) == ["planner", "coder", "reviewer", "coder", "reviewer"]
    assert [e["type"] for e in events].count("done") == 1
    fails = [
        e for e in events
        if e["type"] == "tool_result" and "VERIFY FAIL" in str(e.get("output", ""))
    ]
    assert len(fails) >= 2                               # both reviews produced evidence


def test_role_pass_skips_review_when_nothing_was_written(sandbox) -> None:
    chat = ScriptedChat([
        {"role": "assistant", "content": "Plan: the request needs no changes."},
        {"role": "assistant", "content": "Confirmed: nothing to change."},
    ])
    events = list(run_role_pass(
        _factory(chat, _executor()), [{"role": "user", "content": "is it fine?"}]
    ))

    assert _castes(events) == ["planner", "coder"]
    assert events[-1]["type"] == "done"


def test_role_pass_reviews_pre_applied_grants_even_if_coder_idles(sandbox) -> None:
    # Replay semantics: the approved write lands during the planner leg via the
    # grant pre-apply; the coder has nothing left to do — but approved work
    # produced THIS turn must still be reviewed.
    chat = ScriptedChat([
        {"role": "assistant", "content": "Plan: alpha.py is already approved."},
        {"role": "assistant", "content": "Everything already landed."},
        _tool_call("verify", {"command": "pytest -q"}),
        {"role": "assistant", "content": "Verdict: green."},
    ])
    make_agent = _factory(
        chat, _executor(),
        approved_creations=[{"filepath": "alpha.py", "content": "x = 1\n"}],
        approved_commands=["pytest -q"],
    )
    events = list(run_role_pass(make_agent, [{"role": "user", "content": "make alpha"}]))

    assert (sandbox / "alpha.py").read_text(encoding="utf-8") == "x = 1\n"
    assert _castes(events) == ["planner", "coder", "reviewer"]
    assert events[-1]["type"] == "done"
