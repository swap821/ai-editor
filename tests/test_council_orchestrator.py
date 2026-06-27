from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from aios.council import CouncilMissionRequest, CouncilOrchestrator
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


def test_council_orchestrator_runs_full_loop_and_records_report(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    runtime_root = tmp_path / "runtime"
    request = _request(workspace)

    run = asyncio.run(CouncilOrchestrator(runtime_root=runtime_root).run(request))

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


def test_testing_queen_failure_changes_king_report_to_revision(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path, failing_test=True)
    request = _request(
        workspace,
        mission_id="mission-phase2-verification-fails",
    )

    run = asyncio.run(CouncilOrchestrator(runtime_root=tmp_path / "runtime").run(request))

    assert run.worker_run is not None
    assert run.worker_run.result.status == "completed"
    assert run.ledger.status == "failed"
    assert run.report.status == "failed"
    assert run.report.recommendation == "revise"
    testing = next(verdict for verdict in run.verdicts if verdict.queen == "testing")
    assert testing.verdict == "deny"
    assert run.ledger.verification["commands"][0]["returncode"] != 0
