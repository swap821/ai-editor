"""Worker backend abstractions for Council Runtime v0.1.

The first backend is intentionally modest: a controlled Python subprocess
running the deterministic worker entrypoint. It is a policy-isolation boundary,
not an OS sandbox.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from aios.runtime.contracts import MissionContract, WorkerResult
from aios.runtime.secret_policy import SecretPolicy

WorkerHandleStatus = Literal[
    "born",
    "running",
    "awaiting_approval",
    "dead",
    "killed",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class WorkerHandle:
    worker_id: str
    mission_id: str
    backend: str
    pid: int | None = None
    result_path: str | None = None
    status: WorkerHandleStatus = "born"
    contract_path: str | None = None
    runtime_root: str | None = None


class WorkerBackend(ABC):
    """Abstract interface for pluggable worker execution backends."""

    @abstractmethod
    async def spawn(self, contract: MissionContract) -> WorkerHandle:
        ...

    @abstractmethod
    async def reap(self, handle: WorkerHandle) -> WorkerResult:
        ...

    @abstractmethod
    async def kill(self, handle: WorkerHandle, reason: str) -> None:
        ...


class ControlledSubprocessBackend(WorkerBackend):
    """Run a deterministic worker in a restricted Python subprocess."""

    backend_name = "controlled_subprocess"

    def __init__(
        self,
        runtime_root: str | Path,
        *,
        python_executable: str | None = None,
        worker_module: str = "aios.runtime.worker_entry",
    ) -> None:
        self.runtime_root = Path(runtime_root).resolve()
        self.python_executable = python_executable or sys.executable
        self.worker_module = worker_module
        self.project_root = Path(__file__).resolve().parents[2]
        self.secret_policy = SecretPolicy()
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    async def spawn(self, contract: MissionContract) -> WorkerHandle:
        worker_id = f"worker-{uuid.uuid4().hex[:12]}"
        worker_dir = (
            self.runtime_root
            / "missions"
            / contract.mission_id
            / "workers"
            / worker_id
        )
        worker_dir.mkdir(parents=True, exist_ok=False)
        contract_path = worker_dir / "contract.json"
        result_path = worker_dir / "result.json"
        contract_path.write_text(
            contract.model_dump_json(indent=2),
            encoding="utf-8",
        )

        process = await asyncio.create_subprocess_exec(
            self.python_executable,
            "-m",
            self.worker_module,
            "--contract",
            str(contract_path),
            "--result",
            str(result_path),
            "--worker-id",
            worker_id,
            "--runtime-root",
            str(self.runtime_root),
            cwd=str(self.project_root),
            env=self._restricted_environment(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._processes[worker_id] = process
        return WorkerHandle(
            worker_id=worker_id,
            mission_id=contract.mission_id,
            backend=self.backend_name,
            pid=process.pid,
            result_path=str(result_path),
            status="running",
            contract_path=str(contract_path),
            runtime_root=str(self.runtime_root),
        )

    async def reap(self, handle: WorkerHandle) -> WorkerResult:
        process = self._processes.pop(handle.worker_id, None)
        contract = self._load_contract(handle)
        started_at = _utc_now()
        stdout = ""
        stderr = ""
        if process is not None:
            try:
                raw_stdout, raw_stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=contract.timeout_seconds,
                )
                stdout = raw_stdout.decode("utf-8", errors="replace")
                stderr = raw_stderr.decode("utf-8", errors="replace")
            except TimeoutError:
                process.kill()
                await process.wait()
                handle.status = "killed"
                return WorkerResult(
                    mission_id=handle.mission_id,
                    worker_id=handle.worker_id,
                    status="timeout",
                    summary="Worker exceeded MissionContract timeout.",
                    risk_after=contract.risk_level,
                    stdout=stdout,
                    stderr=stderr,
                    started_at=started_at,
                    ended_at=_utc_now(),
                )

        result_path = Path(handle.result_path) if handle.result_path else None
        if result_path and result_path.exists():
            result = WorkerResult.model_validate_json(
                result_path.read_text(encoding="utf-8")
            )
            result = result.model_copy(
                update={
                    "stdout": stdout,
                    "stderr": stderr,
                }
            )
        else:
            result = WorkerResult(
                mission_id=handle.mission_id,
                worker_id=handle.worker_id,
                status="failed",
                summary="Worker exited without writing WorkerResult.",
                risk_after=contract.risk_level,
                stdout=stdout,
                stderr=stderr,
                started_at=started_at,
                ended_at=_utc_now(),
            )
        handle.status = "dead"
        return result

    async def kill(self, handle: WorkerHandle, reason: str) -> None:
        process = self._processes.pop(handle.worker_id, None)
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()
        handle.status = "killed"

    def _load_contract(self, handle: WorkerHandle) -> MissionContract:
        if not handle.contract_path:
            raise ValueError("worker handle has no contract_path")
        return MissionContract.model_validate_json(
            Path(handle.contract_path).read_text(encoding="utf-8")
        )

    def _restricted_environment(self) -> dict[str, str]:
        allowed_names = {
            "PATH",
            "PATHEXT",
            "SYSTEMROOT",
            "WINDIR",
            "TEMP",
            "TMP",
            "PYTHONIOENCODING",
        }
        env = {
            name: value
            for name, value in os.environ.items()
            if name.upper() in allowed_names
        }
        env = self.secret_policy.worker_environment(env)
        env["PYTHONPATH"] = str(self.project_root)
        env["PYTHONIOENCODING"] = "utf-8"
        return env


__all__ = [
    "ControlledSubprocessBackend",
    "WorkerBackend",
    "WorkerHandle",
    "WorkerHandleStatus",
]
