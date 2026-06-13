"""Behavioral tests for the ephemeral worker swarm (aios.agents.swarm).

Same philosophy as test_role_pass: a scripted fake chat drives the legs while a
fake-runner Executor exercises the REAL gateway, so the caste tool-gating and
stigmergic handoff under test are genuine. We assert the swarm SHAPE
(decompose -> N workers -> synthesize), its bound, that a pause stops the whole
swarm, and that workers coordinate only through the shared conversation.
"""
from __future__ import annotations

import pytest

from aios import config
from aios.agents.swarm import run_swarm
from aios.agents.tool_agent import ToolAgent
from aios.core.executor import Executor
from aios.security import scope_lock
from aios.security.gateway import RateLimiter


class ScriptedChat:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def chat(self, messages, *, tools=None, model=None):
        self.calls.append(messages)
        return self._responses.pop(0)


class FakeRunner:
    def __call__(self, command, *, cwd, env, timeout_s):
        return f"ran: {command}", "", 0


def _executor():
    return Executor(runner=FakeRunner(), rate_limiter=RateLimiter(), audit_log=lambda *a, **k: None)


def _tool_call(name, arguments):
    return {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": name, "arguments": arguments}}
    ]}


def _factory(chat, executor, **fixed):
    def make_agent(**overrides):
        return ToolAgent(chat, executor, **{"max_iters": 5, **fixed, **overrides})
    return make_agent


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    original = scope_lock.get_scope_roots()
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    scope_lock.set_scope_roots([tmp_path])
    yield tmp_path
    scope_lock.set_scope_roots(original)


def _castes(events):
    return [
        str(e["role"]) for e in events
        if e.get("tool") == "swarm" and str(e.get("id", "")).startswith("swarm-")
    ]


def test_swarm_fans_out_one_worker_per_subtask_then_synthesizes(sandbox) -> None:
    chat = ScriptedChat([
        _tool_call("create_file", {"filepath": "a.py", "content": "x = 1\n"}),
        {"role": "assistant", "content": "Delivered a.py"},
        _tool_call("create_file", {"filepath": "b.py", "content": "y = 2\n"}),
        {"role": "assistant", "content": "Delivered b.py"},
        _tool_call("verify", {"command": "pytest -q"}),
        {"role": "assistant", "content": "Synthesis: both subtasks verify."},
    ])
    make_agent = _factory(
        chat, _executor(),
        approved_creations=[
            {"filepath": "a.py", "content": "x = 1\n"},
            {"filepath": "b.py", "content": "y = 2\n"},
        ],
        approved_commands=["pytest -q"],
    )
    events = list(run_swarm(
        make_agent,
        [{"role": "user", "content": "build a and b"}],
        subtasks=["Create a.py", "Create b.py"],  # explicit -> decomposer skipped
    ))

    assert _castes(events) == ["worker-1", "worker-2", "synthesizer"]
    assert (sandbox / "a.py").exists() and (sandbox / "b.py").exists()
    assert [e["type"] for e in events].count("done") == 1
    assert events[-1]["type"] == "done"


def test_swarm_decomposes_when_no_subtasks_given(sandbox) -> None:
    chat = ScriptedChat([
        {"role": "assistant", "content": "1. Create a.py with x=1\n2. Create b.py with y=2"},
        _tool_call("create_file", {"filepath": "a.py", "content": "x = 1\n"}),
        {"role": "assistant", "content": "Delivered a.py"},
        _tool_call("create_file", {"filepath": "b.py", "content": "y = 2\n"}),
        {"role": "assistant", "content": "Delivered b.py"},
        _tool_call("verify", {"command": "pytest -q"}),
        {"role": "assistant", "content": "Synthesis done."},
    ])
    make_agent = _factory(
        chat, _executor(),
        approved_creations=[
            {"filepath": "a.py", "content": "x = 1\n"},
            {"filepath": "b.py", "content": "y = 2\n"},
        ],
        approved_commands=["pytest -q"],
    )
    events = list(run_swarm(make_agent, [{"role": "user", "content": "build a and b"}]))

    castes = _castes(events)
    assert castes[0] == "decomposer"
    assert castes.count("worker-1") == 1 and castes.count("worker-2") == 1
    assert "synthesizer" in castes
    assert events[-1]["type"] == "done"


def test_swarm_is_bounded_by_max_workers(sandbox) -> None:
    six = "\n".join(f"{i}. Subtask {i}" for i in range(1, 7))
    chat = ScriptedChat([
        {"role": "assistant", "content": six},
        # only two workers should ever be spawned -> two final answers consumed
        {"role": "assistant", "content": "worker 1 report"},
        {"role": "assistant", "content": "worker 2 report"},
    ])
    make_agent = _factory(chat, _executor())
    events = list(run_swarm(
        make_agent, [{"role": "user", "content": "do many things"}], max_workers=2,
    ))
    workers = [c for c in _castes(events) if c.startswith("worker-")]
    assert workers == ["worker-1", "worker-2"]  # capped, not six


def test_swarm_pause_in_a_worker_stops_the_whole_swarm(sandbox) -> None:
    chat = ScriptedChat([
        # worker-1 attempts an UNAPPROVED create -> YELLOW pause
        _tool_call("create_file", {"filepath": "a.py", "content": "x = 1\n"}),
    ])
    make_agent = _factory(chat, _executor())  # nothing approved
    events = list(run_swarm(
        make_agent, [{"role": "user", "content": "build a"}], subtasks=["Create a.py"],
    ))
    types = [e["type"] for e in events]
    assert "human_required" in types
    assert "synthesizer" not in _castes(events)
    assert "done" not in types  # the swarm did not complete; a replay resumes it


def test_swarm_handoff_is_stigmergic_through_the_conversation(sandbox) -> None:
    chat = ScriptedChat([
        {"role": "assistant", "content": "worker 1 report"},
        {"role": "assistant", "content": "worker 2 report"},
        {"role": "assistant", "content": "synthesis"},
    ])
    make_agent = _factory(chat, _executor())
    # workers do no writes here; we only assert the handoff medium.
    list(run_swarm(
        make_agent, [{"role": "user", "content": "two things"}],
        subtasks=["task one", "task two"],
    ))
    # worker-2's leg (3rd chat call: decomposer skipped, worker-1 = call 0,
    # worker-2 = call 1) opened with worker-1's labelled answer in the shared
    # conversation — the only channel between them.
    worker2_messages = chat.calls[1]
    assert any(
        str(m.get("content", "")).startswith("[worker-1]") for m in worker2_messages
    ), "a worker must see the prior worker's deposit, not direct messages"
