"""Application services for verifier-backed institutional learning."""

from aios.application.learning.service import (
    LearningService,
    SkillActivationDenied,
    SkillCandidateSpec,
)

__all__ = ["LearningService", "SkillActivationDenied", "SkillCandidateSpec"]
