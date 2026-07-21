"""Slice 27: Emergency Stop Hard Wiring across side-effect boundaries."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aios.application.capabilities.authority import CapabilityAuthority
from aios.application.governance import (
    EmergencyStopController,
    EmergencyStopError,
    EmergencyStopHooks,
)
from aios.application.learning.service import LearningService
from aios.application.maintenance.service import MaintenanceConvergenceService
from aios.domain.capabilities.contracts import CapabilityBinding
from aios.domain.governance import EmergencyStopRequest
from aios.operations.recovery import restore_backup
from aios.runtime.intelligence_gateway import (
    IntelligenceGateway,
    IntelligenceRequest,
)
from aios.runtime.contracts import MissionContract


def _request() -> EmergencyStopRequest:
    return EmergencyStopRequest(
        operator_id="operator-1",
        authentication_event_id="auth-event-1",
        reason="operator requested an immediate halt",
    )


def _engaged_controller(tmp_path: Path) -> EmergencyStopController:
    controller = EmergencyStopController(
        tmp_path / "emergency.db",
        hooks=EmergencyStopHooks(
            revoke_capabilities=lambda: None,
            cancel_queued_missions=lambda: None,
            kill_active_workers=lambda: None,
            disable_autonomy=lambda: None,
            preserve_evidence=lambda reason: None,
        ),
    )
    controller.engage(_request())
    return controller


def _mission_contract(tmp_path: Path, **overrides: object) -> MissionContract:
    data: dict[str, object] = {
        "mission_id": "mission-1",
        "goal": "Create a plan without executing it.",
        "worker_type": "hybrid_plan_worker",
        "created_by": "planner",
        "workspace_root": str(tmp_path),
        "risk_level": "GREEN",
    }
    data.update(overrides)
    return MissionContract(**data)


def _binding(**overrides: object) -> CapabilityBinding:
    fields = dict(
        operator_id="operator-1",
        device_id="device:1",
        authentication_event_id="auth-event-1",
        session_id="session:1",
        action_type="command",
        route="/api/v1/execute",
        http_method="POST",
        payload_digest="a" * 64,
        resource_digest="b" * 64,
        mission_id=None,
        contract_digest=None,
        policy_version="v1",
        scope="mission",
        verification_requirement="strong",
    )
    fields.update(overrides)
    return CapabilityBinding(**fields)


# --- intelligence gateway ---------------------------------------------------


def test_intelligence_gateway_refuses_when_stop_engaged(tmp_path: Path) -> None:
    stopped = _engaged_controller(tmp_path)
    gateway = IntelligenceGateway(emergency_stop=stopped)
    contract = _mission_contract(tmp_path)
    request = IntelligenceRequest(
        mission_id="mission-1",
        worker_id="worker-1",
        purpose="plan",
        prompt="hello",
        risk="GREEN",
    )
    with pytest.raises(EmergencyStopError):
        gateway.request(request, contract=contract)


def test_intelligence_gateway_proceeds_when_stop_not_engaged(tmp_path: Path) -> None:
    class _FakeReasoner:
        def complete(self, prompt: str, *, system: str | None = None) -> str:
            return "ok"

    controller = EmergencyStopController(
        tmp_path / "emergency.db",
        hooks=EmergencyStopHooks(
            revoke_capabilities=lambda: None,
            cancel_queued_missions=lambda: None,
            kill_active_workers=lambda: None,
            disable_autonomy=lambda: None,
            preserve_evidence=lambda reason: None,
        ),
    )
    gateway = IntelligenceGateway(
        local_client=_FakeReasoner(), emergency_stop=controller
    )
    contract = _mission_contract(tmp_path)
    request = IntelligenceRequest(
        mission_id="mission-1",
        worker_id="worker-1",
        purpose="plan",
        prompt="hello",
        risk="GREEN",
    )
    response = gateway.request(request, contract=contract)
    assert response.text == "ok"


# --- skill activation and reuse ---------------------------------------------


def test_learning_service_activate_skill_refuses_when_stop_engaged(
    tmp_path: Path,
) -> None:
    stopped = _engaged_controller(tmp_path)
    service = LearningService(
        mission_service=MagicMock(),
        trajectory_repository=MagicMock(database=tmp_path / "trajectories.db"),
        emergency_stop=stopped,
    )
    with pytest.raises(EmergencyStopError):
        service.activate_skill(MagicMock())


def test_learning_service_attempt_local_reuse_refuses_when_stop_engaged(
    tmp_path: Path,
) -> None:
    stopped = _engaged_controller(tmp_path)
    service = LearningService(
        mission_service=MagicMock(),
        trajectory_repository=MagicMock(database=tmp_path / "trajectories.db"),
        emergency_stop=stopped,
    )
    with pytest.raises(EmergencyStopError):
        service.attempt_local_reuse(
            skill_id="skill-1",
            version=1,
            mission_id="mission-1",
            operator_id="operator-1",
            goal="goal",
            project_id="project-1",
            current_inputs={},
            current_state={},
            current_scope="mission",
            mission_allowed_tools=(),
            validated_version="v1",
        )


# --- maintenance execution ---------------------------------------------------


def test_maintenance_run_scan_refuses_when_stop_engaged(tmp_path: Path) -> None:
    stopped = _engaged_controller(tmp_path)
    promotion_authority = MagicMock()
    promotion_authority.verification = MagicMock()
    service = MaintenanceConvergenceService(
        finding_repository=MagicMock(),
        scan_repository=MagicMock(),
        mission_service=MagicMock(),
        worker_foundry=MagicMock(),
        executor_service=MagicMock(),
        verification_authority=promotion_authority.verification,
        promotion_authority=promotion_authority,
        workspace_manager=MagicMock(),
        lifecycle_engine=MagicMock(),
        emergency_stop=stopped,
    )
    with pytest.raises(EmergencyStopError):
        service.run_scan(
            MagicMock(),
            lambda **_kwargs: (),
            scanner_id="scanner-1",
            scanner_version="v1",
            target_id="target-1",
            source_digest="c" * 64,
        )


@pytest.mark.asyncio
async def test_maintenance_run_approved_repair_refuses_when_stop_engaged(
    tmp_path: Path,
) -> None:
    stopped = _engaged_controller(tmp_path)
    promotion_authority = MagicMock()
    promotion_authority.verification = MagicMock()
    service = MaintenanceConvergenceService(
        finding_repository=MagicMock(),
        scan_repository=MagicMock(),
        mission_service=MagicMock(),
        worker_foundry=MagicMock(),
        executor_service=MagicMock(),
        verification_authority=promotion_authority.verification,
        promotion_authority=promotion_authority,
        workspace_manager=MagicMock(),
        lifecycle_engine=MagicMock(),
        emergency_stop=stopped,
    )
    with pytest.raises(EmergencyStopError):
        await service.run_approved_repair(
            "mission-1",
            scanner=lambda **_kwargs: (),
            rescan_contract=MagicMock(),
            capability_consumer=lambda _proof: True,
            create_checkpoint=lambda _record: "checkpoint-1",
            restore_checkpoint=lambda _cp, _record: True,
            smoke_test=lambda _record: True,
        )


# --- backup restore ----------------------------------------------------------


def test_restore_backup_refuses_when_stop_engaged(tmp_path: Path) -> None:
    stopped = _engaged_controller(tmp_path)
    with pytest.raises(EmergencyStopError):
        restore_backup(
            bundle=tmp_path / "does-not-need-to-exist.tar.gz",
            data_dir=tmp_path / "data",
            emergency_stop=stopped,
        )


# --- capability consume ------------------------------------------------------


def test_capability_authority_consume_refuses_when_stop_engaged(
    tmp_path: Path,
) -> None:
    stopped = EmergencyStopController(
        tmp_path / "emergency.db",
        hooks=EmergencyStopHooks(
            revoke_capabilities=lambda: None,
            cancel_queued_missions=lambda: None,
            kill_active_workers=lambda: None,
            disable_autonomy=lambda: None,
            preserve_evidence=lambda reason: None,
        ),
    )
    authority = CapabilityAuthority(
        db_path=tmp_path / "capabilities.db", emergency_stop=stopped
    )
    binding = _binding()
    token = authority.issue(binding)

    stopped.engage(_request())

    with pytest.raises(EmergencyStopError):
        authority.consume(token, binding)
