"""Typed event vocabulary shared by backend SSE and the GAGOS cognition bus."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from typing import Any


class EventPhase(str, Enum):
    CHEMOTAXIS = "chemotaxis"
    REFLEX = "reflex"
    EMOTION = "emotion"
    NARRATIVE = "narrative"
    WONDER = "wonder"


class EventType(str, Enum):
    KNOWLEDGE_ACQUIRED = "knowledge-acquired"
    DIRECTIVE = "directive"
    BURST = "burst"
    AGENT_DISPATCH = "agent-dispatch"
    SYNTHESIS = "synthesis"
    APPROVAL_REQUIRED = "approval-required"
    APPROVAL_RESOLVED = "approval-resolved"
    TELEMETRY = "telemetry"
    ROUTE = "route"
    VOICE_SPEAKING = "voice-speaking"
    VERIFY = "verify"


_SSE_TO_COGNITION: dict[str, EventType] = {
    "alignment": EventType.AGENT_DISPATCH,
    "caste_end": EventType.AGENT_DISPATCH,
    "caste_start": EventType.AGENT_DISPATCH,
    "cloud_route": EventType.ROUTE,
    "code": EventType.KNOWLEDGE_ACQUIRED,
    "code_chunk": EventType.KNOWLEDGE_ACQUIRED,
    "done": EventType.SYNTHESIS,
    "earned_autonomy": EventType.KNOWLEDGE_ACQUIRED,
    "error": EventType.SYNTHESIS,
    "human_required": EventType.APPROVAL_REQUIRED,
    "route": EventType.ROUTE,
    "step": EventType.KNOWLEDGE_ACQUIRED,
    "swarm_plan": EventType.AGENT_DISPATCH,
    "text_chunk": EventType.SYNTHESIS,
    "verify_result": EventType.VERIFY,
}

_TYPE_TO_PHASE: dict[EventType, EventPhase] = {
    EventType.KNOWLEDGE_ACQUIRED: EventPhase.WONDER,
    EventType.DIRECTIVE: EventPhase.CHEMOTAXIS,
    EventType.BURST: EventPhase.WONDER,
    EventType.AGENT_DISPATCH: EventPhase.REFLEX,
    EventType.SYNTHESIS: EventPhase.NARRATIVE,
    EventType.APPROVAL_REQUIRED: EventPhase.REFLEX,
    EventType.APPROVAL_RESOLVED: EventPhase.REFLEX,
    EventType.TELEMETRY: EventPhase.CHEMOTAXIS,
    EventType.ROUTE: EventPhase.CHEMOTAXIS,
    EventType.VOICE_SPEAKING: EventPhase.NARRATIVE,
    EventType.VERIFY: EventPhase.REFLEX,
}


@dataclass(frozen=True)
class Event:
    type: EventType
    phase: EventPhase
    turn_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    seq: int = 0

    def to_json(self) -> str:
        return json.dumps(
            {
                "type": self.type.value,
                "phase": self.phase.value,
                "turn_id": self.turn_id,
                "payload": self.payload,
                "timestamp": self.timestamp,
                "seq": self.seq,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, raw: str) -> "Event":
        data = json.loads(raw)
        return cls(
            type=EventType(data["type"]),
            phase=EventPhase(data["phase"]),
            turn_id=str(data["turn_id"]),
            payload=dict(data.get("payload") or {}),
            timestamp=str(data["timestamp"]),
            seq=int(data["seq"]),
        )

    def to_sse_payload(self) -> dict[str, Any]:
        """Return a backward-compatible SSE payload with additive metadata.

        Existing frames may already use ``type`` for their own domain payload
        (notably ``step`` frames). To avoid overwriting that field, the schema's
        cognition type is exposed as ``cognition_type`` while the SSE event name
        remains the existing wire-level discriminator.
        """

        payload = dict(self.payload)
        payload.setdefault("phase", self.phase.value)
        payload.setdefault("seq", self.seq)
        payload.setdefault("turn_id", self.turn_id)
        payload.setdefault("timestamp", self.timestamp)
        payload.setdefault("cognition_type", self.type.value)
        return payload


def event_for_sse(
    event_name: str,
    payload: dict[str, Any],
    *,
    turn_id: str,
    seq: int,
) -> Event:
    event_type = _SSE_TO_COGNITION.get(event_name, EventType.SYNTHESIS)
    return Event(
        type=event_type,
        phase=_TYPE_TO_PHASE[event_type],
        turn_id=turn_id,
        payload=payload,
        seq=seq,
    )
