"""Learning boundary domain for GAGOS."""
from aios.domain.learning.contracts import ExpertTrajectory
from aios.domain.learning.trajectory_gate import TrajectoryGate, TrajectoryGateError
from aios.domain.learning.skill_contracts import SkillContract, SkillState
from aios.domain.learning.applicability import SkillApplicabilityEngine, ApplicabilityError
from aios.domain.learning.confidence import ConfidenceUpdater
from aios.domain.learning.reuse_orchestrator import SkillReuseOrchestrator, LocalExecutionDirective, EscalateToFrontierDirective

__all__ = [
    "ExpertTrajectory",
    "TrajectoryGate",
    "TrajectoryGateError",
    "SkillContract",
    "SkillState",
    "SkillApplicabilityEngine",
    "ApplicabilityError",
    "ConfidenceUpdater",
    "SkillReuseOrchestrator",
    "LocalExecutionDirective",
    "EscalateToFrontierDirective",
]
