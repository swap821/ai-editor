"""Coverage-gap tests for six Council Runtime modules.

Targets specific missed/partial line regions in:
  - aios/runtime/worker_entry.py
  - aios/runtime/worker_api.py
  - aios/runtime/backends.py
  - aios/runtime/budget_guard.py
  - aios/runtime/intelligence_gateway.py
  - aios/runtime/king_report.py

All fakes follow the patterns already established in tests/test_worker*.py,
tests/test_runtime_real_worker.py, and tests/test_runtime_intelligence_gateway.py:
in-process calls with injected gateways/command_runners, no network, no Docker,
no real subprocess spawns except where asyncio.create_subprocess_exec itself is
monkeypatched (mirrors how test_runtime_worker_container.py monkeypatches the
executor's process runner rather than shelling out for real).
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from aios.runtime import backends as backends_module
from aios.runtime.backends import ControlledSubprocessBackend, WorkerHandle
from aios.runtime.budget_guard import BudgetGuard
from aios.runtime.contracts import (
    KingReport,
    MissionContract,
    QueenVerdict,
    RunLedger,
    WorkerResult,
)
from aios.runtime.intelligence_gateway import (
    IntelligenceGateway,
    IntelligenceGatewayError,
    IntelligenceRequest,
    LocalOllamaReasoner,
)
from aios.runtime.king_report import _latest_intelligence, build_king_report
from aios.runtime.worker_api import ContractViolation, WorkerRuntime
from aios.runtime.worker_entry import (
    _default_forbidden_probe,
    _run_llm_worker,
    _strip_code_fences,
    main,
    run_worker,
)


# --------------------------------------------------------------------------
# Shared fixtures / helpers
# --------------------------------------------------------------------------


def _workspace(tmp_path: Path, *, target: str = "frontend/src/pages/Login.jsx") -> Path:
    workspace = tmp_path / "workspace"
    file_path = workspace / target
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("export function Login() { return null; }\n", encoding="utf-8")
    return workspace


def _contract(workspace: Path, **overrides: object) -> MissionContract:
    data: dict[str, object] = {
        "mission_id": "mission-gaps",
        "goal": "Exercise runtime coverage gaps.",
        "worker_type": "deterministic_worker",
        "created_by": "planner",
        "workspace_root": str(workspace),
        "allowed_files": ["frontend/src/pages/Login.jsx"],
        "forbidden_files": ["backend/", ".env", "aios/security/"],
        "allowed_tools": ["read_file", "write_file", "run_command"],
        "timeout_seconds": 30,
        "max_steps": 12,
        "verification_commands": [f"{sys.executable} -m pytest --version"],
        "metadata": {"deterministic_forbidden_probe": "backend/secret.py"},
    }
    data.update(overrides)
    return MissionContract(**data)  # type: ignore[arg-type]


def _runtime(
    contract: MissionContract,
    tmp_path: Path,
    *,
    intelligence_gateway=None,
    command_runner=None,
    worker_id: str = "worker-gaps",
) -> WorkerRuntime:
    runtime_root = tmp_path / "runtime"
    return WorkerRuntime(
        contract,
        worker_id=worker_id,
        runtime_root=runtime_root,
        result_path=runtime_root / "result.json",
        intelligence_gateway=intelligence_gateway,
        command_runner=command_runner,
    )


class _FakeIntelligenceResponse:
    def __init__(self, text: str, *, provider: str = "fake") -> None:
        self.text = text
        self.provider = provider
        self.model = "fake-model"
        self.used_cloud = False
        self.fallback_used = False

    def model_dump(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "used_cloud": self.used_cloud,
            "text": self.text,
            "fallback_used": self.fallback_used,
        }


class QueuedGateway:
    """Returns queued texts per call; can raise IntelligenceGatewayError from an
    index onward, mirroring FakeGateway in test_runtime_real_worker.py."""

    def __init__(self, contents: list[str], *, raise_from: int | None = None) -> None:
        self._contents = contents
        self._raise_from = raise_from
        self.calls = 0

    def request(self, request, *, contract):  # noqa: ANN001 - matches gateway protocol
        idx = self.calls
        self.calls += 1
        if self._raise_from is not None and idx >= self._raise_from:
            raise IntelligenceGatewayError("fake reasoning offline")
        text = self._contents[idx] if idx < len(self._contents) else self._contents[-1]
        return _FakeIntelligenceResponse(text)


# ==========================================================================
# aios/runtime/worker_entry.py
# ==========================================================================


class TestDefaultForbiddenProbe:
    """Lines 33-40: the loop building a probe path from forbidden_files rules."""

    def test_directory_rule_with_trailing_slash_yields_blocked_probe(self) -> None:
        contract = _contract(Path("."), forbidden_files=["backend/"])
        probe = _default_forbidden_probe(contract)
        assert probe == "backend/blocked_probe.txt"

    def test_directory_rule_without_extension_yields_blocked_probe(self) -> None:
        # "aios/security" has no "." in the final path segment -> treated as a dir.
        contract = _contract(Path("."), forbidden_files=["aios/security"])
        probe = _default_forbidden_probe(contract)
        assert probe == "aios/security/blocked_probe.txt"

    def test_file_rule_is_returned_as_is(self) -> None:
        # A genuine dotted filename in the middle of the path (unaffected by the
        # lstrip("./") normalization, unlike a leading-dot name such as ".env").
        contract = _contract(Path("."), forbidden_files=["backend/secret.py"])
        probe = _default_forbidden_probe(contract)
        assert probe == "backend/secret.py"

    def test_blank_rule_is_skipped_in_favor_of_next(self) -> None:
        contract = _contract(Path("."), forbidden_files=["   ", "backend/"])
        probe = _default_forbidden_probe(contract)
        assert probe == "backend/blocked_probe.txt"

    def test_no_forbidden_files_falls_back_to_default_probe(self) -> None:
        contract = _contract(Path("."), forbidden_files=[])
        probe = _default_forbidden_probe(contract)
        assert probe == "../outside-contract-probe.txt"

    def test_bare_dotfile_rule_is_preserved_not_corrupted(self) -> None:
        # Regression: ``.lstrip("./")`` strips a CHARACTER SET, not a literal
        # prefix, so a bare dotfile rule like ".env" loses its leading "."
        # (-> "env"), which then has no "." in its name and is (mis)treated as
        # a directory -- probing "env/blocked_probe.txt" instead of the real
        # forbidden file ".env" the rule was meant to guard.
        contract = _contract(Path("."), forbidden_files=[".env"])
        probe = _default_forbidden_probe(contract)
        assert probe == ".env"

    def test_dotfile_rule_nested_in_a_directory_is_unaffected(self) -> None:
        # Sanity check: a dotfile that doesn't START with "." (nested under a
        # directory) was never corrupted by the character-strip; this locks
        # in that the fix doesn't change this already-correct case.
        contract = _contract(Path("."), forbidden_files=["secrets/.env"])
        probe = _default_forbidden_probe(contract)
        assert probe == "secrets/.env"


class TestStripCodeFences:
    """Lines 48-53: fence stripping when the model wraps its output."""

    def test_text_without_fence_is_returned_unchanged(self) -> None:
        text = "plain content\n"
        assert _strip_code_fences(text) == text

    def test_fenced_block_with_trailing_newline_is_unwrapped(self) -> None:
        # The input already ends with "\n", so the trailing-newline ternary adds
        # nothing back after "\n".join drops the closing fence line's newline.
        text = "```python\nprint('hi')\n```\n"
        result = _strip_code_fences(text)
        assert result == "print('hi')"

    def test_fenced_block_without_trailing_newline_gets_one_appended(self) -> None:
        text = "```\ncontent line\n```"
        result = _strip_code_fences(text)
        # original text did not end with \n -> a trailing \n is appended
        assert result == "content line\n"
        assert result.endswith("\n")


class TestRunLlmWorkerDirectCalls:
    """_run_llm_worker branches reached by calling the function directly."""

    def test_missing_allowed_files_raises_contract_violation(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path)
        contract = _contract(
            workspace,
            allowed_files=[],
            allowed_tools=["read_file", "write_file", "run_command", "request_change"],
        )
        runtime = _runtime(contract, tmp_path, intelligence_gateway=QueuedGateway(["x"]))

        code = _run_llm_worker(
            runtime=runtime, contract=contract, worker_id="worker-gaps", started_at="t0"
        )

        assert code == 1
        result = WorkerResult.model_validate_json(runtime.result_path.read_text(encoding="utf-8"))
        assert result.status == "contract_violation"
        assert "at least one allowed file" in result.summary

    def test_gateway_fails_on_repair_after_one_recorded_attempt(self, tmp_path: Path) -> None:
        """attempt 0 succeeds (writes content) but verification fails, then attempt 1
        (repair) raises IntelligenceGatewayError -> the "attempts already recorded"
        branch (gateway_error set with non-empty attempts)."""
        workspace = _workspace(tmp_path)
        (workspace / "check_fail.py").write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
        contract = _contract(
            workspace,
            allowed_tools=["read_file", "write_file", "run_command", "request_change"],
            verification_commands=[f"{sys.executable} check_fail.py"],
        )
        gateway = QueuedGateway(["content v1"], raise_from=1)
        runtime = _runtime(
            contract,
            tmp_path,
            intelligence_gateway=gateway,
            command_runner=None,
        )
        # Verification is allowed to actually run on host for this in-process test.
        from aios.core.executor import _default_runner

        runtime._command_runner = _default_runner

        code = _run_llm_worker(
            runtime=runtime, contract=contract, worker_id="worker-gaps", started_at="t0"
        )

        assert code == 1
        result = WorkerResult.model_validate_json(runtime.result_path.read_text(encoding="utf-8"))
        assert result.status == "failed"
        assert "reasoning failed after 1 attempt(s)" in result.summary
        assert gateway.calls == 2

    def test_passed_but_forbidden_probe_not_blocked_is_contract_violation(
        self, tmp_path: Path
    ) -> None:
        """If the forbidden probe path is actually allowed (readable), the worker
        cannot claim completion even though verification passed."""
        workspace = _workspace(tmp_path)
        # A script file (no embedded quoting) avoids the Windows shlex
        # quote-retention quirk that a "-c \"...\"" one-liner hits when re-parsed
        # by the host runner (see test_runtime_worker_container.py's comment).
        (workspace / "check_ok.py").write_text("pass\n", encoding="utf-8")
        contract = _contract(
            workspace,
            allowed_files=["frontend/src/pages/Login.jsx", "backend/secret.py"],
            allowed_tools=["read_file", "write_file", "run_command", "request_change"],
            forbidden_files=[],  # nothing forbidden -> probe read succeeds
            max_steps=50,  # generous: a passing loop with default max_repairs need not race the cap
            verification_commands=[f"{sys.executable} check_ok.py"],
            metadata={
                "deterministic_forbidden_probe": "backend/secret.py",
                "max_repairs": 0,
            },
        )
        secret = workspace / "backend" / "secret.py"
        secret.parent.mkdir(parents=True)
        secret.write_text("not actually secret\n", encoding="utf-8")

        gateway = QueuedGateway(["new content"])
        runtime = _runtime(contract, tmp_path, intelligence_gateway=gateway)
        from aios.core.executor import _default_runner

        runtime._command_runner = _default_runner

        code = _run_llm_worker(
            runtime=runtime, contract=contract, worker_id="worker-gaps", started_at="t0"
        )

        assert code == 1
        result = WorkerResult.model_validate_json(runtime.result_path.read_text(encoding="utf-8"))
        assert result.status == "contract_violation"
        assert "Forbidden probe was not blocked" in result.summary
        assert result.risk_after == "RED"


class TestRunWorkerDispatchAndDeterministicPath:
    """run_worker(): dispatch to the LLM path, and deterministic-path branches
    (empty allowed_files/verification_commands, plan-in-comment, failed
    verification, contract_violation except-block)."""

    def test_run_worker_dispatches_to_llm_worker_when_reasoning_enabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No allowed_files -> _run_llm_worker raises ContractViolation immediately,
        # before ever touching the IntelligenceGateway, so this stays network-free
        # while still exercising the dispatch line in run_worker.
        monkeypatch.setattr("aios.config.WORKER_REASONING", True)
        workspace = _workspace(tmp_path)
        contract = _contract(
            workspace,
            allowed_files=[],
            allowed_tools=["read_file", "write_file", "run_command", "request_change"],
        )
        contract_path = tmp_path / "contract.json"
        result_path = tmp_path / "result.json"
        contract_path.write_text(contract.model_dump_json(), encoding="utf-8")

        code = run_worker(
            contract_path=contract_path,
            result_path=result_path,
            worker_id="worker-dispatch",
            runtime_root=tmp_path / "runtime",
        )

        assert code == 1
        result = WorkerResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        assert result.status == "contract_violation"

    def test_deterministic_worker_requires_allowed_files(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path)
        contract = _contract(workspace, allowed_files=[])
        contract_path = tmp_path / "contract.json"
        result_path = tmp_path / "result.json"
        contract_path.write_text(contract.model_dump_json(), encoding="utf-8")

        code = run_worker(
            contract_path=contract_path,
            result_path=result_path,
            worker_id="worker-detfiles",
            runtime_root=tmp_path / "runtime",
        )

        assert code == 1
        result = WorkerResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        assert result.status == "contract_violation"
        assert "needs one allowed file" in result.summary

    def test_deterministic_worker_requires_verification_commands(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path)
        contract = _contract(workspace, verification_commands=[])
        contract_path = tmp_path / "contract.json"
        result_path = tmp_path / "result.json"
        contract_path.write_text(contract.model_dump_json(), encoding="utf-8")

        code = run_worker(
            contract_path=contract_path,
            result_path=result_path,
            worker_id="worker-detverif",
            runtime_root=tmp_path / "runtime",
        )

        assert code == 1
        result = WorkerResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        assert result.status == "contract_violation"
        assert "requires verification_commands" in result.summary

    def test_deterministic_worker_includes_plan_first_line_in_comment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exercises the hybrid plan_text -> comment enrichment branch, using the
        established pattern (monkeypatch aios.runtime.worker_api.IntelligenceGateway)
        from test_runtime_intelligence_gateway.py so no real Ollama call happens."""
        workspace = _workspace(tmp_path)
        target = workspace / "frontend/src/pages/Login.jsx"

        class PatchedGateway:
            def request(self, request, *, contract):  # noqa: ANN001
                return _FakeIntelligenceResponse(
                    "Line one of the plan.\nMore detail follows."
                )

        monkeypatch.setattr(
            "aios.runtime.worker_api.IntelligenceGateway", PatchedGateway
        )
        monkeypatch.setattr(
            "aios.runtime.worker_api.config.APPROVED_EXECUTION_BACKEND", "host"
        )
        contract = _contract(
            workspace,
            allowed_tools=["request_plan", "read_file", "write_file", "run_command"],
            metadata={
                "deterministic_forbidden_probe": "backend/secret.py",
                "hybrid_plan_prompt": "Plan the edit",
                "include_plan_in_comment": True,
            },
        )
        contract_path = tmp_path / "contract.json"
        result_path = tmp_path / "result.json"
        contract_path.write_text(contract.model_dump_json(), encoding="utf-8")

        code = run_worker(
            contract_path=contract_path,
            result_path=result_path,
            worker_id="worker-plan-comment",
            runtime_root=tmp_path / "runtime",
        )

        assert code == 0
        result = WorkerResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        assert result.status == "completed"
        content = target.read_text(encoding="utf-8")
        assert "plan: Line one of the plan." in content

    def test_deterministic_worker_reports_failed_on_verification_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "aios.runtime.worker_api.config.APPROVED_EXECUTION_BACKEND", "host"
        )
        workspace = _workspace(tmp_path)
        (workspace / "fail.py").write_text("import sys\nsys.exit(2)\n", encoding="utf-8")
        contract = _contract(
            workspace,
            verification_commands=[f"{sys.executable} fail.py"],
        )
        contract_path = tmp_path / "contract.json"
        result_path = tmp_path / "result.json"
        contract_path.write_text(contract.model_dump_json(), encoding="utf-8")

        code = run_worker(
            contract_path=contract_path,
            result_path=result_path,
            worker_id="worker-detfail",
            runtime_root=tmp_path / "runtime",
        )

        assert code == 1
        result = WorkerResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        assert result.status == "failed"
        assert "verification failed" in result.summary

    def test_deterministic_worker_contract_violation_except_block(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Forces a ContractViolation to be raised from inside the try block (via
        write_file targeting a file outside allowed_files), reaching the
        except ContractViolation branch of the deterministic path directly (not via
        subprocess), which is otherwise invisible to coverage."""
        monkeypatch.setattr(
            "aios.runtime.worker_api.config.APPROVED_EXECUTION_BACKEND", "host"
        )
        workspace = _workspace(tmp_path)
        contract = _contract(
            workspace,
            metadata={
                "deterministic_forbidden_probe": "backend/secret.py",
                "deterministic_target_file": "not/allowed/path.txt",
            },
        )
        contract_path = tmp_path / "contract.json"
        result_path = tmp_path / "result.json"
        contract_path.write_text(contract.model_dump_json(), encoding="utf-8")

        code = run_worker(
            contract_path=contract_path,
            result_path=result_path,
            worker_id="worker-detviolation",
            runtime_root=tmp_path / "runtime",
        )

        assert code == 1
        result = WorkerResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        assert result.status == "contract_violation"
        assert result.risk_after == "RED"
        assert "not/allowed/path.txt" in json.dumps(result.evidence)


class TestMainEntrypoint:
    """Lines 372-379: argparse wiring in main()."""

    def test_main_parses_argv_and_returns_run_worker_exit_code(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path)
        # allowed_files empty -> fast, deterministic ContractViolation, no reasoning.
        contract = _contract(workspace, allowed_files=[])
        contract_path = tmp_path / "contract.json"
        result_path = tmp_path / "result.json"
        contract_path.write_text(contract.model_dump_json(), encoding="utf-8")
        runtime_root = tmp_path / "runtime"

        code = main(
            [
                "--contract",
                str(contract_path),
                "--result",
                str(result_path),
                "--worker-id",
                "worker-main",
                "--runtime-root",
                str(runtime_root),
            ]
        )

        assert code == 1
        assert result_path.exists()
        result = WorkerResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        assert result.status == "contract_violation"
        assert result.worker_id == "worker-main"


# ==========================================================================
# aios/runtime/worker_api.py
# ==========================================================================


class TestRunnerForBackendAndRunCommand:
    def test_unsupported_backend_yields_failed_closed_result(self, tmp_path: Path) -> None:
        """_runner_for_backend returns None for anything other than "container";
        run_command must then fail closed rather than silently falling back."""
        workspace = _workspace(tmp_path)
        contract = _contract(
            workspace,
            allowed_tools=["run_command"],
            verification_commands=["echo ok"],
        )
        runtime = _runtime(contract, tmp_path)
        monkeypatch_backend = "totally-unsupported-backend"
        import aios.runtime.worker_api as worker_api_module

        original = worker_api_module.config.APPROVED_EXECUTION_BACKEND
        worker_api_module.config.APPROVED_EXECUTION_BACKEND = monkeypatch_backend
        try:
            result = runtime.run_command(["echo", "ok"])
        finally:
            worker_api_module.config.APPROVED_EXECUTION_BACKEND = original

        assert result["returncode"] == 1
        assert "not supported" in result["stderr"]

    def test_injected_runner_timeout_propagates(self, tmp_path: Path) -> None:
        import subprocess

        def boom_timeout(command, *, cwd, env, timeout_s):
            raise subprocess.TimeoutExpired(cmd=command, timeout=timeout_s)

        workspace = _workspace(tmp_path)
        contract = _contract(
            workspace,
            allowed_tools=["run_command"],
            verification_commands=["echo ok"],
        )
        runtime = _runtime(contract, tmp_path, command_runner=boom_timeout)

        with pytest.raises(subprocess.TimeoutExpired):
            runtime.run_command(["echo", "ok"])

    def test_host_backend_subprocess_timeout_propagates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import subprocess

        monkeypatch.setattr(
            "aios.runtime.worker_api.config.APPROVED_EXECUTION_BACKEND", "host"
        )
        workspace = _workspace(tmp_path)
        # A script file (no embedded spaces/quoting) sidesteps the Windows shlex
        # quote-retention quirk noted in test_runtime_worker_container.py.
        sleeper = workspace / "sleep_long.py"
        sleeper.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
        cmd = [sys.executable, "sleep_long.py"]
        cmd_str = f"{sys.executable} sleep_long.py"
        contract = _contract(
            workspace,
            allowed_tools=["run_command"],
            verification_commands=[cmd_str],
            timeout_seconds=0,
        )
        runtime = _runtime(contract, tmp_path)

        with pytest.raises(subprocess.TimeoutExpired):
            runtime.run_command(cmd)

    def test_host_backend_launch_failure_reports_cleanly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import subprocess

        monkeypatch.setattr(
            "aios.runtime.worker_api.config.APPROVED_EXECUTION_BACKEND", "host"
        )

        def boom(*args, **kwargs):
            raise OSError("executable not found")

        monkeypatch.setattr(subprocess, "run", boom)
        workspace = _workspace(tmp_path)
        contract = _contract(
            workspace,
            allowed_tools=["run_command"],
            verification_commands=["definitely-not-a-real-binary --flag"],
        )
        runtime = _runtime(contract, tmp_path)

        result = runtime.run_command(["definitely-not-a-real-binary", "--flag"])

        assert result["returncode"] == 1
        assert "host verification failed to launch" in result["stderr"]

    def test_command_allowlist_skips_malformed_entries(self, tmp_path: Path) -> None:
        """A verification_commands entry with unbalanced quoting raises ValueError
        from shlex.split and must be skipped (continue), not crash the check."""
        workspace = _workspace(tmp_path)
        contract = _contract(
            workspace,
            allowed_tools=["run_command"],
            verification_commands=['unterminated "quote', "echo ok"],
        )
        runtime = _runtime(
            contract,
            tmp_path,
            command_runner=lambda *a, **k: ("stdout", "", 0),
        )

        result = runtime.run_command(["echo", "ok"])

        assert result["returncode"] == 0

    def test_run_command_blocks_empty_command(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path)
        contract = _contract(workspace, allowed_tools=["run_command"])
        runtime = _runtime(contract, tmp_path)

        with pytest.raises(ContractViolation, match="empty command"):
            runtime.run_command([])

    def test_run_command_blocks_non_string_parts(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path)
        contract = _contract(workspace, allowed_tools=["run_command"])
        runtime = _runtime(contract, tmp_path)

        with pytest.raises(ContractViolation, match="list of strings"):
            runtime.run_command(["echo", 123])  # type: ignore[list-item]


class TestReadFileNotFound:
    def test_read_file_missing_target_raises_and_records_failure(
        self, tmp_path: Path
    ) -> None:
        workspace = _workspace(tmp_path)
        contract = _contract(
            workspace,
            allowed_files=["frontend/src/pages/Login.jsx", "missing.txt"],
            allowed_tools=["read_file"],
        )
        runtime = _runtime(contract, tmp_path)

        with pytest.raises(FileNotFoundError):
            runtime.read_file("missing.txt")

        assert runtime.tool_calls[-1]["status"] == "failed"
        assert runtime.tool_calls[-1]["tool"] == "read_file"


class TestRequestApprovalPolling:
    def test_request_approval_returns_true_when_response_already_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pre-seeds the response file so the poll loop's first existence check
        succeeds immediately (no real sleeping needed)."""
        workspace = _workspace(tmp_path)
        contract = _contract(
            workspace,
            allowed_tools=["request_approval"],
            metadata={"approval_wait_seconds": 5},
        )
        runtime = _runtime(contract, tmp_path)
        # Guard against any accidental sleep actually blocking the test.
        monkeypatch.setattr("aios.runtime.worker_api.time.sleep", lambda _s: None)

        # request_approval computes request_id internally (uuid4-based) so we must
        # let it create the request file first via a controlled uuid, then drop the
        # matching response file before the poll loop starts. We patch uuid4 to a
        # fixed value to know the request_id up front.
        import uuid

        fixed = uuid.UUID("12345678123456781234567812345678")
        monkeypatch.setattr(
            "aios.runtime.worker_api.uuid.uuid4", lambda: fixed
        )
        approval_dir = runtime.approval_dir
        approval_dir.mkdir(parents=True, exist_ok=True)
        request_id = f"approval-{fixed.hex[:12]}"
        response_path = approval_dir / f"{request_id}.response.json"
        response_path.write_text(json.dumps({"approved": True}), encoding="utf-8")

        approved = runtime.request_approval("write_file", "please allow")

        assert approved is True
        assert runtime.tool_calls[-1]["status"] == "completed"


class TestFinishValidation:
    def _base_result(self, contract: MissionContract, **overrides: object) -> WorkerResult:
        data: dict[str, object] = {
            "mission_id": contract.mission_id,
            "worker_id": "worker-gaps",
            "status": "completed",
            "risk_after": "GREEN",
            "started_at": "2026-01-01T00:00:00+00:00",
            "ended_at": "2026-01-01T00:00:01+00:00",
        }
        data.update(overrides)
        return WorkerResult(**data)  # type: ignore[arg-type]

    def test_finish_rejects_mismatched_mission_id(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path)
        contract = _contract(workspace)
        runtime = _runtime(contract, tmp_path)
        bad_result = self._base_result(contract, mission_id="some-other-mission")

        with pytest.raises(ValueError, match="mission_id does not match"):
            runtime.finish(bad_result)

    def test_finish_rejects_mismatched_worker_id(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path)
        contract = _contract(workspace)
        runtime = _runtime(contract, tmp_path)
        bad_result = self._base_result(contract, worker_id="some-other-worker")

        with pytest.raises(ValueError, match="worker_id does not match"):
            runtime.finish(bad_result)


class TestBeginToolGuards:
    def test_max_steps_of_zero_blocks_the_first_tool_call(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path)
        contract = _contract(workspace, allowed_tools=["read_file"], max_steps=0)
        runtime = _runtime(contract, tmp_path)

        with pytest.raises(ContractViolation, match="max_steps exceeded"):
            runtime.read_file("frontend/src/pages/Login.jsx")

    def test_forbidden_tool_is_blocked_even_if_allowed(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path)
        contract = _contract(
            workspace,
            allowed_tools=["read_file"],
            forbidden_tools=["read_file"],
        )
        runtime = _runtime(contract, tmp_path)

        with pytest.raises(ContractViolation, match="forbidden by MissionContract"):
            runtime.read_file("frontend/src/pages/Login.jsx")


class TestMatchesAndResolveAllowedPath:
    def test_path_not_covered_by_any_allowed_rule_is_blocked(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path)
        (workspace / "other.txt").write_text("x", encoding="utf-8")
        contract = _contract(
            workspace,
            allowed_files=["frontend/src/pages/Login.jsx"],
            allowed_tools=["read_file"],
        )
        runtime = _runtime(contract, tmp_path)

        with pytest.raises(ContractViolation, match="not allowed by MissionContract"):
            runtime.read_file("other.txt")

    def test_glob_rule_matches_and_non_matching_glob_falls_through(
        self, tmp_path: Path
    ) -> None:
        workspace = _workspace(tmp_path)
        (workspace / "src").mkdir()
        (workspace / "src" / "a.py").write_text("x", encoding="utf-8")
        contract = _contract(
            workspace,
            # first rule is a non-matching glob (exercises fnmatch False -> continue),
            # second rule matches -> exercises fnmatch True -> return True.
            allowed_files=["docs/*.md", "src/*.py"],
            allowed_tools=["read_file"],
        )
        runtime = _runtime(contract, tmp_path)

        content = runtime.read_file("src/a.py")

        assert content == "x"

    def test_blank_rule_in_allowed_files_is_skipped(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path)
        contract = _contract(
            workspace,
            allowed_files=["   ", "frontend/src/pages/Login.jsx"],
            allowed_tools=["read_file"],
        )
        runtime = _runtime(contract, tmp_path)

        content = runtime.read_file("frontend/src/pages/Login.jsx")

        assert "Login" in content


# ==========================================================================
# aios/runtime/backends.py
# ==========================================================================


class _FakeProcess:
    """Minimal stand-in for asyncio.subprocess.Process."""

    def __init__(
        self,
        *,
        pid: int = 4321,
        communicate_result: tuple[bytes, bytes] | None = (b"out", b"err"),
        communicate_sleep: float | None = None,
        returncode: int | None = 0,
    ) -> None:
        self.pid = pid
        self._communicate_result = communicate_result
        self._communicate_sleep = communicate_sleep
        self.returncode = returncode
        self.killed = False
        self.waited = False

    async def communicate(self) -> tuple[bytes, bytes]:
        if self._communicate_sleep is not None:
            await asyncio.sleep(self._communicate_sleep)
        return self._communicate_result  # type: ignore[return-value]

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    async def wait(self) -> int:
        self.waited = True
        return self.returncode or 0


def _spawn_contract(workspace: Path, **overrides: object) -> MissionContract:
    data: dict[str, object] = {
        "mission_id": "mission-backend-gaps",
        "goal": "Exercise ControlledSubprocessBackend.",
        "worker_type": "deterministic_worker",
        "created_by": "planner",
        "workspace_root": str(workspace),
        "allowed_files": ["frontend/src/pages/Login.jsx"],
        "allowed_tools": ["read_file", "write_file"],
        "timeout_seconds": 30,
        "verification_commands": [f"{sys.executable} -c \"print('ok')\""],
    }
    data.update(overrides)
    return MissionContract(**data)  # type: ignore[arg-type]


class TestControlledSubprocessBackendReap:
    def test_reap_times_out_and_returns_timeout_result(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path)
        contract = _spawn_contract(workspace, timeout_seconds=0)
        backend = ControlledSubprocessBackend(tmp_path / "runtime")
        handle = WorkerHandle(
            worker_id="worker-timeout",
            mission_id=contract.mission_id,
            backend=backend.backend_name,
            contract_path=str(_write_contract(tmp_path, contract)),
            result_path=str(tmp_path / "result.json"),
        )
        fake_process = _FakeProcess(communicate_sleep=5)
        backend._processes[handle.worker_id] = fake_process  # type: ignore[assignment]

        result = asyncio.run(backend.reap(handle))

        assert handle.status == "killed"
        assert result.status == "timeout"
        assert fake_process.killed is True
        assert fake_process.waited is True

    def test_reap_reports_missing_result_when_process_exits_without_writing_it(
        self, tmp_path: Path
    ) -> None:
        workspace = _workspace(tmp_path)
        contract = _spawn_contract(workspace)
        backend = ControlledSubprocessBackend(tmp_path / "runtime")
        missing_result_path = tmp_path / "never-written-result.json"
        handle = WorkerHandle(
            worker_id="worker-silent",
            mission_id=contract.mission_id,
            backend=backend.backend_name,
            contract_path=str(_write_contract(tmp_path, contract)),
            result_path=str(missing_result_path),
        )
        fake_process = _FakeProcess(communicate_result=(b"", b""))
        backend._processes[handle.worker_id] = fake_process  # type: ignore[assignment]

        result = asyncio.run(backend.reap(handle))

        assert handle.status == "dead"
        assert result.status == "failed"
        assert "exited without writing WorkerResult" in result.summary
        assert not missing_result_path.exists()

    def test_reap_with_no_handle_result_path_treats_result_as_missing(
        self, tmp_path: Path
    ) -> None:
        """handle.result_path=None -> the ternary yields result_path=None, which
        must be handled the same as a non-existent file (else-branch)."""
        workspace = _workspace(tmp_path)
        contract = _spawn_contract(workspace)
        backend = ControlledSubprocessBackend(tmp_path / "runtime")
        handle = WorkerHandle(
            worker_id="worker-no-result-path",
            mission_id=contract.mission_id,
            backend=backend.backend_name,
            contract_path=str(_write_contract(tmp_path, contract)),
            result_path=None,
        )
        fake_process = _FakeProcess(communicate_result=(b"", b""))
        backend._processes[handle.worker_id] = fake_process  # type: ignore[assignment]

        result = asyncio.run(backend.reap(handle))

        assert result.status == "failed"
        assert "exited without writing WorkerResult" in result.summary


class TestControlledSubprocessBackendKillAndLoadContract:
    def test_kill_terminates_a_still_running_registered_process(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exercises spawn() with asyncio.create_subprocess_exec monkeypatched (no
        real process launched), then kill() on the registered fake process."""
        workspace = _workspace(tmp_path)
        contract = _spawn_contract(workspace, mission_id="mission-kill")
        backend = ControlledSubprocessBackend(tmp_path / "runtime")
        fake_process = _FakeProcess(returncode=None)

        async def fake_create_subprocess_exec(*args, **kwargs):
            return fake_process

        monkeypatch.setattr(
            backends_module.asyncio,
            "create_subprocess_exec",
            fake_create_subprocess_exec,
        )

        handle = asyncio.run(backend.spawn(contract))
        asyncio.run(backend.kill(handle, "operator abort"))

        assert handle.status == "killed"
        assert fake_process.killed is True
        assert fake_process.waited is True
        assert handle.worker_id not in backend._processes

    def test_kill_is_a_noop_when_process_already_finished(self, tmp_path: Path) -> None:
        workspace = _workspace(tmp_path)
        contract = _spawn_contract(workspace, mission_id="mission-kill-done")
        backend = ControlledSubprocessBackend(tmp_path / "runtime")
        fake_process = _FakeProcess(returncode=0)
        handle = WorkerHandle(
            worker_id="worker-done",
            mission_id=contract.mission_id,
            backend=backend.backend_name,
        )
        backend._processes[handle.worker_id] = fake_process  # type: ignore[assignment]

        asyncio.run(backend.kill(handle, "already done"))

        assert handle.status == "killed"
        assert fake_process.killed is False  # returncode was not None -> no kill()

    def test_load_contract_without_contract_path_raises(self, tmp_path: Path) -> None:
        backend = ControlledSubprocessBackend(tmp_path / "runtime")
        handle = WorkerHandle(
            worker_id="worker-nocontract",
            mission_id="mission-nocontract",
            backend=backend.backend_name,
            contract_path=None,
        )

        with pytest.raises(ValueError, match="no contract_path"):
            backend._load_contract(handle)


def _write_contract(tmp_path: Path, contract: MissionContract) -> Path:
    path = tmp_path / f"contract-{contract.mission_id}.json"
    path.write_text(contract.model_dump_json(), encoding="utf-8")
    return path


# ==========================================================================
# aios/runtime/budget_guard.py
# ==========================================================================


def _budget_contract(**metadata: object) -> MissionContract:
    return MissionContract(
        mission_id="mission-budget",
        goal="Exercise BudgetGuard branches.",
        worker_type="hybrid_plan_worker",
        created_by="planner",
        workspace_root=".",
        allowed_files=["x.txt"],
        metadata={"model_policy": metadata} if metadata else {},
    )


class TestBudgetGuardPolicyFor:
    def test_non_dict_model_policy_falls_back_to_defaults(self) -> None:
        contract = MissionContract(
            mission_id="mission-budget-baddict",
            goal="g",
            worker_type="hybrid_plan_worker",
            created_by="planner",
            workspace_root=".",
            allowed_files=["x.txt"],
            metadata={"model_policy": "not-a-dict"},
        )
        guard = BudgetGuard()

        policy = guard.policy_for(contract)

        assert policy.mode == "local"
        assert policy.allow_cloud is False


class TestBudgetGuardCheckCloudRequest:
    def test_denied_when_mode_is_local(self) -> None:
        guard = BudgetGuard()
        contract = _budget_contract(mode="local", allow_cloud=True, max_cloud_calls=5)

        decision = guard.check_cloud_request(contract, estimated_tokens=10)

        assert decision.allowed is False
        assert decision.reason == "cloud disabled by model_policy"

    def test_denied_when_allow_cloud_false(self) -> None:
        guard = BudgetGuard()
        contract = _budget_contract(mode="hybrid", allow_cloud=False)

        decision = guard.check_cloud_request(contract, estimated_tokens=10)

        assert decision.allowed is False
        assert decision.reason == "cloud disabled by model_policy"

    def test_denied_when_request_token_budget_exceeded(self) -> None:
        guard = BudgetGuard()
        contract = _budget_contract(
            mode="hybrid", allow_cloud=True, max_tokens_per_request=100, max_cloud_calls=5
        )

        decision = guard.check_cloud_request(contract, estimated_tokens=500)

        assert decision.allowed is False
        assert decision.reason == "request token budget exceeded"

    def test_denied_when_mission_token_total_budget_exceeded(self) -> None:
        guard = BudgetGuard()
        contract = _budget_contract(
            mode="hybrid",
            allow_cloud=True,
            max_cloud_calls=5,
            max_tokens_per_request=1000,
            max_tokens_total=100,
        )

        decision = guard.check_cloud_request(contract, estimated_tokens=500)

        assert decision.allowed is False
        assert decision.reason == "mission token budget exceeded"

    def test_denied_when_mission_cloud_cost_budget_exceeded(self) -> None:
        guard = BudgetGuard()
        contract = _budget_contract(
            mode="hybrid",
            allow_cloud=True,
            max_cloud_calls=5,
            max_tokens_per_request=1000,
            max_tokens_total=10000,
            mission_cloud_budget=1.0,
        )

        decision = guard.check_cloud_request(
            contract, estimated_tokens=10, estimated_cost=5.0
        )

        assert decision.allowed is False
        assert decision.reason == "mission cloud cost budget exceeded"

    def test_denied_when_daily_cloud_cost_budget_exceeded(self) -> None:
        guard = BudgetGuard()
        guard.daily_cost_total = 9.0
        contract = _budget_contract(
            mode="hybrid",
            allow_cloud=True,
            max_cloud_calls=5,
            max_tokens_per_request=1000,
            max_tokens_total=10000,
            daily_cloud_budget=10.0,
        )

        decision = guard.check_cloud_request(
            contract, estimated_tokens=10, estimated_cost=5.0
        )

        assert decision.allowed is False
        assert decision.reason == "daily cloud cost budget exceeded"

    def test_allowed_when_all_budgets_have_headroom(self) -> None:
        guard = BudgetGuard()
        contract = _budget_contract(
            mode="hybrid",
            allow_cloud=True,
            max_cloud_calls=5,
            max_tokens_per_request=1000,
            max_tokens_total=10000,
            mission_cloud_budget=100.0,
            daily_cloud_budget=100.0,
        )

        decision = guard.check_cloud_request(
            contract, estimated_tokens=10, estimated_cost=1.0
        )

        assert decision.allowed is True

    def test_optional_float_converts_a_real_numeric_value(self) -> None:
        guard = BudgetGuard()
        contract = _budget_contract(
            mode="hybrid",
            allow_cloud=True,
            max_cloud_calls=5,
            mission_cloud_budget="12.5",
        )

        policy = guard.policy_for(contract)

        assert policy.mission_cloud_budget == 12.5
        assert isinstance(policy.mission_cloud_budget, float)


# ==========================================================================
# aios/runtime/intelligence_gateway.py
# ==========================================================================


class _FakeReasoner:
    def __init__(self, text: str, *, fail: bool = False) -> None:
        self.text = text
        self.fail = fail
        self.calls: list[str] = []

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls.append(prompt)
        if self.fail:
            raise RuntimeError("provider offline")
        return self.text


def _gateway_contract(tmp_path: Path, **overrides: object) -> MissionContract:
    data: dict[str, object] = {
        "mission_id": "mission-gateway-gaps",
        "goal": "Exercise IntelligenceGateway branches.",
        "worker_type": "hybrid_plan_worker",
        "created_by": "planner",
        "workspace_root": str(tmp_path),
        "allowed_files": ["x.txt"],
        "risk_level": "YELLOW",
    }
    data.update(overrides)
    return MissionContract(**data)  # type: ignore[arg-type]


class TestLocalOllamaReasoner:
    def test_complete_delegates_to_injected_client(self) -> None:
        fake_client = _FakeReasoner("local answer")
        reasoner = LocalOllamaReasoner(client=fake_client, model="test-model")

        text = reasoner.complete("prompt", system="sys")

        assert text == "local answer"
        assert fake_client.calls == ["prompt"]


class TestIntelligenceGatewayRequestValidation:
    def test_mismatched_mission_id_raises_value_error(self, tmp_path: Path) -> None:
        gateway = IntelligenceGateway(local_client=_FakeReasoner("plan"))
        contract = _gateway_contract(tmp_path, mission_id="mission-a")
        request = IntelligenceRequest(
            mission_id="mission-b",
            worker_id="w",
            purpose="plan",
            prompt="do something",
            risk="YELLOW",
        )

        with pytest.raises(ValueError, match="mission_id does not match"):
            gateway.request(request, contract=contract)


class TestIntelligenceGatewayCloudFallback:
    def test_cloud_error_falls_back_to_local_and_records_cloud_error(
        self, tmp_path: Path
    ) -> None:
        local = _FakeReasoner("local fallback plan")
        cloud = _FakeReasoner("unused", fail=True)
        gateway = IntelligenceGateway(
            local_client=local, cloud_clients={"cloud": cloud}
        )
        contract = _gateway_contract(
            tmp_path,
            metadata={
                "model_policy": {
                    "mode": "hybrid",
                    "allow_cloud": True,
                    "max_cloud_calls": 5,
                    "max_tokens_per_request": 1500,
                    "max_tokens_total": 6000,
                    "provider": "cloud",
                }
            },
        )
        request = IntelligenceRequest(
            mission_id=contract.mission_id,
            worker_id="w",
            purpose="plan",
            prompt="plan something",
            risk="YELLOW",
            allow_cloud=True,
        )

        response = gateway.request(request, contract=contract)

        assert response.used_cloud is False
        assert response.text == "local fallback plan"
        assert response.policy["cloud_error"] == "provider offline"

    def test_local_failure_after_cloud_denied_raises_gateway_error(
        self, tmp_path: Path
    ) -> None:
        local = _FakeReasoner("unused", fail=True)
        gateway = IntelligenceGateway(local_client=local, cloud_clients={})
        contract = _gateway_contract(tmp_path)
        request = IntelligenceRequest(
            mission_id=contract.mission_id,
            worker_id="w",
            purpose="plan",
            prompt="plan something",
            risk="YELLOW",
            allow_cloud=False,
        )

        with pytest.raises(IntelligenceGatewayError, match="local reasoning provider failed"):
            gateway.request(request, contract=contract)


class TestCloudAllowedBranches:
    def test_cloud_denied_when_request_does_not_allow_cloud(self, tmp_path: Path) -> None:
        gateway = IntelligenceGateway(local_client=_FakeReasoner("plan"))
        contract = _gateway_contract(tmp_path, risk_level="GREEN")
        request = IntelligenceRequest(
            mission_id=contract.mission_id,
            worker_id="w",
            purpose="plan",
            prompt="p",
            risk="GREEN",
            allow_cloud=False,
        )

        allowed = gateway._cloud_allowed(
            request, contract, secret_cloud_allowed=True, budget_allowed=True
        )

        assert allowed is False

    def test_cloud_denied_when_risk_is_red(self, tmp_path: Path) -> None:
        gateway = IntelligenceGateway(local_client=_FakeReasoner("plan"))
        contract = _gateway_contract(tmp_path, risk_level="GREEN")
        request = IntelligenceRequest(
            mission_id=contract.mission_id,
            worker_id="w",
            purpose="plan",
            prompt="p",
            risk="RED",
            allow_cloud=True,
        )

        allowed = gateway._cloud_allowed(
            request, contract, secret_cloud_allowed=True, budget_allowed=True
        )

        assert allowed is False

    def test_choose_cloud_provider_falls_back_when_provider_missing(
        self, tmp_path: Path
    ) -> None:
        gateway = IntelligenceGateway(
            local_client=_FakeReasoner("plan"), default_cloud_provider="default-cloud"
        )
        contract = _gateway_contract(
            tmp_path, metadata={"model_policy": {"mode": "hybrid"}}
        )

        provider = gateway._choose_cloud_provider(contract)

        assert provider == "default-cloud"


# ==========================================================================
# aios/runtime/king_report.py
# ==========================================================================


def _ledger_contract(**overrides: object) -> MissionContract:
    data: dict[str, object] = {
        "mission_id": "mission-report-gaps",
        "goal": "Exercise KingReport branches.",
        "worker_type": "deterministic_worker",
        "created_by": "planner",
        "requires_approval": True,
        "workspace_root": ".",
        "allowed_files": ["x.txt"],
    }
    data.update(overrides)
    return MissionContract(**data)  # type: ignore[arg-type]


def _ledger(contract: MissionContract, **overrides: object) -> RunLedger:
    data: dict[str, object] = {
        "mission_id": contract.mission_id,
        "mission": contract.goal,
        "risk_before": "YELLOW",
        "risk_after": "YELLOW",
        "contract": contract,
        "status": "running",
        "created_at": "2026-01-01T00:00:00+00:00",
        # STRONG evidence keeps the human_summary free of the below-floor warning
        # prefix, so status-branch tests can assert the plain message directly.
        "verification": {"strength": "STRONG"},
    }
    data.update(overrides)
    return RunLedger(**data)  # type: ignore[arg-type]


def _worker_result(contract: MissionContract, **overrides: object) -> WorkerResult:
    data: dict[str, object] = {
        "mission_id": contract.mission_id,
        "worker_id": "worker-report",
        "status": "failed",
        "risk_after": "YELLOW",
        "started_at": "2026-01-01T00:00:00+00:00",
        "ended_at": "2026-01-01T00:00:01+00:00",
    }
    data.update(overrides)
    return WorkerResult(**data)  # type: ignore[arg-type]


class TestBuildKingReportStatusBranches:
    def test_awaiting_approval_status_produces_observe_recommendation(self) -> None:
        contract = _ledger_contract()
        ledger = _ledger(contract)
        result = _worker_result(contract, status="awaiting_approval")

        report = build_king_report(ledger=ledger, result=result)

        assert report.status == "awaiting_approval"
        assert report.recommendation == "observe"
        assert report.human_summary == "Worker is paused awaiting King approval."

    def test_killed_status_produces_rollback_recommendation(self) -> None:
        contract = _ledger_contract()
        ledger = _ledger(contract)
        result = _worker_result(contract, status="killed", risk_after="RED")

        report = build_king_report(ledger=ledger, result=result)

        assert report.status == "failed"
        assert report.recommendation == "rollback"
        assert report.human_summary == "Worker was killed before successful completion."


class TestLatestIntelligence:
    def test_returns_empty_dict_when_no_intelligence_recorded(self) -> None:
        contract = _ledger_contract()
        ledger = _ledger(contract, evidence={})

        assert _latest_intelligence(ledger) == {}

    def test_returns_empty_dict_when_latest_entry_is_not_a_dict(self) -> None:
        contract = _ledger_contract()
        ledger = _ledger(contract, evidence={"intelligence": ["not-a-dict"]})

        assert _latest_intelligence(ledger) == {}

    def test_extracts_fields_from_latest_dict_entry(self) -> None:
        contract = _ledger_contract()
        ledger = _ledger(
            contract,
            evidence={
                "intelligence": [
                    {"provider": "ollama", "model": "m1", "used_cloud": False},
                    {
                        "provider": "gemini",
                        "model": "m2",
                        "used_cloud": True,
                        "cost_estimate": 0.02,
                        "fallback_used": False,
                    },
                ]
            },
        )

        latest = _latest_intelligence(ledger)

        assert latest == {
            "provider": "gemini",
            "model": "m2",
            "used_cloud": True,
            "cost_estimate": 0.02,
            "fallback_used": False,
        }

    def test_build_king_report_surfaces_model_routing_from_latest_intelligence(
        self,
    ) -> None:
        contract = _ledger_contract(requires_approval=False)
        ledger = _ledger(
            contract,
            evidence={
                "intelligence": [
                    {"provider": "ollama", "model": "m1", "used_cloud": False}
                ]
            },
        )
        result = _worker_result(contract, status="completed", risk_after="GREEN")

        report = build_king_report(ledger=ledger, result=result)

        assert report.council_summary["model_routing"]["provider"] == "ollama"
