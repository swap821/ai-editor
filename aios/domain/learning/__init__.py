"""Learning boundary domain for GAGOS."""
from aios.domain.learning.contracts import ExpertTrajectory
from aios.domain.learning.trajectory_gate import TrajectoryGate, TrajectoryGateError

__all__ = [
    "ExpertTrajectory",
    "TrajectoryGate",
    "TrajectoryGateError",
]
