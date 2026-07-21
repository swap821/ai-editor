"""Mission execution transition journal (Slice 35).

Complements `aios.domain.missions.mission_state.MissionState` (the coarse
DRAFT -> ... -> COMPLETED lifecycle) rather than replacing it: this is the
finer-grained journal for the execution/promotion pipeline sub-states the
coarse state machine doesn't track at all (a mission can sit in `RUNNING`
for the entire staged-workspace -> executor -> verification ->
checkpoint -> promotion sequence with no durable record of which of those
sub-steps actually completed before a crash).

Every transition is idempotent: re-appending the mission's current
transition is a no-op, not a duplicate row or an error -- a retried
recovery step after a crash must be safe to run twice.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: The linear happy-path order. Index is the sequence number a journal
#: entry is stamped with, so "current state" is just "highest sequence
#: recorded for this mission".
MISSION_TRANSITION_ORDER: tuple[str, ...] = (
    "MISSION_CREATED",
    "APPROVED",
    "WORKSPACE_CREATED",
    "EXECUTION_SUBMITTED",
    "EXECUTION_COMPLETED",
    "VERIFIED",
    "CHECKPOINT_CREATED",
    "PROMOTION_STARTED",
    "PROMOTED",
    "POST_PROMOTION_VERIFIED",
    "COMPLETED",
)

#: Escape states reachable from any non-terminal linear state -- a failure
#: or rollback can happen at any point in the sequence, not just at the end.
MISSION_TRANSITION_ESCAPES: tuple[str, ...] = ("FAILED", "ROLLED_BACK")

MISSION_TRANSITION_TERMINAL: frozenset[str] = frozenset(
    {"COMPLETED", "FAILED", "ROLLED_BACK"}
)

MissionTransitionName = Literal[
    "MISSION_CREATED",
    "APPROVED",
    "WORKSPACE_CREATED",
    "EXECUTION_SUBMITTED",
    "EXECUTION_COMPLETED",
    "VERIFIED",
    "CHECKPOINT_CREATED",
    "PROMOTION_STARTED",
    "PROMOTED",
    "POST_PROMOTION_VERIFIED",
    "COMPLETED",
    "FAILED",
    "ROLLED_BACK",
]


class MissionTransitionEntry(BaseModel):
    """One durable, ordered journal entry for one mission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mission_id: str = Field(min_length=1, max_length=200)
    transition: MissionTransitionName
    sequence: int = Field(ge=0)
    recorded_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
    )


__all__ = [
    "MISSION_TRANSITION_ESCAPES",
    "MISSION_TRANSITION_ORDER",
    "MISSION_TRANSITION_TERMINAL",
    "MissionTransitionEntry",
    "MissionTransitionName",
]
