"""Structured contracts for evidence-backed institutional learning."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from aios.domain.evidence import VerificationPlanV1


class ToolObservation(BaseModel):
    """A bounded tool observation captured from the authoritative mission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    observation_id: str
    tool: str
    result_digest: str
    status: Literal["completed", "failed", "blocked"]


class TrajectoryVerification(BaseModel):
    """The verification facts needed for learning, not verifier prose."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verification_id: str
    mission_id: str
    action_id: str
    passed: bool
    strength: int
    required_strength: int
    evidence_ids: tuple[str, ...]

    @property
    def meets_requirement(self) -> bool:
        return self.passed and self.strength >= self.required_strength


class ExpertTrajectory(BaseModel):
    """An immutable trajectory derived from one completed governed mission."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    trajectory_id: str
    mission_id: str
    contract_digest: str
    problem_signature: str
    project_digest: str
    expert_provider: str
    expert_model: str

    context_digest: str
    proposal_digest: str

    actions_attempted: int
    failed_attempts: int
    successful_actions: int

    tool_observations: tuple[ToolObservation, ...]

    verification_plan: VerificationPlanV1
    verification_results: tuple[TrajectoryVerification, ...]
    verification_strength: int

    promotion_status: Literal["promoted", "rejected", "rolled_back", "failed"]
    promotion_evidence_ids: tuple[str, ...]
    rollback_result: str | None

    human_intervention_ids: tuple[str, ...]
    final_mission_status: str
    final_outcome: str

    @property
    def verification_ids(self) -> tuple[str, ...]:
        return tuple(item.verification_id for item in self.verification_results)


class SkillApplicabilityAdvisoryV1(BaseModel):
    """Canonical Granite local model advisory output contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0"
    skill_id: str
    skill_version: int
    applicable: bool
    confidence: float
    reason_code: str
    reason: str
    bounded_procedure_id: str
    required_inputs_present: bool
    abstain: bool
    escalation_reason: str | None = None
    evidence_reference_ids: tuple[str, ...] = ()


class ReuseOutcomeReference(BaseModel):
    """Authority-derived lineage reference for skill reuse outcomes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reuse_outcome_id: str
    skill_id: str
    skill_version: int
    source_trajectory_id: str
    mission_id: str
    worker_id: str
    executor_job_id: str
    promotion_id: str
    local_job_id: str
    local_model_call_id: str
    verification_ids: tuple[str, ...]
    workspace_digest: str
    diff_digest: str
    project_digest: str
    contract_digest: str
    policy_version: str


__all__ = [
    "ExpertTrajectory",
    "ReuseOutcomeReference",
    "SkillApplicabilityAdvisoryV1",
    "ToolObservation",
    "TrajectoryVerification",
]


