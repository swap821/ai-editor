"""Constitutional Learning Organ contracts (Slice 38).

Feeds Slice 37's amendment pipeline (`aios.domain.governance.amendments`)
rather than duplicating it: a `GovernanceLessonV1` can produce an amendment
*proposal*, never an activated change -- ratification still requires a real
human capability exactly as Slice 37 already enforces.

The one rule every other rule in this module exists to serve: GAGOS may
learn that its own sovereignty mechanisms are weak. It may never decide, by
itself, that the human's authority should be reduced.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

GovernanceEventClass = Literal[
    "security_incident",
    "approval_friction",
    "privacy_denial",
    "rollback_event",
    "hallucinated_authority_attempt",
    "human_correction",
    "routing_failure",
    "leaked_assumption",
    "stale_memory_incident",
    "false_verification",
    "operator_complaint",
    "successful_governance_pattern",
]

#: The 9 adversarial simulations every lesson-originated amendment proposal
#: must pass before it becomes ratification-eligible. The checks themselves
#: (real adversarial testing) are not implemented by this slice -- see
#: `aios.application.governance.constitutional_learning` for the honest
#: scope note; this is the fixed catalog nothing may silently skip.
ADVERSARIAL_SIMULATION_CHECKS: tuple[str, ...] = (
    "authority_escalation",
    "approval_bypass",
    "privacy_widening",
    "capability_replay",
    "emergency_stop_interference",
    "memory_as_truth_confusion",
    "model_self_protection",
    "provider_lock_in",
    "reduced_human_reversibility",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class SimulationCheckResult(BaseModel):
    """One adversarial simulation's outcome for one amendment proposal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    check_name: Literal[
        "authority_escalation",
        "approval_bypass",
        "privacy_widening",
        "capability_replay",
        "emergency_stop_interference",
        "memory_as_truth_confusion",
        "model_self_protection",
        "provider_lock_in",
        "reduced_human_reversibility",
    ]
    passed: bool
    notes: str = ""


class GovernanceLessonV1(BaseModel):
    """One learned observation about a weakness in GAGOS's own governance.

    `status` starts `"proposed"`; `amendment_proposal_id` is populated only
    after `lesson_to_amendment_proposal` produces a real
    `ConstitutionalAmendmentProposalV1` -- a lesson never activates
    anything by itself.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    lesson_id: str = Field(min_length=1, max_length=200)
    problem_class: GovernanceEventClass
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    observed_harm: str = Field(min_length=1)
    current_rule: str = Field(min_length=1)
    proposed_improvement: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    amendment_proposal_id: str | None = None
    status: Literal["proposed", "amendment_drafted", "rejected", "withdrawn"] = (
        "proposed"
    )
    created_at: str = Field(default_factory=_utc_now)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


__all__ = [
    "ADVERSARIAL_SIMULATION_CHECKS",
    "GovernanceEventClass",
    "GovernanceLessonV1",
    "SimulationCheckResult",
]
