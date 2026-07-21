"""Slice 34: Multi-Model Deliberation and Dissent Organ."""

from __future__ import annotations

import pytest

from aios.application.intelligence import (
    DeliberationError,
    blocks_promotion,
    should_trigger_deliberation,
    synthesize_deliberation,
    verify_independence,
)
from aios.domain.intelligence.deliberation import (
    DeliberationRecord,
    DeliberationRole,
    ModelPosition,
)


def _position(**overrides: object) -> ModelPosition:
    fields: dict[str, object] = dict(
        role="primary",
        provider="gemini",
        exact_model_id="gemini-2.5",
        answer="approve this change",
        confidence=0.8,
    )
    fields.update(overrides)
    return ModelPosition(**fields)


# --- trigger policy ----------------------------------------------------


def test_no_trigger_reasons_means_no_deliberation() -> None:
    triggered, reasons = should_trigger_deliberation()
    assert triggered is False
    assert reasons == ()


@pytest.mark.parametrize(
    "flag",
    [
        "high_consequence",
        "low_primary_confidence",
        "architectural_change",
        "security_sensitive_change",
        "conflicting_evidence",
        "expensive_promotion",
        "constitutional_proposal",
    ],
)
def test_each_trigger_condition_independently_triggers_deliberation(
    flag: str,
) -> None:
    triggered, reasons = should_trigger_deliberation(**{flag: True})
    assert triggered is True
    assert reasons == (flag,)


# --- independence -----------------------------------------------------


def test_same_provider_cannot_satisfy_required_independence() -> None:
    roles = (
        DeliberationRole(role="primary", independence_required=True),
        DeliberationRole(role="critic", independence_required=True),
    )
    positions = (
        _position(role="primary", provider="gemini"),
        _position(role="critic", provider="gemini"),
    )
    violations = verify_independence(positions, roles)
    assert len(violations) == 1
    assert "gemini" in violations[0]


def test_different_providers_satisfy_required_independence() -> None:
    roles = (
        DeliberationRole(role="primary", independence_required=True),
        DeliberationRole(role="critic", independence_required=True),
    )
    positions = (
        _position(role="primary", provider="gemini"),
        _position(role="critic", provider="bedrock"),
    )
    assert verify_independence(positions, roles) == ()


def test_roles_not_requiring_independence_are_not_checked() -> None:
    roles = (DeliberationRole(role="primary", independence_required=False),)
    positions = (
        _position(role="primary", provider="gemini"),
        _position(role="primary", provider="gemini"),
    )
    assert verify_independence(positions, roles) == ()


# --- synthesis: dissent preservation -------------------------------------


def test_critic_disagreement_with_primary_is_preserved() -> None:
    positions = (
        _position(role="primary", answer="approve this change"),
        _position(role="critic", answer="do not approve"),
    )
    record = synthesize_deliberation(
        deliberation_id="delib-1",
        trigger_reasons=("security_sensitive_change",),
        positions=positions,
        final_disposition="escalate_to_human",
    )
    assert len(record.disagreements) == 2
    assert any("do not approve" in d for d in record.disagreements)


def test_agreement_produces_no_disagreement_entries() -> None:
    positions = (
        _position(role="primary", answer="approve"),
        _position(role="critic", answer="Approve"),
    )
    record = synthesize_deliberation(
        deliberation_id="delib-2",
        trigger_reasons=("high_consequence",),
        positions=positions,
        final_disposition="promote",
    )
    assert record.disagreements == ()


def test_minority_security_concern_blocks_promotion_until_resolved() -> None:
    positions = (
        _position(role="primary", security_concerns=()),
        _position(role="critic", answer="do not approve", security_concerns=("possible injection",)),
    )
    record = synthesize_deliberation(
        deliberation_id="delib-3",
        trigger_reasons=("security_sensitive_change",),
        positions=positions,
        final_disposition="escalate_to_human",
    )
    assert record.unresolved_minority_concerns == ("possible injection",)
    assert blocks_promotion(record) is True

    resolved = synthesize_deliberation(
        deliberation_id="delib-4",
        trigger_reasons=("security_sensitive_change",),
        positions=positions,
        final_disposition="promote",
        resolved_security_concerns=("possible injection",),
    )
    assert resolved.unresolved_minority_concerns == ()
    assert blocks_promotion(resolved) is False


def test_synthesis_never_drops_a_minority_concern_even_with_a_final_disposition() -> None:
    """A local clerk (Slice 32) may summarise disagreement for a human, but
    the underlying record must still carry every reported concern."""
    positions = (
        _position(role="primary", security_concerns=()),
        _position(role="critic", security_concerns=("concern A",)),
        _position(role="alternative", security_concerns=("concern B",)),
    )
    record = synthesize_deliberation(
        deliberation_id="delib-5",
        trigger_reasons=("high_consequence",),
        positions=positions,
        final_disposition="promote",
    )
    assert set(record.unresolved_minority_concerns) == {"concern A", "concern B"}


# --- truthful degradation -------------------------------------------------


def test_cloud_outage_degrades_truthfully_not_a_fake_single_model_deliberation() -> None:
    with pytest.raises(DeliberationError):
        synthesize_deliberation(
            deliberation_id="delib-6",
            trigger_reasons=("security_sensitive_change",),
            positions=(_position(),),
            final_disposition="promote",
        )


def test_deliberation_digest_is_deterministic() -> None:
    positions = (_position(role="primary"), _position(role="critic", provider="bedrock"))
    first = synthesize_deliberation(
        deliberation_id="delib-7",
        trigger_reasons=("high_consequence",),
        positions=positions,
        final_disposition="promote",
    )
    second = synthesize_deliberation(
        deliberation_id="delib-7",
        trigger_reasons=("high_consequence",),
        positions=positions,
        final_disposition="promote",
    )
    assert first.deliberation_digest == second.deliberation_digest


# --- structural: no field grants approval ---------------------------------


def test_no_deliberation_field_can_grant_approval() -> None:
    forbidden = {"approved", "authorized", "grants_authority", "approval"}
    assert forbidden.isdisjoint(DeliberationRecord.model_fields)
    assert forbidden.isdisjoint(ModelPosition.model_fields)
