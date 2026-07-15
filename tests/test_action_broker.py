"""Tests for the ActionBroker application service."""
from __future__ import annotations

import pytest
from dataclasses import replace

from aios.application.action_broker import ActionBroker, PolicyBrokerError
from aios.core.approvals import ApprovalStore, ApprovedAction
from aios.application.capabilities.authority import CapabilityAuthority
from aios.domain.capabilities.contracts import CapabilityBinding
from aios.domain.capabilities.digest import payload_digest, resource_digest
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


def test_broker_rejects_altered_payload_and_leaves_original_capability_usable(broker):
    envelope = ActionEnvelope(
        route="/api/v1/execute",
        action_type=ActionType.COMMAND,
        payload={"command": "mkdir training_ground/exact"},
        principal=Principal(session_id="sess-exact"),
    )
    pending = broker.submit(envelope)
    altered = ActionEnvelope(
        route=envelope.route,
        action_type=envelope.action_type,
        payload={"command": "mkdir training_ground/attacker"},
        principal=envelope.principal,
    )

    with pytest.raises(PolicyBrokerError):
        broker.submit(altered, approval_token=pending.approval_token)
    # A mismatched attempt must not consume the capability or create a side
    # effect; the exact original envelope remains redeemable once.
    assert broker.submit(envelope, approval_token=pending.approval_token).allowed


@pytest.mark.parametrize(
    ("field", "value"),
    (("route", "/api/v1/other"), ("http_method", "PUT")),
)
def test_broker_rejects_altered_route_or_method_and_preserves_capability(
    broker, field, value
):
    envelope = ActionEnvelope(
        route="/api/v1/execute",
        action_type=ActionType.COMMAND,
        payload={"command": "mkdir training_ground/exact-route"},
        principal=Principal(session_id="sess-route"),
    )
    pending = broker.submit(envelope)
    altered = replace(envelope, **{field: value})

    with pytest.raises(PolicyBrokerError):
        broker.submit(altered, approval_token=pending.approval_token)
    assert broker.submit(envelope, approval_token=pending.approval_token).allowed


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


def test_production_broker_issues_and_consumes_exact_capability(tmp_path):
    authority = CapabilityAuthority(db_path=tmp_path / "capabilities.db")
    broker = ActionBroker(
        PolicyKernel(rate_limiter=RateLimiter(max_per_session=100)),
        capabilities=authority,
    )
    payload = {"command": "mkdir training_ground/exact-broker"}
    envelope = ActionEnvelope(
        route="/api/v1/execute",
        action_type=ActionType.COMMAND,
        payload=payload,
        principal=Principal(session_id="session-1"),
        operator_id="operator-1",
        device_id="device-1",
        authentication_event_id="auth-1",
    )
    binding = CapabilityBinding(
        operator_id="operator-1",
        device_id="device-1",
        authentication_event_id="auth-1",
        session_id="session-1",
        action_type="command",
        route="/api/v1/execute",
        http_method="POST",
        payload_digest=payload_digest(payload),
        resource_digest=resource_digest({}),
        mission_id=None,
        contract_digest=None,
        policy_version="v1",
        scope="training_ground/",
        verification_requirement="command_exit_zero",
    )

    pending = broker.submit(envelope, capability_binding=binding)
    assert pending.requires_approval
    assert pending.approval_token

    resolved = broker.submit(
        envelope,
        capability_binding=binding,
        capability_token=pending.approval_token,
    )
    assert resolved.allowed
    assert not resolved.requires_approval

    with pytest.raises(PolicyBrokerError, match="consumed|unknown"):
        broker.submit(
            envelope,
            capability_binding=binding,
            capability_token=pending.approval_token,
        )


def test_production_dependency_constructs_exact_broker(tmp_path, monkeypatch):
    from aios.api import deps

    authority = CapabilityAuthority(db_path=tmp_path / "capabilities-provider.db")
    broker = deps.get_action_broker(
        PolicyKernel(rate_limiter=RateLimiter(max_per_session=100)), authority
    )
    assert isinstance(broker, ActionBroker)
    assert broker.capabilities is authority
    assert broker.approvals is None


def test_production_broker_can_issue_capability_for_green_generate_surface(tmp_path):
    authority = CapabilityAuthority(db_path=tmp_path / "capabilities-generate.db")
    broker = ActionBroker(
        PolicyKernel(rate_limiter=RateLimiter(max_per_session=100)),
        capabilities=authority,
    )
    payload = {"command": "echo generated"}
    envelope = ActionEnvelope(
        route="/api/generate",
        action_type=ActionType.GENERATE,
        payload=payload,
        principal=Principal(session_id="session-1"),
        operator_id="operator-1",
        device_id="device-1",
        authentication_event_id="auth-1",
        requested_capability="generate.command",
    )
    binding = CapabilityBinding(
        operator_id="operator-1",
        device_id="device-1",
        authentication_event_id="auth-1",
        session_id="session-1",
        action_type="command",
        route="/api/generate",
        http_method="POST",
        payload_digest=payload_digest(payload),
        resource_digest=resource_digest({}),
        mission_id=None,
        contract_digest=None,
        policy_version="v1",
        scope="training_ground/",
        verification_requirement="command_exit_zero",
    )
    pending = broker.submit(
        envelope,
        capability_binding=binding,
        issue_capability=True,
    )
    assert pending.requires_approval
    assert pending.approval_token

    consumed = broker.submit(
        envelope,
        capability_binding=binding,
        capability_token=pending.approval_token,
    )
    assert consumed.allowed
