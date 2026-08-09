"""Constitutional Learning Organ pipeline (Slice 38).

Turns an observed governance event into a `GovernanceLessonV1`, and a
lesson into a real Slice 37 `ConstitutionalAmendmentProposalV1` -- never
further than a proposal. Ratification still requires the real human
capability Slice 37 already enforces; this module adds nothing that could
activate a change by itself.

The 9 adversarial simulations named in the brief
(`ADVERSARIAL_SIMULATION_CHECKS`) are a fixed, typed catalog a proposal must
have a passing result for before this module calls it ready for human
review. `require_all_simulations_pass` refuses to proceed on a missing
result exactly the same way it refuses on a failed one, so a simulation
can never be silently skipped. The simulations themselves are run by
`aios.application.governance.adversarial_simulations.
run_adversarial_simulations` -- a real per-check textual risk screen plus a
live probe of the production mechanism each check protects, never a
caller-asserted result.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from aios.application.governance.amendment_authority import propose_amendment
from aios.application.governance.text_screening import screen_text
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
#:
#: Matched through `text_screening.screen_text`, which folds homoglyphs,
#: zero-width characters, combining marks, compatibility forms, leetspeak and
#: punctuation before comparing, and refuses mixed-script words outright. The
#: separate "auto-approve"/"auto approve" and "self-approve"/"self approve"
#: entries this list used to carry are gone: they normalise to one token
#: sequence now, so the duplicates were doing nothing.
_AUTHORITY_REDUCTION_MARKERS: tuple[str, ...] = (
    "auto-approve",
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
)


class ConstitutionalLearningAuthority:
    """Organ 46's named owner: one authority over what GAGOS may learn.

    The ledger has always named `ConstitutionalLearningAuthority` as this
    organ's authority owner, and no such class existed -- the pipeline was a
    set of free functions, so nothing owned the invariant that ties them
    together.

    That invariant is the point of the organ: a lesson may become an amendment
    proposal ONLY after every one of the nine adversarial simulations has been
    run for real and passed. Keeping `run` and `require` as separate free
    functions made it possible for a caller to run the checks and then simply
    not consult them. `screen_proposal()` closes that by doing both, so
    refusing is the default rather than a step a caller must remember.

    Deliberately NOT an amendment-ratification authority: passing these checks
    permits a proposal to be *considered*, never to activate. Ratification
    stays with organ 45 behind a human decision.
    """

    def propose_lesson(
        self,
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

    def assert_never_reduces_human_authority(self, text: str) -> None:
        """The one rule this whole organ exists to serve: GAGOS may learn that
        its sovereignty mechanisms are weak, but may never itself propose
        reducing human authority to fix that.

        Screened through `text_screening.screen_text`, not raw substring
        matching. The 2026-08-08 red-team campaign walked the old raw version
        with four separate one-line encodings of the same English sentence
        (Cyrillic homoglyphs, a zero-width space, a combining mark, full-width
        forms) -- a human reviewer read "the model can approve its own
        amendments without human confirmation" and this guard read nothing.
        """
        hit = screen_text(text, _AUTHORITY_REDUCTION_MARKERS)
        if hit is not None:
            raise ConstitutionalLearningError(
                f"proposed text {hit.describe('an authority-reduction marker')}; "
                "a governance lesson may never propose reducing human authority"
            )

    def run_simulations(
        self, proposal: ConstitutionalAmendmentProposalV1
    ) -> tuple[SimulationCheckResult, ...]:
        """Run all nine checks for real against `proposal`.

        Imported lazily: `adversarial_simulations` probes live production
        mechanisms and importing it at module scope would create an import
        cycle back through this module.
        """
        from aios.application.governance.adversarial_simulations import (
            run_adversarial_simulations,
        )

        return tuple(run_adversarial_simulations(proposal))

    def require_all_simulations_pass(
        self, results: Sequence[SimulationCheckResult]
    ) -> None:
        """Refuses unless every one of the 9 named adversarial simulations is
        both present and passed -- a missing check is treated exactly like a
        failed one, never silently skipped."""
        seen = {result.check_name: result for result in results}
        missing = [name for name in ADVERSARIAL_SIMULATION_CHECKS if name not in seen]
        if missing:
            raise ConstitutionalLearningError(
                f"missing required adversarial simulations: {missing}"
            )
        failed = [
            name for name in ADVERSARIAL_SIMULATION_CHECKS if not seen[name].passed
        ]
        if failed:
            raise ConstitutionalLearningError(
                f"failed adversarial simulations: {failed}"
            )

    def screen_proposal(
        self, proposal: ConstitutionalAmendmentProposalV1
    ) -> tuple[SimulationCheckResult, ...]:
        """Run every check and refuse unless all nine pass.

        Returns the full per-check breakdown on success so a caller can show
        an operator what was actually proven, rather than a bare boolean.
        Raises `ConstitutionalLearningError` otherwise -- a missing check is
        treated exactly like a failed one.
        """
        results = self.run_simulations(proposal)
        self.require_all_simulations_pass(results)
        return results

    def lesson_to_amendment_proposal(
        self,
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
        # Every free-text field, not just the two that describe the change.
        # The red-team campaign's highest-severity finding was a sentence
        # placed in `rollback_plan` -- a field this guard did not read -- that
        # granted the learning organ standing permission to skip human review.
        # Identical text in `proposed_diff` was refused. A screen that can be
        # defeated by moving a sentence one field to the right is not a screen.
        for field in (
            lesson.proposed_improvement,
            lesson.observed_harm,
            proposed_diff,
            migration_plan,
            rollback_plan,
        ):
            self.assert_never_reduces_human_authority(field)

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


_CONSTITUTIONAL_LEARNING = ConstitutionalLearningAuthority()


def propose_lesson(**kwargs: Any) -> GovernanceLessonV1:
    return _CONSTITUTIONAL_LEARNING.propose_lesson(**kwargs)


def assert_never_reduces_human_authority(text: str) -> None:
    _CONSTITUTIONAL_LEARNING.assert_never_reduces_human_authority(text)


def lesson_to_amendment_proposal(
    lesson: GovernanceLessonV1, **kwargs: Any
) -> tuple[GovernanceLessonV1, ConstitutionalAmendmentProposalV1]:
    return _CONSTITUTIONAL_LEARNING.lesson_to_amendment_proposal(lesson, **kwargs)


def require_all_simulations_pass(results: Sequence[SimulationCheckResult]) -> None:
    _CONSTITUTIONAL_LEARNING.require_all_simulations_pass(results)


__all__ = [
    "ConstitutionalLearningAuthority",
    "ConstitutionalLearningError",
    "assert_never_reduces_human_authority",
    "lesson_to_amendment_proposal",
    "propose_lesson",
    "require_all_simulations_pass",
]
