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
