"""Tests for the ActionBroker application service."""
from __future__ import annotations

import pytest

from aios.application.action_broker import ActionBroker, PolicyBrokerError
from aios.core.approvals import ApprovalStore, ApprovedAction
from aios.domain.actions.envelope import ActionEnvelope, ActionType, Principal
from aios.policy.kernel import PolicyKernel
from aios.security.gateway import RateLimiter, Zone


@pytest.fixture
def broker(tmp_path):
    approvals = ApprovalStore(db_path=tmp_path / "approvals.db")
    kernel = PolicyKernel(rate_limiter=RateLimiter(max_per_session=100))
    return ActionBroker(kernel, approvals)


def test_broker_allows_green_action(broker):
    envelope = ActionEnvelope(
        route="/api/v1/plan",
        action_type=ActionType.PLAN,
        principal=Principal(session_id="sess-1"),
    )
    decision = broker.submit(envelope)
    assert decision.allowed
    assert decision.zone is Zone.GREEN


def test_broker_blocks_red_action(broker):
    envelope = ActionEnvelope(
        route="/api/v1/system/restart",
        action_type=ActionType.SYSTEM_RESTART,
        principal=Principal(session_id="sess-1"),
    )
    with pytest.raises(PolicyBrokerError):
        broker.submit(envelope)


def test_broker_issues_token_for_yellow_action(broker):
    envelope = ActionEnvelope(
        route="/api/v1/execute",
        action_type=ActionType.COMMAND,
        payload={"command": "mkdir training_ground/test"},
        principal=Principal(session_id="sess-1"),
    )
    decision = broker.submit(envelope)
    assert decision.requires_approval
    assert decision.approval_token is not None
    assert decision.zone is Zone.YELLOW


def test_broker_consumes_token_and_allows_yellow_action(broker):
    command = "mkdir training_ground/test_broker"
    envelope = ActionEnvelope(
        route="/api/v1/execute",
        action_type=ActionType.COMMAND,
        payload={"command": command},
        principal=Principal(session_id="sess-1"),
    )
    pending = broker.submit(envelope)
    token = pending.approval_token

    # Re-submit with the token: broker should consume it and allow execution.
    resolved = broker.submit(envelope, approval_token=token)
    assert resolved.allowed
    assert resolved.approval_token is None


def test_broker_rejects_invalid_approval_token(broker):
    envelope = ActionEnvelope(
        route="/api/v1/execute",
        action_type=ActionType.COMMAND,
        payload={"command": "mkdir training_ground/test"},
        principal=Principal(session_id="sess-1"),
    )
    with pytest.raises(PolicyBrokerError):
        broker.submit(envelope, approval_token="not-a-real-token")


def test_broker_requires_session_to_issue_token(broker):
    envelope = ActionEnvelope(
        route="/api/v1/execute",
        action_type=ActionType.COMMAND,
        payload={"command": "mkdir training_ground/test"},
    )
    with pytest.raises(PolicyBrokerError):
        broker.submit(envelope)


def test_broker_rollback_action_type_maps_to_rollback_approval(broker):
    envelope = ActionEnvelope(
        route="/api/v1/rollback",
        action_type=ActionType.ROLLBACK,
        payload={"snapshot_id": "abc123"},
        principal=Principal(session_id="sess-2"),
    )
    decision = broker.submit(envelope)
    assert decision.requires_approval
    token = decision.approval_token

    # The approval store records the action as a rollback.
    approved = broker.approvals.consume(token, "sess-2")
    assert isinstance(approved, ApprovedAction)
    assert approved.action_type == "rollback"
