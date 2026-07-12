"""Typed event vocabulary shared by backend SSE and the GAGOS cognition bus."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from typing import Any, Optional
import uuid


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
    HESITATION = "hesitation"


_SSE_TO_COGNITION: dict[str, EventType] = {
    "alignment": EventType.AGENT_DISPATCH,
    "caste_end": EventType.AGENT_DISPATCH,
    "caste_start": EventType.AGENT_DISPATCH,
    # Cerebellum (sovereignty engine S1) — compiled experience replay.
    # Match and step events use AGENT_DISPATCH (reflex phase — orange).
    # Done uses SYNTHESIS (narrative phase — green settle).
    # Abort uses HESITATION (emotion phase — the replay couldn't complete).
    "cerebellum_match": EventType.AGENT_DISPATCH,
    "cerebellum_step": EventType.AGENT_DISPATCH,
    "cerebellum_step_done": EventType.KNOWLEDGE_ACQUIRED,
    "cerebellum_done": EventType.SYNTHESIS,
    "cerebellum_abort": EventType.HESITATION,
    # Sovereignty S2: Knowledge graph — associative recall events.
    "graph_inference": EventType.KNOWLEDGE_ACQUIRED,
    "graph_horizon": EventType.HESITATION,
    # Sovereignty S3: Native planner — template-based plan from verified experience.
    "native_plan": EventType.AGENT_DISPATCH,
    "cloud_route": EventType.ROUTE,
    # Confidence gating is the EMOTION layer (uncertainty/hesitation), NOT
    # reflex approval — it shares no permission token with human_required.
    # Its own type keeps its phase emotion, so the body tints purple (weather),
    # not orange (reflex), when the mind pauses unsure. (The organism
    # conformance test caught this sharing APPROVAL_REQUIRED's reflex phase.)
    "confidence.gated": EventType.HESITATION,
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
    EventType.HESITATION: EventPhase.EMOTION,
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


class TrustLevel(str, Enum):
    VERIFIED = "verified"
    ADVISORY = "advisory"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class CanonicalEventType(str, Enum):
    ALIGNMENT_DECLARED = "alignment.declared"
    PLAN_CREATED = "plan.created"
    ROUTE_SELECTED = "route.selected"
    APPROVAL_REQUIRED = "approval.required"
    APPROVAL_DECIDED = "approval.decided"
    TOOL_LIFECYCLE_CHANGED = "tool.lifecycle.changed"
    VERIFICATION_COMPLETED = "verification.completed"
    WORKER_STARTED = "worker.started"
    WORKER_COMPLETED = "worker.completed"
    WORKER_DISSOLVED = "worker.dissolved"
    AUTONOMY_GRANT_CHANGED = "autonomy.grant.changed"
    LEARNING_SKILL_MASTERED = "learning.skill.mastered"
    TURN_COMPLETED = "turn.completed"
    TURN_FAILED = "turn.failed"
    FACTS_PROPOSED = "facts.proposed"
    EDIT_PROPOSED = "edit.proposed"
    EDIT_BLOCKED = "edit.blocked"
    MEMORY_RECALLED = "memory.recalled"
    MEMORY_TRUSTED_WORKFLOW_APPLIED = "memory.trusted_workflow_applied"
    TELEMETRY_AGENT_STARTED = "telemetry.agent_started"


@dataclass(frozen=True)
class CanonicalEvent:
    event_type: str
    phase: str
    status: str
    trust: str
    source: str
    session_id: str
    schema_version: str = "1.0"
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sequence: int = 0
    occurred_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    turn_id: Optional[str] = None
    mission_id: Optional[str] = None
    worker_id: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.event_type:
            raise ValueError("event_type is required")
        if not self.phase:
            raise ValueError("phase is required")
        if not self.status:
            raise ValueError("status is required")
        if not self.trust:
            raise ValueError("trust is required")
        if not self.source:
            raise ValueError("source is required")
        if not self.session_id:
            raise ValueError("session_id is required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "eventId": self.event_id,
            "sequence": self.sequence,
            "eventType": self.event_type,
            "occurredAt": self.occurred_at,
            "source": self.source,
            "sessionId": self.session_id,
            "turnId": self.turn_id,
            "missionId": self.mission_id,
            "workerId": self.worker_id,
            "phase": self.phase,
            "status": self.status,
            "trust": self.trust,
            "payload": self.payload,
            "evidenceRefs": self.evidence_refs,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> "CanonicalEvent":
        data = json.loads(raw)
        return cls(
            schema_version=data.get("schemaVersion", "1.0"),
            event_id=data.get("eventId", str(uuid.uuid4())),
            sequence=int(data.get("sequence", 0)),
            event_type=str(data["eventType"]),
            occurred_at=str(data.get("occurredAt", datetime.now(timezone.utc).isoformat())),
            source=str(data["source"]),
            session_id=str(data["sessionId"]),
            turn_id=data.get("turnId"),
            mission_id=data.get("missionId"),
            worker_id=data.get("workerId"),
            phase=str(data["phase"]),
            status=str(data["status"]),
            trust=str(data["trust"]),
            payload=data.get("payload") or {},
            evidence_refs=data.get("evidenceRefs") or [],
        )

    def to_sse_payload(self) -> dict[str, Any]:
        """Backward compatibility for existing UI while we bridge buses."""
        # The frontend expects a certain shape. We'll map CanonicalEvent to the old expected payload
        # structure for intermediate compatibility if needed.
        return {
            "schemaVersion": self.schema_version,
            "eventId": self.event_id,
            "seq": self.sequence,
            "type": self.event_type, # Using 'type' for older SSE listeners if they look here
            "eventType": self.event_type,
            "timestamp": self.occurred_at,
            "source": self.source,
            "sessionId": self.session_id,
            "turnId": self.turn_id,
            "missionId": self.mission_id,
            "workerId": self.worker_id,
            "phase": self.phase,
            "status": self.status,
            "trust": self.trust,
            "payload": self.payload,
            "evidenceRefs": self.evidence_refs,
        }

