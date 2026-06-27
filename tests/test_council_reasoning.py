"""Tests for Phase 3 thinking Queens: narrow-only reasoning + memory retrieval."""
from __future__ import annotations

import json

import pytest

from aios import config
from aios.council.queens.memory import MemoryQueen
from aios.council.queens.planner import CouncilMissionRequest, PlannerQueen
from aios.council.reasoning import MemoryRetrieval, reconcile_plan
from aios.runtime.contracts import MissionContract


class FakeLLM:
    """Minimal LLMClient: returns a canned completion string."""

    def __init__(self, payload: str) -> None:
        self._payload = payload

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        return self._payload


class FakeRetriever:
    def __init__(self, result: MemoryRetrieval) -> None:
        self._result = result

    def retrieve(self, goal: str) -> MemoryRetrieval:
        return self._result


def _request(**over: object) -> CouncilMissionRequest:
    data: dict[str, object] = {
        "mission_id": "m-reason-1",
        "goal": "Improve the login page without backend changes.",
        "workspace_root": "/tmp/ws",
        "allowed_files": ["frontend/src/pages/Login.jsx"],
    }
    data.update(over)
    return CouncilMissionRequest(**data)  # type: ignore[arg-type]


def _contract(**over: object) -> MissionContract:
    data: dict[str, object] = {
        "mission_id": "m1",
        "goal": "Improve login page",
        "worker_type": "w",
        "created_by": "planner",
        "workspace_root": "/tmp/ws",
        "allowed_files": ["frontend/src/pages/Login.jsx"],
    }
    data.update(over)
    return MissionContract(**data)  # type: ignore[arg-type]


# --- reconcile_plan: the security core (narrow-only) -----------------------

def test_reconcile_is_narrow_only_under_adversarial_plan() -> None:
    """An LLM trying to widen scope / lower risk / clear approval is fully clamped."""
    plan = {
        "files_to_touch": [
            "frontend/src/pages/Login.jsx",
            "aios/security/gateway.py",  # not permitted -> dropped
            "../../etc/passwd",  # traversal -> dropped
        ],
        "forbidden_files": ["secrets.txt"],
        "risk_level": "GREEN",  # tries to LOWER from YELLOW
        "requires_approval": False,  # tries to CLEAR
        "verification_commands": ["pytest -q"],
        "confidence": 0.99,
    }
    out = reconcile_plan(
        request_allowed=["frontend/src/pages/Login.jsx"],
        request_forbidden=["backend/", ".env", "aios/security/"],
        request_risk="YELLOW",
        request_requires_approval=True,
        request_verification=[],
        plan=plan,
    )
    assert out.allowed_files == ["frontend/src/pages/Login.jsx"]
    assert "aios/security/gateway.py" not in out.allowed_files
    assert "../../etc/passwd" not in out.allowed_files
    assert "secrets.txt" in out.forbidden_files  # union added
    assert "aios/security/" in out.forbidden_files  # original kept
    assert out.risk_level == "YELLOW"  # never lowered
    assert out.requires_approval is True  # never cleared
    assert "pytest -q" in out.verification_commands


def test_reconcile_allows_raising_risk_and_adding_approval() -> None:
    out = reconcile_plan(
        request_allowed=["a.py"],
        request_forbidden=[],
        request_risk="GREEN",
        request_requires_approval=False,
        request_verification=[],
        plan={"risk_level": "RED", "requires_approval": True, "files_to_touch": ["a.py"]},
    )
    assert out.risk_level == "RED"
    assert out.requires_approval is True


def test_reconcile_keeps_request_allowed_when_plan_files_invalid() -> None:
    out = reconcile_plan(
        request_allowed=["a.py"],
        request_forbidden=[],
        request_risk="YELLOW",
        request_requires_approval=True,
        request_verification=[],
        plan={"files_to_touch": ["nonexistent.py"]},
    )
    assert out.allowed_files == ["a.py"]  # never emptied or widened


def test_reconcile_fails_closed_to_red_on_noncanonical_floor() -> None:
    """A malformed current risk collapses to RED (ceiling), never YELLOW (middle)."""
    out = reconcile_plan(
        request_allowed=["a.py"],
        request_forbidden=[],
        request_risk="CRITICAL",  # not a canonical level
        request_requires_approval=True,
        request_verification=[],
        plan={"risk_level": "GREEN", "files_to_touch": ["a.py"]},
    )
    assert out.risk_level == "RED"


def test_reconcile_rejects_nonfinite_confidence() -> None:
    for bad in (float("nan"), float("inf"), float("-inf")):
        out = reconcile_plan(
            request_allowed=["a.py"],
            request_forbidden=[],
            request_risk="YELLOW",
            request_requires_approval=True,
            request_verification=[],
            plan={"files_to_touch": ["a.py"], "confidence": bad},
        )
        assert out.confidence == pytest.approx(0.6)  # default, not 1.0


def test_reconcile_tolerates_non_list_fields() -> None:
    out = reconcile_plan(
        request_allowed=["a.py"],
        request_forbidden=[],
        request_risk="YELLOW",
        request_requires_approval=True,
        request_verification=[],
        plan={"files_to_touch": "a.py", "verification_commands": "pytest", "steps": None},
    )
    assert out.allowed_files == ["a.py"]
    assert out.verification_commands == []  # garbage string ignored
    assert out.steps == []


# --- PlannerQueen reasoning -------------------------------------------------

def test_planner_applies_reasoning_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "COUNCIL_REASONING", True)
    payload = json.dumps(
        {
            "steps": ["read Login.jsx", "add aria-label"],
            "files_to_touch": ["frontend/src/pages/Login.jsx"],
            "verification_commands": ["python -m pytest tests -q"],
            "risk_level": "YELLOW",
            "requires_approval": True,
            "confidence": 0.71,
        }
    )
    draft = PlannerQueen(llm=FakeLLM(payload)).draft(_request())
    assert draft.contract.metadata["council_plan"] == ["read Login.jsx", "add aria-label"]
    assert "python -m pytest tests -q" in draft.contract.verification_commands
    assert draft.verdict.confidence == pytest.approx(0.71)
    assert draft.verdict.metadata["reasoned"] is True


def test_planner_reasoning_cannot_widen_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "COUNCIL_REASONING", True)
    payload = json.dumps(
        {
            "files_to_touch": ["frontend/src/pages/Login.jsx", "aios/security/gateway.py"],
            "risk_level": "GREEN",
            "requires_approval": False,
            "confidence": 1.0,
        }
    )
    draft = PlannerQueen(llm=FakeLLM(payload)).draft(
        _request(risk_level="YELLOW", requires_approval=True)
    )
    assert "aios/security/gateway.py" not in draft.contract.allowed_files
    assert draft.contract.risk_level == "YELLOW"
    assert draft.contract.requires_approval is True


def test_planner_falls_back_on_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "COUNCIL_REASONING", True)
    draft = PlannerQueen(llm=FakeLLM("not json at all")).draft(_request())
    assert "council_plan" not in draft.contract.metadata
    assert draft.verdict.confidence == pytest.approx(0.82)


def test_planner_deterministic_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "COUNCIL_REASONING", False)
    draft = PlannerQueen(llm=FakeLLM('{"risk_level":"RED"}')).draft(_request())
    assert draft.contract.risk_level == "YELLOW"  # request default, untouched
    assert draft.verdict.confidence == pytest.approx(0.82)


def test_planner_deterministic_when_no_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "COUNCIL_REASONING", True)
    draft = PlannerQueen().draft(_request())
    assert "council_plan" not in draft.contract.metadata


# --- MemoryQueen retrieval --------------------------------------------------

def test_memory_allows_when_no_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "COUNCIL_REASONING", True)
    queen = MemoryQueen(
        retriever=FakeRetriever(MemoryRetrieval(hints=["reuse X"], cautions=[], block=False))
    )
    verdict = queen.review(_contract())
    assert verdict.verdict == "allow"
    assert "reuse X" in verdict.constraints


def test_memory_defers_on_relevant_prior_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "COUNCIL_REASONING", True)
    queen = MemoryQueen(
        retriever=FakeRetriever(
            MemoryRetrieval(cautions=["prior failure: broke tests"], block=False)
        )
    )
    verdict = queen.review(_contract())
    assert verdict.verdict == "defer"
    assert any("broke tests" in c for c in verdict.constraints)


def test_memory_denies_on_strong_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "COUNCIL_REASONING", True)
    queen = MemoryQueen(
        retriever=FakeRetriever(MemoryRetrieval(cautions=["prior failure"], block=True))
    )
    verdict = queen.review(_contract())
    assert verdict.verdict == "deny"


def test_memory_deterministic_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "COUNCIL_REASONING", False)
    queen = MemoryQueen(retriever=FakeRetriever(MemoryRetrieval(block=True)))
    assert queen.review(_contract()).verdict == "allow"  # flag off ignores retriever


def test_memory_retrieval_error_falls_back_to_allow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "COUNCIL_REASONING", True)

    class Boom:
        def retrieve(self, goal: str) -> MemoryRetrieval:
            raise RuntimeError("db down")

    verdict = MemoryQueen(retriever=Boom()).review(_contract())
    assert verdict.verdict == "allow"
    assert verdict.metadata.get("retrieval_error") is True
