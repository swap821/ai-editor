"""Skill confidence-driven demotion policy (Slice 36).

`aios.domain.learning.confidence.ConfidenceUpdater.record_failure` already
tracks confidence and failure counts, but its own docstring says: "We don't
automatically change state here to avoid complex side effects, but the
applicability engine will catch the low confidence on the next run." This
module is that missing piece -- composed on top of the existing
`ConfidenceUpdater` and `SkillRepository.transition_state()` (whose
authority-validated transition graph this module never bypasses), not a
replacement for either.
"""

from __future__ import annotations

from typing import Literal

from aios.domain.learning.confidence import ConfidenceUpdater
from aios.domain.learning.repository import SkillRecord, SkillRepository
from aios.domain.learning.skill_contracts import SkillState

FailureReason = Literal[
    "verification",
    "applicability",
    "version_drift",
    "human_correction",
    "rollback",
    "side_effects",
]

#: Reasons meaning the skill's *preconditions* no longer hold -- not merely
#: that it was statistically less reliable this time. These force an
#: immediate demotion regardless of the confidence threshold below.
_PRECONDITION_FAILURE_REASONS: frozenset[str] = frozenset(
    {"applicability", "version_drift"}
)

DEMOTION_CONFIDENCE_FLOOR = 0.5
MIN_ATTEMPTS_BEFORE_FLOOR_APPLIES = 3

_DEMOTABLE_STATES: frozenset[str] = frozenset({"active", "probation", "degraded"})


def evaluate_demotion(
    skill: SkillRecord,
    *,
    reason: FailureReason | None = None,
) -> SkillState | None:
    """Decide the target demotion state for a skill's *current* recorded
    confidence/counts/state, or None if no demotion is warranted.

    Only ever suggests a transition already present in `SkillRepository`'s
    validated graph -- it decides *whether*, never *how*, a transition
    happens.
    """
    if skill.state not in _DEMOTABLE_STATES:
        return None

    if reason in _PRECONDITION_FAILURE_REASONS:
        return "suspended"

    total_attempts = skill.success_count + skill.failure_count
    if total_attempts < MIN_ATTEMPTS_BEFORE_FLOOR_APPLIES:
        return None
    if skill.confidence >= DEMOTION_CONFIDENCE_FLOOR:
        return None

    if skill.state == "active":
        return "degraded"
    return "suspended"


def apply_reuse_outcome(
    repository: SkillRepository,
    skill_id: str,
    version: int,
    *,
    success: bool,
    reason: FailureReason | None = None,
    updater: ConfidenceUpdater | None = None,
) -> SkillRecord:
    """Record a real reuse outcome, then demote if the resulting evidence
    (or the failure reason itself) warrants it. Confidence is always
    updated first and persisted even when no demotion follows, so a skill
    that stays `active` still reflects the true, current evidence."""
    current = repository.get(skill_id, version)
    if current is None:
        raise KeyError(f"skill {skill_id!r} version {version} not found")

    conf_updater = updater or ConfidenceUpdater()
    if success:
        updated = conf_updater.record_success(current)
    else:
        if reason is None:
            raise ValueError("a failure outcome requires a reason")
        updated = conf_updater.record_failure(current, reason)

    record = SkillRecord.model_validate(
        {**updated.model_dump(), "created_at": current.created_at, "updated_at": current.updated_at}
    )
    repository.save(record)

    target_state = None if success else evaluate_demotion(record, reason=reason)
    if target_state is not None:
        return repository.transition_state(skill_id, version, target_state)
    return repository.get(skill_id, version)  # type: ignore[return-value]


def human_revoke(
    repository: SkillRepository, skill_id: str, version: int
) -> SkillRecord:
    """A human-initiated permanent revocation -- always reachable from any
    non-terminal state (the repository's transition graph guarantees this;
    see its comment), unlike automatic demotion which only moves one step
    through the validated graph at a time."""
    current = repository.get(skill_id, version)
    if current is None:
        raise KeyError(f"skill {skill_id!r} version {version} not found")
    if current.state in {"revoked", "superseded", "deprecated"}:
        raise ValueError(
            f"cannot revoke a skill already in terminal state {current.state!r}"
        )
    return repository.transition_state(skill_id, version, "revoked")


__all__ = [
    "DEMOTION_CONFIDENCE_FLOOR",
    "MIN_ATTEMPTS_BEFORE_FLOOR_APPLIES",
    "FailureReason",
    "apply_reuse_outcome",
    "evaluate_demotion",
    "human_revoke",
]
