"""Integration tests for the mandatory plan stage (``AIOS_PLAN_STAGE``).

The stage runs the SAME deterministic Planner behind ``POST /api/v1/plan``
unconditionally on every non-reflex ``/api/generate`` turn, surfacing the
confidence-partitioned plan as a ``plan`` SSE event + advisory context. These
tests drive REAL requests through the FastAPI app (fakes only at the
provider/executor boundary, per house style — see ``tests/test_telemetry_wiring.py``)
and assert the stage's contract: default-OFF, structured emission when ON,
fail-open on planner failure, gate ordering, and coexistence with the
approval surface.
"""
from __future__ import annotations

import json
import os
from typing import Iterator, Optional

import pytest
from fastapi.testclient import TestClient

import aios.api.main as api_main
from aios import config
from aios.api.main import (
    app,
    get_approval_store,
    get_autonomy,
    get_cerebellum,
    get_development_tracker,
    get_executor,
    get_alignment_interpreter,
    get_llm_client,
    get_mistake_memory,
    get_ollama_client,
    get_reflection_agent,
    get_semantic_indexer,
    get_skill_memory,
)
from aios.core.autonomy import AutonomyLedger
from aios.core.cerebellum import Cerebellum
from aios.core.confidence_filter import GateResult
from aios.core.executor import Executor
from aios.memory.development import DevelopmentTracker
from aios.memory.mistake import MistakeMemory
from aios.memory.skills import SkillMemory
from aios.security.gateway import RateLimiter


class FakeIndexer:
    def __init__(self) -> None:
        self.added: list[str] = []

    def add(self, text: str) -> int:
        self.added.append(text)
        return len(self.added)


class FakeRunner:
    def __call__(self, command, *, cwd, env, timeout_s):
        return f"ran: {command}", "", 0


class RecordingAudit:
    def __call__(self, actor, payload, zone, **kwargs):
        return None


def _fake_executor() -> Executor:
    return Executor(runner=FakeRunner(), rate_limiter=RateLimiter(), audit_log=RecordingAudit())


_ALIGNMENT_JSON = json.dumps(
    {
        "goal": "Handle the latest request",
        "intent": "execute",
        "desired_outcome": "A completed response or gated action",
        "constraints": [],
        "assumptions": [],
        "unknowns": [],
        "decisions": [],
        "confidence": 0.92,
        "next_action": "Proceed under existing gates",
    }
)


class PlanningAlignedLLM:
    """One completion client serving BOTH advisory prompts deterministically.

    The alignment interpreter and the plan stage share ``get_llm_client``; the
    ``system`` argument discriminates them (the planner's system prompt names
    itself "the planning module"). Step 2's 0.05 confidence sits far below the
    0.72 gate so it lands in the ``escalate`` partition regardless of small
    verified-memory calibration adjustments.
    """

    def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
        if system and "planning module" in system:
            return json.dumps(
                {
                    "steps": [
                        {"step_id": "1", "description": "inspect the target", "confidence": 0.95},
                        {"step_id": "2", "description": "apply the risky change", "confidence": 0.05},
                    ]
                }
            )
        return _ALIGNMENT_JSON


class AlignedOnlyLLM:
    """Valid alignment frame; NO usable plan JSON — the planner must fail open."""

    def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
        return _ALIGNMENT_JSON


class PlainOllama:
    """No tool calls, no verify — the baseline LLM dispatch path."""

    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b"]}

    def chat(
        self,
        messages: list,
        *,
        tools: Optional[list] = None,
        model: Optional[str] = None,
    ) -> dict:
        return {"role": "assistant", "content": "just an answer, no tools involved"}


class YellowOllama:
    """First turn calls a YELLOW (needs-approval) command — the turn pauses."""

    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b"]}

    def chat(
        self,
        messages: list,
        *,
        tools: Optional[list] = None,
        model: Optional[str] = None,
    ) -> dict:
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "execute_terminal",
                        "arguments": {"command": "pip install flask"},
                    }
                }
            ],
        }


def _isolate_turn_memory(tmp_path, llm_factory) -> None:
    """Pin every advisory turn-gate input to fresh, deterministic state.

    Same rationale as ``test_telemetry_wiring._isolate_turn_memory``; the plan
    stage adds one more advisory input (planner calibration), which decision 6
    of the stage design routes through the SAME injected development/skills
    providers pinned here.
    """
    db = tmp_path / "turn_memory.db"
    app.dependency_overrides[get_llm_client] = llm_factory
    app.dependency_overrides[get_mistake_memory] = lambda: MistakeMemory(db)
    app.dependency_overrides[get_development_tracker] = lambda: DevelopmentTracker(db)
    app.dependency_overrides[get_skill_memory] = lambda: SkillMemory(db)
    app.dependency_overrides[get_autonomy] = lambda: AutonomyLedger(db)
    app.dependency_overrides[get_cerebellum] = lambda: Cerebellum(db)
    app.dependency_overrides[get_reflection_agent] = lambda: None


def _sse_events(text: str) -> list[tuple[str, dict]]:
    """Parse a TestClient SSE body into (event, payload) tuples."""
    events: list[tuple[str, dict]] = []
    event: Optional[str] = None
    data_lines: list[str] = []
    for raw in text.splitlines() + [""]:
        if raw == "":
            if event is not None:
                payload = json.loads("\n".join(data_lines) or "{}")
                events.append((event, payload))
            event, data_lines = None, []
        elif raw.startswith("event:"):
            event = raw[len("event:"):].strip()
        elif raw.startswith("data:"):
            data_lines.append(raw[len("data:"):].strip())
    return events


def _plan_events(text: str) -> list[dict]:
    return [payload for name, payload in _sse_events(text) if name == "plan"]


@pytest.fixture()
def stage_client(tmp_path) -> Iterator[TestClient]:
    """Plain-LLM turn with the planning-capable completion client."""
    app.dependency_overrides[get_ollama_client] = lambda: PlainOllama()
    app.dependency_overrides[get_executor] = _fake_executor
    app.dependency_overrides[get_semantic_indexer] = lambda: FakeIndexer()
    _isolate_turn_memory(tmp_path, PlanningAlignedLLM)
    get_approval_store().clear()
    with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _generate(client: TestClient, session_id: str, text: str):
    return client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": text}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": session_id,
        },
    )


def test_plan_stage_suppressed_when_disabled(stage_client: TestClient, monkeypatch) -> None:
    """Flag OFF: no `plan` event. (Pinned via monkeypatch rather than asserting
    the env-derived literal, so a dev/CI environment exporting AIOS_PLAN_STAGE
    while dogfooding cannot fail the opt-out behavior test.)"""
    monkeypatch.setattr(config, "PLAN_STAGE_ENABLED", False)
    response = _generate(stage_client, "plan-stage-off", "plan stage probe xyzzy quux")
    assert response.status_code == 200
    assert "event: done" in response.text
    assert _plan_events(response.text) == []


@pytest.mark.skipif(
    os.environ.get("AIOS_PLAN_STAGE") is not None,
    reason="an explicit AIOS_PLAN_STAGE override is active — the default literal is masked",
)
def test_plan_stage_on_by_default() -> None:
    """The default flipped ON (2026-07-07) once the learning-loop prover was green
    at 19/19 with the stage enabled. Skipped when the env var pins it, so a machine
    that opts out cannot fail the default-contract test."""
    assert config.PLAN_STAGE_ENABLED is True


def test_plan_stage_emits_structured_plan_event(
    stage_client: TestClient, monkeypatch
) -> None:
    """Flag ON: one `plan` event carrying the confidence-partitioned plan
    (the /api/v1/plan serialization + a native flag), and the turn still
    proceeds to the tool loop and `done` — the stage is advisory."""
    monkeypatch.setattr(config, "PLAN_STAGE_ENABLED", True)
    response = _generate(stage_client, "plan-stage-on", "plan stage probe xyzzy quux")
    assert response.status_code == 200
    assert "event: done" in response.text

    plans = _plan_events(response.text)
    assert len(plans) == 1
    plan = plans[0]
    assert plan["goal"] == "plan stage probe xyzzy quux"
    assert len(plan["steps"]) == 2
    assert plan["native"] is False  # no native template matched this goal
    # Step 2's 0.05 confidence must land in the escalate partition.
    escalated_ids = {e["step"]["step_id"] for e in plan["escalate"]}
    assert "2" in escalated_ids
    assert plan["requires_human"] is True


def test_plan_stage_fails_open_on_unusable_plan(tmp_path, monkeypatch) -> None:
    """A planner failure (no usable steps JSON) logs and emits nothing; the
    turn completes normally — planning is advisory, never fatal."""
    monkeypatch.setattr(config, "PLAN_STAGE_ENABLED", True)
    app.dependency_overrides[get_ollama_client] = lambda: PlainOllama()
    app.dependency_overrides[get_executor] = _fake_executor
    app.dependency_overrides[get_semantic_indexer] = lambda: FakeIndexer()
    _isolate_turn_memory(tmp_path, AlignedOnlyLLM)
    get_approval_store().clear()
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            response = _generate(client, "plan-stage-fail-open", "plan stage probe xyzzy quux")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "event: done" in response.text
    assert _plan_events(response.text) == []


def test_confidence_gated_turn_skips_plan_stage(tmp_path, monkeypatch) -> None:
    """Gate ordering: a confidence-gated turn diverts BEFORE the plan stage —
    no planning consultation is paid for a turn the gate already stopped."""
    monkeypatch.setattr(config, "PLAN_STAGE_ENABLED", True)
    monkeypatch.setattr(
        api_main,
        "confidence_gate",
        lambda confidence: GateResult(False, "forced below threshold for test"),
    )
    app.dependency_overrides[get_ollama_client] = lambda: PlainOllama()
    app.dependency_overrides[get_executor] = _fake_executor
    app.dependency_overrides[get_semantic_indexer] = lambda: FakeIndexer()
    _isolate_turn_memory(tmp_path, PlanningAlignedLLM)
    get_approval_store().clear()
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            response = _generate(client, "plan-stage-gated", "plan stage probe xyzzy quux")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "event: confidence.gated" in response.text
    assert _plan_events(response.text) == []


def test_plan_stage_coexists_with_approval_pause(tmp_path, monkeypatch) -> None:
    """The stage is advisory: with it enabled, a YELLOW tool call still pauses
    at the existing per-action approval surface — plan event AND
    human_required appear in the same turn, and no approval is consumed by
    the stage itself."""
    monkeypatch.setattr(config, "PLAN_STAGE_ENABLED", True)
    app.dependency_overrides[get_ollama_client] = lambda: YellowOllama()
    app.dependency_overrides[get_executor] = _fake_executor
    app.dependency_overrides[get_semantic_indexer] = lambda: FakeIndexer()
    _isolate_turn_memory(tmp_path, PlanningAlignedLLM)
    get_approval_store().clear()
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            response = _generate(client, "plan-stage-approval", "plan stage probe xyzzy quux")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert len(_plan_events(response.text)) == 1
    assert "event: human_required" in response.text

    # Approval-resume guard: replaying the turn with the granted token must
    # NOT re-plan the same goal (no second `plan` event, no second planner
    # LLM call injected mid-approved-action).
    paused = [p for name, p in _sse_events(response.text) if name == "human_required"]
    token = paused[0].get("input", {}).get("approvalToken")
    assert token
    with TestClient(app, client=("127.0.0.1", 12345)) as client2:
        app.dependency_overrides[get_ollama_client] = lambda: YellowOllama()
        app.dependency_overrides[get_executor] = _fake_executor
        app.dependency_overrides[get_semantic_indexer] = lambda: FakeIndexer()
        resume = client2.post(
            "/api/generate",
            json={
                "messages": [
                    {"role": "user", "content": [{"text": "plan stage probe xyzzy quux"}]}
                ],
                "modelId": "ollama.llama3.2:3b",
                "sessionId": "plan-stage-approval",
                "approvalTokens": [token],
            },
        )
    assert resume.status_code == 200
    assert _plan_events(resume.text) == []


def test_plan_stage_runs_with_alignment_interpreter_disabled(
    tmp_path, monkeypatch
) -> None:
    """AIOS_INTERPRET_ALIGNMENT=false must not break the stage: the hoisted
    cerebellum pre-check and `_cerebellum_matched` are defined outside the
    alignment block, so a non-reflex turn still plans and completes."""
    monkeypatch.setattr(config, "PLAN_STAGE_ENABLED", True)
    app.dependency_overrides[get_ollama_client] = lambda: PlainOllama()
    app.dependency_overrides[get_executor] = _fake_executor
    app.dependency_overrides[get_semantic_indexer] = lambda: FakeIndexer()
    _isolate_turn_memory(tmp_path, PlanningAlignedLLM)
    app.dependency_overrides[get_alignment_interpreter] = lambda: None
    get_approval_store().clear()
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            response = _generate(client, "plan-stage-no-align", "plan stage probe xyzzy quux")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "event: done" in response.text
    assert len(_plan_events(response.text)) == 1
