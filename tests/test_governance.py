"""Slice 24 emergency-control and autonomy-gate tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from aios.application.autonomy import GovernedAutonomy
from aios.application.governance import (
    EmergencyStopController,
    EmergencyStopError,
    EmergencyStopHooks,
)
from aios.domain.autonomy import ActionClassKey
from aios.domain.governance import EmergencyStopRequest


def _request() -> EmergencyStopRequest:
    return EmergencyStopRequest(
        operator_id="operator-1",
        authentication_event_id="auth-event-1",
        reason="operator requested an immediate halt",
    )


def _controller(tmp_path: Path, calls: list[str]) -> EmergencyStopController:
    return EmergencyStopController(
        tmp_path / "emergency.db",
        hooks=EmergencyStopHooks(
            revoke_capabilities=lambda: calls.append("revoke"),
            cancel_queued_missions=lambda: calls.append("cancel"),
            kill_active_workers=lambda: calls.append("kill"),
            disable_autonomy=lambda: calls.append("disable"),
            preserve_evidence=lambda reason: calls.append(f"evidence:{reason}"),
        ),
    )


def test_emergency_stop_persists_before_running_all_hooks(tmp_path: Path) -> None:
    calls: list[str] = []
    controller = _controller(tmp_path, calls)
    state = controller.engage(_request())
    assert state.engaged is True
    assert state.generation == 1
    assert set(calls[:4]) == {"revoke", "cancel", "kill", "disable"}
    assert calls[4].startswith("evidence:")
    assert all(value == "completed" for value in state.actions.values())
    assert EmergencyStopController(
        tmp_path / "emergency.db", hooks=controller.hooks
    ).is_engaged()
    with controller._connect() as conn:
        migration = conn.execute(
            "SELECT version, name FROM schema_migrations WHERE version = 3"
        ).fetchone()
    assert tuple(migration) == (3, "emergency_stop_v1")


def test_emergency_stop_is_idempotent_and_clear_requires_authentication(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    controller = _controller(tmp_path, calls)
    controller.engage(_request())
    call_count = len(calls)
    assert controller.engage(_request()).generation == 1
    assert len(calls) == call_count
    with pytest.raises(EmergencyStopError):
        controller.clear(operator_id="", authentication_event_id="")
    cleared = controller.clear(
        operator_id="operator-1", authentication_event_id="auth-event-2"
    )
    assert cleared.engaged is False
    controller.assert_operational()


def test_failed_stop_hook_keeps_latch_engaged_and_reports_failure(
    tmp_path: Path,
) -> None:
    controller = EmergencyStopController(
        tmp_path / "emergency.db",
        hooks=EmergencyStopHooks(
            revoke_capabilities=lambda: True,
            cancel_queued_missions=lambda: (_ for _ in ()).throw(
                RuntimeError("no scheduler")
            ),
            kill_active_workers=lambda: True,
            disable_autonomy=lambda: True,
            preserve_evidence=lambda reason: True,
        ),
    )
    with pytest.raises(EmergencyStopError, match="cancel_queued_missions"):
        controller.engage(_request())
    state = controller.state()
    assert state.engaged is True
    assert state.actions["cancel_queued_missions"].startswith("failed:")
    with pytest.raises(EmergencyStopError, match="side effects are disabled"):
        controller.assert_operational()


def test_governed_autonomy_denies_when_emergency_latch_is_engaged() -> None:
    class Stopped:
        def assert_operational(self) -> None:
            raise EmergencyStopError("emergency stop is engaged")

    class Ledger:
        pass

    key = ActionClassKey(
        project_id="project-1",
        action_type="file_edit",
        tool="editor",
        target="src/app.py",
        path_class="workspace",
        verification_plan_digest="plan-1",
        policy_version="policy-1",
        model_id="local-model",
        data_classification="PROJECT_INTERNAL",
    )
    autonomy = GovernedAutonomy(
        ledger=Ledger(),
        enabled=True,
        profile_name="development",
        production_gate_open=True,
        emergency_stop=Stopped(),
    )
    decision = autonomy.evaluate(key)
    assert decision.status.value == "deny"
    assert decision.reason_codes == ("EMERGENCY_STOP_ENGAGED",)
