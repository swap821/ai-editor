"""A GAGOS mission approved within the operator's envelope (organ 10, 2026-11-12).

Move A3, step 1. Each approval uses the one slot the mission took when it was
originated; the slot is re-checked at the moment of approval by organ 9's
envelope authority; the record's actor is the envelope, never the operator.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest

from aios.api.routes import council as council_route
from aios.application.capabilities.envelope import EnvelopeRefused
from aios.application.missions.mission_service import MissionAuthority
from aios.domain.governance.contracts import EmergencyStopRequest
from aios.domain.missions.mission_repository import MissionTransitionError
from aios.domain.missions.mission_state import MissionState
from aios.infrastructure.missions.sqlite_mission_repository import (
    SqliteMissionRepository,
)
from aios.operations import council_origination as co
from tests.test_gagos_council_origination import _briefed, _envelope, _task


@pytest.fixture()
def originated(tmp_path):
    envelope = _envelope(tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    out = co.originate_goal(
        _task(),
        _briefed(),
        envelope=envelope,
        workspace_root=co.gagos_workspace(tmp_path / "council_workspace"),
        runtime_root=runtime,
        detect_injection=lambda text: None,
    )
    assert out["state"] == "awaiting_approval", out
    db = runtime / council_route.MISSIONS_DB_NAME
    missions = MissionAuthority(
        SqliteMissionRepository(db), export_dir=tmp_path / "exports"
    )
    return envelope, missions, out["mission_id"], db


def _state(missions, mission_id):
    return missions.repository.get(mission_id).state


def test_a_mission_inside_a_live_envelope_is_approved_by_its_slot(originated) -> None:
    envelope, missions, mission_id, db = originated
    record = missions.approve_within_envelope(mission_id, envelope=envelope)
    assert record.state is MissionState.APPROVED
    slot = envelope.held_slot(mission_id)
    with sqlite3.connect(db) as conn:
        actor, reason, capability, event = conn.execute(
            "SELECT actor, reason, capability_digest, authentication_event_id "
            "FROM mission_transitions WHERE mission_id = ? AND to_state = ?",
            (mission_id, MissionState.APPROVED.value),
        ).fetchone()
    assert actor == f"envelope:{slot.envelope_id}"  # never the operator
    assert "slot 1 of 2" in reason
    assert capability == slot.slot_digest
    assert event == "auth-1"  # the authentication he signed the envelope with


def test_a_revoked_envelope_approves_nothing(originated) -> None:
    from tests.test_gagos_envelope import Who

    envelope, missions, mission_id, _db = originated
    envelope.revoke(principal=Who())
    with pytest.raises(EnvelopeRefused, match="revoked"):
        missions.approve_within_envelope(mission_id, envelope=envelope)
    assert _state(missions, mission_id) is MissionState.AWAITING_APPROVAL


def test_a_stop_since_signing_approves_nothing(originated) -> None:
    envelope, missions, mission_id, _db = originated
    envelope.emergency_stop.engage(
        EmergencyStopRequest(
            operator_id="operator-1", authentication_event_id="auth-9", reason="t"
        )
    )
    with pytest.raises(EnvelopeRefused, match="emergency stop"):
        missions.approve_within_envelope(mission_id, envelope=envelope)
    assert _state(missions, mission_id) is MissionState.AWAITING_APPROVAL


def test_a_mission_with_no_slot_is_never_approved_by_an_envelope(originated) -> None:
    envelope, missions, _mission_id, _db = originated
    with pytest.raises(EnvelopeRefused, match="holds no envelope slot"):
        missions.approve_within_envelope("mission-ffffffffffff", envelope=envelope)


def test_a_contract_naming_another_slot_is_refused(originated, monkeypatch) -> None:
    envelope, missions, mission_id, _db = originated
    real = envelope.held_slot(mission_id)
    monkeypatch.setattr(
        envelope, "held_slot", lambda m: replace(real, slot_digest="f" * 64)
    )
    with pytest.raises(MissionTransitionError, match="does not name"):
        missions.approve_within_envelope(mission_id, envelope=envelope)
    assert _state(missions, mission_id) is MissionState.AWAITING_APPROVAL
