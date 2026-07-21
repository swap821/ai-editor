"""Slice 28: Human Representation Core."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from aios.application.memory.human_representation import (
    build_correction_record_v1,
    build_project_passport_v1,
    classify_human_state,
    is_project_passport_stale,
)
from aios.domain.memory.human_representation import (
    CorrectionRecordV1,
    HumanStateHypothesis,
    OperatorPreferenceV1,
    ProjectPassportV1,
)


# --- OperatorPreferenceV1 ---------------------------------------------------


def test_operator_preference_requires_a_known_source_type() -> None:
    with pytest.raises(ValidationError):
        OperatorPreferenceV1(
            preference_id="pref-1",
            domain="testing",
            key="prefers_pytest",
            value=True,
            scope="project:ai-editor",
            confidence=0.8,
            source_type="guessed",  # type: ignore[arg-type]
        )


def test_operator_preference_confidence_is_bounded() -> None:
    with pytest.raises(ValidationError):
        OperatorPreferenceV1(
            preference_id="pref-1",
            domain="testing",
            key="prefers_pytest",
            value=True,
            scope="project:ai-editor",
            confidence=1.5,
            source_type="explicit_user",
        )


def test_operator_preference_has_no_authority_granting_field() -> None:
    """A preference can never be, or contain, an approval -- structurally."""
    assert "grants_authority" not in OperatorPreferenceV1.model_fields
    assert "approval" not in OperatorPreferenceV1.model_fields


def test_operator_preference_carries_scope_for_leak_prevention() -> None:
    """Slice 28 ships the typed field a store must key on to prevent a
    preference observed in one project leaking into another; the store
    itself (scoped persistence/lookup) is a follow-up, tracked in the
    ledger's known_blockers, not built in this contract-only slice."""
    project_scoped = OperatorPreferenceV1(
        preference_id="pref-1",
        domain="testing",
        key="prefers_pytest",
        value=True,
        scope="project:ai-editor",
        confidence=0.8,
        source_type="explicit_user",
    )
    other_project_scoped = project_scoped.model_copy(
        update={"scope": "project:other-repo"}
    )
    assert project_scoped.scope != other_project_scoped.scope


def test_explicit_correction_outranks_inferred_observation_by_source_type() -> None:
    """Both source types exist; a consuming policy is expected to prefer
    explicit_user/human_correction over observed_pattern on conflict --
    this test only proves the type distinction the policy would key on."""
    explicit = OperatorPreferenceV1(
        preference_id="pref-1",
        domain="testing",
        key="prefers_pytest",
        value=True,
        scope="global",
        confidence=0.9,
        source_type="human_correction",
    )
    inferred = OperatorPreferenceV1(
        preference_id="pref-2",
        domain="testing",
        key="prefers_pytest",
        value=False,
        scope="global",
        confidence=0.4,
        source_type="observed_pattern",
        contradicted_by=(explicit.preference_id,),
    )
    assert explicit.source_type in ("explicit_user", "human_correction")
    assert inferred.source_type == "observed_pattern"
    assert explicit.preference_id in inferred.contradicted_by


# --- ProjectPassportV1 ------------------------------------------------------


def test_project_passport_digest_is_deterministic(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Test Project\n", encoding="utf-8")
    first = build_project_passport_v1(
        tmp_path, project_id="proj-1", verified_at_commit="sha-a"
    )
    second = build_project_passport_v1(
        tmp_path, project_id="proj-1", verified_at_commit="sha-a"
    )
    assert first.passport_digest == second.passport_digest
    assert len(first.passport_digest) == 64


def test_project_passport_digest_changes_with_commit(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Test Project\n", encoding="utf-8")
    at_a = build_project_passport_v1(
        tmp_path, project_id="proj-1", verified_at_commit="sha-a"
    )
    at_b = build_project_passport_v1(
        tmp_path, project_id="proj-1", verified_at_commit="sha-b"
    )
    assert at_a.passport_digest != at_b.passport_digest


def test_project_passport_with_matching_commit_is_not_stale(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Test Project\n", encoding="utf-8")
    passport = build_project_passport_v1(
        tmp_path, project_id="proj-1", verified_at_commit="sha-current"
    )
    assert is_project_passport_stale(passport, current_commit_sha="sha-current") is False


def test_project_passport_with_stale_commit_is_marked_stale(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Test Project\n", encoding="utf-8")
    passport = build_project_passport_v1(
        tmp_path, project_id="proj-1", verified_at_commit="sha-old"
    )
    assert is_project_passport_stale(passport, current_commit_sha="sha-new") is True


def test_project_passport_with_no_recorded_commit_is_conservatively_stale(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text("# Test Project\n", encoding="utf-8")
    passport = build_project_passport_v1(tmp_path, project_id="proj-1")
    assert passport.verified_at_commit is None
    assert is_project_passport_stale(passport, current_commit_sha="sha-anything") is True


def test_project_passport_commands_grouped_by_kind(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Test Project\n", encoding="utf-8")
    passport = build_project_passport_v1(tmp_path, project_id="proj-1")
    assert set(passport.commands) == {"install", "run", "build", "test"}


# --- CorrectionRecordV1 -----------------------------------------------------


def test_correction_record_grants_authority_is_pinned_false() -> None:
    record = build_correction_record_v1(
        correction_id="corr-1",
        session_id="session-1",
        base_revision=None,
        correction_revision=1,
        corrected_fields=["intent"],
        before_frame={"intent": "deploy"},
        after_frame={"intent": "do not deploy"},
    )
    assert record.grants_authority is False
    with pytest.raises(ValidationError):
        CorrectionRecordV1(
            correction_id="corr-2",
            session_id="session-1",
            base_revision=0,
            correction_revision=1,
            corrected_fields=("intent",),
            prior_interpretation_digest="a" * 64,
            current_interpretation_digest="b" * 64,
            grants_authority=True,  # type: ignore[arg-type]
        )


def test_correction_record_retains_prior_interpretation_by_digest() -> None:
    record = build_correction_record_v1(
        correction_id="corr-1",
        session_id="session-1",
        base_revision=3,
        correction_revision=4,
        corrected_fields=["intent"],
        before_frame={"intent": "deploy"},
        after_frame={"intent": "do not deploy"},
    )
    assert record.base_revision == 3
    assert record.correction_revision == 4
    assert record.prior_interpretation_digest != record.current_interpretation_digest
    assert len(record.prior_interpretation_digest) == 64


def test_correction_record_base_revision_defaults_to_zero_when_none() -> None:
    record = build_correction_record_v1(
        correction_id="corr-1",
        session_id="session-1",
        base_revision=None,
        correction_revision=1,
        corrected_fields=["intent"],
        before_frame={},
        after_frame={"intent": "new"},
    )
    assert record.base_revision == 0


# --- HumanStateHypothesis ----------------------------------------------------


def test_human_state_hypothesis_pinned_fields_cannot_be_overridden() -> None:
    hypothesis = HumanStateHypothesis(
        state="frustrated", confidence=0.6, visible_reason="test"
    )
    assert hypothesis.user_correctable is True
    assert hypothesis.grants_authority is False
    with pytest.raises(ValidationError):
        HumanStateHypothesis(
            state="frustrated",
            confidence=0.6,
            visible_reason="test",
            grants_authority=True,  # type: ignore[arg-type]
        )
    with pytest.raises(ValidationError):
        HumanStateHypothesis(
            state="frustrated",
            confidence=0.6,
            visible_reason="test",
            user_correctable=False,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("text", "expected_state"),
    [
        ("UGH this is still broken again?!", "frustrated"),
        ("do it asap, no time to waste", "rushed"),
        ("just do it, go ahead", "decisive"),
        ("not sure, maybe try X instead", "uncertain"),
        ("what if we tried Y instead?", "exploratory"),
        ("please summarize this document", "neutral"),
    ],
)
def test_classify_human_state_priority_order(text: str, expected_state: str) -> None:
    hypothesis = classify_human_state(text)
    assert hypothesis.state == expected_state
    assert hypothesis.visible_reason
    assert hypothesis.grants_authority is False
    assert hypothesis.user_correctable is True


def test_classify_human_state_frustration_outranks_rushed_when_both_present() -> None:
    hypothesis = classify_human_state("ugh, still not working, need this asap")
    assert hypothesis.state == "frustrated"
