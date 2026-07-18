"""Fail-closed applicability checks for institutional skills."""

from __future__ import annotations

from fnmatch import fnmatch
from typing import Mapping, Sequence

from aios.domain.learning.skill_contracts import SkillContract


class ApplicabilityError(RuntimeError):
    """Raised when a skill cannot be safely used for the current mission."""


class SkillApplicabilityEngine:
    """Validate explicit state, scope, tool, version and policy evidence."""

    def __init__(self, minimum_confidence: float = 0.8) -> None:
        self.minimum_confidence = minimum_confidence

    def check_applicability(
        self,
        skill: SkillContract,
        current_inputs: Mapping[str, str],
        current_state: Mapping[str, str],
        *,
        current_scope: str | None = None,
        mission_allowed_tools: Sequence[str] | None = None,
        validated_version: str | None = None,
        verification_plan_executable: bool = False,
        policy_allows: bool = False,
    ) -> bool:
        """Return true only when all deterministic reuse gates pass."""
        if skill.state != "active":
            raise ApplicabilityError(
                f"Skill {skill.skill_id} is not active (state: {skill.state})"
            )
        if skill.confidence < self.minimum_confidence:
            raise ApplicabilityError(
                f"Skill {skill.skill_id} confidence {skill.confidence} is below minimum {self.minimum_confidence}"
            )
        if not skill.source_trajectory_ids:
            raise ApplicabilityError(
                f"Skill {skill.skill_id} lacks verified source trajectories"
            )
        missing_inputs = [
            required
            for required in skill.required_inputs
            if required not in current_inputs
        ]
        if missing_inputs:
            raise ApplicabilityError(
                f"Missing required inputs for skill {skill.skill_id}: {', '.join(missing_inputs)}"
            )
        for key, expected in skill.applicability_conditions.items():
            if current_inputs.get(key) != expected:
                raise ApplicabilityError(
                    f"Applicability condition mismatch for {key}: expected {expected}, got {current_inputs.get(key)}"
                )
        for key, expected in skill.required_project_state.items():
            if current_state.get(key) != expected:
                raise ApplicabilityError(
                    f"Project state mismatch for {key}: expected {expected}, got {current_state.get(key)}"
                )
        for exclusion in skill.known_exclusions:
            if exclusion in current_inputs:
                raise ApplicabilityError(
                    f"Skill {skill.skill_id} hits known exclusion: {exclusion}"
                )
        if not current_scope or not fnmatch(current_scope, skill.allowed_scope_pattern):
            raise ApplicabilityError(
                f"Skill {skill.skill_id} scope does not match allowed pattern"
            )
        if mission_allowed_tools is None:
            raise ApplicabilityError("Mission tool contract is missing")
        allowed = set(mission_allowed_tools)
        if not set(skill.allowed_tools).issubset(allowed):
            raise ApplicabilityError("Skill tools exceed the mission contract")
        if (
            not validated_version
            or validated_version not in skill.last_validated_versions
        ):
            raise ApplicabilityError(
                "Validated project version does not match the skill"
            )
        if not verification_plan_executable:
            raise ApplicabilityError("Skill verification plan is not executable")
        if not policy_allows:
            raise ApplicabilityError("Policy does not allow skill reuse")
        return True
