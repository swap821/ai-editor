"""Slice 29: Human Representative Context Compiler."""

from __future__ import annotations

from aios.application.intelligence.context_compiler import (
    compile_representative_context,
)
from aios.domain.intelligence.representative_context import RepresentativeContextV1
from aios.domain.memory.human_representation import (
    CorrectionRecordV1,
    OperatorPreferenceV1,
)
from aios.domain.privacy.contracts import ModelCallRequest
from aios.runtime.intelligence_gateway import IntelligenceRequest


def _preference(**overrides: object) -> OperatorPreferenceV1:
    fields: dict[str, object] = dict(
        preference_id="pref-1",
        domain="testing",
        key="framework",
        value="pytest",
        scope="global",
        confidence=0.9,
        source_type="explicit_user",
        status="active",
    )
    fields.update(overrides)
    return OperatorPreferenceV1(**fields)


def _compile(**overrides: object) -> RepresentativeContextV1:
    fields: dict[str, object] = dict(
        request_id="req-1",
        operator_identity_digest="operator-digest",
        constitution_digest="c" * 64,
        goal="Fix the failing test",
        desired_outcome="the suite is green",
        target="local",
        delegated_authority_summary="advisory plan only, no write authority",
    )
    fields.update(overrides)
    return compile_representative_context(**fields)


def test_same_source_state_creates_the_same_digest() -> None:
    first = _compile()
    second = _compile()
    assert first.context_digest == second.context_digest
    assert len(first.context_digest) == 64


def test_two_cloud_compilations_are_semantically_identical_regardless_of_provider() -> None:
    """The compiler never branches on *which* cloud provider will be used --
    only on local-vs-cloud target -- so two providers of the same target
    receive byte-identical compiled context."""
    first = _compile(target="cloud")
    second = _compile(target="cloud")
    assert first.context_digest == second.context_digest
    assert first.model_dump() == second.model_dump()


def test_secret_fields_do_not_appear_in_cloud_projection() -> None:
    ctx = _compile(
        target="cloud",
        goal="fix the bug; my AWS key is AKIAABCDEFGHIJKLMNOP",
        relevant_memory_refs=("mem-1", "mem-2"),
    )
    assert "AKIAABCDEFGHIJKLMNOP" not in ctx.goal
    assert "REDACTED" in ctx.goal
    assert ctx.relevant_memory_refs == ()
    assert "relevant_memory_refs" in ctx.forbidden_fields


def test_local_projection_may_contain_local_only_data() -> None:
    ctx = _compile(target="local", relevant_memory_refs=("mem-1", "mem-2"))
    assert ctx.relevant_memory_refs == ("mem-1", "mem-2")
    assert ctx.forbidden_fields == ()


def test_stale_passport_is_labelled_in_uncertainty() -> None:
    from aios.domain.memory.human_representation import ProjectPassportV1

    passport = ProjectPassportV1(
        project_id="proj-1",
        goal="ship it",
        architecture_summary="",
        passport_digest="d" * 64,
        verified_at_commit="sha-old",
    )
    ctx = _compile(project_passport=passport, project_passport_stale=True)
    assert any("stale" in note for note in ctx.uncertainty)
    assert ctx.project_passport_digest == "d" * 64


def test_fresh_passport_is_not_labelled_stale() -> None:
    from aios.domain.memory.human_representation import ProjectPassportV1

    passport = ProjectPassportV1(
        project_id="proj-1",
        goal="ship it",
        architecture_summary="",
        passport_digest="d" * 64,
        verified_at_commit="sha-current",
    )
    ctx = _compile(project_passport=passport, project_passport_stale=False)
    assert not any("stale" in note for note in ctx.uncertainty)


def test_contradicted_or_superseded_preference_is_not_silently_selected() -> None:
    active = _preference(preference_id="pref-active", status="active")
    superseded = _preference(preference_id="pref-old", status="superseded", value="unittest")
    rejected = _preference(preference_id="pref-bad", status="rejected", value="nose")
    ctx = _compile(active_preferences=[active, superseded, rejected])
    assert len(ctx.approved_preferences) == 1
    assert ctx.approved_preferences[0].value == "pytest"


def test_human_correction_appears_in_the_compiled_packet() -> None:
    correction = CorrectionRecordV1(
        correction_id="corr-1",
        session_id="session-1",
        base_revision=1,
        correction_revision=2,
        corrected_fields=("intent",),
        prior_interpretation_digest="a" * 64,
        current_interpretation_digest="b" * 64,
    )
    ctx = _compile(latest_correction=correction)
    assert any("correction" in decision for decision in ctx.current_decisions)
    assert any("revision 2" in decision for decision in ctx.current_decisions)
    # The correction is visible, but nothing about it grants authority.
    assert not hasattr(ctx, "grants_authority")
    assert not hasattr(ctx, "approved")


def test_no_representation_field_can_become_an_approval() -> None:
    """Structural guarantee: the compiled context has no field name that
    could be mistaken for, or misused as, an authorization decision."""
    forbidden_field_names = {"approved", "authorized", "grants_authority", "approval"}
    assert forbidden_field_names.isdisjoint(RepresentativeContextV1.model_fields)


def test_current_model_call_contracts_do_not_yet_carry_a_compiled_context() -> None:
    """Documents the honest current gap rather than overclaiming: Slice 29
    builds the compiler; wiring every model call through it (so a raw prompt
    can never be a call's full context) is Slice 30's Universal Intelligence
    Gateway. This test fails loudly, on purpose, the day someone adds a
    `context_digest` field to either contract without updating this note and
    actually wiring the compiler in -- forcing that work to be deliberate."""
    assert "context_digest" not in ModelCallRequest.model_fields
    assert "context_digest" not in IntelligenceRequest.model_fields
