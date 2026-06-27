from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from aios.runtime.backends import ControlledSubprocessBackend
from aios.runtime.contracts import MissionContract, WorkerResult
from aios.runtime.king_report import KingReportStore
from aios.runtime.run_ledger import RunLedgerStore
from aios.runtime.spawner import WorkerSpawner
from aios.runtime.worker_api import ContractViolation, WorkerRuntime


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    target = workspace / "frontend" / "src" / "pages" / "Login.jsx"
    target.parent.mkdir(parents=True)
    target.write_text("export function Login() { return null; }\n", encoding="utf-8")
    return workspace


def _mission(workspace: Path, **overrides: object) -> MissionContract:
    data: dict[str, object] = {
        "mission_id": "mission-phase1a",
        "goal": "Append a harmless comment to Login.jsx.",
        "worker_type": "deterministic_worker",
        "created_by": "planner",
        "requires_approval": True,
        "workspace_root": str(workspace),
        "allowed_files": ["frontend/src/pages/Login.jsx"],
        "forbidden_files": ["backend/", ".env", "aios/security/"],
        "allowed_tools": ["read_file", "write_file", "run_command"],
        "timeout_seconds": 30,
        "max_steps": 12,
        "verification_commands": [
            f"{sys.executable} -c \"print('verification ok')\"",
        ],
        "metadata": {
            "deterministic_forbidden_probe": "backend/secret.py",
        },
    }
    data.update(overrides)
    return MissionContract(**data)


def test_worker_runtime_enforces_file_contract(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    runtime_root = tmp_path / "runtime"
    result_path = runtime_root / "result.json"
    contract = _mission(
        workspace,
        allowed_tools=["read_file", "write_file"],
        verification_commands=[],
    )
    runtime = WorkerRuntime(
        contract,
        worker_id="worker-test",
        runtime_root=runtime_root,
        result_path=result_path,
    )

    assert "Login" in runtime.read_file("frontend/src/pages/Login.jsx")
    with pytest.raises(ContractViolation):
        runtime.read_file("backend/secret.py")
    with pytest.raises(ContractViolation):
        runtime.read_file("../outside.txt")

    runtime.write_file("frontend/src/pages/Login.jsx", "// changed\n")
    runtime.finish(
        WorkerResult(
            mission_id=contract.mission_id,
            worker_id="worker-test",
            status="completed",
            risk_after="GREEN",
            started_at="2026-06-27T00:00:00+00:00",
            ended_at="2026-06-27T00:00:01+00:00",
        )
    )

    result = WorkerResult.model_validate_json(result_path.read_text(encoding="utf-8"))
    assert result.files_touched == ["frontend/src/pages/Login.jsx"]
    assert len(result.evidence["blocked_attempts"]) == 2


def test_worker_runtime_writes_approval_request_without_ui_wiring(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    runtime_root = tmp_path / "runtime"
    contract = _mission(
        workspace,
        allowed_tools=["request_approval"],
        verification_commands=[],
        metadata={"approval_wait_seconds": 0},
    )
    runtime = WorkerRuntime(
        contract,
        worker_id="worker-approval",
        runtime_root=runtime_root,
        result_path=runtime_root / "result.json",
    )

    assert runtime.request_approval("write_file", "YELLOW action") is False
    requests = list(
        (runtime_root / "missions" / contract.mission_id / "approvals").glob(
            "*.request.json"
        )
    )
    assert len(requests) == 1


def test_controlled_subprocess_worker_birth_writes_ledger_and_report(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    runtime_root = tmp_path / "runtime"
    contract = _mission(workspace)

    run = asyncio.run(WorkerSpawner(runtime_root=runtime_root).run(contract))

    target = workspace / "frontend" / "src" / "pages" / "Login.jsx"
    assert run.handle.status == "dead"
    assert run.result.status == "completed"
    assert run.result.risk_after == "GREEN"
    assert "// Council Runtime deterministic worker heartbeat" in target.read_text(
        encoding="utf-8"
    )
    assert run.result.files_touched == ["frontend/src/pages/Login.jsx"]
    assert run.ledger.files_allowed == ["frontend/src/pages/Login.jsx"]
    assert run.ledger.files_touched == ["frontend/src/pages/Login.jsx"]
    assert run.ledger.blocked_attempts[0]["payload"]["path"] == "backend/secret.py"
    assert run.ledger.verification["commands"][0]["returncode"] == 0
    assert run.report.status == "completed"
    assert run.report.recommendation == "approve"
    assert run.report.approval_needed is True
    assert run.contract.snapshot_id is not None
    assert run.ledger_path.exists()
    assert run.report_path.exists()

    stored_ledger = RunLedgerStore(runtime_root).read(contract.mission_id)
    stored_report = KingReportStore(runtime_root).read(contract.mission_id)
    assert stored_ledger == run.ledger
    assert stored_report == run.report


def test_controlled_subprocess_backend_omits_cloud_secret_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-test")
    monkeypatch.setenv("AIOS_ROUTER_CLOUD_TASKS", "reasoning,coding")

    env = ControlledSubprocessBackend(tmp_path / "runtime")._restricted_environment()

    assert "OPENAI_API_KEY" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert "AIOS_ROUTER_CLOUD_TASKS" not in env
    assert env["PYTHONIOENCODING"] == "utf-8"
