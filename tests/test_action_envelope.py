"""Tests for the ActionEnvelope domain model."""
from __future__ import annotations

import uuid

import pytest

from aios.domain.actions.envelope import ActionEnvelope, ActionType, Principal


def test_envelope_defaults():
    envelope = ActionEnvelope(route="/api/v1/execute", action_type=ActionType.COMMAND)
    assert envelope.route == "/api/v1/execute"
    assert envelope.action_type is ActionType.COMMAND
    assert envelope.http_method == "POST"
    assert isinstance(uuid.UUID(envelope.action_id), uuid.UUID)
    assert envelope.principal.client_ip == "127.0.0.1"
    assert envelope.payload == {}
    assert len(envelope.payload_digest) == 64
    assert len(envelope.resource_digest) == 64
    assert envelope.policy_version == "v1"
    assert envelope.data_classification == "PROJECT_INTERNAL"
    assert envelope.correlation_id


def test_envelope_carries_complete_r4_action_binding():
    envelope = ActionEnvelope(
        route="/api/v1/execute",
        action_type=ActionType.COMMAND,
        payload={"command": "echo hi"},
        operator_id="operator-1",
        device_id="device-1",
        authentication_event_id="auth-1",
        mission_id="mission-1",
        contract_digest="contract-1",
        resource={"workspace": "training_ground"},
        policy_version="policy:v1",
        data_classification="PROJECT_INTERNAL",
        requested_capability="command.execute",
        correlation_id="corr-1",
    )
    assert envelope.operator_id == "operator-1"
    assert envelope.device_id == "device-1"
    assert envelope.authentication_event_id == "auth-1"
    assert envelope.mission_id == "mission-1"
    assert envelope.contract_digest == "contract-1"
    assert envelope.requested_capability == "command.execute"
    assert envelope.correlation_id == "corr-1"
    assert envelope.payload_digest != envelope.resource_digest


def test_envelope_rejects_forged_digests():
    with pytest.raises(ValueError, match="payload_digest"):
        ActionEnvelope(
            route="/api/v1/execute",
            action_type=ActionType.COMMAND,
            payload={"command": "echo hi"},
            payload_digest="forged",
        )


def test_envelope_session_id_property():
    envelope = ActionEnvelope(
        route="/api/v1/execute",
        action_type=ActionType.COMMAND,
        principal=Principal(session_id="sess-123"),
    )
    assert envelope.session_id == "sess-123"


def test_envelope_is_frozen():
    envelope = ActionEnvelope(route="/api/v1/execute", action_type=ActionType.COMMAND)
    with pytest.raises(AttributeError):
        envelope.route = "/other"


def test_action_type_values_are_stable_strings():
    assert ActionType.COMMAND.value == "command"
    assert ActionType.ROLLBACK.value == "rollback"
    assert ActionType.PROPOSAL_APPLY.value == "proposal_apply"
