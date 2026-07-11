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
    get_skill_memory,
)
from aios.memory.db import init_memory_db
from aios.memory.facts import SemanticFacts
from aios.memory.skills import SkillMemory
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
            assert "turn.completed" in types, f"expected 'turn.completed', got: {types}"
            
            authority_prefixes = (
                "skill.", "autonomy.", "approval.", "verdict.", "zone.", "grant.",
            )
            leaked = {t for t in types if t.startswith(authority_prefixes)}
            assert not leaked, (
                f"no authority-family event type may EVER appear on the bus "
                f"(ADR §4.1); leaked: {leaked}"
            )

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


class _NoopCortexBusDispatcher:
    """A stub with the exact start()/stop() surface of CortexBusDispatcher that
    NEVER drains the bus. This deliberately neuters dispatch for CAUSAL
    ISOLATION: production dispatch liveness is already pinned by
    test_bus_carries_only_observations_on_a_real_turn (W2) above. Here, a
    verified skill appearing while every bus observation is still undrained
    is the proof that promotion did not — and structurally cannot — ride the
    bus."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def start(self) -> None:
        pass

    def stop(self, timeout: float = 2.0) -> None:
        pass


class FakeOllamaVerifyStrongPass:
    """Plans ONE verify tool step, then answers. Adapted from
    tests/test_api.py::FakeOllamaVerify. The caller pairs this with its own
    Executor whose runner reports "1 passed" (exit 0) for the planned pytest
    command — a recognized test runner, so derive_strength() classifies the
    pass STRONG (this suite's shared _fake_executor is deliberately NOT used
    here)."""

    def __init__(self) -> None:
        self.calls = 0

    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b"]}

    def chat(self, messages, *, tools=None, model=None) -> dict:
        self.calls += 1
        if self.calls == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "verify", "arguments": {"command": "pytest -q"}}}
                ],
            }
        return {"role": "assistant", "content": "Verified."}


def test_skill_promotion_is_synchronous_and_never_rides_the_bus(
    tmp_path, monkeypatch: pytest.MonkeyPatch, facts_db: SemanticFacts
) -> None:
    """W3 — the wonder-epoch conformance guard for ADR §4.1: authority stays
    synchronous on the verifier's return value; the bus carries observations
    only.

    The dispatcher is deliberately neutered here for CAUSAL ISOLATION
    (production dispatch liveness is pinned by the W2 test above,
    test_bus_carries_only_observations_on_a_real_turn), so a verified skill
    appearing while every observation is still undrained PROVES promotion did
    not ride the bus: it landed synchronously, inside record_outcome, on the
    verifier's own return value — never via a bus handler reacting to
    turn.completed."""
    import sqlite3 as sql

    from aios import config
    from aios.api import main as api_main
    from aios.core.executor import Executor
    from aios.security.gateway import RateLimiter
    from tests.test_api import RecordingAudit

    monkeypatch.setattr(config, "CORTEX_BUS", True)
    monkeypatch.setattr(config, "CORTEX_BUS_DB", tmp_path / "w3_bus.db")

    # Neuter dispatch: the lifespan builds the dispatcher via
    # _build_cortex_dispatcher(bus), which resolves api_main.CortexBusDispatcher
    # at call time. Patching that symbol swaps in a start()/stop() no-op with
    # the identical surface, so the drainer thread never runs.
    monkeypatch.setattr(api_main, "CortexBusDispatcher", _NoopCortexBusDispatcher)

    # Hermetic skills store, PRODUCTION defaults (min_successes=3, rate=0.8).
    skills = SkillMemory(db_path=tmp_path / "w3_skills.db")

    app.dependency_overrides[get_llm_client] = FakeLLM
    app.dependency_overrides[get_ollama_client] = FakeOllamaVerifyStrongPass
    # A recognized test runner ("pytest -q") reporting "1 passed" (exit 0) is
    # genuine STRONG evidence per derive_strength() — the same pattern proven
    # in tests/test_api.py::test_generate_records_verifier_backed_development_and_skill_evidence.
    app.dependency_overrides[get_executor] = lambda: Executor(
        runner=lambda command, *, cwd, env, timeout_s: ("1 passed", "", 0),
        rate_limiter=RateLimiter(),
        audit_log=RecordingAudit(),
    )
    app.dependency_overrides[get_semantic_indexer] = lambda: FakeIndexer()
    app.dependency_overrides[get_semantic_facts] = lambda: facts_db
    app.dependency_overrides[get_skill_memory] = lambda: skills
    get_approval_store().clear()
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            token = get_approval_store().issue(
                "command", {"command": "pytest -q"}, "w3-promotion"
            )
            user_text = "verify the project"
            # SAME user text + SAME token id/session each turn -> the SAME
            # goal/steps trail (signature_v2) reinforces across all 3 attempts.
            for _ in range(3):
                frames = _turn_with_session(client, user_text, "w3-promotion", [token])
                assert [e for e, _ in frames][-1] == "done"
                # Re-issue a fresh token for the next turn (tokens are single-use).
                token = get_approval_store().issue(
                    "command", {"command": "pytest -q"}, "w3-promotion"
                )

            # --- Assert A: the authority outcome landed SYNCHRONOUSLY -------
            with sql.connect(tmp_path / "w3_skills.db") as conn:
                conn.row_factory = sql.Row
                rows = conn.execute(
                    "SELECT status, success_count, verification_strength "
                    "FROM procedural_skills WHERE status != 'superseded'"
                ).fetchall()
            assert len(rows) == 1, (
                f"exactly one non-superseded skill trail must exist for the "
                f"repeated identical turn; got {len(rows)}"
            )
            row = rows[0]
            assert row["status"] == "verified", (
                "3 identical STRONG successes must promote the skill to "
                f"'verified' synchronously; got status={row['status']!r}"
            )
            assert row["success_count"] == 3, (
                f"all 3 attempts must be promotion-eligible; got "
                f"success_count={row['success_count']}"
            )
            assert row["verification_strength"] == "STRONG", (
                f"the recorded strength must be the forced auto-verify's "
                f"STRONG pass; got {row['verification_strength']!r}"
            )

            # --- Assert B: the bus is STILL fully undrained ------------------
            bus = api_main._cortex_bus
            assert bus is not None, "CORTEX_BUS=True must construct a live bus"
            assert bus.pending_count() >= 3, (
                "dispatch was neutered, so observations "
                f"must still be UNDRAINED; got pending_count={bus.pending_count()} "
                "(promotion could not have come from the bus, because the bus "
                "never ran)"
            )

            # --- Assert C: the outbox carries ONLY observations ---------------
            with sql.connect(tmp_path / "w3_bus.db") as conn:
                types = {
                    row[0]
                    for row in conn.execute("SELECT DISTINCT event_type FROM cortex_events")
                }
            assert "turn.completed" in types, (
                f"the outbox must carry the 'turn.completed' observation "
                f"type; got {types}"
            )
            authority_prefixes = (
                "skill.", "autonomy.", "approval.", "verdict.", "zone.", "grant.",
            )
            leaked = {t for t in types if t.startswith(authority_prefixes)}
            assert not leaked, (
                f"no authority-family event type may EVER appear on the bus "
                f"(ADR §4.1); leaked: {leaked}"
            )
    finally:
        app.dependency_overrides.clear()


def _turn_with_session(
    client: TestClient, text: str, session_id: str, approval_tokens: list[str]
) -> list[tuple[str, dict]]:
    """Like _turn(), but carries a session id + approval tokens so an
    approval-gated command tool can execute (needed to drive workflow_steps
    non-empty, which is what makes record_outcome call skills.record_attempt)."""
    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": text}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": session_id,
            "approvalTokens": approval_tokens,
        },
    )
    assert response.status_code == 200
    return _frames(response.text)
