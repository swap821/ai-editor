"""Applicability Engine for the Institutional Skill Library."""
from typing import Mapping

from aios.domain.learning.skill_contracts import SkillContract


class ApplicabilityError(RuntimeError):
    """Raised when a skill is deemed inapplicable to the current context."""


class SkillApplicabilityEngine:
    """Validates whether a skill can be safely applied to a specific execution context."""

    def __init__(self, minimum_confidence: float = 0.8) -> None:
        self.minimum_confidence = minimum_confidence

    def check_applicability(self, skill: SkillContract, current_inputs: Mapping[str, str], current_state: Mapping[str, str]) -> bool:
        """Evaluate if the skill is applicable given the current context.
        
        Enforces that semantic similarity alone is never enough to grant applicability.
        
        Raises ApplicabilityError if the skill cannot be safely used.
        """
        # 1. Active status check
        if skill.state != "active":
            raise ApplicabilityError(f"Skill {skill.skill_id} is not active (state: {skill.state})")
            
        # 2. Confidence floor check
        if skill.confidence < self.minimum_confidence:
            raise ApplicabilityError(f"Skill {skill.skill_id} confidence {skill.confidence} is below minimum {self.minimum_confidence}")
            
        # 3. Source trajectory check
        if not skill.source_trajectory_ids:
            raise ApplicabilityError(f"Skill {skill.skill_id} lacks verified source trajectories")
            
        # 4. Required inputs check
        missing_inputs = [req for req in skill.required_inputs if req not in current_inputs]
        if missing_inputs:
            raise ApplicabilityError(f"Missing required inputs for skill {skill.skill_id}: {', '.join(missing_inputs)}")
            
        # 5. Project state check
        for state_key, expected_val in skill.required_project_state.items():
            if current_state.get(state_key) != expected_val:
                raise ApplicabilityError(
                    f"Project state mismatch for {state_key}: expected {expected_val}, got {current_state.get(state_key)}"
                )
                
        # 6. Known exclusions check
        # For this prototype, we check if any exclusion string is present as a key in the inputs
        # (A real implementation might use a more complex rules engine for exclusions)
        for exclusion in skill.known_exclusions:
            if exclusion in current_inputs:
                raise ApplicabilityError(f"Skill {skill.skill_id} hits known exclusion: {exclusion}")
                
        return True
