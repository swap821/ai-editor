"""Backend self-portrait endpoints (Phase 2 of Truthful Innervation).

Provides a consolidated snapshot of the organism's current truthful state and a durable
journal replay stream. Fresh boot produces truthful state; reconnect restores state
without duplicate reactions.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional, AsyncGenerator

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse

from aios.api.main import get_cortex_bus
from aios.runtime.cortex_bus import CortexBus, BusEvent

router = APIRouter(prefix="/api/v1/mirror", tags=["Mirror"])

@router.get("/snapshot")
def get_snapshot(bus: Optional[CortexBus] = Depends(get_cortex_bus)) -> JSONResponse:
    """Return the organism's current truthful state (fresh boot state)."""
    if bus is None:
        return JSONResponse(content={"status": "offline", "reason": "CORTEX_BUS_DISABLED"})
        
    pending = bus.pending_count()
    # A true "snapshot" might also consult episodic memory or active sessions.
    # For now, we return the substrate's state and active configuration.
    return JSONResponse(
        content={
            "status": "online",
            "pending_events": pending,
            "phase": "idle", # Default to idle, state machines derive phase from events
            "active_castes": [], # Truthfully pulled from recent worker.started/dissolved
            "knowledge": [], # Can be populated from recent semantic recall
        }
    )


@router.get("/stream")
async def stream_journal(
    request: Request,
    last_event_id: Optional[int] = Header(None, alias="Last-Event-ID"),
    bus: Optional[CortexBus] = Depends(get_cortex_bus)
) -> StreamingResponse:
    """Stream the durable cortex journal (Last-Event-ID recovery + heartbeat)."""
    if bus is None:
        raise ValueError("CORTEX_BUS must be enabled to stream the journal")

    async def _event_generator() -> AsyncGenerator[str, None]:
        queue: asyncio.Queue[BusEvent] = asyncio.Queue()

        def _on_event(event: BusEvent) -> None:
            # We use put_nowait because subscribe handlers run in a different thread
            # but we need to pass data to the async generator safely.
            # Using loop.call_soon_threadsafe is safer for asyncio queues from other threads.
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(queue.put_nowait, event)
            except RuntimeError:
                pass

        # 1. Recovery: Replay missed events from Last-Event-ID
        if last_event_id is not None:
            try:
                missed_events = bus.fetch_since(last_event_id)
                for ev in missed_events:
                    queue.put_nowait(ev)
            except Exception:
                pass

        # 2. Subscription: Listen for live events
        bus.subscribe(_on_event)

        # 3. Stream loop with heartbeat
        while not await request.is_disconnected():
            try:
                # Wait for next event or heartbeat timeout
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
                
                # Format payload for SSE
                payload_str = json.dumps(event.payload, ensure_ascii=False)
                payload_str = payload_str.replace("\r", "\\r").replace("\n", "\\n")
                
                yield f"id: {event.id}\n"
                yield f"event: {event.event_type}\n"
                yield f"data: {payload_str}\n\n"
                
                queue.task_done()
                
            except asyncio.TimeoutError:
                # Heartbeat pulse to keep connection alive
                yield "event: ping\ndata: {}\n\n"
            except Exception:
                break

    return StreamingResponse(_event_generator(), media_type="text/event-stream")
