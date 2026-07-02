"""The organism conformance test — the heartbeat of the whole.

Line coverage cannot see seams: on 2026-07-02 the memory halo had tested
store logic, tested endpoints, and green gates everywhere — and the
operator's first real touch still failed at an interaction boundary. This
suite instruments the backend half of the organism's one load-bearing seam:
a REAL turn driven through POST /api/generate, asserting the SSE contract
every body system depends on. The frontend half of the same contract is
pinned by aiosAdapter.dispatch.test.ts (the adapter forwards these exact
fields to the cognition bus). Together the seam is held from both ends.

Contract under test:
  1. Every frame carries the typed event spine: a phase from the five-phase
     vocabulary, a monotonically non-decreasing seq, one constant turn_id.
  2. Exactly one `done` frame, and it is the final frame.
  3. The `route` frame (the active-brain badge) precedes the first token.
  4. Emotion leg: a low-confidence turn emits `confidence.gated` with the
     threshold and a clarifying question, runs NO tool steps, and still
     closes with `done`.
  5. Narrative leg: an operator preference statement lands in the
     QUARANTINED fact_proposals queue — and never directly in active facts.
"""
from __future__ import annotations

import json
import re
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from aios.api.main import (
    app,
    get_executor,
    get_llm_client,
    get_ollama_client,
    get_semantic_facts,
    get_semantic_indexer,
    get_approval_store,
)
from aios.memory.db import init_memory_db
from aios.memory.facts import SemanticFacts
from tests.test_api import FakeIndexer, FakeLLM, FakeOllama, _fake_executor

PHASES = {"chemotaxis", "reflex", "emotion", "narrative", "wonder"}


class LowConfidenceLLM(FakeLLM):
    """An alignment layer that honestly reports it does not understand.

    unknowns stays EMPTY on purpose: populated unknowns trip the earlier
    ambiguity ask-exit, which pauses before the confidence gate ever speaks.
    This fake isolates the gate itself: understood-but-unsure."""

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        if "understanding layer" in (system or ""):
            return json.dumps(
                {
                    "goal": "Do something vaguely specified",
                    "intent": "execute",
                    "desired_outcome": "unclear",
                    "constraints": [],
                    "assumptions": [],
                    "unknowns": [],
                    "decisions": [],
                    "confidence": 0.2,
                    "next_action": "proceed",
                }
            )
        return super().complete(prompt, system=system)


@pytest.fixture()
def facts_db(tmp_path) -> SemanticFacts:
    """An ISOLATED facts store so a real turn's proposals are hermetic — the
    conformance turn must never pollute (or read) the shared session ledger."""
    db_path = tmp_path / "conformance_facts.db"
    init_memory_db(db_path)
    return SemanticFacts(db_path=db_path)


@pytest.fixture()
def client(facts_db: SemanticFacts) -> Iterator[TestClient]:
    app.dependency_overrides[get_llm_client] = FakeLLM
    app.dependency_overrides[get_ollama_client] = FakeOllama
    app.dependency_overrides[get_executor] = _fake_executor
    app.dependency_overrides[get_semantic_indexer] = lambda: FakeIndexer()
    app.dependency_overrides[get_semantic_facts] = lambda: facts_db
    get_approval_store().clear()
    with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _frames(body: str) -> list[tuple[str, dict]]:
    """Parse an SSE body into ordered (event, data) frames."""
    out: list[tuple[str, dict]] = []
    for block in re.split(r"\n\n+", body.strip()):
        event, data_lines = None, []
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())
        if event:
            try:
                data = json.loads("".join(data_lines)) if data_lines else {}
            except json.JSONDecodeError:
                data = {}
            out.append((event, data))
    return out


def _turn(client: TestClient, text: str) -> list[tuple[str, dict]]:
    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": text}]}],
            "modelId": "ollama.llama3.2:3b",
        },
    )
    assert response.status_code == 200
    return _frames(response.text)


def test_every_frame_carries_the_typed_spine(client: TestClient) -> None:
    frames = _turn(client, "make a button")
    assert frames, "a turn must stream frames"

    turn_ids = set()
    last_seq = -1
    for event, data in frames:
        assert data.get("phase") in PHASES, f"{event} frame missing/unknown phase: {data.get('phase')!r}"
        seq = data.get("seq")
        assert isinstance(seq, int), f"{event} frame missing integer seq"
        assert seq >= last_seq, f"seq regressed at {event}: {seq} < {last_seq}"
        last_seq = seq
        turn_ids.add(data.get("turn_id"))
    assert len(turn_ids) == 1 and None not in turn_ids, "one constant turn_id per turn"


def test_done_is_singular_and_final_and_route_precedes_tokens(client: TestClient) -> None:
    frames = _turn(client, "make a button")
    events = [event for event, _ in frames]

    assert events.count("done") == 1
    assert events[-1] == "done"

    assert "route" in events, "the active-brain badge frame must stream"
    first_token = events.index("text_chunk") if "text_chunk" in events else len(events)
    assert events.index("route") < first_token, "route must precede the first token"


def test_low_confidence_turn_pauses_asks_and_runs_no_tools(client: TestClient) -> None:
    app.dependency_overrides[get_llm_client] = LowConfidenceLLM
    frames = _turn(client, "do it like before")
    events = [event for event, _ in frames]

    gated = [data for event, data in frames if event == "confidence.gated"]
    assert gated, "the emotion layer must gate a low-confidence turn"
    assert gated[0]["confidence"] < gated[0]["threshold"]
    assert gated[0]["question"], "the pause must ask something"
    assert gated[0].get("phase") == "emotion"

    assert "step" not in events, "a gated turn must execute NO tools"
    question_text = "".join(data.get("text", "") for event, data in frames if event == "text_chunk")
    assert question_text, "the clarifying question must reach the reply stream"
    assert events[-1] == "done"


def test_bus_carries_only_observations_on_a_real_turn(
    tmp_path, monkeypatch: pytest.MonkeyPatch, facts_db: SemanticFacts
) -> None:
    """W3, integrated: with the cortex bus ON, a REAL turn through the app must
    (a) produce only observation events on the bus — never an authority type,
    (b) prove the PRODUCTION wiring is live: the lifespan-subscribed
    SelfModelHandler processes the observation within ~1s (the adversarial W2
    review found the handler dispatching into a void; this pins the fix)."""
    import time
    import sqlite3 as sql

    from aios import config
    from aios.api import main as api_main

    monkeypatch.setattr(config, "CORTEX_BUS", True)
    monkeypatch.setattr(config, "CORTEX_BUS_DB", tmp_path / "conformance_bus.db")

    app.dependency_overrides[get_llm_client] = FakeLLM
    app.dependency_overrides[get_ollama_client] = FakeOllama
    app.dependency_overrides[get_executor] = _fake_executor
    app.dependency_overrides[get_semantic_indexer] = lambda: FakeIndexer()
    app.dependency_overrides[get_semantic_facts] = lambda: facts_db
    get_approval_store().clear()
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            # The lifespan must have wired the observer — not a test harness.
            assert api_main._self_model_handler is not None, (
                "lifespan must subscribe SelfModelHandler when CORTEX_BUS is on"
            )
            frames = _turn(client, "make a button")
            assert [e for e, _ in frames][-1] == "done"

            # (a) Only observation types ever landed on the bus.
            with sql.connect(tmp_path / "conformance_bus.db") as conn:
                types = {
                    row[0]
                    for row in conn.execute(
                        "SELECT DISTINCT event_type FROM cortex_events"
                    )
                }
            assert types == {"turn.completed"}, f"unexpected bus events: {types}"

            # (b) The production-wired handler processes it within ~1s: the
            # dispatcher drains on its 250ms heartbeat and the handler either
            # caches a rendering or (with too little verified evidence in this
            # hermetic DB) an honest empty result — either way the EVENT must
            # be consumed, proving the observer is attached.
            deadline = time.monotonic() + 2.0
            bus = api_main._cortex_bus
            assert bus is not None
            while time.monotonic() < deadline and bus.pending_count() > 0:
                time.sleep(0.05)
            assert bus.pending_count() == 0, "the observation was never consumed"
    finally:
        app.dependency_overrides.clear()


def test_operator_preference_lands_quarantined_never_active(
    client: TestClient, facts_db: SemanticFacts
) -> None:
    frames = _turn(client, "I prefer dark mode. Also make a button")
    events = [event for event, _ in frames]
    assert "done" in events, f"turn must complete; streamed: {events}"

    proposals = facts_db.pending_proposals()
    matches = [
        row for row in proposals
        if row["subject"] == "operator" and row["predicate"] == "prefers"
        and row["object"] == "dark mode" and row["status"] == "pending"
    ]
    assert matches, (
        "the narrative organ must propose the operator's preference; "
        f"streamed events: {events}; proposals: {[dict(r) for r in proposals]}"
    )
    # Quarantine: the proposal is NOT active knowledge until a human approves.
    assert facts_db.facts_for("operator") == [], (
        "auto-extraction must NEVER mint active knowledge"
    )
