"""Result and event-stream contract for a coordinated turn."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

from aios.application.turns.turn_context import TurnContext


@dataclass
class TurnResult:
    """Outcome of a single coordinated turn.

    ``events`` is the primary machine-readable product of the turn. Each event
    carries a ``turn_id`` so the caller can correlate streamed deltas with the
    original request without parsing an SSE stream.
    """

    context: TurnContext
    events: AsyncIterator[Any]
    outcome: Optional[dict[str, Any]] = None

    @staticmethod
    def wrap_event(turn_id: str, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        """Return a consistently-shaped event with turn_id attached."""
        return {
            "type": event_type,
            "turn_id": turn_id,
            **data,
        }
