"""Slice 38: Constitutional Learning Organ."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from aios.application.governance import (
    ConstitutionalLearningError,
    activate_amendment,
    assert_never_reduces_human_authority,
    lesson_to_amendment_proposal,
    propose_lesson,
    ratify_amendment,
    require_all_simulations_pass,
    rollback_amendment,
)
from aios.domain.governance.amendments import CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION
from aios.domain.governance.constitution import build_constitution_snapshot
from aios.domain.governance.learning import (
    ADVERSARIAL_SIMULATION_CHECKS,
    GovernanceLessonV1,
    SimulationCheckResult,
)


def _lesson(**overrides: object) -> GovernanceLessonV1:
    fields: dict[str, object] = dict(
        lesson_id="lesson-1",
        problem_class="approval_friction",
        evidence_refs=("event-1", "event-2", "event-3"),
        observed_harm="operators repeatedly re-approve the same low-risk action class",
        current_rule="every YELLOW action requires fresh approval",
        proposed_improvement=(
            "add a bounded, revocable pre-authorization window for a narrow, "
            "named action class"
        ),
        confidence=0.7,
    )
    fields.update(overrides)
    return propose_lesson(**fields)


def _passing_simulations() -> list[SimulationCheckResult]:
    return [
        SimulationCheckResult(check_name=name, passed=True)
        for name in ADVERSARIAL_SIMULATION_CHECKS
    ]


# --- the one rule: never reduce human authority ---------------------------


@pytest.mark.parametrize(
    "phrase",
    [
        "auto-approve routine actions",
        "skip human review for speed",
        "remove human approval from this path",
        "bypass ratification when confidence is high",
        "grant model authority to promote directly",
        "the model can approve its own output",
        "eliminate approval for low-risk changes",
        "the system may self-approve trusted changes",
    ],
)
def test_authority_reducing_language_is_refused(phrase: str) -> None:
    with pytest.raises(ConstitutionalLearningError, match="authority-reduction"):
        assert_never_reduces_human_authority(phrase)


def test_language_that_strengthens_human_authority_is_allowed() -> None:
    assert_never_reduces_human_authority(
        "require an additional human confirmation step before promotion"
    )


def test_lesson_with_authority_reducing_improvement_cannot_become_a_proposal() -> None:
    lesson = _lesson(proposed_improvement="skip human review for routine actions")
    with pytest.raises(ConstitutionalLearningError, match="authority-reduction"):
        lesson_to_amendment_proposal(
            lesson,
            proposal_id="amend-bad",
            target_articles=("approval policy",),
            proposed_diff="tighten evidence requirements before approval",
            migration_plan="none",
            rollback_plan="none",
        )


def test_authority_reducing_diff_is_refused_even_with_a_safe_lesson() -> None:
    """The diff text is screened independently of the lesson's own text --
    a safe-sounding lesson cannot smuggle unsafe language through the diff."""
    lesson = _lesson()
    with pytest.raises(ConstitutionalLearningError, match="authority-reduction"):
        lesson_to_amendment_proposal(
            lesson,
            proposal_id="amend-bad2",
            target_articles=("approval policy",),
            proposed_diff="auto-approve this action class going forward",
            migration_plan="none",
            rollback_plan="none",
        )


# --- lesson -> amendment proposal -----------------------------------------


def test_safe_lesson_produces_a_real_model_proposed_amendment() -> None:
    lesson = _lesson()
    updated_lesson, proposal = lesson_to_amendment_proposal(
        lesson,
        proposal_id="amend-1",
        target_articles=("approval policy",),
        proposed_diff="add a bounded, revocable pre-authorization window",
        migration_plan="no data migration",
        rollback_plan="revert to per-action approval",
    )
    assert updated_lesson.status == "amendment_drafted"
    assert updated_lesson.amendment_proposal_id == proposal.proposal_id
    assert proposal.proposer_type == "model"
    assert proposal.evidence_refs == lesson.evidence_refs


def test_cannot_draft_a_second_amendment_from_an_already_drafted_lesson() -> None:
    lesson = _lesson()
    updated_lesson, _proposal = lesson_to_amendment_proposal(
        lesson,
        proposal_id="amend-1",
        target_articles=("approval policy",),
        proposed_diff="add a bounded, revocable pre-authorization window",
        migration_plan="m",
        rollback_plan="r",
    )
    with pytest.raises(ConstitutionalLearningError, match="cannot draft"):
        lesson_to_amendment_proposal(
            updated_lesson,
            proposal_id="amend-2",
            target_articles=("approval policy",),
            proposed_diff="a different change",
            migration_plan="m",
            rollback_plan="r",
        )


# --- adversarial simulation gate -------------------------------------------


def test_missing_simulation_blocks_readiness() -> None:
    partial = [
        SimulationCheckResult(check_name=name, passed=True)
        for name in ADVERSARIAL_SIMULATION_CHECKS[:-1]  # omit the last one
    ]
    with pytest.raises(ConstitutionalLearningError, match="missing required"):
        require_all_simulations_pass(partial)


def test_failed_simulation_blocks_readiness() -> None:
    results = [
        SimulationCheckResult(
            check_name=name, passed=(name != "reduced_human_reversibility")
        )
        for name in ADVERSARIAL_SIMULATION_CHECKS
    ]
    with pytest.raises(ConstitutionalLearningError, match="failed adversarial"):
        require_all_simulations_pass(results)


def test_all_nine_named_checks_present_and_passing_is_accepted() -> None:
    require_all_simulations_pass(_passing_simulations())


def test_the_nine_checks_match_the_brief_exactly() -> None:
    assert set(ADVERSARIAL_SIMULATION_CHECKS) == {
        "authority_escalation",
        "approval_bypass",
        "privacy_widening",
        "capability_replay",
        "emergency_stop_interference",
        "memory_as_truth_confusion",
        "model_self_protection",
        "provider_lock_in",
        "reduced_human_reversibility",
    }


# --- full pipeline: proposal -> simulation -> human ratification -> ------
# --- rollback-capable activation (the organ's own green gate) -------------


def test_a_governance_weakness_travels_the_complete_proposal_to_rollback_path() -> None:
    lesson = _lesson()
    updated_lesson, proposal = lesson_to_amendment_proposal(
        lesson,
        proposal_id="amend-full",
        target_articles=("approval policy",),
        proposed_diff="add a bounded, revocable pre-authorization window",
        migration_plan="no data migration",
        rollback_plan="revert to per-action approval",
    )
    require_all_simulations_pass(_passing_simulations())

    real_capability = SimpleNamespace(
        action_type=CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION,
        operator_id="operator:abc",
        consumed_at=1234567890.0,
        token_digest="d" * 64,
    )
    ratified = ratify_amendment(
        proposal, capability_proof=real_capability, operator_id="operator:abc"
    )
    assert ratified.status == "ratified"

    v1 = build_constitution_snapshot(ratified_by_operator_id="operator:abc")
    activated, v2 = activate_amendment(ratified, previous_snapshot=v1)
    assert activated.status == "activated"
    assert v2.version == v1.version + 1

    rolled_back, restored = rollback_amendment(
        activated, current_snapshot=v2, previous_snapshot=v1
    )
    assert rolled_back.status == "rolled_back"
    assert restored.snapshot_digest == v1.snapshot_digest
    assert updated_lesson.amendment_proposal_id == proposal.proposal_id
