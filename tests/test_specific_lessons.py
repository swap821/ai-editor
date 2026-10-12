"""Lessons state a specific fact, or nothing is stored; practice never touches
the judged targets (D10).

Measured on the live store 2026-10-12: 1 of 23 lesson texts named a code
identifier, while 17 of 23 root causes did. The reflection prompt asked for "a
generalised rule", and the model threw the specific knowledge away.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aios.agents import reflection_agent as ra
from aios.memory.db import init_memory_db
from aios.memory.mistake import MistakeMemory


class _LLM:
    def __init__(self, lesson_text: str) -> None:
        self.lesson_text = lesson_text
        self.systems: list[str] = []

    def complete(
        self, prompt: str, *, system: str | None = None, json_mode=False
    ) -> str:
        self.systems.append(system or "")
        return json.dumps(
            {
                "error_type": "ModuleNotFoundError",
                "root_cause": "the test imported `config`, which is aios.config",
                "fix_applied": "imported it as from aios import config",
                "lesson_text": self.lesson_text,
                "confidence_delta": -0.2,
            }
        )


def _agent(
    tmp_path: Path, lesson_text: str
) -> tuple[ra.ReflectionAgent, MistakeMemory]:
    db = tmp_path / "memory.db"
    init_memory_db(db)
    mistakes = MistakeMemory(db)
    return ra.ReflectionAgent(
        _LLM(lesson_text), mistakes=mistakes, db_path=db
    ), mistakes


def test_the_prompt_asks_for_a_specific_fact_not_a_generalised_rule() -> None:
    prompt = ra.REFLECT_SYSTEM_PROMPT
    assert "generalised rule" not in prompt and "generalised lesson" not in prompt
    assert "specific fact" in prompt
    assert "No specific lesson" in prompt
    assert "never contains a command to run" in prompt, "a fact, not an instruction"
    assert "aios" not in prompt, "examples come from another codebase: no fact leaks"


def test_a_specific_lesson_is_stored(tmp_path) -> None:
    agent, mistakes = _agent(
        tmp_path, "aios.config is a module: import it as `from aios import config`."
    )
    reflection = agent.reflect(
        "pytest -q", "ModuleNotFoundError: No module named 'config'"
    )
    assert reflection is not None and mistakes.count() == 1


@pytest.mark.parametrize(
    "text",
    ["No specific lesson: a transient network error", "no specific lesson: flaky"],
)
def test_a_failure_that_teaches_nothing_specific_stores_nothing(tmp_path, text) -> None:
    agent, mistakes = _agent(tmp_path, text)
    assert agent.reflect("pytest -q", "E   ConnectionResetError") is None
    assert mistakes.count() == 0


def test_the_failure_hook_takes_no_lesson_quietly(caplog) -> None:
    from aios.api.turn_pipeline import _make_failure_hook

    class Nothing:
        def reflect(self, command, error_output, *, task_id=None):
            return None

    hook = _make_failure_hook(Nothing(), "s")
    with caplog.at_level("WARNING"):
        assert hook("pytest -q", "E  boom") is None
    assert not [r for r in caplog.records if r.levelname == "WARNING"]


def test_practice_never_takes_a_frozen_judged_target(tmp_path) -> None:
    from tools.self_corpus_targets import (
        frozen_target_labels,
        practice_targets,
    )

    repo = Path(__file__).resolve().parents[1]
    frozen = frozen_target_labels(repo)
    assert len(frozen) > 100
    first = practice_targets(repo, limit=40)
    assert first and not any(t.label in frozen for t in first)
    later = practice_targets(repo, limit=5, offset=5)
    assert [t.label for t in later] == [t.label for t in first[5:10]]


def test_a_missing_frozen_list_refuses_rather_than_excluding_nothing(tmp_path) -> None:
    from tools.self_corpus_targets import frozen_target_labels

    with pytest.raises(OSError):
        frozen_target_labels(tmp_path)


def test_a_cloud_chat_client_can_write_a_lesson_in_practice(tmp_path) -> None:
    """organic_chain_run reflected through ladder[0] directly; a chat-only
    client has no complete(), so every cloud-ladder reflection raised."""
    from tools.organic_chain_run import reflection_client

    class ChatOnly:
        def chat(self, messages, *, tools=None, model=None):
            return {
                "role": "assistant",
                "content": _LLM("`app.settings` is a module.").complete("x"),
            }

    db = tmp_path / "memory.db"
    init_memory_db(db)
    mistakes = MistakeMemory(db)
    agent = ra.ReflectionAgent(
        reflection_client(ChatOnly()), mistakes=mistakes, db_path=db
    )
    assert agent.reflect("pytest -q", "E  ModuleNotFoundError") is not None
    assert mistakes.count() == 1
    local = _LLM("x")
    assert reflection_client(local) is local, "a completion client is used as is"


# --------------------------------------------------------------------------- #
# D11: lessons are written from the fix that worked, never promoted guesses
# --------------------------------------------------------------------------- #


def test_a_resolution_lesson_is_stored_verified_and_grounded_in_the_change(
    tmp_path,
) -> None:
    agent, mistakes = _agent(
        tmp_path, "`collect_meta_loop_evidence` takes `reflections=`, not `context=`."
    )
    agent.llm.prompts = []
    original = agent.llm.complete

    def capture(prompt, *, system=None, json_mode=False):
        agent.llm.prompts.append((prompt, system))
        return original(prompt, system=system, json_mode=json_mode)

    agent.llm.complete = capture
    guess = agent.reflect("pytest t.py", "TypeError: unexpected keyword 'context'")
    grounded = agent.reflect_resolution(
        "pytest t.py",
        "TypeError: unexpected keyword 'context'",
        "-    collect_meta_loop_evidence(context={})\n+    collect_meta_loop_evidence(reflections=[])\n",
        task_id="t",
    )
    assert grounded is not None and grounded.mistake_id != guess.mistake_id
    assert grounded.task_id == "t#resolved", "never a recurrence of the guess"
    assert mistakes.get(grounded.mistake_id)["verification_status"] == "verified"
    prompt, system = agent.llm.prompts[-1]
    assert "reflections=[]" in prompt and system == ra.RESOLVE_SYSTEM_PROMPT


def test_a_fix_that_proves_nothing_stores_nothing(tmp_path) -> None:
    agent, mistakes = _agent(tmp_path, "No specific lesson: fixed a typo in the test")
    assert (
        agent.reflect_resolution("pytest t.py", "SyntaxError", "-x\n+y\n", task_id="t")
        is None
    )
    assert mistakes.count() == 0


class _Grounded:
    def __init__(self, mistake_id):
        self.mistake_id = mistake_id


class _Resolver:
    def __init__(self, result):
        self.result = result
        self.changes = []

    def reflect_resolution(self, command, error_output, change, *, task_id):
        self.changes.append(change)
        return self.result


def _two_guesses(tmp_path):
    db = tmp_path / "m.db"
    init_memory_db(db)
    mistakes = MistakeMemory(db)
    guesses = [
        mistakes.record("t", "TypeError", "r", "f", f"guess {i}", -0.1) for i in (1, 2)
    ]
    return mistakes, guesses


def test_grounding_supersedes_the_guesses_and_never_promotes_them(tmp_path) -> None:
    from tools.organic_chain_run import ground_on_success

    mistakes, guesses = _two_guesses(tmp_path)
    fact = mistakes.record("t#resolved", "TypeError", "r", "f", "the fact", -0.1)
    mistakes.promote(fact)
    resolver = _Resolver(_Grounded(fact))
    new_id, what = ground_on_success(
        resolver,
        mistakes,
        guesses=guesses,
        command="pytest t.py",
        failure="E",
        failed_code="x = 1\n",
        passing_code="x = 2\n",
        task_id="t",
    )
    assert new_id == fact and "-x = 1" in resolver.changes[0]
    statuses = {g: mistakes.get(g)["verification_status"] for g in guesses}
    assert statuses == {g: "superseded" for g in guesses}, what


def test_without_a_grounded_fact_the_guesses_stay_pending(tmp_path) -> None:
    from tools.organic_chain_run import ground_on_success

    mistakes, guesses = _two_guesses(tmp_path)
    new_id, what = ground_on_success(
        _Resolver(None),
        mistakes,
        guesses=guesses,
        command="pytest t.py",
        failure="E",
        failed_code="x = 1\n",
        passing_code="x = 2\n",
        task_id="t",
    )
    assert new_id is None and "pending" in what
    assert {mistakes.get(g)["verification_status"] for g in guesses} == {"pending"}


def test_no_change_asks_nothing(tmp_path) -> None:
    from tools.organic_chain_run import ground_on_success

    mistakes, guesses = _two_guesses(tmp_path)
    resolver = _Resolver(None)
    assert (
        ground_on_success(
            resolver,
            mistakes,
            guesses=guesses,
            command="c",
            failure="E",
            failed_code="same\n",
            passing_code="same\n",
            task_id="t",
        )[0]
        is None
    )
    assert resolver.changes == []
