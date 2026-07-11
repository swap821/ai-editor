from aios.core.events import Event, EventPhase, EventType, event_for_sse, CanonicalEvent, CanonicalEventType, TrustLevel


def test_event_round_trips_json() -> None:
    event = Event(
        type=EventType.ROUTE,
        phase=EventPhase.CHEMOTAXIS,
        turn_id="turn-1",
        payload={"provider": "ollama"},
        timestamp="2026-07-01T00:00:00+00:00",
        seq=7,
    )

    assert Event.from_json(event.to_json()) == event


def test_sse_payload_adds_metadata_without_overwriting_existing_type() -> None:
    event = event_for_sse(
        "step",
        {"type": "tool_call", "tool": "verify"},
        turn_id="turn-1",
        seq=2,
    )

    payload = event.to_sse_payload()

    assert payload["type"] == "tool_call"
    assert payload["tool"] == "verify"
    assert payload["cognition_type"] == "knowledge-acquired"
    assert payload["phase"] == "wonder"
    assert payload["turn_id"] == "turn-1"
    assert payload["seq"] == 2
    assert "timestamp" in payload


def test_confidence_gate_is_the_emotion_layer_not_reflex() -> None:
    # confidence.gated is uncertainty (emotion), NOT approval (reflex): it must
    # carry its own hesitation type + emotion phase so the body tints purple,
    # not orange. Regression guard for the seam the conformance test caught.
    event = event_for_sse("confidence.gated", {"confidence": 0.4}, turn_id="t", seq=1)
    assert event.type == EventType.HESITATION
    assert event.phase == EventPhase.EMOTION
    assert event.to_sse_payload()["cognition_type"] == "hesitation"


def test_real_human_approval_stays_reflex() -> None:
    # human_required is genuine permission-seeking — it stays reflex, distinct
    # from the emotion-phase confidence gate above.
    event = event_for_sse("human_required", {"text": "approve?"}, turn_id="t", seq=1)
    assert event.type == EventType.APPROVAL_REQUIRED
    assert event.phase == EventPhase.REFLEX


def test_canonical_event_round_trips_json() -> None:
    event = CanonicalEvent(
        event_type=CanonicalEventType.PLAN_CREATED,
        phase="narrative",
        status="success",
        trust=TrustLevel.VERIFIED,
        source="planner",
        session_id="session-1",
        sequence=1,
        turn_id="turn-1",
        payload={"plan": "details"}
    )
    assert CanonicalEvent.from_json(event.to_json()) == event


def test_canonical_event_sse_payload_compatibility() -> None:
    event = CanonicalEvent(
        event_type=CanonicalEventType.ROUTE_SELECTED,
        phase="chemotaxis",
        status="success",
        trust=TrustLevel.VERIFIED,
        source="router",
        session_id="session-1",
        sequence=42,
        turn_id="turn-1",
    )
    
    payload = event.to_sse_payload()
    
    assert payload["schemaVersion"] == "1.0"
    assert payload["eventId"] == event.event_id
    assert payload["seq"] == 42
    assert payload["type"] == CanonicalEventType.ROUTE_SELECTED
    assert payload["eventType"] == CanonicalEventType.ROUTE_SELECTED
    assert payload["timestamp"] == event.occurred_at
    assert payload["source"] == "router"
    assert payload["sessionId"] == "session-1"
    assert payload["turnId"] == "turn-1"
    assert payload["phase"] == "chemotaxis"
    assert payload["status"] == "success"
    assert payload["trust"] == TrustLevel.VERIFIED
    assert payload["payload"] == {}
    assert payload["evidenceRefs"] == []

