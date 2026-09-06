"""Slice 27: Emergency Stop Hard Wiring across side-effect boundaries."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace
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


# --------------------------------------------------------------------------- #
# The stop control: observing the latch vs deciding to halt
# --------------------------------------------------------------------------- #
#
# These are the same question asked for opposite purposes, and the same answer
# is wrong for one of them. Flagged by external review for four cycles as the
# one control still unmeasured: whether work stops when the human says stop.


def test_halt_fails_closed_when_the_latch_cannot_be_read(monkeypatch) -> None:
    """An unreadable stop control means STOP, not "carry on".

    `latch_is_engaged` fails OPEN by design -- an unreadable latch is not
    evidence of revocation, and recording one that never happened would put a
    false row in the governance record. But `generate_pipeline` used that same
    observation to make its step-boundary HALT decision, so an unreadable latch
    meant "keep working" on the one control that exists to make work stop when
    a human says stop.

    No attacker is required. A locked SQLite file during a checkpoint reaches
    this.
    """
    import aios.api.deps as deps
    from aios.application.governance import emergency_stop as es

    def _unreadable():
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(deps, "get_emergency_stop", _unreadable)

    assert es.halt_requires_stop() is True, "work would have continued"
    assert es.latch_is_engaged() is False, (
        "the observation must still fail OPEN -- inventing a revocation would "
        "falsify the audit record"
    )


def test_halt_and_observation_agree_when_the_latch_is_readable(monkeypatch) -> None:
    """The split must not change behaviour in the ordinary case."""
    import aios.api.deps as deps
    from aios.application.governance import emergency_stop as es

    class _Stop:
        def __init__(self, engaged):
            self._engaged = engaged

        def state(self):
            return SimpleNamespace(engaged=self._engaged)

    for engaged in (True, False):
        monkeypatch.setattr(deps, "get_emergency_stop", lambda e=engaged: _Stop(e))
        assert es.halt_requires_stop() is engaged
        assert es.latch_is_engaged() is engaged


def test_the_pipeline_halt_uses_the_fail_closed_check() -> None:
    """Pins WHICH function the halt decision calls.

    The bug was not a missing control; it was the right control asked the wrong
    question. A future edit that swaps this back to the observation would
    reintroduce it silently, because both functions return a bool and the
    ordinary path behaves identically -- they differ only when the latch cannot
    be read, which no ordinary test exercises.
    """
    import inspect

    from aios.application.turns import generate_pipeline

    source = inspect.getsource(generate_pipeline)

    assert "if _halt_requires_stop():" in source, (
        "the step-boundary halt no longer uses the fail-closed check"
    )
    assert "if _latch_is_engaged():" not in source, (
        "the halt decision is using the fail-OPEN observation again"
    )


def test_one_interrupted_turn_records_exactly_one_row_under_concurrency(
    monkeypatch,
) -> None:
    """The dedupe is check-then-append across TWO THREADS.

    `generate_pipeline` runs inside a threadpool (its sync generator is iterated
    via `iterate_in_threadpool` so it cannot block the event loop) while
    `TurnCoordinator`'s `finally` runs on the loop. Both may reach this for the
    same turn. Unlocked, both can pass the membership test before either
    appends -- and a governance audit then sees two rows for one interrupted
    turn, for the single fact the function's own docstring says must appear
    exactly once.
    """
    import aios.api.deps as deps
    from aios.application.governance import emergency_stop as es

    class _Engaged:
        def state(self):
            return SimpleNamespace(engaged=True)

    monkeypatch.setattr(deps, "get_emergency_stop", lambda: _Engaged())
    monkeypatch.setattr(es, "_RECORDED_TURNS", [])

    written: list[str] = []
    lock = threading.Lock()

    class _Bus:
        def publish(self, *args, **kwargs):
            with lock:
                written.append("row")
            return True

        emit = publish
        record = publish

    bus = _Bus()
    barrier = threading.Barrier(8)
    results: list[bool] = []
    results_lock = threading.Lock()

    def claim():
        barrier.wait()  # maximise the overlap on the check-then-append
        got = es.record_turn_incomplete_if_revoked(
            bus, session_id="s", turn_id="the-same-turn"
        )
        with results_lock:
            results.append(bool(got))

    threads = [threading.Thread(target=claim) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(results) <= 1, (
        f"{sum(results)} threads each believed they were the sole recorder of "
        "one interrupted turn"
    )
