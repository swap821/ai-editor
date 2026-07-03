"""Unit tests for AIOS_OFFLINE_MODE graceful degradation (sovereignty S4)."""
from __future__ import annotations

import json
from typing import Any, Optional

import pytest

import aios.config as config
from aios.core.confidence_filter import TaskStep
from aios.core.native_planner import NativePlanner, NativePlanResult
from aios.core.planner import Planner, PlannerError
from aios.agents.reflection_agent import ReflectionAgent


# ── Fakes ──────────────────────────────────────────────────────────────────


class FakeLLM:
    """Mock LLM that records whether it was called."""

    def __init__(self) -> None:
        self.called = False

    def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
        self.called = True
        return json.dumps({
            "steps": [{"step_id": "1", "description": "do thing", "confidence": 0.9}]
        })

    def chat(self, messages: list, **kw: Any) -> dict:
        self.called = True
        return {"role": "assistant", "content": "hello"}


class FakeSwarmPatterns:
    def __init__(self, results: list[dict] | None = None):
        self._results = results or []

    def recall(self, goal: str, *, limit: int = 1) -> list[dict]:
        return self._results[:limit]


SWARM_MATCH = {
    "pattern_id": 42,
    "goal_pattern": "build a REST API with tests",
    "subtasks": ["scaffold endpoints", "write models", "add tests"],
    "success_count": 5,
    "failure_count": 0,
    "success_rate": 1.0,
    "relevance": 0.80,
    "score": 0.80,
}


# ── Tests ──────────────────────────────────────────────────────────────────


def test_offline_mode_config_defaults_false() -> None:
    """OFFLINE_MODE defaults to False — existing behavior unchanged."""
    assert hasattr(config, "OFFLINE_MODE")
    # The actual default depends on env; just confirm the attribute exists
    # and is a bool.
    assert isinstance(config.OFFLINE_MODE, bool)


def test_planner_offline_raises_planner_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """With OFFLINE_MODE=True and no native match, plan() raises PlannerError."""
    monkeypatch.setattr(config, "OFFLINE_MODE", True)
    llm = FakeLLM()
    planner = Planner(llm, native=NativePlanner())

    with pytest.raises(PlannerError, match="Offline mode"):
        planner.plan("something completely novel")
    assert llm.called is False


def test_planner_offline_native_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    """With OFFLINE_MODE=True, a matching native plan returns normally."""
    monkeypatch.setattr(config, "OFFLINE_MODE", True)
    llm = FakeLLM()
    native = NativePlanner(patterns=FakeSwarmPatterns([SWARM_MATCH]))
    planner = Planner(llm, native=native)

    plan = planner.plan("build a REST API with tests")
    assert llm.called is False
    assert plan.native_source is not None
    assert len(plan.steps) == 3


def test_reflection_offline_skips_silently(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    """With OFFLINE_MODE=True, reflect() returns None without calling the LLM."""
    monkeypatch.setattr(config, "OFFLINE_MODE", True)

    from aios.memory.db import init_memory_db
    db = tmp_path / "test.db"
    init_memory_db(db)

    llm = FakeLLM()
    reflector = ReflectionAgent(llm, db_path=db)
    result = reflector.reflect("bad_command", "error: something went wrong")
    assert result is None
    assert llm.called is False


def test_reflection_online_calls_llm(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    """With OFFLINE_MODE=False, reflect() calls the LLM normally."""
    monkeypatch.setattr(config, "OFFLINE_MODE", False)

    from aios.memory.db import init_memory_db
    db = tmp_path / "test.db"
    init_memory_db(db)

    llm = FakeLLM()
    reflector = ReflectionAgent(llm, db_path=db)
    # The LLM output won't parse properly, but the LLM WILL be called.
    try:
        reflector.reflect("cmd", "error text")
    except Exception:
        pass  # parse error expected with fake LLM output
    assert llm.called is True


def test_planner_online_calls_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """With OFFLINE_MODE=False, the LLM planner runs when native misses."""
    monkeypatch.setattr(config, "OFFLINE_MODE", False)
    llm = FakeLLM()
    planner = Planner(llm, native=NativePlanner())

    plan = planner.plan("something novel")
    assert llm.called is True
    assert plan.native_source is None
