"""Tests for the PolicyDecision domain model."""
from __future__ import annotations

import pytest

from aios.domain.policy.decision import PolicyDecision
from aios.security.gateway import Zone


def test_decision_defaults_to_blocked():
    decision = PolicyDecision(envelope_id="e1", route="/api/v1/execute")
    assert decision.blocked is False
    assert decision.allowed is False
    assert decision.requires_approval is False
    assert decision.zone is Zone.RED
    assert decision.approval_token is None


def test_decision_allowed_state():
    decision = PolicyDecision(
        envelope_id="e1",
        route="/api/v1/execute",
        allowed=True,
        zone=Zone.GREEN,
        reason="green",
    )
    assert decision.allowed
    assert not decision.blocked
    assert not decision.requires_approval


@pytest.mark.parametrize(
    ("allowed", "blocked", "requires_approval"),
    [
        (True, True, False),
        (True, False, True),
        (False, True, True),
    ],
)
def test_decision_rejects_conflicting_states(
    allowed: bool, blocked: bool, requires_approval: bool
):
    with pytest.raises(ValueError):
        PolicyDecision(
            envelope_id="e1",
            route="/api/v1/execute",
            allowed=allowed,
            blocked=blocked,
            requires_approval=requires_approval,
            zone=Zone.RED,
        )


def test_decision_is_frozen():
    decision = PolicyDecision(envelope_id="e1", route="/api/v1/execute")
    with pytest.raises(AttributeError):
        decision.allowed = True
