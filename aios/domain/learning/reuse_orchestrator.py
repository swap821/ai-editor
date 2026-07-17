"""Skill Reuse Orchestrator for R15 Slice 9."""
from typing import Mapping, Sequence, Literal, Union

from pydantic import BaseModel, ConfigDict
from aios.domain.learning.skill_contracts import SkillContract
from aios.domain.learning.applicability import SkillApplicabilityEngine, ApplicabilityError


class LocalExecutionDirective(BaseModel):
    model_config = ConfigDict(frozen=True)
    directive_type: Literal["local_execute"] = "local_execute"
    skill: SkillContract


class EscalateToFrontierDirective(BaseModel):
    model_config = ConfigDict(frozen=True)
    directive_type: Literal["escalate"] = "escalate"
    reason: str


class SkillReuseOrchestrator:
    """Manages the lifecycle of trying to reuse a skill locally before escalating."""

    def __init__(self, applicability_engine: SkillApplicabilityEngine) -> None:
        self.applicability_engine = applicability_engine

    def attempt_reuse(self, candidates: Sequence[SkillContract], current_inputs: Mapping[str, str], current_state: Mapping[str, str]) -> Union[LocalExecutionDirective, EscalateToFrontierDirective]:
        """Attempt to find and validate a skill for local execution.
        
        Returns a LocalExecutionDirective if a skill is successfully validated.
        Returns an EscalateToFrontierDirective if no skill qualifies.
        """
        if not candidates:
            return EscalateToFrontierDirective(reason="No candidate skills provided")

        for skill in candidates:
            try:
                # The engine throws ApplicabilityError if validation fails
                self.applicability_engine.check_applicability(skill, current_inputs, current_state)
                # If we get here, the first matching skill is deemed safe to execute
                return LocalExecutionDirective(skill=skill)
            except ApplicabilityError as e:
                # Log the failure in a real system, but continue checking other candidates
                continue
                
        # If all candidates fail applicability checks, we strictly fail-closed
        return EscalateToFrontierDirective(reason="No candidate skill met applicability conditions")
