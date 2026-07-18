"""Domain models for the Institutional Skill Library."""

from typing import Sequence, Literal, Mapping

from pydantic import BaseModel, ConfigDict


SkillState = Literal[
    "candidate",
    "human_reviewed",
    "qualified",
    "active",
    "degraded",
    "superseded",
    "deprecated",
    "blocked",
]


class SkillContract(BaseModel):
    """An evidence-backed, reusable procedure extracted from a verified trajectory."""

    model_config = ConfigDict(frozen=True)

    skill_id: str
    version: int
    problem_signature: str

    # Conditions that must be met to apply this skill
    applicability_conditions: Mapping[str, str]
    known_exclusions: Sequence[str]
    required_inputs: Sequence[str]
    required_project_state: Mapping[str, str]

    # The actual instruction/procedure
    procedure: str
    allowed_tools: Sequence[str]
    allowed_scope_pattern: str
    expected_observations: Sequence[str]

    # Gating and verification
    verification_plan: str
    escalation_conditions: Sequence[str]

    # Provenance and reliability
    source_trajectory_ids: Sequence[str]
    confidence: float
    success_count: int
    failure_count: int
    last_validated_versions: Sequence[str]
    state: SkillState
