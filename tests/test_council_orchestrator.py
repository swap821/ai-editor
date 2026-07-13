from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from aios.council import CouncilMissionRequest, CouncilOrchestrator
from aios.council.council_memory import CouncilMemory
from aios.council.council_state import CouncilState
from aios.runtime.king_report import KingReportStore
from aios.runtime.run_ledger import RunLedgerStore


def _workspace(tmp_path: Path, *, failing_test: bool = False) -> Path:
    workspace = tmp_path / "workspace"
    target = workspace / "frontend" / "src" / "pages" / "Login.jsx"
    target.parent.mkdir(parents=True)
    target.write_text("export function Login() { return null; }\n", encoding="utf-8")
    tests_dir = workspace / "tests"
    tests_dir.mkdir()
    test_body = "def test_smoke():\n    assert False\n" if failing_test else "def test_smoke():\n    assert True\n"
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
            queen="security", verdict="deny", risk="RED", reason="denied for test", confidence=0.9
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
    assert {"planner", "security", "memory", "testing"} <= queens
    events = state.events_for(request.mission_id)
    assert any(event["event_type"] == "report" for event in events)


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
    assert memory.deliberations_for(request.mission_id)[0]["payload"]["synthesis"] == synthesis


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
    assert run.worker_run is not None
    assert run.worker_run.handle.status == "dead"
    assert run.report.status == "completed"
    assert run.report.recommendation == "approve"
    assert run.ledger.status == "completed"
    assert "// Council Runtime deterministic worker heartbeat" in target.read_text(
        encoding="utf-8"
    )
    assert [verdict.queen for verdict in run.verdicts] == [
        "planner",
        "security",
        "memory",
        "testing",
    ]
    assert run.verdicts[-1].verdict == "allow"
    assert run.ledger.council_verdicts == run.verdicts
    assert run.ledger.verification["commands"][0]["returncode"] == 0
    assert run.report.council_summary["council_verdicts"][-1]["queen"] == "testing"
    assert run.report.council_summary["ganglia_signals"][-1]["source"] == "testing"
    assert run.report.council_summary["ganglia_synthesis"]["can_authorize"] is False
    deliberations = memory.deliberations_for(request.mission_id)
    assert len(deliberations) == 2
    assert deliberations[-1]["payload"]["signals"][-1]["source"] == "testing"
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

    run = asyncio.run(CouncilOrchestrator(runtime_root=tmp_path / "runtime").run(request))

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

    run = asyncio.run(CouncilOrchestrator(runtime_root=tmp_path / "runtime").run(request))

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
