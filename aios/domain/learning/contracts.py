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
