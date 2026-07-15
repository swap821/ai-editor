"""Tests for PolicyKernel.decide() ActionEnvelope -> PolicyDecision."""
from __future__ import annotations

import pytest
from dataclasses import replace

from aios.domain.actions.envelope import ActionEnvelope, ActionType, Principal
from aios.policy.kernel import PolicyKernel
from aios.security.gateway import RateLimiter, Zone


@pytest.fixture
def kernel(tmp_path):
    return PolicyKernel(rate_limiter=RateLimiter(max_per_session=100))


def test_decide_green_route(kernel):
    envelope = ActionEnvelope(
        route="/api/v1/plan",
        action_type=ActionType.PLAN,
        principal=Principal(session_id="sess-1"),
    )
    decision = kernel.decide(envelope)
    assert decision.allowed
    assert decision.zone is Zone.GREEN
    assert decision.envelope_id == envelope.action_id
    assert decision.route == envelope.route


def test_decide_yellow_route(kernel):
    envelope = ActionEnvelope(
        route="/api/v1/files/edit",
        action_type=ActionType.FILES_EDIT,
        principal=Principal(session_id="sess-1"),
    )
    decision = kernel.decide(envelope)
    assert decision.requires_approval
    assert decision.zone is Zone.YELLOW
    assert not decision.allowed
    assert not decision.blocked


def test_decide_red_route(kernel):
    envelope = ActionEnvelope(
        route="/api/v1/system/restart",
        action_type=ActionType.SYSTEM_RESTART,
        principal=Principal(session_id="sess-1"),
    )
    decision = kernel.decide(envelope)
    assert decision.blocked
    assert decision.zone is Zone.RED


def test_decide_command_green(kernel):
    envelope = ActionEnvelope(
        route="/api/v1/execute",
        action_type=ActionType.COMMAND,
        payload={"command": "echo hello"},
        principal=Principal(session_id="sess-1"),
    )
    decision = kernel.decide(envelope)
    assert decision.allowed
    assert decision.zone is Zone.GREEN


def test_decide_command_yellow(kernel):
    envelope = ActionEnvelope(
        route="/api/v1/execute",
        action_type=ActionType.COMMAND,
        payload={"command": "mkdir training_ground/test_decide"},
        principal=Principal(session_id="sess-1"),
    )
    decision = kernel.decide(envelope)
    assert decision.requires_approval
    assert decision.zone is Zone.YELLOW


def test_decide_command_red(kernel):
    envelope = ActionEnvelope(
        route="/api/v1/execute",
        action_type=ActionType.COMMAND,
        payload={"command": "rm -rf /"},
        principal=Principal(session_id="sess-1"),
    )
    decision = kernel.decide(envelope)
    assert decision.blocked
    assert decision.zone is Zone.RED


def test_decide_rate_limit_blocks(kernel):
    path = "/api/v1/runtime/rollbacks/prune"
    cap = kernel.rate_limit_endpoints[path]
    for i in range(cap + 1):
        envelope = ActionEnvelope(
            route=path,
            action_type=ActionType.RUNTIME_ROLLBACK_PRUNE,
            principal=Principal(session_id=f"sess-{i}", client_ip="1.2.3.4"),
        )
        decision = kernel.decide(envelope)
    assert decision.blocked
    assert "rate limited" in decision.reason.lower()


def test_decide_templated_route(kernel):
    envelope = ActionEnvelope(
        route="/api/v1/policy/abc123/vote",
        action_type=ActionType.POLICY_VOTE,
        principal=Principal(session_id="sess-1"),
    )
    decision = kernel.decide(envelope)
    assert decision.requires_approval
    assert decision.zone is Zone.YELLOW


def test_decide_unknown_route_is_red_and_blocked(kernel):
    envelope = ActionEnvelope(
        route="/not/registered/anywhere",
        action_type=ActionType.UNKNOWN,
        principal=Principal(session_id="sess-1"),
    )
    decision = kernel.decide(envelope)
    assert decision.blocked
    assert decision.zone is Zone.RED
    assert "unknown route" in decision.reason.lower()


def test_decide_registered_route_with_wrong_action_type_is_red_and_blocked(kernel):
    envelope = ActionEnvelope(
        route="/api/v1/plan",
        action_type=ActionType.COMMAND,
        principal=Principal(session_id="sess-1"),
    )
    decision = kernel.decide(envelope)
    assert decision.blocked
    assert decision.zone is Zone.RED
    assert "action type" in decision.reason.lower()


def test_decide_registered_route_with_wrong_policy_version_is_red_and_blocked(kernel):
    envelope = ActionEnvelope(
        route="/api/v1/plan",
        action_type=ActionType.PLAN,
        policy_version="policy:v0",
        principal=Principal(session_id="sess-1"),
    )
    decision = kernel.decide(envelope)
    assert decision.blocked
    assert decision.zone is Zone.RED
    assert "policy version" in decision.reason.lower()
