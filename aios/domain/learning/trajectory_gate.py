"""Gate for qualifying structured, verifier-backed trajectories."""

from aios.domain.learning.contracts import ExpertTrajectory


class TrajectoryGateError(RuntimeError):
    """Raised when a trajectory fails to meet qualification criteria."""


class TrajectoryGate:
    """Allow learning only from a completed mission with structured proof."""

    def qualify(self, trajectory: ExpertTrajectory) -> bool:
        if not trajectory.trajectory_id:
            raise TrajectoryGateError("Missing trajectory id")
        if not trajectory.mission_id:
            raise TrajectoryGateError("Missing mission id")
        if not trajectory.contract_digest:
            raise TrajectoryGateError("Missing contract digest")
        if not trajectory.project_digest:
            raise TrajectoryGateError("Missing project digest")
        if not trajectory.problem_signature:
            raise TrajectoryGateError("Missing problem signature")
        if not trajectory.proposal_digest:
            raise TrajectoryGateError("Missing proposal digest")
        if not trajectory.context_digest:
            raise TrajectoryGateError("Missing context digest")
        if not trajectory.tool_observations:
            raise TrajectoryGateError("Missing tool observations")
        if trajectory.actions_attempted <= 0:
            raise TrajectoryGateError("No actions recorded")
        if trajectory.successful_actions <= 0:
            raise TrajectoryGateError("No successful actions recorded")
        if trajectory.failed_attempts < 0 or (
            trajectory.successful_actions + trajectory.failed_attempts
            != trajectory.actions_attempted
        ):
            raise TrajectoryGateError("Action counts are inconsistent")

        plan = trajectory.verification_plan
        if not plan.targets or not (
            plan.required_tests or plan.static_checks or plan.security_checks
        ):
            raise TrajectoryGateError("Verification plan is not executable")
        results = tuple(trajectory.verification_results)
        if not results:
            raise TrajectoryGateError("Missing structured verification")
        ids = [result.verification_id for result in results]
        if len(set(ids)) != len(ids):
            raise TrajectoryGateError("Duplicate verification ids")
        if any(result.mission_id != trajectory.mission_id for result in results):
            raise TrajectoryGateError("Verification mission mismatch")
        if any(not result.meets_requirement for result in results):
            raise TrajectoryGateError("Verification requirement not met")
        if trajectory.verification_strength < plan.minimum_strength:
            raise TrajectoryGateError("Verification strength is insufficient")

        if trajectory.promotion_status != "promoted":
            raise TrajectoryGateError("Mission was not promoted")
        if not trajectory.promotion_evidence_ids:
            raise TrajectoryGateError("Missing promotion evidence")
        if trajectory.final_mission_status != "completed":
            raise TrajectoryGateError("Final mission status is not completed")
        if trajectory.final_outcome != "success":
            raise TrajectoryGateError("Final mission outcome is not successful")
        return True
