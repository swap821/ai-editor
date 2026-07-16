"""R13 regression tests for the production emergency-stop dependency graph."""

from __future__ import annotations

import pytest

from aios.application.capabilities.authority import CapabilityAuthority
from aios.application.governance import EmergencyStopError
from aios.api import deps
from aios.core.autonomy import AutonomyLedger
from aios.core.executor import Executor
from aios.domain.capabilities.contracts import CapabilityBinding
from aios.domain.capabilities.digest import payload_digest


class _Stopped:
    def assert_operational(self) -> None:
        raise EmergencyStopError("emergency stop is engaged")


def _binding() -> CapabilityBinding:
    return CapabilityBinding(
        operator_id="operator:one",
        device_id="device:one",
        authentication_event_id="event:strong",
        session_id="session:one",
        action_type="command",
        route="/api/v1/execute",
        http_method="POST",
        payload_digest=payload_digest({"command": "echo safe"}),
        resource_digest=payload_digest({"workspace": "training_ground"}),
        mission_id=None,
        contract_digest=None,
        policy_version="policy:v1",
        scope="training_ground/",
        verification_requirement="command_exit_zero",
    )


def test_production_providers_share_the_durable_emergency_stop(monkeypatch) -> None:
    stopped = _Stopped()
    monkeypatch.setattr(deps, "_emergency_stop", stopped)
    monkeypatch.setattr(deps._CAPABILITIES, "emergency_stop", None)

    capability_authority = deps.get_capability_authority()
    autonomy = deps.get_autonomy()
    executor = deps.get_executor()

    assert capability_authority.emergency_stop is stopped
    assert autonomy.emergency_stop is stopped
    assert isinstance(executor, Executor)
    assert executor.emergency_stop is stopped


def test_capability_issuance_fails_closed_when_the_latch_is_engaged(tmp_path) -> None:
    authority = CapabilityAuthority(
        db_path=tmp_path / "capabilities.db", emergency_stop=_Stopped()
    )
    with pytest.raises(EmergencyStopError):
        authority.issue(_binding())


def test_earned_autonomy_cannot_be_reused_when_the_latch_is_engaged(tmp_path) -> None:
    ledger = AutonomyLedger(
        db_path=tmp_path / "autonomy.db", emergency_stop=_Stopped()
    )
    assert ledger.is_earned("create_file", "training_ground/example.py") is False
