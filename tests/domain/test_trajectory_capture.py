"""Tests for Verified Expert Trajectory Capture."""
import pytest
from aios.domain.learning.contracts import ExpertTrajectory
from aios.domain.learning.trajectory_gate import TrajectoryGate, TrajectoryGateError

@pytest.fixture
def base_trajectory():
    return ExpertTrajectory(
        problem_signature="sig-123",
        project_digest="hash-abc",
        expert_provider="bedrock",
        expert_model="claude-3-5-sonnet",
        context_digest="ctx-hash",
        proposal_digest="prop-hash",
        actions_attempted=2,
        failed_attempts=0,
        successful_actions=2,
        tool_observations=["test run passed"],
        verification_plan="run tests",
        verification_results="pass",
        promotion_result="merged",
        rollback_result=None,
        human_interventions=0,
        final_outcome="success"
    )

def test_trajectory_gate_accepts_valid(base_trajectory):
    gate = TrajectoryGate()
    assert gate.qualify(base_trajectory) is True

def test_trajectory_gate_rejects_missing_verification(base_trajectory):
    traj = base_trajectory.model_copy(update={"verification_results": ""})
    gate = TrajectoryGate()
    with pytest.raises(TrajectoryGateError, match="Missing verification results"):
        gate.qualify(traj)

def test_trajectory_gate_rejects_failed_verification(base_trajectory):
    traj = base_trajectory.model_copy(update={"verification_results": "tests failed on line 42"})
    gate = TrajectoryGate()
    with pytest.raises(TrajectoryGateError, match="Trajectory contains failed verification"):
        gate.qualify(traj)

def test_trajectory_gate_rejects_missing_proposal(base_trajectory):
    traj = base_trajectory.model_copy(update={"proposal_digest": ""})
    gate = TrajectoryGate()
    with pytest.raises(TrajectoryGateError, match="Missing proposal digest"):
        gate.qualify(traj)

def test_trajectory_gate_rejects_no_actions(base_trajectory):
    traj = base_trajectory.model_copy(update={"actions_attempted": 0, "successful_actions": 0})
    gate = TrajectoryGate()
    with pytest.raises(TrajectoryGateError, match="No actions recorded"):
        gate.qualify(traj)
