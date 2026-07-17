"""Gate for qualifying verified trajectories for skill extraction."""
from typing import Optional

from aios.domain.learning.contracts import ExpertTrajectory


class TrajectoryGateError(RuntimeError):
    """Raised when a trajectory fails to meet qualification criteria."""


class TrajectoryGate:
    """Enforces that only fully verified trajectories are considered for learning."""

    def qualify(self, trajectory: ExpertTrajectory) -> bool:
        """Evaluate if an ExpertTrajectory is eligible for skill extraction.
        
        Rules:
        - The mission contract is known (problem_signature present).
        - The resulting change is known (proposal_digest and actions tracked).
        - Verification is sufficiently strong (verification_results present and passing).
        - Promotion or recovery is known (promotion_result present).
        - Evidence provenance is complete.
        
        Raises TrajectoryGateError if qualification fails.
        """
        if not trajectory.problem_signature:
            raise TrajectoryGateError("Missing problem signature")
            
        if not trajectory.proposal_digest:
            raise TrajectoryGateError("Missing proposal digest")
            
        if trajectory.actions_attempted == 0 and trajectory.successful_actions == 0:
            raise TrajectoryGateError("No actions recorded")
            
        if not trajectory.verification_results:
            raise TrajectoryGateError("Missing verification results")
            
        if "fail" in trajectory.verification_results.lower():
            raise TrajectoryGateError("Trajectory contains failed verification")
            
        if not trajectory.promotion_result:
            raise TrajectoryGateError("Missing promotion result")
            
        if not trajectory.context_digest:
            raise TrajectoryGateError("Missing context digest")
            
        return True
