"""Tests for the LLM-driven real worker (think -> act -> verify -> repair).

Exercises _run_llm_worker in-process with a fake IntelligenceGateway, so the loop
is fully deterministic and needs neither Ollama nor a subprocess. Verification
commands run for real (a tiny check.py in the workspace) so the self-correction
loop is genuinely driven by observed pass/fail.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from aios.core.executor import _default_runner
from aios.runtime.contracts import MissionContract, WorkerResult
from aios.runtime.intelligence_gateway import IntelligenceGatewayError
from aios.runtime.worker_api import WorkerRuntime
from aios.runtime.worker_entry import _run_llm_worker

MARKER = "MISSION-DONE"
TARGET = "frontend/src/pages/Login.jsx"
WITH_MARKER = f"export function Login() {{ /* {MARKER} */ return null; }}\n"
NO_MARKER = "export function Login() { return null; }\n"


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.provider = "fake"
        self.model = "fake"
        self.used_cloud = False
        self.fallback_used = False

    def model_dump(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "used_cloud": False,
            "text": self.text,
            "fallback_used": False,
        }


class FakeGateway:
    """Returns queued contents per call; optionally raises from a given call index."""

    def __init__(self, contents: list[str], *, raise_from: int | None = None) -> None:
        self._contents = contents
        self._raise_from = raise_from
        self.calls = 0

    def request(self, request, *, contract):  # noqa: ANN001 - matches gateway signature
        idx = self.calls
        self.calls += 1
        if self._raise_from is not None and idx >= self._raise_from:
            raise IntelligenceGatewayError("fake reasoning offline")
        text = self._contents[idx] if idx < len(self._contents) else self._contents[-1]
        return _FakeResponse(text)


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    target = workspace / "frontend" / "src" / "pages" / "Login.jsx"
    target.parent.mkdir(parents=True)
    target.write_text(NO_MARKER, encoding="utf-8")
    # A real verification check: exit 0 iff the marker is present in the target.
    check = (
        "import io, sys\n"
        f"content = io.open({TARGET!r}, encoding='utf-8').read()\n"
        f"sys.exit(0 if {MARKER!r} in content else 1)\n"
    )
    (workspace / "check.py").write_text(check, encoding="utf-8")
    return workspace


def _contract(workspace: Path, **over: object) -> MissionContract:
    data: dict[str, object] = {
        "mission_id": "m-real-worker",
        "goal": "Add a MISSION-DONE marker comment to the Login component.",
        "worker_type": "llm_worker",
        "created_by": "planner",
        "workspace_root": str(workspace),
        "allowed_files": [TARGET],
        "forbidden_files": ["backend/", ".env", "aios/security/"],
        "allowed_tools": ["read_file", "write_file", "run_command", "request_change"],
        "timeout_seconds": 30,
        "max_steps": 30,
        "verification_commands": [f"{sys.executable} check.py"],
        "metadata": {"deterministic_forbidden_probe": "backend/secret.py"},
    }
    data.update(over)
    return MissionContract(**data)  # type: ignore[arg-type]


def _runtime(contract: MissionContract, gateway: FakeGateway, tmp_path: Path) -> WorkerRuntime:
    runtime_root = tmp_path / "runtime"
    return WorkerRuntime(
        contract,
        worker_id="worker-real",
        runtime_root=runtime_root,
        result_path=runtime_root / "result.json",
        intelligence_gateway=gateway,
        # These tests exercise the think->act->verify LOOP with real verification
        # in-process; the isolation backend is orthogonal (Phase 2b) and there is no
        # Docker in CI, so run verification on the host runner explicitly.
        command_runner=_default_runner,
    )


def _result(runtime: WorkerRuntime) -> WorkerResult:
    return WorkerResult.model_validate_json(
        Path(runtime.result_path).read_text(encoding="utf-8")
    )


def test_worker_completes_on_first_attempt(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    contract = _contract(workspace)
    gateway = FakeGateway([WITH_MARKER])
    runtime = _runtime(contract, gateway, tmp_path)

    code = _run_llm_worker(
        runtime=runtime, contract=contract, worker_id="worker-real", started_at="t0"
    )

    assert code == 0
    result = _result(runtime)
    assert result.status == "completed"
    assert MARKER in (workspace / "frontend/src/pages/Login.jsx").read_text(encoding="utf-8")
    assert gateway.calls == 1  # no repair needed


def test_worker_self_corrects_after_failed_verification(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    contract = _contract(workspace)
    # Attempt 0 lacks the marker -> check.py fails -> repair attempt 1 adds it.
    gateway = FakeGateway([NO_MARKER, WITH_MARKER])
    runtime = _runtime(contract, gateway, tmp_path)

    code = _run_llm_worker(
        runtime=runtime, contract=contract, worker_id="worker-real", started_at="t0"
    )

    assert code == 0
    result = _result(runtime)
    assert result.status == "completed"
    assert gateway.calls == 2  # one repair
    llm_attempts = result.evidence["llm_worker"]["attempts"]
    assert [a["purpose"] for a in llm_attempts] == ["plan", "repair"]


def test_worker_reports_failed_when_repairs_exhausted(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    contract = _contract(workspace, metadata={
        "deterministic_forbidden_probe": "backend/secret.py",
        "max_repairs": 1,
    })
    gateway = FakeGateway([NO_MARKER, NO_MARKER])  # never satisfies verification
    runtime = _runtime(contract, gateway, tmp_path)

    code = _run_llm_worker(
        runtime=runtime, contract=contract, worker_id="worker-real", started_at="t0"
    )

    assert code == 1
    result = _result(runtime)
    assert result.status == "failed"
    assert gateway.calls == 2  # max_repairs=1 -> 2 attempts
    assert result.evidence["llm_worker"]["passed"] is False


def test_worker_requires_request_change_tool_authority(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    contract = _contract(
        workspace,
        allowed_tools=["read_file", "write_file", "run_command"],
    )
    gateway = FakeGateway([WITH_MARKER])
    runtime = _runtime(contract, gateway, tmp_path)

    code = _run_llm_worker(
        runtime=runtime, contract=contract, worker_id="worker-real", started_at="t0"
    )

    assert code == 1
    result = _result(runtime)
    assert result.status == "contract_violation"
    assert result.evidence["blocked_attempts"][-1]["tool"] == "request_change"
    assert gateway.calls == 0


def test_worker_cannot_write_outside_scope(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    # Point the worker at an out-of-scope target; even with reasoning it must be blocked.
    contract = _contract(workspace, metadata={
        "deterministic_forbidden_probe": "backend/secret.py",
        "deterministic_target_file": "backend/evil.py",
    })
    gateway = FakeGateway(["malicious content"])
    runtime = _runtime(contract, gateway, tmp_path)

    code = _run_llm_worker(
        runtime=runtime, contract=contract, worker_id="worker-real", started_at="t0"
    )

    assert code == 1
    result = _result(runtime)
    assert result.status == "contract_violation"
    assert not (workspace / "backend" / "evil.py").exists()


def test_worker_refuses_without_verification_commands(tmp_path: Path) -> None:
    """Fail-closed: no verification_commands -> cannot honestly confirm -> never
    'completed'. (Closes the empty-verification false-success the review found.)"""
    workspace = _workspace(tmp_path)
    contract = _contract(workspace, verification_commands=[])
    gateway = FakeGateway([WITH_MARKER])
    runtime = _runtime(contract, gateway, tmp_path)

    code = _run_llm_worker(
        runtime=runtime, contract=contract, worker_id="worker-real", started_at="t0"
    )

    assert code == 1
    assert _result(runtime).status == "contract_violation"
    assert gateway.calls == 0  # bailed before generating/writing anything
    assert MARKER not in (workspace / "frontend/src/pages/Login.jsx").read_text(encoding="utf-8")


def test_worker_rejects_oversized_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """DoS guard: content exceeding WORKER_MAX_FILE_BYTES is refused, not written."""
    monkeypatch.setattr("aios.config.WORKER_MAX_FILE_BYTES", 1000)
    workspace = _workspace(tmp_path)
    contract = _contract(workspace)
    gateway = FakeGateway(["x" * 5000])
    runtime = _runtime(contract, gateway, tmp_path)

    code = _run_llm_worker(
        runtime=runtime, contract=contract, worker_id="worker-real", started_at="t0"
    )

    assert code == 1
    assert _result(runtime).status == "contract_violation"
    # the oversized content was never written to disk
    assert len((workspace / "frontend/src/pages/Login.jsx").read_text(encoding="utf-8")) < 1000


def test_worker_fails_honestly_when_reasoning_unavailable(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    contract = _contract(workspace)
    gateway = FakeGateway([WITH_MARKER], raise_from=0)  # offline from the first call
    runtime = _runtime(contract, gateway, tmp_path)

    code = _run_llm_worker(
        runtime=runtime, contract=contract, worker_id="worker-real", started_at="t0"
    )

    assert code == 1
    result = _result(runtime)
    assert result.status == "failed"
    assert "reasoning unavailable" in result.summary
    # The target was never falsely edited to claim success.
    assert MARKER not in (workspace / "frontend/src/pages/Login.jsx").read_text(encoding="utf-8")
