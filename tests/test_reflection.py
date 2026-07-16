"""Reflection-agent tests — JSON validation, clamping, recurrence, promotion.

Uses a fake in-memory LLM client implementing the :class:`LLMClient` protocol,
so these tests need neither Ollama nor a network connection.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

import pytest

from aios.agents.reflection_agent import ReflectionAgent, ReflectionError
from aios.core.llm import OllamaClient
from aios.core.verification_strength import VerificationStrength
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


class SequenceLLM:
    """Returns queued responses in order (last repeats), for retry tests."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
        idx = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return self.responses[idx]


class OllamaSpyLLM(OllamaClient):
    """An OllamaClient (so ``isinstance`` holds) whose ``complete`` is stubbed
    to record whether reflection requested ``json_mode``."""

    def __init__(self, response: str) -> None:  # noqa: D401 - skip real HTTP init
        self.response = response
        self.json_mode_seen: Optional[bool] = None

    def complete(  # type: ignore[override]
        self, prompt: str, *, system: Optional[str] = None, json_mode: bool = False
    ) -> str:
        self.json_mode_seen = json_mode
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


def test_reflection_refuses_implicit_legacy_store(db_path: Path) -> None:
    with pytest.raises(
        RuntimeError,
        match="MemoryAuthority or an explicit mistake store is required",
    ):
        ReflectionAgent(FakeLLM(_VALID), db_path=db_path)


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


def test_reflect_retries_until_parseable(db_path: Path) -> None:
    # A small local model can emit an unparseable object once and a good one on
    # the next draw; a bounded retry recovers the lesson instead of losing it.
    mistakes = MistakeMemory(db_path)
    llm = SequenceLLM(["not json at all", _VALID])
    agent = ReflectionAgent(llm, mistakes=mistakes)
    reflection = agent.reflect("cmd", "err", task_id="t1")
    assert reflection is not None
    assert llm.calls == 2
    assert mistakes.count() == 1


def test_reflect_gives_up_after_max_attempts(db_path: Path) -> None:
    # Persistent garbage raises after the bounded number of attempts (never an
    # unbounded loop) and writes nothing.
    mistakes = MistakeMemory(db_path)
    llm = FakeLLM("still not json")
    agent = ReflectionAgent(llm, mistakes=mistakes)
    with pytest.raises(ReflectionError):
        agent.reflect("x", "y", task_id="t1")
    assert llm.calls == ReflectionAgent._MAX_REFLECT_ATTEMPTS
    assert mistakes.count() == 0


def test_reflect_requests_json_mode_for_local_ollama(db_path: Path) -> None:
    # Reflection on a local Ollama model must request json_mode so the small
    # model stays parseable (the fix for the learning-loop reflect-step).
    llm = OllamaSpyLLM(_VALID)
    agent = ReflectionAgent(llm, mistakes=MistakeMemory(db_path))
    agent.reflect("cmd", "err", task_id="t1")
    assert llm.json_mode_seen is True


def test_reflect_stores_the_failed_command(db_path: Path) -> None:
    # The failed command is persisted so a later turn can rebuild the fail->confirm
    # tracker across an approval pause. A secret-free command is stored unchanged
    # (scrubbing is a no-op), so the exact byte-match against the live command holds.
    mistakes = MistakeMemory(db_path)
    agent = ReflectionAgent(FakeLLM(_VALID), mistakes=mistakes)
    r = agent.reflect("pytest lab/test_x.py -q", "boom", task_id="t1")
    assert mistakes.get(r.mistake_id)["failed_command"] == "pytest lab/test_x.py -q"


def test_reflect_scrubs_a_secret_in_the_failed_command(db_path: Path) -> None:
    # failed_command is the SAME secrets-at-rest surface as every other stored
    # field: a failing command that embeds a credential must not persist it raw.
    mistakes = MistakeMemory(db_path)
    agent = ReflectionAgent(FakeLLM(_VALID), mistakes=mistakes)
    secret = "sk-ant-api03-" + "A" * 40
    r = agent.reflect(
        f'curl -H "Authorization: Bearer {secret}" https://api.internal/x',
        "boom", task_id="t1",
    )
    stored = mistakes.get(r.mistake_id)["failed_command"]
    assert secret not in stored, "a credential in the failed command must be redacted at rest"


def test_pending_command_pairs_lists_pending_and_excludes_promoted(db_path: Path) -> None:
    mistakes = MistakeMemory(db_path)
    agent = ReflectionAgent(FakeLLM(_VALID), mistakes=mistakes)
    r = agent.reflect("pytest lab/test_x.py -q", "boom", task_id="sess")
    assert (r.mistake_id, "pytest lab/test_x.py -q") in agent.pending_command_pairs("sess")
    # A different session's lessons never leak into this one's tracker seed.
    assert agent.pending_command_pairs("other") == []
    # Once promoted (verified), it is no longer a pending pair to re-confirm.
    agent.confirm_lesson(r.mistake_id)
    assert agent.pending_command_pairs("sess") == []


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


def test_concurrent_reflections_increment_one_active_lesson(db_path: Path) -> None:
    barrier = threading.Barrier(2)
    reflections = []

    def reflect() -> None:
        barrier.wait()
        reflections.append(
            ReflectionAgent(FakeLLM(_VALID), mistakes=MistakeMemory(db_path)).reflect(
                "cmd", "err", task_id="shared-task"
            )
        )

    threads = [threading.Thread(target=reflect) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    mistakes = MistakeMemory(db_path)
    assert mistakes.count() == 1
    assert mistakes.get(reflections[0].mistake_id)["occurrence_count"] == 2
    assert sorted(reflection.recurrence for reflection in reflections) == [False, True]


def test_recall_pending_returns_session_lessons_until_verified(db_path: Path) -> None:
    mistakes = MistakeMemory(db_path)
    agent = ReflectionAgent(FakeLLM(_VALID), mistakes=mistakes)
    reflection = agent.reflect("cat missing.txt", "No such file", task_id="sess-A")
    # A lesson from a different session must not leak into sess-A's recall.
    ReflectionAgent(FakeLLM(_VALID), mistakes=mistakes).reflect("x", "y", task_id="sess-B")

    pending = agent.recall_pending("sess-A")
    assert [p["mistake_id"] for p in pending] == [reflection.mistake_id]
    assert pending[0]["error_type"] == "PathNotFound"
    assert "verify a path exists" in pending[0]["lesson_text"]

    # Once verified, it is no longer recalled as pending.
    agent.confirm_lesson(reflection.mistake_id)
    assert agent.recall_pending("sess-A") == []


def test_confirm_lesson_promotes_to_verified(db_path: Path) -> None:
    mistakes = MistakeMemory(db_path)
    agent = ReflectionAgent(FakeLLM(_VALID), mistakes=mistakes)
    reflection = agent.reflect("c", "e", task_id="t1")
    agent.confirm_lesson(reflection.mistake_id)
    assert mistakes.get(reflection.mistake_id)["verification_status"] == "verified"


def test_confirm_lesson_refuses_weak_evidence(db_path: Path) -> None:
    mistakes = MistakeMemory(db_path)
    agent = ReflectionAgent(FakeLLM(_VALID), mistakes=mistakes)
    reflection = agent.reflect("c", "e", task_id="t1")
    agent.confirm_lesson(reflection.mistake_id, strength=VerificationStrength.WEAK)
    assert mistakes.get(reflection.mistake_id)["verification_status"] == "pending"


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
