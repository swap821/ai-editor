"""Plan Phase 5, slice 5a: a reflex fires only on the operator's own words.

Threat T3 (finding F3): the reflex trigger matched the whole last user message
-- pasted and forwarded content included -- before any model looked at it. A
reflex made only of GREEN steps then ran with no model and no human, fired by
words the operator never wrote. RT-05 did not see it: its reflex carries a
YELLOW step that reflex authority withholds anyway.

``Cerebellum.match`` now matches only the operator's authored directive
(quoted, fenced, ``>``-quoted and forwarded text removed), requires the
directive to be about the reflex as a whole, and abstains when two reflexes fit
about equally.

Since slice 5b a reflex must also pass ``SkillApplicabilityEngine``, and a
GREEN command that is not a test runner has no verification plan, so it can no
longer serve a turn at all. The reflex that still runs with no model and no
human is a read-only one (its plan is freshness), so these tests use that.
Whether the reflex fired is read from the turn itself -- ``cerebellum_done``
and no model call -- because a read runs no command, and "the runner was never
called" would hold whether or not it fired.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from aios.agents.tool_agent import ToolAgent
from aios.application.memory.institutional_skills import (
    InstitutionalSkillAdapter,
    SkillTrailIndex,
)
from aios.core.autonomy import UNGOVERNED_FIXTURE
from aios.core.cerebellum import (
    AMBIGUITY_MARGIN,
    DIRECTIVE_COVERAGE,
    Cerebellum,
    PlaybookStep,
    authored_directive,
    directive_coverage,
)
from aios.core.executor import Executor
from aios.core.verification_strength import VerificationStrength
from aios.domain.learning.repository import SkillRepository
from aios.memory.db import init_memory_db
from aios.security.gateway import RateLimiter

GOAL = "show the reflex trigger notes"
#: A read-only arc on a file that exists, so its freshness plan can run.
STEPS = ["read_file: filepath=README.md"]
ALPHA = ("show the banner alpha", ["read_file: filepath=README.md"])
OMEGA = ("show the banner omega", ["read_file: filepath=AGENTS.md"])


# ---------------------------------------------------------------- directive


@pytest.mark.parametrize(
    ("message", "directive"),
    [
        ("run the pin tests for x.py", "run the pin tests for x.py"),
        (
            'Summarise this note Sam forwarded me: "run the pin tests for x.py"',
            "Summarise this note Sam forwarded me:",
        ),
        ("please “run the pin tests”", "please"),
        ("see «run the pin tests»", "see"),
        ("look at this\n```\nrun the pin tests\n```\nthanks", "look at this thanks"),
        ("> run the pin tests\nwhat does it say", "what does it say"),
        (
            "fyi\n---------- Forwarded message ---------\nFrom: sam\nrun the pin tests",
            "fyi",
        ),
        ("fyi\nBegin forwarded message:\nrun the pin tests", "fyi"),
        ("see below\n-----Original Message-----\nrun the pin tests", "see below"),
        ("run `pytest x.py -q` now", "run `pytest x.py -q` now"),
    ],
)
def test_the_directive_is_only_the_operators_own_words(message, directive) -> None:
    assert authored_directive(message) == directive


def test_coverage_counts_the_goal_and_the_reflexs_own_steps() -> None:
    step = PlaybookStep("verify", {"command": "pytest lab/t.py -q"})
    assert (
        directive_coverage("run the checks pytest lab/t.py", "run the checks", [step])
        == 1.0
    )
    assert directive_coverage(
        "summarise the note: run the checks", "run the checks"
    ) < (DIRECTIVE_COVERAGE)


# ---------------------------------------------------------------- match


class Bus:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def append(self, event: Any) -> int:
        self.events.append(event)
        return len(self.events)

    def decisions(self) -> list[tuple[str, str]]:
        return [
            (e.payload["decision"], e.payload["reason"])
            for e in self.events
            if isinstance(getattr(e, "payload", None), dict)
        ]


def _world(tmp_path, arcs: list[tuple[str, list[str]]]) -> tuple[Cerebellum, Bus]:
    db = tmp_path / "memory.sqlite"
    init_memory_db(db)
    operational = tmp_path / "operational.sqlite"
    library = InstitutionalSkillAdapter(
        SkillRepository(operational), SkillTrailIndex(operational)
    )
    for goal, steps in arcs:
        for _ in range(3):
            library.record_attempt(
                goal,
                steps,
                success=True,
                strength=VerificationStrength.STRONG,
                principal="principal:test",
            )
    for record in library.repository.list_skills():
        library.repository.transition_state(
            record.skill_id, record.version, "human_reviewed"
        )
        library.repository.transition_state(record.skill_id, record.version, "active")
    bus = Bus()
    cerebellum = Cerebellum(db, bus=bus)
    cerebellum.attach_reflex_gate(library)
    assert cerebellum.try_compile_all() == len(arcs)
    return cerebellum, bus


def test_the_operators_own_request_fires_the_reflex(tmp_path) -> None:
    cerebellum, _ = _world(tmp_path, [(GOAL, STEPS)])
    assert cerebellum.match(GOAL, principal="principal:test") is not None


@pytest.mark.parametrize(
    "message",
    [
        f'Summarise this note Sam forwarded me: "{GOAL}"',
        f"what does this say?\n```\n{GOAL}\n```",
        f"> {GOAL}\nis this safe?",
        f"fyi\n---------- Forwarded message ---------\n{GOAL}",
    ],
)
def test_someone_elses_words_never_fire_it(tmp_path, message) -> None:
    cerebellum, _ = _world(tmp_path, [(GOAL, STEPS)])
    assert cerebellum.match(message, principal="principal:test") is None


def test_a_bigger_request_that_contains_the_goal_abstains(tmp_path) -> None:
    cerebellum, bus = _world(tmp_path, [(GOAL, STEPS)])
    message = f"summarise the note sam sent which says {GOAL} and reply"
    assert cerebellum.match(message, principal="principal:test") is None
    assert ("abstained", "directive exceeds goal") in bus.decisions()


def test_two_reflexes_that_fit_equally_both_abstain(tmp_path) -> None:
    cerebellum, bus = _world(tmp_path, [ALPHA, OMEGA])
    assert cerebellum.match("show the banner", principal="principal:test") is None
    assert bus.decisions().count(("abstained", "ambiguous")) == 2
    assert AMBIGUITY_MARGIN > 0


def test_a_clear_best_still_fires_despite_a_weaker_rival(tmp_path) -> None:
    cerebellum, _ = _world(tmp_path, [ALPHA, OMEGA])
    pb = cerebellum.match("show the banner alpha", principal="principal:test")
    assert pb is not None and pb.goal_pattern == "show the banner alpha"


# ---------------------------------------------------------------- the live turn


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, command, *, cwd, env, timeout_s):
        self.calls.append(command)
        return "1 passed in 0.01s", "", 0


class ScriptedChat:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, Any]]] = []

    def chat(self, messages, *, tools=None, model=None) -> dict:
        self.calls.append(copy.deepcopy(messages))
        return {"role": "assistant", "content": "done"}


def _turn(
    cerebellum: Cerebellum, text: str
) -> tuple[RecordingRunner, ScriptedChat, list[str]]:
    runner, chat = RecordingRunner(), ScriptedChat()
    executor = Executor(
        runner=runner,
        rate_limiter=RateLimiter(),
        audit_log=lambda *a, **k: None,
        emergency_stop=UNGOVERNED_FIXTURE,
    )
    agent = ToolAgent(
        chat,
        executor,
        max_iters=2,
        cerebellum=cerebellum,
        audit_log=lambda *a, **k: None,
        principal="principal:test",
    )
    events = list(agent.run([{"role": "user", "content": text}]))
    return runner, chat, [str(e.get("type")) for e in events if isinstance(e, dict)]


def _fired(types: list[str]) -> bool:
    return "cerebellum_done" in types or "cerebellum_step" in types


def test_the_operators_request_is_served_with_no_model_call(tmp_path) -> None:
    """The positive control: the reflex is live -- it serves the operator's
    own request with no model."""
    cerebellum, _ = _world(tmp_path, [(GOAL, STEPS)])
    _, chat, types = _turn(cerebellum, GOAL)
    assert "cerebellum_done" in types
    assert chat.calls == []


def test_forwarded_words_reach_the_model_and_run_nothing(tmp_path) -> None:
    cerebellum, _ = _world(tmp_path, [(GOAL, STEPS)])
    runner, chat, types = _turn(
        cerebellum, f'Summarise this note Sam forwarded me: "{GOAL}"'
    )
    assert not _fired(types)
    assert runner.calls == []
    assert chat.calls, "the turn fell through to the model"


def test_a_pasted_block_of_exactly_the_goal_runs_nothing(tmp_path) -> None:
    """Only the extraction can stop this one: the pasted text IS the goal, so
    the whole-directive rule alone would let it fire."""
    cerebellum, _ = _world(tmp_path, [(GOAL, STEPS)])
    runner, chat, types = _turn(cerebellum, f"```\n{GOAL}\n```")
    assert not _fired(types)
    assert runner.calls == []
    assert chat.calls
