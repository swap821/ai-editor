"""Append-only Council deliberation evidence.

CouncilMemory is an adapter over the existing CouncilState store. It records
ganglia synthesis as replayable evidence and never authorizes future work.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from aios import config
from aios.council.council_state import CouncilState
from aios.council.ganglia import GanglionSignal, SignalSynthesis
from aios.runtime.contracts import QueenVerdict


class CouncilMemory:
    """Durable advisory evidence store for Council deliberations."""

    event_type = "ganglia_synthesis"

    def __init__(
        self,
        db_path: str | Path = config.COUNCIL_STATE_DB,
        *,
        state: CouncilState | None = None,
    ) -> None:
        self.state = state or CouncilState(db_path=db_path)

    def record_deliberation(
        self,
        *,
        mission_id: str,
        verdicts: Iterable[QueenVerdict],
        signals: Iterable[GanglionSignal],
        synthesis: SignalSynthesis,
    ) -> int:
        payload = {
            "authority": "proposal/evidence",
            "can_authorize": False,
            "verdicts": [verdict.model_dump() for verdict in verdicts],
            "signals": [signal.model_dump() for signal in signals],
            "synthesis": synthesis.model_dump(),
        }
        return self.state.record_event(
            mission_id,
            event_type=self.event_type,
            payload=payload,
            risk=synthesis.risk,
        )

    def deliberations_for(self, mission_id: str) -> list[dict[str, Any]]:
        return [
            row
            for row in self.state.events_for(mission_id)
            if row["event_type"] == self.event_type
        ]


__all__ = ["CouncilMemory"]
