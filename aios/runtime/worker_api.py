"""Policy-enforced API exposed to temporary Council Runtime workers."""

from __future__ import annotations

import fnmatch
import json
import os
import shlex
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aios import config
from aios.application.executor.service import private_executor_runner_from_config
from aios.core.executor import DockerRunner, _sanitise_env
from aios.runtime.contracts import MissionContract, WorkerResult
from aios.runtime.intelligence_gateway import (
    IntelligenceGateway,
    IntelligenceRequest,
)
from aios.runtime.secret_policy import SecretPolicy
from aios.security.gateway import Zone, classify

# Captured command output is redacted and capped before it is persisted into the
# durable evidence ledger, so a noisy or hostile command cannot bloat the ledger.
_MAX_COMMAND_OUTPUT: int = 50_000


def _runner_for_backend(backend: str):
    """Resolve the isolated runner for a worker's verification command (Phase 2b).

    Container-by-default isolates the only arbitrary command a worker runs, reusing
    the Phase 2 hardened DockerRunner. ``host`` is handled separately (a direct
    argv subprocess — the explicit dev-only opt-out), so this returns None for it;
    any other value is unsupported and the caller fails closed.
    """
    if backend == "container":
        return DockerRunner()
    return None


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
        intelligence_gateway: IntelligenceGateway | None = None,
        command_runner=None,
    ) -> None:
        self.contract = contract
        #: Phase 2b — the runner for verification commands. None => resolved from the
        #: configured execution backend at call time (container by default). Injected
        #: in tests to force a backend or assert fail-closed behavior.
        self._command_runner = command_runner
        self.worker_id = worker_id
        from aios.runtime import _safe_resolve

        self.runtime_root = _safe_resolve(runtime_root)
        self.result_path = _safe_resolve(result_path)
        self.workspace_root = Path(contract.workspace_root).resolve()
        self.mission_dir = self.runtime_root / "missions" / contract.mission_id
        self.worker_dir = self.mission_dir / "workers" / worker_id
        self.approval_dir = self.mission_dir / "approvals"
        self.evidence_path = self.worker_dir / "evidence.json"
        self.intelligence_gateway = intelligence_gateway or IntelligenceGateway()
        self._secret_policy = SecretPolicy()
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

    def _command_allowed(self, command: list[str]) -> bool:
        """A command may run only if its argv is the shlex split of a declared
        ``verification_commands`` entry. This is fail-closed: an empty allowlist
        permits nothing, and the normalization mirrors ``worker_entry`` exactly
        so the legitimate verification path matches while arbitrary host commands
        do not."""
        for allowed in self.contract.verification_commands:
            try:
                if shlex.split(allowed, posix=os.name != "nt") == command:
                    return True
            except ValueError:
                continue
        return False

    def run_command(self, command: list[str]) -> dict[str, Any]:
        self._begin_tool("run_command", {"command": command})
        if not command:
            self._block("run_command", "empty command", {"command": command})
        if not all(isinstance(part, str) for part in command):
            self._block(
                "run_command",
                "command must be a list of strings",
                {"command": command},
            )
        if not self._command_allowed(command):
            self._block(
                "run_command",
                "command is not in MissionContract.verification_commands",
                {"command": command},
            )
        # Defense-in-depth: contract membership is not proof of operator intent
        # (verification_commands can be LLM-proposed under COUNCIL_REASONING),
        # so the RED gateway's hostile-CONTENT classes (destructive ops, network
        # egress, env/secret mutation, injection, embedded credentials, shell
        # escapes) are re-checked at the exec boundary — those are never
        # executable, contract or no contract. Two chat-context stages are
        # deliberately out of jurisdiction here, because the worker has its own
        # containment (workspace root + container boundary + the contract
        # allowlist above): the chat SCOPE_ROOTS check (verification commands
        # legitimately run the absolute interpreter path) and the chat
        # auto-execute allowlist default (contract-declared `python -c ...`
        # is legitimate here). Reason drift in the gateway fails CLOSED: an
        # unrecognized future RED reason blocks. argv[0] is reduced to its
        # basename so the interpreter's location is not misread as content;
        # every argument is still checked in full.
        gateway_view = shlex.join([Path(command[0]).name, *command[1:]])
        gateway_verdict = classify(gateway_view)
        # "Shell composition" is also out of jurisdiction: run_command executes
        # an argv list with shell=False, so `;|&<>` inside an argument (e.g. a
        # `python -c "import sys; sys.exit(1)"` code string) is literal data --
        # there is no shell to compose in. Spawning a shell IS still content
        # ("Shell/interpreter escape" fires before composition and stays
        # blocked), and hostile content inside -c strings still trips the
        # destructive/network/env classes on their own patterns.
        _out_of_jurisdiction = (
            "Scope violation:",
            "Unknown command is not on the auto-execute allowlist",
            "Shell composition blocked:",
        )
        if gateway_verdict.zone is Zone.RED and not gateway_verdict.reason.startswith(
            _out_of_jurisdiction
        ):
            self._block(
                "run_command",
                f"security gateway re-check: RED ({gateway_verdict.reason})",
                {"command": command},
            )
        # Phase 2b — run the (already allowlisted) verification command through the
        # container boundary by DEFAULT; host is the explicit dev-only opt-out.
        #   * host -> run the argv directly (no reparse, so a quoted argument like
        #     `-c "print('a b')"` survives and a bare `python` resolves normally).
        #   * container (or an injected runner) -> the Phase 2 hardened runner, with
        #     the command re-quoted via shlex.join (round-trips through the runner's
        #     argv parse on the Linux host where containers run) and the workspace as
        #     cwd. Fail-closed: a runner that cannot launch (container unavailable)
        #     yields a non-zero result, NEVER a silent host fallback.
        runner = self._command_runner
        backend = config.APPROVED_EXECUTION_BACKEND
        profile = os.environ.get("AIOS_PROFILE", "development").strip().lower()
        if runner is None and profile in {"production", "demo"}:
            # Worker-side verification is part of the production control-plane
            # boundary.  The private client refuses missing service/auth or an
            # unstaged workspace; this branch never falls back to host or local
            # Docker execution.
            active = private_executor_runner_from_config()
            try:
                stdout, stderr, returncode = active(
                    shlex.join(command),
                    cwd=str(self.workspace_root),
                    env=_sanitise_env(),
                    timeout_s=self.contract.timeout_seconds,
                )
            except subprocess.TimeoutExpired:
                raise
            except Exception as exc:  # noqa: BLE001 - fail closed
                stdout, stderr, returncode = (
                    "",
                    f"[private executor unavailable] {exc}",
                    1,
                )
        elif runner is None and backend == "host":
            try:
                proc = subprocess.run(
                    command,
                    cwd=str(self.workspace_root),
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=self.contract.timeout_seconds,
                    check=False,
                )
                stdout, stderr, returncode = (
                    proc.stdout or "",
                    proc.stderr or "",
                    proc.returncode,
                )
            except subprocess.TimeoutExpired:
                raise
            except Exception as exc:  # noqa: BLE001 - report a launch failure cleanly
                stdout, stderr, returncode = (
                    "",
                    f"[host verification failed to launch] {exc}",
                    1,
                )
        else:
            active = runner if runner is not None else _runner_for_backend(backend)
            if active is None:
                stdout, stderr, returncode = (
                    "",
                    f"[verification backend '{backend}' is not supported]",
                    1,
                )
            else:
                try:
                    stdout, stderr, returncode = active(
                        shlex.join(command),
                        cwd=str(self.workspace_root),
                        env=_sanitise_env(),
                        timeout_s=self.contract.timeout_seconds,
                    )
                except subprocess.TimeoutExpired:
                    raise
                except Exception as exc:  # noqa: BLE001 - fail closed, never a host fallback
                    stdout, stderr, returncode = (
                        "",
                        f"[verification backend unavailable] {exc}",
                        1,
                    )
        payload = {
            "command": command,
            "returncode": returncode,
            "stdout": self._secret_policy.redact_text(
                (stdout or "")[:_MAX_COMMAND_OUTPUT]
            ),
            "stderr": self._secret_policy.redact_text(
                (stderr or "")[:_MAX_COMMAND_OUTPUT]
            ),
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
        response = self.intelligence_gateway.request(
            IntelligenceRequest(
                mission_id=self.contract.mission_id,
                worker_id=self.worker_id,
                purpose="plan",
                prompt=prompt,
                risk=self.contract.risk_level,
                allow_cloud=allow_cloud,
                max_tokens=int(self.contract.metadata.get("plan_max_tokens", 1500)),
                timeout_seconds=int(
                    self.contract.metadata.get("plan_timeout_seconds", 20)
                ),
            ),
            contract=self.contract,
        )
        self.evidence.setdefault("intelligence", []).append(response.model_dump())
        self._record_tool(
            "request_plan",
            {
                "allow_cloud": allow_cloud,
                "provider": response.provider,
                "used_cloud": response.used_cloud,
                "fallback_used": response.fallback_used,
            },
            "completed",
        )
        self._persist_evidence()
        return response.text

    def request_change(
        self,
        prompt: str,
        *,
        allow_cloud: bool = False,
        purpose: str = "plan",
    ) -> str:
        """Ask the IntelligenceGateway for proposed file content (the worker's
        "think/act" generation). ``purpose`` is "plan" for the first attempt and
        "repair" for self-correction. Output is already secret-redacted by the
        gateway; the worker still applies it only via the scoped write_file."""
        self._begin_tool(
            "request_change",
            {
                "prompt_length": len(prompt),
                "allow_cloud": allow_cloud,
                "purpose": purpose,
            },
        )
        response = self.intelligence_gateway.request(
            IntelligenceRequest(
                mission_id=self.contract.mission_id,
                worker_id=self.worker_id,
                purpose=purpose,  # type: ignore[arg-type]
                prompt=prompt,
                risk=self.contract.risk_level,
                allow_cloud=allow_cloud,
                max_tokens=int(self.contract.metadata.get("change_max_tokens", 2000)),
                timeout_seconds=int(
                    self.contract.metadata.get("change_timeout_seconds", 30)
                ),
            ),
            contract=self.contract,
        )
        self.evidence.setdefault("intelligence", []).append(response.model_dump())
        self._record_tool(
            "request_change",
            {
                "purpose": purpose,
                "allow_cloud": allow_cloud,
                "provider": response.provider,
                "used_cloud": response.used_cloud,
                "fallback_used": response.fallback_used,
            },
            "completed",
        )
        self._persist_evidence()
        return response.text

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
        if tool in {
            "read_file",
            "write_file",
            "run_command",
            "request_approval",
            "request_plan",
            "request_change",
        }:
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
