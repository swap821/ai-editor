"""Domain models for Verified Expert Trajectory Capture."""
from typing import Sequence, Any, Optional

from pydantic import BaseModel, ConfigDict


class ExpertTrajectory(BaseModel):
    """A verified expert trajectory representing a completed mission.
    
    This record explicitly separates the proposal, actions, and verification
    so that raw model output is not blindly merged into trusted learning.
    """
    model_config = ConfigDict(frozen=True)

    problem_signature: str
    project_digest: str
    expert_provider: str
    expert_model: str
    
    context_digest: str
    proposal_digest: str
    
    actions_attempted: int
    failed_attempts: int
    successful_actions: int
    
    tool_observations: Sequence[str]
    
    verification_plan: str
    verification_results: str
    
    promotion_result: str
    rollback_result: Optional[str]
    
    human_interventions: int
    final_outcome: str
