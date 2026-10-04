"""Plan Phase 5, slice 5c: a per-turn cap on what recalled learning can chain.

Threat T12 (EvoBreak): individually benign learned experiences compose into an
unattended harm. Taint (Phase 4a) pauses a command that carries recalled TEXT;
it cannot see a model composing several benign commands, in its own words,
from lessons or skills it recalled.

Operator decision, 2026-10-04: in a turn whose context carries learned recall
-- a lesson, a skill, or a reflex -- at most ``UNATTENDED_COMMAND_CAP`` (3)
commands run with no human; the next one pauses as a resumable checkpoint.
Reads are not counted. Only a command that would otherwise run unattended is
held: a YELLOW one pauses anyway, a refused one is refused as usual.
"""

from __future__ import annotations

import copy
import subprocess
from pathlib import Path
from typing import Any

import pytest

from aios.agents import recall_envelope
from aios.agents.tool_agent import ToolAgent
from aios.core.autonomy import UNGOVERNED_FIXTURE
from aios.core.executor import Executor
from aios.memory.db import init_memory_db
from aios.security.gateway import RateLimiter
from tests.reflex_fixtures import ActivatedSkills, gated

CAP = recall_envelope.UNATTENDED_COMMAND_CAP
COMMANDS = [f"echo lrt-cap-{i}" for i in range(1, 6)]
LESSONS = (
    "RELEVANT LESSONS (verified cross-task or pending from this task):\n"
    "- [verified; release_build] Check the workspace step by step before a release."
)
SKILLS = (
    "VERIFIED REUSABLE WORKFLOWS:\n"
    "- For check the workspace: read_file -> verify (verified success rate 90%)"
)
FACTS = "RELEVANT APPROVED FACTS (use these; do not invent beyond this graph):\n- x"


class Runner:
    def __init__(self, raise_timeout: int = 0) -> None:
        self.calls: list[str] = []
        self._timeouts = raise_timeout

    def __call__(self, command, *, cwd, env, timeout_s):
        self.calls.append(command)
        if self._timeouts:
            self._timeouts -= 1
            raise subprocess.TimeoutExpired(command, timeout_s)
        return "ok", "", 0


class Chat:
    """One reply proposing *calls*, then a plain answer."""

    def __init__(self, calls: list[tuple[str, dict[str, Any]]]) -> None:
        self.calls: list[Any] = []
        self._replies = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": name, "arguments": args}}
                    for name, args in calls
                ],
            }
        ]

    def chat(self, messages, *, tools=None, model=None) -> dict:
        self.calls.append(copy.deepcopy(messages))
        if self._replies:
            return self._replies.pop(0)
        return {"role": "assistant", "content": "done"}


def _commands(commands: list[str]) -> list[tuple[str, dict[str, Any]]]:
    return [("execute_terminal", {"command": c}) for c in commands]


def _turn(
    calls: list[tuple[str, dict[str, Any]]],
    *,
    memory_context: str | None = None,
    cerebellum: Any = None,
    text: str = "prepare the release",
    approved: list[str] | None = None,
    runner: Runner | None = None,
) -> tuple[Runner, list[dict[str, Any]]]:
    runner = runner or Runner()
    executor = Executor(
        runner=runner,
        rate_limiter=RateLimiter(),
        audit_log=lambda *a, **k: None,
        emergency_stop=UNGOVERNED_FIXTURE,
    )
    agent = ToolAgent(
        Chat(calls),
        executor,
        max_iters=3,
        memory_context=memory_context,
        cerebellum=cerebellum,
        approved_commands=approved,
        audit_log=lambda *a, **k: None,
        principal="principal:test",
    )
    events = [
        e for e in agent.run([{"role": "user", "content": text}]) if isinstance(e, dict)
    ]
    return runner, events


def _cap_pauses(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        e for e in events if e.get("control") == recall_envelope.COMPOSITION_CAP_CONTROL
    ]


# ------------------------------------------------------------ learned recall


@pytest.mark.parametrize(
    ("context", "learned"),
    [
        (LESSONS, True),
        (SKILLS, True),
        (f"{FACTS}\n\n{LESSONS}", True),
        (FACTS, False),
        ("UNVERIFIED PRIOR CHAT MEMORY (may be stale):\n- hi", False),
        ("Self-model from my verified work: I am careful.", False),
        ("", False),
        (None, False),
    ],
)
def test_learned_recall_is_a_lesson_or_a_skill(context, learned) -> None:
    assert recall_envelope.carries_learned_recall(context) is learned


# ------------------------------------------------------------ the cap


def test_recalled_lessons_steer_at_most_the_cap_unattended() -> None:
    runner, events = _turn(_commands(COMMANDS), memory_context=LESSONS)
    assert runner.calls == COMMANDS[:CAP]
    (pause,) = _cap_pauses(events)
    assert COMMANDS[CAP] in str(pause)


def test_recalled_skills_count_too() -> None:
    runner, events = _turn(_commands(COMMANDS), memory_context=SKILLS)
    assert runner.calls == COMMANDS[:CAP]
    assert _cap_pauses(events)


def test_without_learned_recall_nothing_is_capped() -> None:
    """The positive control: the same turn with only facts recalled."""
    runner, events = _turn(_commands(COMMANDS), memory_context=FACTS)
    assert runner.calls == COMMANDS
    assert not _cap_pauses(events)


def test_a_reflex_in_the_turn_is_learned_recall(tmp_path: Path) -> None:
    """A matched reflex whose YELLOW step reflex authority withheld: the turn
    falls through to the model, and the reflex was in it."""
    db = tmp_path / "memory.db"
    init_memory_db(db)
    gate = ActivatedSkills()
    gate.activate("prepare the release", ["verify: command=pytest x.py -q"])
    cerebellum = gated(gate, db)
    assert cerebellum.try_compile_all() == 1
    runner, events = _turn(_commands(COMMANDS), cerebellum=cerebellum)
    assert any(e.get("control") == "reflex_authority" for e in events)
    assert runner.calls == COMMANDS[:CAP]
    assert _cap_pauses(events)


def test_a_reflex_that_did_not_match_is_not_learned_recall(tmp_path: Path) -> None:
    db = tmp_path / "memory.db"
    init_memory_db(db)
    gate = ActivatedSkills()
    gate.activate("prepare the release", ["verify: command=pytest x.py -q"])
    cerebellum = gated(gate, db)
    cerebellum.try_compile_all()
    runner, _ = _turn(_commands(COMMANDS), cerebellum=cerebellum, text="say hello")
    assert runner.calls == COMMANDS


def test_reads_are_not_counted() -> None:
    reads = [("read_file", {"filepath": "README.md"})] * 4
    runner, events = _turn(reads + _commands(COMMANDS[:CAP]), memory_context=LESSONS)
    assert runner.calls == COMMANDS[:CAP]
    assert not _cap_pauses(events)


def test_a_command_a_human_approved_runs_and_is_not_counted() -> None:
    approved = [COMMANDS[CAP]]
    runner, events = _turn(
        _commands(COMMANDS), memory_context=LESSONS, approved=approved
    )
    assert runner.calls == COMMANDS[: CAP + 1]
    (pause,) = _cap_pauses(events)
    assert COMMANDS[CAP + 1] in str(pause)


def test_a_refused_or_timed_out_command_still_counts() -> None:
    """``blocked`` covers a timeout, which ran; counting it reaches the
    checkpoint sooner, never later."""
    runner, events = _turn(
        _commands(COMMANDS), memory_context=LESSONS, runner=Runner(raise_timeout=CAP)
    )
    assert runner.calls == COMMANDS[:CAP]
    assert _cap_pauses(events)


def test_a_yellow_command_pauses_as_it_always_did() -> None:
    """It needs a human anyway, so the cap does not claim the pause."""
    runner, events = _turn(
        _commands([*COMMANDS[:CAP], "pip install requests"]), memory_context=LESSONS
    )
    assert runner.calls == COMMANDS[:CAP]
    assert not _cap_pauses(events)
    assert any(e.get("type") == "human_required" for e in events)


def test_a_red_command_is_refused_never_offered() -> None:
    runner, events = _turn(
        _commands([*COMMANDS[:CAP], "rm -rf /"]), memory_context=LESSONS
    )
    assert "rm -rf /" not in runner.calls
    assert not _cap_pauses(events)
    assert not any(
        e.get("type") == "human_required" and "rm -rf" in str(e) for e in events
    )


def test_the_cap_is_three_and_not_configurable() -> None:
    """Operator decision, 2026-10-04. Raising it is a reviewed code change."""
    assert CAP == 3
    import aios.config as config

    assert not any("CAP" in name and "COMMAND" in name for name in dir(config))


def test_an_approved_command_does_not_use_up_the_cap() -> None:
    """The human's approval is the checkpoint: what they approved is not
    counted against the commands that may still run without them."""
    approved = [COMMANDS[0]]
    runner, events = _turn(
        _commands(COMMANDS), memory_context=LESSONS, approved=approved
    )
    assert runner.calls == COMMANDS[: CAP + 1]
    (pause,) = _cap_pauses(events)
    assert COMMANDS[CAP + 1] in str(pause)
