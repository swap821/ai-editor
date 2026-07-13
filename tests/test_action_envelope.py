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
