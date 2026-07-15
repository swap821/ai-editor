from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aios import config
from aios.council import CouncilMissionRequest, CouncilOrchestrator
from aios.council.council_memory import CouncilMemory
from aios.council.council_state import CouncilState
from aios.runtime.king_report import KingReportStore
from aios.runtime.run_ledger import RunLedgerStore


def test_production_orchestrator_wires_one_staged_workspace_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_PROFILE", "production")
    monkeypatch.setattr(config, "EXECUTOR_WORKSPACE_ROOT", tmp_path / "staged")
    monkeypatch.setattr(config, "COUNCIL_WORKSPACE_ROOT", tmp_path / "projects")
    orchestrator = CouncilOrchestrator(runtime_root=tmp_path / "runtime")

    assert orchestrator.workspace_manager is not None
    assert orchestrator.foundry.workspace_manager is orchestrator.workspace_manager
    assert (
        orchestrator.mission_service.workspace_manager is orchestrator.workspace_manager
    )


def test_production_council_promotes_only_after_staged_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_PROFILE", "production")
    monkeypatch.setattr(config, "EXECUTOR_WORKSPACE_ROOT", tmp_path / "staged")
    monkeypatch.setattr(config, "COUNCIL_WORKSPACE_ROOT", tmp_path / "projects")
    project = _workspace(tmp_path / "projects")
    runtime_root = tmp_path / "runtime"

    from aios.application.workers.foundry import WorkerFoundry
    from aios.application.workspaces import StagedWorkspaceManager
    from aios.runtime.backends import WorkerHandle
    from aios.runtime.contracts import RunLedger, WorkerResult
    from aios.runtime.king_report import build_king_report
    from aios.runtime.spawner import WorkerRun, WorkerSpawner

    class FakeSpawner:
        async def run(self, contract, *, claim=True):  # noqa: ANN001
            target = Path(contract.workspace_root) / "frontend/src/pages/Login.jsx"
            target.write_text(
                target.read_text(encoding="utf-8") + "// promoted heartbeat\n",
                encoding="utf-8",
            )
            handle = WorkerHandle(
                worker_id="worker-production-promotion",
                mission_id=contract.mission_id,
                backend="fake_executor",
                status="dead",
            )
            observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            result = WorkerResult(
                mission_id=contract.mission_id,
                worker_id=handle.worker_id,
                status="completed",
                summary="staged worker completed",
                files_touched=["frontend/src/pages/Login.jsx"],
                evidence={
                    "verification": [
                        {
                            "command": "python -m pytest tests -q",
                            "returncode": 0,
                            "stdout": "1 passed",
                            "stderr": "",
                        }
                    ]
                },
                risk_after="GREEN",
                started_at=observed_at,
                ended_at=observed_at,
            )
            ledger = RunLedger(
                mission_id=contract.mission_id,
                mission=contract.goal,
                risk_before=contract.risk_level,
                risk_after=result.risk_after,
                contract=contract,
                workers_created=[handle.worker_id],
                files_allowed=list(contract.allowed_files),
                files_touched=list(result.files_touched),
                verification={
                    "commands": result.evidence["verification"],
                    "strength": "STRONG",
                },
                status=result.status,
                created_at=result.started_at,
                completed_at=result.ended_at,
                evidence=result.evidence,
            )
            return WorkerRun(
                contract=contract,
                handle=handle,
                result=result,
                ledger=ledger,
                report=build_king_report(ledger=ledger, result=result),
                ledger_path=runtime_root / "fake-ledger.json",
                report_path=runtime_root / "fake-report.json",
            )

    manager = StagedWorkspaceManager(
        tmp_path / "staged",
        enrolled_roots=(config.COUNCIL_WORKSPACE_ROOT,),
    )
    orchestrator = CouncilOrchestrator(
        runtime_root=runtime_root,
        spawner=WorkerSpawner(runtime_root=runtime_root),
        workspace_manager=manager,
        foundry=WorkerFoundry(
            spawner=FakeSpawner(),
            workspace_manager=manager,
        ),
    )
    deliberation = orchestrator.deliberate(
        _request(
            project,
            mission_id="mission-production-promotion",
            allowed_files=["frontend/src/pages/Login.jsx"],
            verification_commands=["python -m pytest tests -q"],
        )
    )
    record = orchestrator.mission_service.repository.get("mission-production-promotion")
    orchestrator.mission_service.approve(
        "mission-production-promotion",
        operator_id="human-sovereign-test",
        capability_digest="sha256:promotion-approval",
        contract_digest=record.contract_digest,
        authentication_event_id="auth-production-promotion",
        session_id="session-production-promotion",
    )

    run = asyncio.run(
        orchestrator.execute(deliberation.contract, deliberation.verdicts)
    )

    assert run.report.status == "completed"
    assert "// promoted heartbeat" in (
        project / "frontend/src/pages/Login.jsx"
    ).read_text(encoding="utf-8")
    assert (
        orchestrator.workspace_manager.for_mission("mission-production-promotion")
        is None
    )
    assert run.ledger.evidence["promotion"]["status"] == "promoted"


def _workspace(tmp_path: Path, *, failing_test: bool = False) -> Path:
    workspace = tmp_path / "workspace"
    target = workspace / "frontend" / "src" / "pages" / "Login.jsx"
    target.parent.mkdir(parents=True)
    target.write_text("export function Login() { return null; }\n", encoding="utf-8")
    tests_dir = workspace / "tests"
    tests_dir.mkdir()
    test_body = (
        "def test_smoke():\n    assert False\n"
        if failing_test
        else "def test_smoke():\n    assert True\n"
    )
    (tests_dir / "test_smoke.py").write_text(test_body, encoding="utf-8")
    return workspace


def _request(workspace: Path, **overrides: object) -> CouncilMissionRequest:
    data: dict[str, object] = {
        "mission_id": "mission-phase2",
        "goal": "Improve the login page without changing backend logic.",
        "workspace_root": workspace,
        "allowed_files": ["frontend/src/pages/Login.jsx"],
        "forbidden_files": ["backend/", ".env", "aios/security/"],
        "allowed_tools": ["read_file", "write_file", "run_command"],
        "verification_commands": [f"{sys.executable} -m pytest tests -q"],
        "timeout_seconds": 45,
        "max_steps": 12,
        "metadata": {
            "deterministic_forbidden_probe": "backend/secret.py",
        },
    }
    data.update(overrides)
    return CouncilMissionRequest(**data)  # type: ignore[arg-type]


class _DenySecurity:
    name = "security"

    def review(self, contract):  # noqa: ANN001 - matches SecurityQueen.review
        from aios.runtime.contracts import QueenVerdict

        return QueenVerdict(
            queen="security",
            verdict="deny",
            risk="RED",
            reason="denied for test",
            confidence=0.9,
        )


def test_deliberate_produces_awaiting_approval_without_acting(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    runtime_root = tmp_path / "runtime"
    run = CouncilOrchestrator(runtime_root=runtime_root).deliberate(_request(workspace))

    assert run.report.status == "awaiting_approval"
    assert run.worker_run is None
    # The worker never ran: the target file is untouched.
    target = workspace / "frontend" / "src" / "pages" / "Login.jsx"
    assert "heartbeat" not in target.read_text(encoding="utf-8")


def test_execute_after_deliberate_runs_worker_without_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Verification runs in the spawned worker subprocess; pin host (no Docker in CI;
    # isolation backend is orthogonal, Phase 2b — the var propagates to the worker).
    monkeypatch.setenv("AIOS_APPROVED_EXECUTION_BACKEND", "host")
    workspace = _workspace(tmp_path)
    runtime_root = tmp_path / "runtime"
    orchestrator = CouncilOrchestrator(runtime_root=runtime_root)

    deliberation = orchestrator.deliberate(_request(workspace))
    assert deliberation.report.status == "awaiting_approval"
    authority = orchestrator.mission_service.repository.get(
        deliberation.contract.mission_id
    )
    orchestrator.mission_service.approve(
        deliberation.contract.mission_id,
        operator_id="human-sovereign-test",
        capability_digest="sha256:test-approval",
        contract_digest=authority.contract_digest,
        authentication_event_id="auth-test-approval",
        session_id="session-test-approval",
    )

    run = asyncio.run(
        orchestrator.execute(deliberation.contract, deliberation.verdicts)
    )
    assert run.report.status == "completed"
    assert "// Council Runtime deterministic worker heartbeat" in (
        workspace / "frontend" / "src" / "pages" / "Login.jsx"
    ).read_text(encoding="utf-8")


def test_deliberate_blocks_on_denying_security(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    runtime_root = tmp_path / "runtime"
    run = CouncilOrchestrator(
        runtime_root=runtime_root, security=_DenySecurity()
    ).deliberate(_request(workspace))

    assert run.worker_run is None
    assert run.report.status == "failed"  # denied mission never awaits/executes


def test_council_orchestrator_persists_deliberation_to_state(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    runtime_root = tmp_path / "runtime"
    state = CouncilState(db_path=tmp_path / "council_state.db")
    request = _request(workspace)

    asyncio.run(
        CouncilOrchestrator(runtime_root=runtime_root, council_state=state).run(request)
    )

    verdicts = state.verdicts_for(request.mission_id)
    queens = {verdict["queen_name"] for verdict in verdicts}
    assert {"planner", "security", "memory"} <= queens
    assert "testing" not in queens  # testing is an execution-phase verdict
    events = state.events_for(request.mission_id)
    assert any(event["event_type"] == "deliberated" for event in events)


def test_council_orchestrator_attaches_ganglia_and_memory_evidence(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    runtime_root = tmp_path / "runtime"
    memory = CouncilMemory(db_path=tmp_path / "council_memory.db")
    request = _request(workspace, mission_id="mission-ganglia")

    run = CouncilOrchestrator(
        runtime_root=runtime_root,
        council_memory=memory,
    ).deliberate(request)

    synthesis = run.contract.metadata["ganglia_synthesis"]
    assert synthesis["authority"] == "proposal/evidence"
    assert synthesis["can_authorize"] is False
    assert run.ledger.evidence["ganglia_synthesis"] == synthesis
    assert run.report.council_summary["ganglia_synthesis"] == synthesis
    assert memory.deliberations_for(request.mission_id)


def test_ganglia_security_veto_remains_blocking_and_non_authorizing(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    runtime_root = tmp_path / "runtime"
    memory = CouncilMemory(db_path=tmp_path / "council_memory.db")
    request = _request(workspace, mission_id="mission-ganglia-blocked")

    run = CouncilOrchestrator(
        runtime_root=runtime_root,
        security=_DenySecurity(),
        council_memory=memory,
    ).deliberate(request)

    synthesis = run.contract.metadata["ganglia_synthesis"]
    assert run.worker_run is None
    assert run.ledger.status == "blocked"
    assert synthesis["status"] == "blocked"
    assert synthesis["security_veto"] is True
    assert synthesis["can_authorize"] is False
    assert (
        memory.deliberations_for(request.mission_id)[0]["payload"]["synthesis"]
        == synthesis
    )


def test_council_orchestrator_runs_full_loop_and_records_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Verification runs in the spawned worker subprocess; pin host (no Docker in CI).
    monkeypatch.setenv("AIOS_APPROVED_EXECUTION_BACKEND", "host")
    workspace = _workspace(tmp_path)
    runtime_root = tmp_path / "runtime"
    request = _request(workspace)
    state = CouncilState(db_path=tmp_path / "council_state.db")
    memory = CouncilMemory(state=state)

    run = asyncio.run(
        CouncilOrchestrator(
            runtime_root=runtime_root,
            council_memory=memory,
        ).run(request)
    )

    target = workspace / "frontend" / "src" / "pages" / "Login.jsx"
    assert run.worker_run is None
    assert run.report.status == "awaiting_approval"
    assert run.report.recommendation == "approve"
    assert run.ledger.status == "awaiting_approval"
    assert "// Council Runtime deterministic worker heartbeat" not in target.read_text(
        encoding="utf-8"
    )
    assert [verdict.queen for verdict in run.verdicts] == [
        "planner",
        "security",
        "memory",
    ]
    assert run.ledger.council_verdicts == run.verdicts
    assert run.report.council_summary["ganglia_synthesis"]["can_authorize"] is False
    deliberations = memory.deliberations_for(request.mission_id)
    assert len(deliberations) == 1
    assert deliberations[-1]["payload"]["signals"][-1]["source"] == "memory"
    assert run.report.council_summary["model_routing"] == {}
    assert run.ledger_path.exists()
    assert run.report_path.exists()
    assert RunLedgerStore(runtime_root).read(request.mission_id) == run.ledger
    assert KingReportStore(runtime_root).read(request.mission_id) == run.report


def test_council_orchestrator_blocks_protected_allowed_file_before_worker(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    request = _request(
        workspace,
        mission_id="mission-phase2-blocked",
        allowed_files=["aios/security/gateway.py"],
    )

    run = asyncio.run(
        CouncilOrchestrator(runtime_root=tmp_path / "runtime").run(request)
    )

    assert run.worker_run is None
    assert run.ledger.status == "blocked"
    assert run.report.status == "failed"
    assert run.report.recommendation == "reject"
    assert run.report.files == []
    security = next(verdict for verdict in run.verdicts if verdict.queen == "security")
    assert security.verdict == "deny"
    assert "Protected foundation file" in security.reason


def test_testing_queen_failure_changes_king_report_to_rollback(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path, failing_test=True)
    request = _request(
        workspace,
        mission_id="mission-phase2-verification-fails",
    )

    orchestrator = CouncilOrchestrator(runtime_root=tmp_path / "runtime")
    deliberation = orchestrator.deliberate(request)
    authority = orchestrator.mission_service.repository.get(request.mission_id)
    orchestrator.mission_service.approve(
        request.mission_id,
        operator_id="human-sovereign-test",
        capability_digest="sha256:test-failure-approval",
        contract_digest=authority.contract_digest,
        authentication_event_id="auth-test-failure",
        session_id="session-test-failure",
    )
    run = asyncio.run(
        orchestrator.execute(deliberation.contract, deliberation.verdicts)
    )

    assert run.worker_run is not None
    assert run.worker_run.result.status == "failed"
    assert run.ledger.status == "failed"
    assert run.report.status == "failed"
    assert run.report.recommendation == "rollback"
    assert run.report.rollback_available is True
    assert run.report.rollback_id == run.contract.snapshot_id
    testing = next(verdict for verdict in run.verdicts if verdict.queen == "testing")
    assert testing.verdict == "deny"
    assert run.ledger.verification["commands"][0]["returncode"] != 0


def test_deliberation_includes_optional_queens_when_justified(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    runtime_root = tmp_path / "runtime"
    request = _request(
        workspace,
        mission_id="mission-optional-queens",
        allowed_files=["a", "b", "c", "d"],
        metadata={"project_id": "proj-42", "complex_task": True},
    )

    run = CouncilOrchestrator(runtime_root=runtime_root).deliberate(request)

    queens = [verdict.queen for verdict in run.verdicts]
    assert "routing" in queens
    assert "project_understanding" in queens
    assert set(run.ledger.evidence["council_participation"]["optional"]) >= {
        "routing",
        "project_understanding",
    }
    assert run.ledger.evidence["council_metrics"]["cost_usd"] == 0.0
    assert run.ledger.evidence["council_metrics"]["latency_ms"] >= 0


def test_deliberation_records_participation_for_minimal_council(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    runtime_root = tmp_path / "runtime"
    request = _request(workspace, mission_id="mission-minimal")

    run = CouncilOrchestrator(runtime_root=runtime_root).deliberate(request)

    assert run.ledger.evidence["council_participation"]["required"] == [
        "planner",
        "security",
        "memory",
        "testing",
    ]
    assert "critique" in run.ledger.evidence["council_participation"]["optional"]


def test_queen_services_registry_can_be_used_for_deliberation(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    runtime_root = tmp_path / "runtime"
    request = _request(
        workspace,
        mission_id="mission-services",
        allowed_files=["a", "b", "c", "d"],
    )

    run = CouncilOrchestrator(
        runtime_root=runtime_root, use_queen_services=True
    ).deliberate(request)

    assert "routing" in [verdict.queen for verdict in run.verdicts]
    assert run.report.status == "awaiting_approval"
