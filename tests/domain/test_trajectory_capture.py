"""Tests for structured verified expert trajectory capture."""

import pytest

from aios.domain.evidence import VerificationPlanV1
from aios.domain.learning.contracts import (
    ExpertTrajectory,
    ToolObservation,
    TrajectoryVerification,
)
from aios.domain.learning.trajectory_gate import TrajectoryGate, TrajectoryGateError


@pytest.fixture
def base_trajectory() -> ExpertTrajectory:
    return ExpertTrajectory(
        trajectory_id="trajectory-001",
        mission_id="mission-001",
        contract_digest="contract-abc",
        problem_signature="sig-123",
        project_digest="hash-abc",
        expert_provider="bedrock",
        expert_model="claude-3-5-sonnet",
        context_digest="ctx-hash",
        proposal_digest="prop-hash",
        actions_attempted=2,
        failed_attempts=0,
        successful_actions=2,
        tool_observations=(
            ToolObservation(
                observation_id="tool-001",
                tool="run_tests",
                result_digest="result-001",
                status="completed",
            ),
            ToolObservation(
                observation_id="tool-002",
                tool="inspect_diff",
                result_digest="result-002",
                status="completed",
            ),
        ),
        verification_plan=VerificationPlanV1(
            intended_behavior="repair is correct",
            targets=("unit-tests",),
            required_tests=("pytest",),
        ),
        verification_results=(
            TrajectoryVerification(
                verification_id="verification-001",
                mission_id="mission-001",
                action_id="action-001",
                passed=True,
                strength=4,
                required_strength=3,
                evidence_ids=("evidence-001",),
            ),
        ),
        verification_strength=4,
        promotion_status="promoted",
        promotion_evidence_ids=("promotion-001",),
        rollback_result=None,
        human_intervention_ids=(),
        final_mission_status="completed",
        final_outcome="success",
    )


def test_trajectory_gate_accepts_valid(base_trajectory: ExpertTrajectory) -> None:
    assert TrajectoryGate().qualify(base_trajectory) is True


def test_trajectory_gate_rejects_missing_verification(
    base_trajectory: ExpertTrajectory,
) -> None:
    trajectory = base_trajectory.model_copy(update={"verification_results": ()})
    with pytest.raises(TrajectoryGateError, match="structured verification"):
        TrajectoryGate().qualify(trajectory)


def test_trajectory_gate_rejects_failed_verification(
    base_trajectory: ExpertTrajectory,
) -> None:
    failed = base_trajectory.verification_results[0].model_copy(
        update={"passed": False}
    )
    trajectory = base_trajectory.model_copy(update={"verification_results": (failed,)})
    with pytest.raises(TrajectoryGateError, match="requirement"):
        TrajectoryGate().qualify(trajectory)


def test_trajectory_gate_rejects_missing_proposal(
    base_trajectory: ExpertTrajectory,
) -> None:
    trajectory = base_trajectory.model_copy(update={"proposal_digest": ""})
    with pytest.raises(TrajectoryGateError, match="proposal digest"):
        TrajectoryGate().qualify(trajectory)


def test_trajectory_gate_rejects_no_actions(
    base_trajectory: ExpertTrajectory,
) -> None:
    trajectory = base_trajectory.model_copy(
        update={"actions_attempted": 0, "successful_actions": 0}
    )
    with pytest.raises(TrajectoryGateError, match="No actions recorded"):
        TrajectoryGate().qualify(trajectory)
