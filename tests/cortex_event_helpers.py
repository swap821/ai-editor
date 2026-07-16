"""Test-only constructors for the canonical Cortex observation envelope."""

from __future__ import annotations

from typing import Any

from aios.core.events import CanonicalEvent, EventPhase, TrustLevel
from aios.runtime.cortex_bus import CortexBus


def append_event(
    bus: CortexBus,
    event_type: str,
    signature: str,
    payload: dict[str, Any],
) -> int:
    return bus.append(
        CanonicalEvent(
            event_type=event_type,
            phase=EventPhase.NARRATIVE.value,
            status="observed",
            trust=TrustLevel.ADVISORY.value,
            source="tests.cortex_event_helpers",
            session_id=signature,
            payload=payload,
        )
    )
