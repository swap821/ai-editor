"""Policy-enforced API exposed to temporary Council Runtime workers."""
from __future__ import annotations

import fnmatch
import json
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aios.runtime.contracts import MissionContract, WorkerResult


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ContractViolation(RuntimeError):
    """Raised when a worker attempts an action outside its MissionContract."""


class WorkerRuntime:
    """The only API a v0.1 worker is allowed to use.

    This class enforces policy at the Python layer. It deliberately does not
    claim to be a hardened OS sandbox.
    """

    def __init__(
        self,
        contract: MissionContract,
        *,
        worker_id: str,
        runtime_root: str | Path,
        result_path: str | Path,
    ) -> None:
        self.contract = contract
        self.worker_id = worker_id
        self.runtime_root = Path(runtime_root).resolve()
        self.result_path = Path(result_path).resolve()
        self.workspace_root = Path(contract.workspace_root).resolve()
        self.mission_dir = self.runtime_root / "missions" / contract.mission_id
        self.worker_dir = self.mission_dir / "workers" / worker_id
        self.approval_dir = self.mission_dir / "approvals"
        self.evidence_path = self.worker_dir / "evidence.json"
        self.worker_dir.mkdir(parents=True, exist_ok=True)
        self.approval_dir.mkdir(parents=True, exist_ok=True)

        self._steps = 0
        self.files_touched: list[str] = []
        self.blocked_attempts: list[dict[str, Any]] = []
        self.tool_calls: list[dict[str, Any]] = []
        self.evidence: dict[str, Any] = {
            "blocked_attempts": self.blocked_attempts,
            "verification": [],
        }

    def read_file(self, path: str) -> str:
        self._begin_tool("read_file", {"path": path})
        target, rel = self._resolve_allowed_path(path, tool="read_file")
        try:
            content = target.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            self._record_tool("read_file", {"path": rel}, "failed", str(exc))
            raise
        self._record_tool("read_file", {"path": rel}, "completed")
        return content

    def write_file(self, path: str, content: str) -> None:
        self._begin_tool("write_file", {"path": path})
        target, rel = self._resolve_allowed_path(path, tool="write_file")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        if rel not in self.files_touched:
            self.files_touched.append(rel)
        self._record_tool("write_file", {"path": rel}, "completed")
        self._persist_evidence()

    def run_command(self, command: list[str]) -> dict[str, Any]:
        self._begin_tool("run_command", {"command": command})
        if not command:
            self._block("run_command", "empty command", {"command": command})
        result = subprocess.run(
            command,
            cwd=str(self.workspace_root),
            shell=False,
            capture_output=True,
            text=True,
            timeout=self.contract.timeout_seconds,
            check=False,
        )
        payload = {
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        self.evidence.setdefault("verification", []).append(payload)
        self._record_tool("run_command", {"command": command}, "completed")
        self._persist_evidence()
        return payload

    def request_approval(self, action: str, reason: str) -> bool:
        self._begin_tool(
            "request_approval",
            {"action": action, "reason": reason},
        )
        request_id = f"approval-{uuid.uuid4().hex[:12]}"
        request_path = self.approval_dir / f"{request_id}.request.json"
        response_path = self.approval_dir / f"{request_id}.response.json"
        request_path.write_text(
            json.dumps(
                {
                    "request_id": request_id,
                    "mission_id": self.contract.mission_id,
                    "worker_id": self.worker_id,
                    "action": action,
                    "reason": reason,
                    "created_at": _utc_now(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        self._record_tool("request_approval", {"request_id": request_id}, "awaiting")
        wait_seconds = float(self.contract.metadata.get("approval_wait_seconds", 0))
        deadline = time.monotonic() + wait_seconds
        while wait_seconds > 0 and time.monotonic() < deadline:
            if response_path.exists():
                break
            time.sleep(0.25)
        if not response_path.exists():
            self._persist_evidence()
            return False
        response = json.loads(response_path.read_text(encoding="utf-8"))
        self._record_tool("request_approval", {"request_id": request_id}, "completed")
        self._persist_evidence()
        return bool(response.get("approved"))

    def request_plan(self, prompt: str, allow_cloud: bool = False) -> str:
        self._begin_tool(
            "request_plan",
            {"prompt_length": len(prompt), "allow_cloud": allow_cloud},
        )
        if allow_cloud:
            self._block(
                "request_plan",
                "cloud reasoning is disabled during deterministic worker birth",
                {"allow_cloud": allow_cloud},
            )
        self._record_tool(
            "request_plan",
            {"allow_cloud": allow_cloud},
            "completed",
        )
        return "Phase 1A deterministic worker birth has no reasoning provider."

    def emit_evidence(self, data: dict[str, Any]) -> None:
        self.evidence.update(data)
        self._persist_evidence()

    def finish(self, result: WorkerResult) -> None:
        if result.mission_id != self.contract.mission_id:
            raise ValueError("WorkerResult mission_id does not match contract")
        if result.worker_id != self.worker_id:
            raise ValueError("WorkerResult worker_id does not match runtime worker")
        enriched = result.model_copy(
            update={
                "files_touched": list(self.files_touched),
                "tool_calls": list(self.tool_calls),
                "evidence": dict(self.evidence),
            }
        )
        self.result_path.parent.mkdir(parents=True, exist_ok=True)
        self.result_path.write_text(
            enriched.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def _begin_tool(self, tool: str, payload: dict[str, Any]) -> None:
        if self._steps >= self.contract.max_steps:
            self._block(tool, "max_steps exceeded", payload)
        self._steps += 1
        if tool in self.contract.forbidden_tools:
            self._block(tool, "tool is forbidden by MissionContract", payload)
        if tool in {"read_file", "write_file", "run_command", "request_approval", "request_plan"}:
            if tool not in self.contract.allowed_tools:
                self._block(tool, "tool is not allowed by MissionContract", payload)

    def _resolve_allowed_path(self, path: str, *, tool: str) -> tuple[Path, str]:
        raw = Path(path)
        target = raw if raw.is_absolute() else self.workspace_root / raw
        resolved = target.resolve()
        try:
            relative = resolved.relative_to(self.workspace_root)
        except ValueError:
            self._block(tool, "path escapes workspace_root", {"path": path})
        rel = relative.as_posix()
        if self._matches(rel, self.contract.forbidden_files):
            self._block(tool, "path is forbidden by MissionContract", {"path": rel})
        if not self._matches(rel, self.contract.allowed_files):
            self._block(tool, "path is not allowed by MissionContract", {"path": rel})
        return resolved, rel

    def _matches(self, rel: str, rules: list[str]) -> bool:
        normalized = rel.replace("\\", "/").lstrip("./")
        for rule in rules:
            clean = rule.replace("\\", "/").strip().lstrip("./")
            if not clean:
                continue
            clean = clean.rstrip("/")
            if any(char in clean for char in "*?[]"):
                if fnmatch.fnmatchcase(normalized, clean):
                    return True
                continue
            if normalized == clean or normalized.startswith(f"{clean}/"):
                return True
        return False

    def _block(self, tool: str, reason: str, payload: dict[str, Any]) -> None:
        attempt = {
            "tool": tool,
            "reason": reason,
            "payload": payload,
            "step": self._steps,
            "created_at": _utc_now(),
        }
        self.blocked_attempts.append(attempt)
        self._record_tool(tool, payload, "blocked", reason)
        self._persist_evidence()
        raise ContractViolation(reason)

    def _record_tool(
        self,
        tool: str,
        payload: dict[str, Any],
        status: str,
        reason: str = "",
    ) -> None:
        self.tool_calls.append(
            {
                "tool": tool,
                "payload": payload,
                "status": status,
                "reason": reason,
                "created_at": _utc_now(),
            }
        )

    def _persist_evidence(self) -> None:
        self.evidence_path.write_text(
            json.dumps(self.evidence, indent=2),
            encoding="utf-8",
        )


__all__ = ["ContractViolation", "WorkerRuntime"]
