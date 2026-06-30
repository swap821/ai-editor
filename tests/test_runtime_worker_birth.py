from __future__ import annotations

import asyncio
import os
import shlex
import sys
from pathlib import Path

import pytest

from aios.agents.rollback_engine import RollbackEngine, RollbackError
from aios.runtime.backends import ControlledSubprocessBackend
from aios.runtime.contracts import MissionContract, WorkerResult
from aios.runtime.king_report import KingReportStore
from aios.runtime.run_ledger import RunLedgerStore
from aios.runtime.snapshots import SnapshotManager
from aios.runtime.spawner import MissionCollisionError, WorkerSpawner
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # This test exercises worker birth + the full ledger/report; verification runs
    # for real in the spawned subprocess. The isolation backend is orthogonal
    # (Phase 2b) and there is no Docker in CI, so run verification on the host (the
    # var now propagates into the worker subprocess).
    monkeypatch.setenv("AIOS_APPROVED_EXECUTION_BACKEND", "host")
    workspace = _workspace(tmp_path)
    runtime_root = tmp_path / "runtime"
    contract = _mission(workspace)
    original = (workspace / "frontend" / "src" / "pages" / "Login.jsx").read_text(
        encoding="utf-8"
    )

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
    assert run.result.rollback_id == run.contract.snapshot_id
    assert run.ledger.rollback_id == run.contract.snapshot_id
    assert run.report.rollback_available is True
    assert run.report.rollback_id == run.contract.snapshot_id
    assert run.ledger_path.exists()
    assert run.report_path.exists()

    restored = RollbackEngine(repo_dir=workspace).rollback(run.report.rollback_id)
    assert restored.restored is True
    assert target.read_text(encoding="utf-8") == original

    stored_ledger = RunLedgerStore(runtime_root).read(contract.mission_id)
    stored_report = KingReportStore(runtime_root).read(contract.mission_id)
    assert stored_ledger == run.ledger
    assert stored_report == run.report


def test_controlled_subprocess_worker_fails_when_verification_command_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOS_APPROVED_EXECUTION_BACKEND", "host")
    workspace = _workspace(tmp_path)
    (workspace / "fail.py").write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
    runtime_root = tmp_path / "runtime"
    contract = _mission(
        workspace,
        mission_id="mission-failing-verifier",
        verification_commands=[f"{sys.executable} fail.py"],
    )

    run = asyncio.run(WorkerSpawner(runtime_root=runtime_root).run(contract))

    assert run.handle.status == "dead"
    assert run.result.status == "failed"
    assert run.ledger.status == "failed"
    assert run.report.status == "failed"
    assert run.ledger.verification["commands"][0]["returncode"] == 3


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


def test_restricted_environment_preserves_appdata_for_user_site(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """APPDATA/LOCALAPPDATA are non-secret OS path vars the Windows interpreter
    needs to locate user site-packages (where pip installs without admin). They
    belong with PATH/TEMP/WINDIR in the allowlist — withholding them crashes a
    system-Python worker with ModuleNotFoundError. Secrets are STILL scrubbed."""
    monkeypatch.setenv("APPDATA", r"C:\Users\x\AppData\Roaming")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\x\AppData\Local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-test")

    env = ControlledSubprocessBackend(tmp_path / "runtime")._restricted_environment()

    assert env.get("APPDATA") == r"C:\Users\x\AppData\Roaming"
    assert env.get("LOCALAPPDATA") == r"C:\Users\x\AppData\Local"
    assert "AWS_SECRET_ACCESS_KEY" not in env  # secrets still gone


def test_run_command_is_fail_closed_to_verification_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_command must run ONLY declared verification commands; an arbitrary
    host command (e.g. dumping the environment to exfiltrate secrets) is blocked
    and recorded as a durable blocked_attempt."""
    # The allowlist check (the property under test) is independent of the execution
    # backend; pin host so the permitted command runs in-process without Docker.
    monkeypatch.setattr("aios.runtime.worker_api.config.APPROVED_EXECUTION_BACKEND", "host")
    workspace = _workspace(tmp_path)
    runtime_root = tmp_path / "runtime"
    allowed_cmd = f"{sys.executable} -c \"print('verification ok')\""
    contract = _mission(
        workspace,
        allowed_tools=["read_file", "write_file", "run_command"],
        verification_commands=[allowed_cmd],
    )
    runtime = WorkerRuntime(
        contract,
        worker_id="worker-cmd",
        runtime_root=runtime_root,
        result_path=runtime_root / "result.json",
    )

    # The declared verification command is permitted.
    result = runtime.run_command(shlex.split(allowed_cmd, posix=os.name != "nt"))
    assert result["returncode"] == 0

    # An undeclared command is fail-closed blocked, even though run_command is
    # an allowed tool — this is the regression the review flagged.
    with pytest.raises(ContractViolation):
        runtime.run_command([sys.executable, "-c", "import os; print(dict(os.environ))"])
    assert any(
        attempt["tool"] == "run_command"
        and "verification_commands" in attempt["reason"]
        for attempt in runtime.blocked_attempts
    )


def test_restricted_environment_sets_worker_sandbox_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The spawner flags the worker as sandboxed so aios.config skips dotenv."""
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "bearer-secret-value")
    env = ControlledSubprocessBackend(tmp_path / "runtime")._restricted_environment()
    assert env["AIOS_WORKER_SANDBOX"] == "1"
    assert "AWS_BEARER_TOKEN_BEDROCK" not in env


def test_config_skips_dotenv_inside_worker_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Closes the load_dotenv re-injection hole: with the sandbox flag set,
    aios.config must not re-read .env (which would restore scrubbed secrets)."""
    import aios.config as config_module

    monkeypatch.setenv("AIOS_WORKER_SANDBOX", "1")
    assert config_module._worker_sandbox_active() is True
    monkeypatch.delenv("AIOS_WORKER_SANDBOX", raising=False)
    assert config_module._worker_sandbox_active() is False


def test_spawner_refuses_duplicate_mission_id(tmp_path: Path) -> None:
    """A second run with the same mission_id is fail-closed, so it cannot
    silently clobber the first run's ledger/report artifacts."""
    workspace = _workspace(tmp_path)
    runtime_root = tmp_path / "runtime"
    contract = _mission(workspace)

    asyncio.run(WorkerSpawner(runtime_root=runtime_root).run(contract))
    with pytest.raises(MissionCollisionError):
        asyncio.run(WorkerSpawner(runtime_root=runtime_root).run(contract))


def test_snapshot_manager_refuses_existing_git_workspace(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace / ".git").mkdir()
    contract = _mission(workspace, mission_id="mission-existing-git")

    with pytest.raises(RollbackError, match="already contains a .git"):
        SnapshotManager(tmp_path / "runtime").create_snapshot(contract)
