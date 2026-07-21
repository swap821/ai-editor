"""Application services for verifier-backed institutional learning."""

from aios.application.learning.service import (
    LearningService,
    SkillActivationDenied,
    SkillCandidateSpec,
)
from aios.application.learning.skill_lifecycle import (
    DEMOTION_CONFIDENCE_FLOOR,
    MIN_ATTEMPTS_BEFORE_FLOOR_APPLIES,
    apply_reuse_outcome,
    evaluate_demotion,
    human_revoke,
)

__all__ = [
    "DEMOTION_CONFIDENCE_FLOOR",
    "LearningService",
    "MIN_ATTEMPTS_BEFORE_FLOOR_APPLIES",
    "SkillActivationDenied",
    "SkillCandidateSpec",
    "apply_reuse_outcome",
    "evaluate_demotion",
    "human_revoke",
]
