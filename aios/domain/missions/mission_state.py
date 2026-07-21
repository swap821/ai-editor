from __future__ import annotations

from enum import Enum


class MissionState(str, Enum):
    """Authoritative lifecycle states for a MissionContract v1."""

    DRAFT = "draft"
    DELIBERATING = "deliberating"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    RUNNING = "running"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    ROLLED_BACK = "rolled_back"
    KILLED = "killed"


class MissionTransition(Enum):
    """Allowed, auditable transitions between mission states."""

    START_DELIBERATION = (MissionState.DRAFT, MissionState.DELIBERATING)
    DIRECT_REQUEST_APPROVAL = (MissionState.DRAFT, MissionState.AWAITING_APPROVAL)
    DELIBERATION_BLOCKED = (MissionState.DELIBERATING, MissionState.BLOCKED)
    REQUEST_APPROVAL = (MissionState.DELIBERATING, MissionState.AWAITING_APPROVAL)
    APPROVE = (MissionState.AWAITING_APPROVAL, MissionState.APPROVED)
    REJECT = (MissionState.AWAITING_APPROVAL, MissionState.REJECTED)
    START_EXECUTION = (MissionState.APPROVED, MissionState.RUNNING)
    START_VERIFICATION = (MissionState.RUNNING, MissionState.VERIFYING)
    EXECUTION_FAILED = (MissionState.RUNNING, MissionState.FAILED)
    VERIFICATION_PASSED = (MissionState.VERIFYING, MissionState.COMPLETED)
    VERIFICATION_FAILED = (MissionState.VERIFYING, MissionState.FAILED)
    ROLL_BACK = (MissionState.COMPLETED, MissionState.ROLLED_BACK)
    KILL = (MissionState.RUNNING, MissionState.KILLED)
    ABORT = (MissionState.DELIBERATING, MissionState.FAILED)
    EMERGENCY_KILL_DRAFT = (MissionState.DRAFT, MissionState.KILLED)
    EMERGENCY_KILL_DELIBERATION = (MissionState.DELIBERATING, MissionState.KILLED)
    EMERGENCY_KILL_APPROVAL = (MissionState.AWAITING_APPROVAL, MissionState.KILLED)
    EMERGENCY_KILL_APPROVED = (MissionState.APPROVED, MissionState.KILLED)

    def __init__(self, from_state: MissionState, to_state: MissionState) -> None:
        self.from_state = from_state
        self.to_state = to_state

    @classmethod
    def is_allowed(cls, from_state: MissionState, to_state: MissionState) -> bool:
        return any(
            member.from_state == from_state and member.to_state == to_state
            for member in cls
        )
