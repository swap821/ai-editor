from aios.core.events import Event, EventPhase, EventType, event_for_sse


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
