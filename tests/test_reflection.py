"""Reflection-agent tests — JSON validation, clamping, recurrence, promotion.

Uses a fake in-memory LLM client implementing the :class:`LLMClient` protocol,
so these tests need neither Ollama nor a network connection.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest

from aios.agents.reflection_agent import ReflectionAgent, ReflectionError
from aios.memory import db as memdb
from aios.memory.mistake import MistakeMemory


class FakeLLM:
    """Returns a fixed response, satisfying the LLMClient protocol."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0

    def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
        self.calls += 1
        return self.response


_VALID = json.dumps(
    {
        "error_type": "PathNotFound",
        "root_cause": "the target file did not exist",
        "fix_applied": "created the file before reading",
        "lesson_text": "verify a path exists before reading it",
        "confidence_delta": -0.2,
    }
)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "memory.db"
    memdb.init_memory_db(path)
    return path


def test_reflect_writes_pending_lesson(db_path: Path) -> None:
    agent = ReflectionAgent(FakeLLM(_VALID), mistakes=MistakeMemory(db_path))
    reflection = agent.reflect("cat missing.txt", "No such file", task_id="t1")

    assert reflection.error_type == "PathNotFound"
    assert reflection.confidence_delta == -0.2
    assert reflection.recurrence is False
    stored = MistakeMemory(db_path).get(reflection.mistake_id)
    assert stored is not None
    assert stored["verification_status"] == "pending"
    assert stored["fix_applied"] == "created the file before reading"


def test_malformed_json_is_rejected_without_writing(db_path: Path) -> None:
    mistakes = MistakeMemory(db_path)
    agent = ReflectionAgent(FakeLLM("Sorry, I can't help with that."), mistakes=mistakes)
    with pytest.raises(ReflectionError):
        agent.reflect("x", "y", task_id="t1")
    assert mistakes.count() == 0


def test_missing_required_field_is_rejected(db_path: Path) -> None:
    incomplete = json.dumps({"error_type": "E", "confidence_delta": -0.1})
    mistakes = MistakeMemory(db_path)
    agent = ReflectionAgent(FakeLLM(incomplete), mistakes=mistakes)
    with pytest.raises(ReflectionError):
        agent.reflect("x", "y", task_id="t1")
    assert mistakes.count() == 0


def test_positive_delta_is_clamped_to_zero(db_path: Path) -> None:
    payload = json.dumps(
        {
            "error_type": "E",
            "root_cause": "r",
            "fix_applied": "f",
            "lesson_text": "l",
            "confidence_delta": 0.9,
        }
    )
    agent = ReflectionAgent(FakeLLM(payload), mistakes=MistakeMemory(db_path))
    assert agent.reflect("x", "y", task_id="t1").confidence_delta == 0.0


def test_recurrence_increments_instead_of_duplicating(db_path: Path) -> None:
    mistakes = MistakeMemory(db_path)
    agent = ReflectionAgent(FakeLLM(_VALID), mistakes=mistakes)
    first = agent.reflect("cmd", "err", task_id="same-task")
    second = agent.reflect("cmd", "err", task_id="same-task")

    assert second.recurrence is True
    assert first.mistake_id == second.mistake_id
    assert mistakes.get(first.mistake_id)["occurrence_count"] == 2
    assert mistakes.count() == 1


def test_confirm_lesson_promotes_to_verified(db_path: Path) -> None:
    mistakes = MistakeMemory(db_path)
    agent = ReflectionAgent(FakeLLM(_VALID), mistakes=mistakes)
    reflection = agent.reflect("c", "e", task_id="t1")
    agent.confirm_lesson(reflection.mistake_id)
    assert mistakes.get(reflection.mistake_id)["verification_status"] == "verified"


def test_legacy_suggested_fix_alias_is_accepted(db_path: Path) -> None:
    legacy = json.dumps(
        {
            "error_type": "E",
            "root_cause": "r",
            "suggested_fix": "do the thing",
            "lesson_text": "l",
            "confidence_delta": -0.1,
        }
    )
    agent = ReflectionAgent(FakeLLM(legacy), mistakes=MistakeMemory(db_path))
    assert agent.reflect("x", "y", task_id="t1").fix_applied == "do the thing"
