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
from aios.runtime.cortex_bus import (
    BusEvent,
    ConsumerReplayGap,
    CortexBus,
    ReplayWindowTooLarge,
)
from aios.application.read_models.projection import get_system_projection
from aios.application.read_models.governance_projections import (
    ReadModelProjectionAuthority,
    project_constitution,
    project_emergency_stop,
    project_pending_approvals,
    project_provider_health_list,
)
from aios.application.read_models.executor_projections import (
    get_isolated_executor_live_authority,
)
from aios.application.read_models.provenance_projections import (
    project_privacy_audits,
    project_routing_decisions,
)
from aios.application.capabilities.authority import CapabilityAuthority
from aios.application.governance.emergency_stop import EmergencyStopController
from aios.application.identity.service import IdentityService
from aios.application.memory.authority import MemoryAuthority
from aios.application.models.health import ProviderHealthTracker
from aios.application.models.privacy_audit import PrivacyAuditTracker
from aios.api.deps import (
    get_capability_authority,
    get_constitution_authority,
    get_development_tracker,
    get_emergency_stop,
    get_identity_service,
    get_memory_authority,
    get_privacy_audit_tracker,
    get_private_executor_service,
    get_provider_health,
    get_skill_memory,
)
from aios.application.governance.constitution_authority import (
    ConstitutionAuthority,
    NoEnrolledSovereignError,
)
from aios.domain.identity.models import PrincipalType
from aios.domain.read_models import MetricEnvelope, MetricStatus


_READ_MODEL_PROJECTION_AUTHORITY = ReadModelProjectionAuthority()
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
    """Return truthful operational state for the authenticated mirror client.

    The HTTP edge performs the bonded-operator/API-token check before this
    dependency is reached; an unbonded loopback process is not a viewer.
    """
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
    verified_success_rate = metrics.get("verified_success_rate")
    average_tool_calls = metrics.get("average_tool_calls")
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
                "verified_success_rate": verified_success_rate,
                "average_tool_calls": average_tool_calls,
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
    privacy_audit_tracker: PrivacyAuditTracker = Depends(get_privacy_audit_tracker),
) -> JSONResponse:
    """Organs 47/48/50: the truthful constitution, emergency-stop,
    provider-health, pending-approvals, routing-decision, and privacy-audit
    surface.

    Unauthenticated by design, matching /snapshot's own convention -- the
    living mirror reflects state, it never gates on who's watching (risky
    ACTIONS are gated elsewhere). The constitution is honestly UNAVAILABLE
    (never fabricated) unless a real Human Sovereign session is active, and
    now reads the DURABLE chain via ConstitutionAuthority (organ 25) -- the
    same single authority that stamps every Principal and gates capability
    consumption. It previously rebuilt a snapshot from live config per
    request, which meant this panel showed version 1 forever and never
    reflected a ratified amendment. providerHealth omits any provider with zero recorded
    outcomes entirely (never a fabricated "healthy" placeholder). approvals
    projects CapabilityAuthority.list_pending() -- the real production
    issue/consume authority, not the legacy ApprovalStore -- and never
    exposes a usable bearer token. routingDecisions answers "why was this
    model chosen" for the most recent real turns from development_events'
    already-durable metadata. privacyAudits answers "what was sent / what
    was removed" from PrivacyAuditTracker's real per-call redaction audits,
    captured at all 5 real PrivacyFilter.filter() call sites -- closing
    organ 50's full two-part claim.
    """
    principal = identity.get_authenticated_principal(request.cookies.get("session_id"))
    snapshot = None
    if principal is not None and principal.principal_type is PrincipalType.OPERATOR:
        try:
            # The authority that stamped this principal, not the process
            # singleton -- checking a principal against an identity store that
            # never enrolled it reads as "operator identity changed".
            snapshot = identity.constitution_authority.get_active_snapshot(
                principal.principal_id
            )
        except NoEnrolledSovereignError:
            # Honestly UNAVAILABLE, matching the unauthenticated branch. A
            # ConstitutionDegraded is deliberately NOT caught: a store that is
            # unreadable or tampered is a real 503, not an empty panel.
            snapshot = None
    surface = _READ_MODEL_PROJECTION_AUTHORITY.build_governance_surface(
        constitution=snapshot,
        emergency_stop=emergency_stop,
        provider_health=provider_health,
        capability_authority=capability_authority,
        development_tracker=development_tracker,
        privacy_audit_tracker=privacy_audit_tracker,
    )
    return JSONResponse(
        content={
            key: (
                value.model_dump(mode="json")
                if hasattr(value, "model_dump")
                else [item.model_dump(mode="json") for item in value]
            )
            for key, value in surface.items()
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
    status = get_isolated_executor_live_authority().project(client)
    return JSONResponse(content={"executor": status.model_dump(mode="json")})


@router.get("/stream")
async def stream_journal(
    request: Request,
    last_event_id_header: Optional[int] = Header(None, alias="Last-Event-ID"),
    last_event_id_query: Optional[int] = Query(None, alias="last_event_id"),
    bus: Optional[CortexBus] = Depends(get_cortex_bus),
) -> StreamingResponse:
    """Stream an authenticated, barriered durable cortex journal.

    The edge middleware requires a bonded operator session (or the configured
    API token) before this route can expose operational state.  A real
    ``CortexBus`` establishes its replay window and live handler atomically;
    ``sync_complete`` is the only frame that lets the client promote a
    snapshot to continuously fresh.
    """
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
        replay_events: list[BusEvent] = []
        barrier_event_id: int | None = None
        barrier_supported = False

        def _on_event(event: BusEvent) -> None:
            # Dispatcher runs in a separate thread, use the captured loop
            def _enqueue() -> None:
                if queue.full():
                    queue_overflowed.set()
                    return
                queue.put_nowait(event)

            loop.call_soon_threadsafe(_enqueue)

        # 1. Recovery + live handoff.  Production CortexBus performs both
        # under one delivery lock.  The fallback keeps older test doubles and
        # integrations readable, but is deliberately not allowed to claim a
        # sync barrier that they do not implement.
        if isinstance(bus, CortexBus):
            try:
                subscription = bus.subscribe_replay(
                    last_event_id or 0,
                    _on_event,
                    limit=1000,
                )
                unsubscribe = subscription.unsubscribe
                replay_events = list(subscription.events)
                barrier_event_id = subscription.barrier_event_id
                barrier_supported = True
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
            except ReplayWindowTooLarge as exc:
                logger.warning(
                    "mirror_replay_too_large",
                    extra={
                        "cursor": exc.cursor,
                        "limit": exc.limit,
                        "latest_event_id": exc.latest_event_id,
                    },
                )
                replay_issue = {
                    "reason": "replay_too_large",
                    "cursor": exc.cursor,
                    "limit": exc.limit,
                    "latest_event_id": exc.latest_event_id,
                }
            except Exception:
                logger.warning("mirror_replay_failed", exc_info=True)
                replay_issue = {"reason": "replay_failed"}
        else:
            if last_event_id is not None:
                try:
                    replay_events = bus.fetch_since(last_event_id, limit=1000)
                except ConsumerReplayGap as exc:
                    replay_issue = {
                        "reason": "replay_gap",
                        "cursor": exc.cursor,
                        "earliest_event_id": exc.earliest_event_id,
                    }
                except Exception:
                    logger.warning("mirror_replay_failed", exc_info=True)
                    replay_issue = {"reason": "replay_failed"}
            unsubscribe = bus.subscribe(_on_event)

        try:
            if replay_issue is not None:
                yield (
                    "event: snapshot_required\n"
                    f"data: {json.dumps(replay_issue, ensure_ascii=False)}\n\n"
                )
                return

            def _format_event(event: BusEvent) -> str:
                payload_str = json.dumps(event.payload, ensure_ascii=False)
                payload_str = payload_str.replace("\r", "\\r").replace("\n", "\\n")
                return f"id: {event.id}\ndata: {payload_str}\n\n"

            # Replay is emitted before the barrier.  A duplicate already
            # queued by at-least-once dispatch is harmless and is suppressed
            # below by the durable cursor.
            sent_event_id = last_event_id if barrier_supported and last_event_id is not None else -1
            for event in replay_events:
                if barrier_supported and event.id <= sent_event_id:
                    continue
                yield _format_event(event)
                sent_event_id = max(sent_event_id, event.id)

            if barrier_supported:
                if barrier_event_id is None:
                    yield 'event: snapshot_required\ndata: {"reason":"barrier_missing"}\n\n'
                    return
                if sent_event_id < barrier_event_id:
                    yield 'event: snapshot_required\ndata: {"reason":"replay_incomplete"}\n\n'
                    return
                yield (
                    "event: sync_complete\n"
                    f"data: {json.dumps({'cursor': barrier_event_id, 'replayed': last_event_id is not None})}\n\n"
                )
                sent_event_id = barrier_event_id

            # 3. Stream loop with heartbeat
            while not await request.is_disconnected():
                if queue_overflowed.is_set():
                    yield 'event: snapshot_required\ndata: {"reason":"slow_client"}\n\n'
                    break
                try:
                    # Wait for next event or heartbeat timeout
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)

                    if barrier_supported and event.id <= sent_event_id:
                        queue.task_done()
                        continue
                    if barrier_supported and event.id > sent_event_id + 1:
                        yield 'event: snapshot_required\ndata: {"reason":"live_gap"}\n\n'
                        queue.task_done()
                        break

                    yield _format_event(event)
                    sent_event_id = max(sent_event_id, event.id)

                    queue.task_done()

                except asyncio.TimeoutError:
                    # Heartbeat pulse to keep connection alive
                    yield ": heartbeat\n\n"
                except Exception:
                    break
        finally:
            unsubscribe()

    return StreamingResponse(_event_generator(), media_type="text/event-stream")
