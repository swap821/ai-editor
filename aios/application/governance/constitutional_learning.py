"""Constitutional Learning Organ pipeline (Slice 38).

Turns an observed governance event into a `GovernanceLessonV1`, and a
lesson into a real Slice 37 `ConstitutionalAmendmentProposalV1` -- never
further than a proposal. Ratification still requires the real human
capability Slice 37 already enforces; this module adds nothing that could
activate a change by itself.

Honest scope note: the 9 adversarial simulations named in the brief
(`ADVERSARIAL_SIMULATION_CHECKS`) are a fixed, typed catalog a proposal must
have a passing result for before this module calls it ready for human
review -- but this module does not implement the simulations themselves
(real adversarial testing against a running system). `require_all_
simulations_pass` refuses to proceed on a missing result exactly the same
way it refuses on a failed one, so a simulation can never be silently
skipped, but who runs them is a caller responsibility this slice does not
build.
"""

from __future__ import annotations

from collections.abc import Sequence

from aios.application.governance.amendment_authority import propose_amendment
from aios.domain.governance.amendments import ConstitutionalAmendmentProposalV1
from aios.domain.governance.learning import (
    ADVERSARIAL_SIMULATION_CHECKS,
    GovernanceLessonV1,
    SimulationCheckResult,
)


class ConstitutionalLearningError(RuntimeError):
    """Raised when a lesson-derived action would violate the one rule this
    organ exists to enforce, or is otherwise not ready to proceed."""


#: Deterministic, human-auditable markers for language that would reduce
#: human authority or oversight. A keyword screen is a floor beneath human
#: review, not a substitute for it -- real review still happens at
#: ratification (Slice 37), which this screen cannot bypass either way.
_AUTHORITY_REDUCTION_MARKERS: tuple[str, ...] = (
    "auto-approve",
    "auto approve",
    "without human",
    "skip human",
    "remove human approval",
    "bypass ratification",
    "no human review",
    "reduce oversight",
    "grant model authority",
    "model can approve",
    "eliminate approval",
    "without operator",
    "self-approve",
    "self approve",
)


def propose_lesson(
    *,
    lesson_id: str,
    problem_class: str,
    evidence_refs: tuple[str, ...],
    observed_harm: str,
    current_rule: str,
    proposed_improvement: str,
    confidence: float,
) -> GovernanceLessonV1:
    """Any observed governance event may become a candidate lesson --
    proposing one has no effect on the active constitution."""
    return GovernanceLessonV1(
        lesson_id=lesson_id,
        problem_class=problem_class,
        evidence_refs=evidence_refs,
        observed_harm=observed_harm,
        current_rule=current_rule,
        proposed_improvement=proposed_improvement,
        confidence=confidence,
        status="proposed",
    )


def assert_never_reduces_human_authority(text: str) -> None:
    """The one rule this whole organ exists to serve: GAGOS may learn that
    its sovereignty mechanisms are weak, but may never itself propose
    reducing human authority to fix that."""
    lowered = text.lower()
    hit = next(
        (marker for marker in _AUTHORITY_REDUCTION_MARKERS if marker in lowered),
        None,
    )
    if hit is not None:
        raise ConstitutionalLearningError(
            f"proposed text contains an authority-reduction marker ({hit!r}); "
            "a governance lesson may never propose reducing human authority"
        )


def lesson_to_amendment_proposal(
    lesson: GovernanceLessonV1,
    *,
    proposal_id: str,
    target_articles: Sequence[str],
    proposed_diff: str,
    migration_plan: str,
    rollback_plan: str,
    proposed_by: str = "constitutional_learning_organ",
) -> tuple[GovernanceLessonV1, ConstitutionalAmendmentProposalV1]:
    """Draft a real amendment proposal from a lesson. Screened against the
    authority-reduction guard before anything is constructed; the resulting
    proposal is always `proposer_type="model"` -- a lesson is machine-
    derived even when a human later ratifies what it produced."""
    if lesson.status != "proposed":
        raise ConstitutionalLearningError(
            f"cannot draft an amendment from a lesson in status {lesson.status!r}"
        )
    assert_never_reduces_human_authority(lesson.proposed_improvement)
    assert_never_reduces_human_authority(proposed_diff)

    proposal = propose_amendment(
        proposal_id=proposal_id,
        target_articles=tuple(target_articles),
        proposed_diff=proposed_diff,
        motivation=lesson.observed_harm,
        migration_plan=migration_plan,
        rollback_plan=rollback_plan,
        proposed_by=proposed_by,
        proposer_type="model",
        evidence_refs=lesson.evidence_refs,
    )
    updated_lesson = lesson.model_copy(
        update={
            "status": "amendment_drafted",
            "amendment_proposal_id": proposal.proposal_id,
        }
    )
    return updated_lesson, proposal


def require_all_simulations_pass(results: Sequence[SimulationCheckResult]) -> None:
    """Refuses unless every one of the 9 named adversarial simulations is
    both present and passed -- a missing check is treated exactly like a
    failed one, never silently skipped."""
    seen = {result.check_name: result for result in results}
    missing = [name for name in ADVERSARIAL_SIMULATION_CHECKS if name not in seen]
    if missing:
        raise ConstitutionalLearningError(
            f"missing required adversarial simulations: {missing}"
        )
    failed = [name for name in ADVERSARIAL_SIMULATION_CHECKS if not seen[name].passed]
    if failed:
        raise ConstitutionalLearningError(f"failed adversarial simulations: {failed}")


__all__ = [
    "ConstitutionalLearningError",
    "assert_never_reduces_human_authority",
    "lesson_to_amendment_proposal",
    "propose_lesson",
    "require_all_simulations_pass",
]
