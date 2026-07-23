"""Slice 28: Human Representation Core."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from aios.application.memory.human_representation import (
    build_correction_record_v1,
    build_project_passport_v1,
    classify_human_state,
    correction_lineage_v1,
    is_project_passport_stale,
    record_correction_and_build_v1,
)
from aios.domain.memory.human_representation import (
    CorrectionRecordV1,
    HumanStateHypothesis,
    OperatorPreferenceV1,
    ProjectPassportV1,
)
from aios.memory.conversation import ConversationStateStore


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


def test_project_passport_invariants_and_decisions_default_empty_but_are_now_acceptable(
    tmp_path: Path,
) -> None:
    """Organ 28: these fields were previously hardcoded to () INSIDE the
    function with no parameter at all -- a caller with a real source could
    never supply them. They still default empty (no auto-derivation exists
    or is safely derivable), but a caller can now actually pass real values
    through."""
    (tmp_path / "README.md").write_text("# Test Project\n", encoding="utf-8")

    default = build_project_passport_v1(tmp_path, project_id="proj-1")
    assert default.invariants == ()
    assert default.explicit_human_decisions == ()

    supplied = build_project_passport_v1(
        tmp_path,
        project_id="proj-1",
        invariants=["never write outside the workspace root"],
        explicit_human_decisions=["operator chose local-first over cloud-first"],
    )
    assert supplied.invariants == ("never write outside the workspace root",)
    assert supplied.explicit_human_decisions == (
        "operator chose local-first over cloud-first",
    )
    assert supplied.passport_digest != default.passport_digest


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


def test_record_correction_and_build_v1_returns_a_real_typed_record(
    tmp_path: Path,
) -> None:
    """Organ 29's stated gap: callers previously had to build a
    CorrectionRecordV1 themselves from record_correction's raw dict output."""
    store = ConversationStateStore(tmp_path / "mem.db")
    revision, persisted, record = record_correction_and_build_v1(
        store,
        "session-1",
        before_frame={"intent": "deploy"},
        after_frame={"intent": "do not deploy"},
        corrections={"intent": "do not deploy"},
        corrected_fields=["intent"],
    )
    assert isinstance(record, CorrectionRecordV1)
    assert record.correction_revision == revision
    assert record.session_id == "session-1"
    assert record.grants_authority is False
    assert persisted["intent"] == "do not deploy"


def test_record_correction_and_build_v1_does_not_change_record_correction() -> None:
    """The wrapper must be additive -- record_correction's own return
    contract (used directly by aios/api/routes/memory.py) is untouched."""
    import inspect

    original = ConversationStateStore.record_correction
    assert "before_frame" in inspect.signature(original).parameters
    assert "after_frame" in inspect.signature(original).parameters


def test_correction_lineage_v1_reconstructs_typed_history_newest_first(
    tmp_path: Path,
) -> None:
    store = ConversationStateStore(tmp_path / "mem.db")
    first_revision, _, _ = record_correction_and_build_v1(
        store,
        "session-2",
        before_frame={"intent": "deploy"},
        after_frame={"intent": "hold"},
        corrections={"intent": "hold"},
        corrected_fields=["intent"],
    )
    second_revision, _, _ = record_correction_and_build_v1(
        store,
        "session-2",
        before_frame={"intent": "hold"},
        after_frame={"intent": "cancel"},
        corrections={"intent": "cancel"},
        corrected_fields=["intent"],
        expected_revision=first_revision,
    )
    lineage = correction_lineage_v1(store, "session-2")
    assert [record.correction_revision for record in lineage] == [
        second_revision,
        first_revision,
    ]
    assert lineage[0].base_revision == first_revision
    assert lineage[1].base_revision == 0
    for record in lineage:
        assert isinstance(record, CorrectionRecordV1)
        assert record.grants_authority is False


def test_correction_lineage_v1_empty_for_unknown_session(tmp_path: Path) -> None:
    store = ConversationStateStore(tmp_path / "mem.db")
    assert correction_lineage_v1(store, "no-such-session") == ()


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
