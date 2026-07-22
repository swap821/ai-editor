"""Confidence update rules for the Institutional Skill Library."""

from typing import Literal

from aios.domain.learning.skill_contracts import SkillContract


class ConfidenceUpdater:
    """Adjusts skill confidence based on real-world usage outcomes.

    Failures are punished much more severely than successes are rewarded,
    implementing a fail-closed posture for local skill reuse.
    """

    SUCCESS_REWARD = 0.05
    FAILURE_PENALTY = 0.20

    def record_success(self, skill: SkillContract) -> SkillContract:
        """Increase confidence after an independent, verified successful reuse."""
        new_conf = min(1.0, round(skill.confidence + self.SUCCESS_REWARD, 2))
        return skill.model_copy(
            update={"confidence": new_conf, "success_count": skill.success_count + 1}
        )

    def record_failure(
        self,
        skill: SkillContract,
        reason: Literal[
            "verification",
            "applicability",
            "version_drift",
            "human_correction",
            "rollback",
            "side_effects",
            "clerk_advisory_refused",
        ],
    ) -> SkillContract:
        """Decrease confidence and potentially disable automatic reuse after a failure."""
        new_conf = max(0.0, round(skill.confidence - self.FAILURE_PENALTY, 2))

        # If confidence drops below a theoretical floor (e.g., 0.8), state could transition.
        # We don't automatically change state here to avoid complex side effects,
        # but the applicability engine will catch the low confidence on the next run.
        return skill.model_copy(
            update={"confidence": new_conf, "failure_count": skill.failure_count + 1}
        )
