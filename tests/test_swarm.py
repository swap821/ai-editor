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
    # Default concurrency is 1, so worker-2 starts after worker-1 deposits.
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


def test_swarm_concurrent_workers_fan_out_and_synthesize(sandbox) -> None:
    chat = ScriptedChat([
        _tool_call("create_file", {"filepath": "a.py", "content": "x = 1\n"}),
        _tool_call("create_file", {"filepath": "b.py", "content": "y = 2\n"}),
        {"role": "assistant", "content": "Delivered a.py"},
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
        subtasks=["Create a.py", "Create b.py"],
        worker_concurrency=2,
    ))

    assert _castes(events) == ["worker-1", "worker-2", "synthesizer"]
    assert (sandbox / "a.py").exists() and (sandbox / "b.py").exists()
    assert [e["type"] for e in events].count("done") == 1
    assert events[-1]["type"] == "done"


def test_swarm_concurrent_workers_do_not_cross_read(sandbox) -> None:
    chat = ScriptedChat([
        {"role": "assistant", "content": "worker 1 report"},
        {"role": "assistant", "content": "worker 2 report"},
        {"role": "assistant", "content": "synthesis"},
    ])
    make_agent = _factory(chat, _executor())
    list(run_swarm(
        make_agent,
        [{"role": "user", "content": "two things"}],
        subtasks=["task one", "task two"],
        worker_concurrency=2,
    ))
    # With concurrency >1, worker-2's leg_messages were snapshotted before any
    # worker deposited its answer, so it must NOT contain worker-1's handoff.
    worker2_messages = chat.calls[1]
    assert not any(
        str(m.get("content", "")).startswith("[worker-1]") for m in worker2_messages
    ), "concurrent workers must not read each other's deposits"


class FakePatternMemory:
    """In-memory stand-in for SwarmPatternMemory."""

    def __init__(self, patterns):
        self.patterns = list(patterns)
        self.bumped: list[int] = []

    def recall(self, goal, *, limit=1):
        return self.patterns[:limit]

    def bump_use(self, pattern_id):
        self.bumped.append(pattern_id)


def test_swarm_scout_recalls_pattern_and_skips_decomposer(sandbox) -> None:
    chat = ScriptedChat([
        {"role": "assistant", "content": "USE_PATTERN\n1. Create a.py\n2. Create b.py"},
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
    memory = FakePatternMemory([
        {"pattern_id": 7, "goal_pattern": "build a and b", "subtasks": ["Create a.py", "Create b.py"],
         "success_count": 3, "success_rate": 1.0},
    ])
    events = list(run_swarm(
        make_agent,
        [{"role": "user", "content": "build a and b"}],
        pattern_memory=memory,
    ))

    assert _castes(events) == ["scout", "worker-1", "worker-2", "synthesizer"]
    assert "decomposer" not in _castes(events)
    assert memory.bumped == [7]
    assert (sandbox / "a.py").exists() and (sandbox / "b.py").exists()


def test_swarm_scout_falls_back_to_decomposer_when_no_pattern_matches(sandbox) -> None:
    chat = ScriptedChat([
        {"role": "assistant", "content": "DECOMPOSE"},
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
    memory = FakePatternMemory([
        {"pattern_id": 9, "goal_pattern": "build a and b", "subtasks": ["Create a.py", "Create b.py"],
         "success_count": 2, "success_rate": 1.0},
    ])
    events = list(run_swarm(
        make_agent,
        [{"role": "user", "content": "build a and b"}],
        pattern_memory=memory,
    ))

    castes = _castes(events)
    assert castes[0] == "scout"
    assert "decomposer" in castes
    assert castes.count("worker-1") == 1 and castes.count("worker-2") == 1
    assert memory.bumped == []


def test_swarm_quorum_runs_for_redundant_replicas(sandbox, monkeypatch) -> None:
    monkeypatch.setattr(config, "SWARM_REDUNDANCY", 2)
    chat = ScriptedChat([
        # replica 1a
        _tool_call("create_file", {"filepath": "a.py", "content": "x = 1\n"}),
        {"role": "assistant", "content": "Delivered a.py (replica A)"},
        # replica 1b
        _tool_call("create_file", {"filepath": "a.py", "content": "x = 1\n"}),
        {"role": "assistant", "content": "Delivered a.py (replica B)"},
        # quorum picks one
        {"role": "assistant", "content": "Canonical report: a.py created."},
        _tool_call("verify", {"command": "pytest -q"}),
        {"role": "assistant", "content": "Synthesis: quorum verified."},
    ])
    make_agent = _factory(
        chat, _executor(),
        approved_creations=[{"filepath": "a.py", "content": "x = 1\n"}],
        approved_commands=["pytest -q"],
    )
    events = list(run_swarm(
        make_agent,
        [{"role": "user", "content": "build a"}],
        subtasks=["Create a.py"],
        redundancy=2,
    ))

    castes = _castes(events)
    assert "worker-1-1" in castes and "worker-1-2" in castes
    assert "quorum-1" in castes
    assert "synthesizer" in castes
    # Quorum's canonical report is deposited as the worker-1 handoff.
    assert any(
        str(m.get("content", "")).startswith("[worker-1]\nCanonical report")
        for m in chat.calls[-1]
    )
    assert events[-1]["type"] == "done"


def test_swarm_cloud_burst_routes_eligible_subtask_to_cloud_factory(sandbox) -> None:
    local_chat = ScriptedChat([
        # cloud broker labels subtask 1 as cloud, subtask 2 as local
        {"role": "assistant", "content": "1. CLOUD\n2. LOCAL"},
        # local worker for subtask 2
        _tool_call("create_file", {"filepath": "b.py", "content": "y = 2\n"}),
        {"role": "assistant", "content": "Delivered b.py locally"},
        # synthesizer
        _tool_call("verify", {"command": "pytest -q"}),
        {"role": "assistant", "content": "Synthesis done."},
    ])
    cloud_chat = ScriptedChat([
        # cloud worker for subtask 1
        _tool_call("create_file", {"filepath": "a.py", "content": "x = 1\n"}),
        {"role": "assistant", "content": "Delivered a.py from cloud"},
    ])
    executor = _executor()
    make_agent = _factory(
        local_chat, executor,
        approved_creations=[
            {"filepath": "a.py", "content": "x = 1\n"},
            {"filepath": "b.py", "content": "y = 2\n"},
        ],
        approved_commands=["pytest -q"],
    )
    make_cloud_agent = _factory(
        cloud_chat, executor,
        approved_creations=[{"filepath": "a.py", "content": "x = 1\n"}],
    )
    events = list(run_swarm(
        make_agent,
        [{"role": "user", "content": "build a and b"}],
        subtasks=["Create a.py", "Create b.py"],
        cloud_burst=True,
        make_cloud_agent=make_cloud_agent,
    ))

    castes = _castes(events)
    assert "cloud_broker" in castes
    assert "worker-1" in castes and "worker-2" in castes
    assert events[-1]["type"] == "done"
    assert (sandbox / "a.py").exists() and (sandbox / "b.py").exists()
    # The cloud chat was consumed, proving the cloud factory served worker-1.
    assert len(cloud_chat.calls) >= 1


def test_swarm_cloud_burst_emits_cloud_route_with_provider_metadata(sandbox) -> None:
    local_chat = ScriptedChat([
        {"role": "assistant", "content": "1. CLOUD\n2. LOCAL"},
        _tool_call("create_file", {"filepath": "b.py", "content": "y = 2\n"}),
        {"role": "assistant", "content": "Delivered b.py locally"},
        _tool_call("verify", {"command": "pytest -q"}),
        {"role": "assistant", "content": "Synthesis done."},
    ])
    cloud_chat = ScriptedChat([
        _tool_call("create_file", {"filepath": "a.py", "content": "x = 1\n"}),
        {"role": "assistant", "content": "Delivered a.py from cloud"},
    ])
    executor = _executor()
    make_agent = _factory(
        local_chat, executor,
        approved_creations=[
            {"filepath": "a.py", "content": "x = 1\n"},
            {"filepath": "b.py", "content": "y = 2\n"},
        ],
        approved_commands=["pytest -q"],
    )
    make_cloud_agent = _factory(
        cloud_chat, executor,
        approved_creations=[{"filepath": "a.py", "content": "x = 1\n"}],
    )
    events = list(run_swarm(
        make_agent,
        [{"role": "user", "content": "build a and b"}],
        subtasks=["Create a.py", "Create b.py"],
        cloud_burst=True,
        make_cloud_agent=make_cloud_agent,
        cloud_provider="bedrock",
    ))

    cloud_routes = [e for e in events if e.get("type") == "cloud_route"]
    assert len(cloud_routes) == 1
    assert cloud_routes[0]["role"] == "swarm"
    assert cloud_routes[0]["subtask_index"] == 0
    assert cloud_routes[0]["provider"] == "bedrock"
    # A local-only run must not produce cloud_route frames.
    local_chat2 = ScriptedChat([
        _tool_call("create_file", {"filepath": "a.py", "content": "x = 1\n"}),
        {"role": "assistant", "content": "Delivered a.py"},
        _tool_call("create_file", {"filepath": "b.py", "content": "y = 2\n"}),
        {"role": "assistant", "content": "Delivered b.py"},
        _tool_call("verify", {"command": "pytest -q"}),
        {"role": "assistant", "content": "Synthesis done."},
    ])
    make_local_agent = _factory(
        local_chat2, executor,
        approved_creations=[
            {"filepath": "a.py", "content": "x = 1\n"},
            {"filepath": "b.py", "content": "y = 2\n"},
        ],
        approved_commands=["pytest -q"],
    )
    local_only = list(run_swarm(
        make_local_agent,
        [{"role": "user", "content": "build a and b"}],
        subtasks=["Create a.py", "Create b.py"],
    ))
    assert not any(e.get("type") == "cloud_route" for e in local_only)
    assert any("Create a.py" in str(m.get("content", "")) for m in cloud_chat.calls[0])
