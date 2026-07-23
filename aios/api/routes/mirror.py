"""Backend self-portrait endpoints (Phase 2 of Truthful Innervation).

Provides a consolidated snapshot of the organism's current truthful state and a durable
journal replay stream. Fresh boot produces truthful state; reconnect restores state
without duplicate reactions.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional, AsyncGenerator

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from aios.api.main import get_cortex_bus
from aios.runtime.cortex_bus import BusEvent, ConsumerReplayGap, CortexBus
from aios.application.read_models.projection import get_system_projection
from aios.application.read_models.governance_projections import (
    project_constitution,
    project_emergency_stop,
    project_pending_approvals,
    project_provider_health_list,
)
from aios.application.read_models.executor_projections import project_executor_status
from aios.application.read_models.provenance_projections import project_routing_decisions
from aios.application.capabilities.authority import CapabilityAuthority
from aios.application.governance.emergency_stop import EmergencyStopController
from aios.application.identity.service import IdentityService
from aios.application.memory.authority import MemoryAuthority
from aios.application.models.health import ProviderHealthTracker
from aios.api.deps import (
    get_capability_authority,
    get_development_tracker,
    get_emergency_stop,
    get_identity_service,
    get_memory_authority,
    get_private_executor_service,
    get_provider_health,
    get_skill_memory,
)
from aios.domain.governance.constitution import build_constitution_snapshot
from aios.domain.identity.models import PrincipalType
from aios.domain.read_models import MetricEnvelope, MetricStatus
from aios.memory.development import DevelopmentTracker
from aios.memory.skills import SkillMemory

router = APIRouter(prefix="/api/v1/mirror", tags=["Mirror"])
logger = logging.getLogger(__name__)


def _read_development_summary(
    tracker: Optional[DevelopmentTracker], authority: MemoryAuthority
) -> dict[str, Any]:
    if tracker is None:
        return {}
    if authority.owns_store("development", tracker):
        return authority.development_summary()
    return tracker.summary()


def _read_skill_trails(
    skills: Optional[SkillMemory], authority: MemoryAuthority
) -> dict[str, Any]:
    if skills is None:
        return {"trails": []}
    if authority.owns_store("skills", skills):
        return authority.skills_trail_map()
    return skills.trail_map()


@router.get("/snapshot")
def get_snapshot(
    bus: Optional[CortexBus] = Depends(get_cortex_bus),
    tracker: Optional[DevelopmentTracker] = Depends(get_development_tracker),
    skills: Optional[SkillMemory] = Depends(get_skill_memory),
    authority: MemoryAuthority = Depends(get_memory_authority),
) -> JSONResponse:
    """Return the organism's current truthful state (fresh boot state)."""
    if bus is None:
        return JSONResponse(
            content={"status": "offline", "reason": "CORTEX_BUS_DISABLED"}
        )

    pending = bus.pending_count()

    try:
        from aios import __version__

        version = __version__
    except ImportError:
        version = "unknown"

    # A real CortexBus always uses the incremental projection. The fallback
    # below is only for legacy test doubles and older integrations.
    if isinstance(bus, CortexBus):
        projection = get_system_projection(bus.db_path)
        snapshot_required = False
        try:
            projection.process_available(bus)
        except Exception:  # noqa: BLE001 - stale state is surfaced to the client
            snapshot_required = True
        projected = projection.snapshot()
        projected_metrics = dict(projected.metrics)
        projected_metrics["pending_events"] = MetricEnvelope(
            value=pending,
            status=MetricStatus.MEASURED,
            source="cortex_events.pending_count",
            freshness=0,
        )
        tracker_metrics = _read_development_summary(tracker, authority)
        for key in ("verified_success_rate", "average_tool_calls"):
            value = tracker_metrics.get(key)
            projected_metrics[key] = MetricEnvelope(
                value=value,
                status=(
                    MetricStatus.MEASURED
                    if value is not None
                    else MetricStatus.UNAVAILABLE
                ),
                source=(
                    "development_tracker"
                    if value is not None
                    else "development_tracker.unavailable"
                ),
                freshness=0 if value is not None else None,
            )
        trail_data = _read_skill_trails(skills, authority)
        trails = trail_data.get("trails", [])
        return JSONResponse(
            content={
                "status": "online",
                "state": "stale" if snapshot_required else "measured",
                "snapshot_required": snapshot_required,
                "pending_events": pending,
                "phase": projected.phase,
                "active_castes": list(projected.active_castes),
                "active_workers": list(projected.active_workers),
                "active_missions": list(projected.active_missions),
                "last_event_id": projected.last_event_id,
                "metrics": {
                    key: value.model_dump(mode="json")
                    for key, value in projected_metrics.items()
                },
                "knowledge": [],
                "boot_facts": {
                    "version": version,
                    "verified_success_rate": tracker_metrics.get(
                        "verified_success_rate"
                    ),
                    "average_tool_calls": tracker_metrics.get("average_tool_calls"),
                    "trails_total": len(trails),
                    "trails_verified": sum(
                        1 for trail in trails if trail.get("status") == "verified"
                    ),
                    "nodes_count": None,
                    "models_engaged": len(projected.active_models),
                    "models_total": None,
                    "memory_gb": None,
                },
            }
        )

    metrics = _read_development_summary(tracker, authority)
    trail_data = _read_skill_trails(skills, authority)
    trails = trail_data.get("trails", [])
    verified_trails = sum(1 for trail in trails if trail.get("status") == "verified")
    phase = "idle"
    active_castes = set()
    events = bus.fetch_since(0, limit=1000)
    for ev in events:
        et = (
            ev.payload.get("eventType")
            if isinstance(ev.payload, dict) and "eventType" in ev.payload
            else ev.event_type
        )
        nested = ev.payload.get("payload") if isinstance(ev.payload, dict) else None
        event_payload = nested if isinstance(nested, dict) else ev.payload
        role = event_payload.get("role") if isinstance(event_payload, dict) else None
        if et == "worker.started" and role:
            active_castes.add(role)
        elif et in {"worker.dissolved", "worker.completed"} and role:
            active_castes.discard(role)
        elif et == "turn.started":
            phase = "active"
        elif et in {"turn.completed", "turn.failed"}:
            phase = "idle"

    last_event_id = events[-1].id if events else 0

    return JSONResponse(
        content={
            "status": "online",
            "pending_events": pending,
            "phase": phase,
            "active_castes": list(active_castes),
            "last_event_id": last_event_id,
            "knowledge": [],  # Can be populated from recent semantic recall
            "boot_facts": {
                "version": version,
                "verified_success_rate": metrics.get("verified_success_rate", 0),
                "average_tool_calls": metrics.get("average_tool_calls", 0),
                "trails_total": len(trails),
                "trails_verified": verified_trails,
                "nodes_count": None,
                "models_engaged": None,
                "models_total": None,
                "memory_gb": None,
            },
        }
    )


@router.get("/governance")
def get_governance_projection(
    request: Request,
    identity: IdentityService = Depends(get_identity_service),
    emergency_stop: EmergencyStopController = Depends(get_emergency_stop),
    provider_health: ProviderHealthTracker = Depends(get_provider_health),
    capability_authority: CapabilityAuthority = Depends(get_capability_authority),
    development_tracker: DevelopmentTracker = Depends(get_development_tracker),
) -> JSONResponse:
    """Organs 47/48/50 (half): the truthful constitution, emergency-stop,
    provider-health, pending-approvals, and recent-routing-decisions surface.

    Unauthenticated by design, matching /snapshot's own convention -- the
    living mirror reflects state, it never gates on who's watching (risky
    ACTIONS are gated elsewhere). The constitution is honestly UNAVAILABLE
    (never fabricated) unless a real Human Sovereign session is active,
    reusing the exact same per-request build_constitution_snapshot()
    pattern IdentityService._current_constitution_digest() already stamps
    onto every authenticated Principal -- not a new construction, the same
    established one. providerHealth omits any provider with zero recorded
    outcomes entirely (never a fabricated "healthy" placeholder). approvals
    projects CapabilityAuthority.list_pending() -- the real production
    issue/consume authority, not the legacy ApprovalStore -- and never
    exposes a usable bearer token. routingDecisions answers "why was this
    model chosen" for the most recent real turns from development_events'
    already-durable metadata -- it does NOT answer "what was sent / what
    was removed" (the PrivacyFilter audit remains log-only, a separate,
    still-open gap).
    """
    principal = identity.get_authenticated_principal(request.cookies.get("session_id"))
    if principal is not None and principal.principal_type is PrincipalType.OPERATOR:
        snapshot = build_constitution_snapshot(
            ratified_by_operator_id=principal.principal_id
        )
    else:
        snapshot = None
    constitution = project_constitution(snapshot)
    stop_projection = project_emergency_stop(emergency_stop.state())
    provider_health_list = project_provider_health_list(provider_health)
    approvals = project_pending_approvals(capability_authority)
    routing_decisions = project_routing_decisions(development_tracker, limit=10)
    return JSONResponse(
        content={
            "constitution": constitution.model_dump(mode="json"),
            "emergencyStop": stop_projection.model_dump(mode="json"),
            "providerHealth": [p.model_dump(mode="json") for p in provider_health_list],
            "approvals": [a.model_dump(mode="json") for a in approvals],
            "routingDecisions": [r.model_dump(mode="json") for r in routing_decisions],
        }
    )


@router.get("/executor")
def get_executor_status_projection(
    executor_service: Any = Depends(get_private_executor_service),
) -> JSONResponse:
    """Organ 40: the truthful private-executor status surface.

    Unauthenticated by design, matching /snapshot and /governance -- this
    reflects reachability, it never gates on who's watching. Reuses the exact
    same production ExecutorService the real job-execution path uses; a
    configured-but-unreachable service can take up to
    config.EXECUTOR_HTTP_TIMEOUT_S to respond, matching that path's own
    existing bound rather than inventing a second, narrower timeout.
    """
    client = getattr(executor_service, "client", None)
    status = project_executor_status(client)
    return JSONResponse(content={"executor": status.model_dump(mode="json")})


@router.get("/stream")
async def stream_journal(
    request: Request,
    last_event_id_header: Optional[int] = Header(None, alias="Last-Event-ID"),
    last_event_id_query: Optional[int] = Query(None, alias="last_event_id"),
    bus: Optional[CortexBus] = Depends(get_cortex_bus),
) -> StreamingResponse:
    """Stream the durable cortex journal (Last-Event-ID recovery + heartbeat)."""
    if bus is None:
        raise ValueError("CORTEX_BUS must be enabled to stream the journal")

    last_event_id = (
        last_event_id_header
        if last_event_id_header is not None
        else last_event_id_query
    )

    async def _event_generator() -> AsyncGenerator[str, None]:
        queue: asyncio.Queue[BusEvent] = asyncio.Queue(maxsize=256)
        queue_overflowed = asyncio.Event()
        loop = asyncio.get_running_loop()
        replay_issue: dict[str, Any] | None = None
        unsubscribe = lambda: None

        def _on_event(event: BusEvent) -> None:
            # Dispatcher runs in a separate thread, use the captured loop
            def _enqueue() -> None:
                if queue.full():
                    queue_overflowed.set()
                    return
                queue.put_nowait(event)

            loop.call_soon_threadsafe(_enqueue)

        # 1. Recovery: Replay missed events from Last-Event-ID
        if last_event_id is not None:
            try:
                missed_events = bus.fetch_since(last_event_id, limit=1000)
                for ev in missed_events:
                    if queue.full():
                        queue_overflowed.set()
                        break
                    queue.put_nowait(ev)
            except ConsumerReplayGap as exc:
                logger.warning(
                    "mirror_replay_gap",
                    extra={
                        "consumer": exc.consumer_name,
                        "cursor": exc.cursor,
                        "earliest_event_id": exc.earliest_event_id,
                    },
                )
                replay_issue = {
                    "reason": "replay_gap",
                    "cursor": exc.cursor,
                    "earliest_event_id": exc.earliest_event_id,
                }
            except Exception:
                logger.warning("mirror_replay_failed", exc_info=True)
                replay_issue = {"reason": "replay_failed"}

        # 2. Subscription: Listen for live events
        unsubscribe = bus.subscribe(_on_event)

        try:
            if replay_issue is not None:
                yield (
                    "event: snapshot_required\n"
                    f"data: {json.dumps(replay_issue, ensure_ascii=False)}\n\n"
                )

            # 3. Stream loop with heartbeat
            while not await request.is_disconnected():
                if queue_overflowed.is_set():
                    yield 'event: snapshot_required\ndata: {"reason":"slow_client"}\n\n'
                    break
                try:
                    # Wait for next event or heartbeat timeout
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)

                    # Format payload for SSE
                    payload_str = json.dumps(event.payload, ensure_ascii=False)
                    payload_str = payload_str.replace("\r", "\\r").replace("\n", "\\n")

                    yield f"id: {event.id}\n"
                    yield f"data: {payload_str}\n\n"

                    queue.task_done()

                except asyncio.TimeoutError:
                    # Heartbeat pulse to keep connection alive
                    yield ": heartbeat\n\n"
                except Exception:
                    break
        finally:
            unsubscribe()

    return StreamingResponse(_event_generator(), media_type="text/event-stream")
