"""Scope-constrained, approval-gated command executor (Blueprint stage 7).

No command reaches the host without first clearing the security gateway, and
every decision — blocked, escalated, or executed — is written to the
tamper-evident audit ledger. Execution itself is constrained:

  * **Scope-locked working directory** — commands run inside a declared scope
    root (the ``training_ground`` playground by default), never the host root.
  * **Sanitised environment** — secret-bearing variables (``*KEY*``,
    ``*TOKEN*``, ``*SECRET*``, ``*PASSWORD*``) and ``HOME``/``USERPROFILE`` are
    stripped before the child process starts, so credentials cannot leak into a
    subprocess or its output.
  * **Structured argv** — shell composition is rejected and processes launch
    with ``shell=False``.
  * **Hard timeout** — a runaway process is killed and reported, never left
    orphaned.

This is not an OS/container isolation boundary. Approved arbitrary-code
commands run as the backend OS user. The process spawn is injected
(:class:`Runner`) so tests can drive the full gateway+audit pipeline
deterministically without spawning a process.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Protocol

from aios import config
from aios.security.audit_logger import log_action
from aios.security.gateway import RateLimiter, Zone, classify, validate_command

#: Environment variables whose *names* indicate a secret; stripped from children.
_SECRET_NAME_HINTS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL", "BEARER")
#: Variables removed regardless of value (no home/identity propagation).
_STRIPPED_NAMES = ("HOME", "USERPROFILE", "AWS_BEARER_TOKEN_BEDROCK")


@dataclass(frozen=True)
class ExecutionResult:
    """Outcome of an execution attempt.

    ``status`` is one of:
      * ``OK``               — ran to completion (check ``exit_code``).
      * ``BLOCKED``          — refused by the gateway (RED); never ran.
      * ``REQUIRE_APPROVAL`` — escalated (YELLOW); awaiting human approval.
      * ``TIMEOUT``          — killed after exceeding the time budget.
      * ``ERROR``            — could not be launched.
    """

    status: str
    zone: str
    command: str
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    duration_ms: int = 0
    reason: str = ""


class Runner(Protocol):
    """Spawns a classified command and returns ``(stdout, stderr, exit_code)``."""

    def __call__(
        self, command: str, *, cwd: str, env: dict[str, str], timeout_s: int
    ) -> tuple[str, str, int]:
        ...


def _sanitise_env() -> dict[str, str]:
    """Return a copy of the environment with secret-bearing vars removed."""
    clean: dict[str, str] = {}
    for name, value in os.environ.items():
        upper = name.upper()
        if upper in _STRIPPED_NAMES:
            continue
        if any(hint in upper for hint in _SECRET_NAME_HINTS):
            continue
        clean[name] = value
    # Commands such as the force-verify runner intentionally use a bare
    # `python`/`pytest` so the scope lock never has to permit an absolute or `..`
    # interpreter path. Prefer this project's existing venv deterministically,
    # independent of how uvicorn itself was launched.
    venv_bin = config.PROJECT_ROOT / ".venv" / ("Scripts" if os.name == "nt" else "bin")
    if venv_bin.is_dir():
        current_path = clean.get("PATH", "")
        clean["PATH"] = str(venv_bin) + (os.pathsep + current_path if current_path else "")
    return clean


def _parse_argv(command: str) -> list[str]:
    """Parse one already-classified command into argv without invoking a shell."""
    if not command or any(ch in command for ch in ";&|<>`\r\n"):
        raise ValueError("shell composition is not permitted")
    argv = shlex.split(command, posix=os.name != "nt")
    if os.name == "nt":
        argv = [
            arg[1:-1] if len(arg) >= 2 and arg[0] == arg[-1] and arg[0] in "\"'" else arg
            for arg in argv
        ]
    if not argv:
        raise ValueError("empty command")
    return argv


def _default_runner(
    command: str, *, cwd: str, env: dict[str, str], timeout_s: int
) -> tuple[str, str, int]:
    """Real subprocess runner: structured argv, captured output, and timeout."""
    argv = _parse_argv(command)
    executable = argv[0].lower()
    if executable == "echo":
        return " ".join(argv[1:]) + "\n", "", 0
    if executable == "pwd":
        return cwd + "\n", "", 0
    completed = subprocess.run(
        argv,
        shell=False,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    return completed.stdout or "", completed.stderr or "", completed.returncode


class Executor:
    """Gateway-guarded, scope-locked, audited command executor."""

    def __init__(
        self,
        *,
        runner: Optional[Runner] = None,
        rate_limiter: Optional[RateLimiter] = None,
        timeout_s: int = 30,
        actor: str = "executor",
        audit_log: Optional[Callable[..., object]] = None,
    ) -> None:
        self.runner: Runner = runner or _default_runner
        self.rate_limiter = rate_limiter
        self.timeout_s = timeout_s
        self.actor = actor
        #: Audit sink; defaults to the real tamper-evident ledger. Injectable so
        #: tests can record actions without touching the on-disk ledger.
        self._audit: Callable[..., object] = audit_log or log_action

    def _scope_cwd(self) -> Path:
        """The working directory for child processes (primary scope root)."""
        roots = config.SCOPE_ROOTS
        cwd = roots[0] if roots else Path.cwd()
        cwd.mkdir(parents=True, exist_ok=True)
        return cwd

    def execute(self, command: str, *, session_id: Optional[str] = None) -> ExecutionResult:
        """Classify, gate, audit, and (if allowed) run *command*.

        A RED command is blocked and never run; a YELLOW command is reported as
        requiring approval and never run here (use the approval flow); a GREEN
        command runs inside the configured scope. Every outcome is audited.
        """
        decision = validate_command(
            command, session_id=session_id, rate_limiter=self.rate_limiter
        )

        if decision.status == "BLOCK":
            self._audit(self.actor, f"BLOCKED: {command}", Zone.RED)
            return ExecutionResult(
                status="BLOCKED",
                zone=decision.zone.value,
                command=command,
                reason=decision.reason,
            )

        if decision.status == "REQUIRE_HUMAN":
            self._audit(self.actor, f"ESCALATED: {command}", Zone.YELLOW)
            return ExecutionResult(
                status="REQUIRE_APPROVAL",
                zone=decision.zone.value,
                command=command,
                reason=decision.reason,
            )

        # GREEN -> ALLOW: run it inside the configured scope.
        self._audit(self.actor, f"EXECUTING: {command}", Zone.GREEN)
        return self._run_in_sandbox(command, Zone.GREEN)

    def execute_approved(self, command: str) -> ExecutionResult:
        """Run a command that a human has explicitly approved.

        Used by the approval flow after a YELLOW escalation. RED commands are
        still refused — destructive actions cannot be granted by one-click
        approval. GREEN/YELLOW commands are audited as approved and run inside
        the configured scope.
        """
        result = classify(command)
        if result.zone is Zone.RED:
            self._audit(self.actor, f"APPROVAL DENIED (RED): {command}", Zone.RED)
            return ExecutionResult(
                status="BLOCKED",
                zone=Zone.RED.value,
                command=command,
                reason=f"Human approval cannot authorise a RED action: {result.reason}",
            )
        self._audit(self.actor, f"APPROVED+EXECUTING: {command}", result.zone)
        return self._run_in_sandbox(command, result.zone)

    def _run_in_sandbox(self, command: str, zone: Zone) -> ExecutionResult:
        """Run *command* in the scope-locked working directory."""
        cwd = self._scope_cwd()
        env = _sanitise_env()
        started = time.monotonic()
        try:
            _parse_argv(command)
            stdout, stderr, exit_code = self.runner(
                command, cwd=str(cwd), env=env, timeout_s=self.timeout_s
            )
        except subprocess.TimeoutExpired:
            duration_ms = int((time.monotonic() - started) * 1000)
            self._audit(self.actor, f"TIMEOUT: {command}", zone)
            return ExecutionResult(
                status="TIMEOUT",
                zone=zone.value,
                command=command,
                duration_ms=duration_ms,
                reason=f"Command exceeded {self.timeout_s}s budget and was killed.",
            )
        except Exception as exc:  # noqa: BLE001 - report launch failures cleanly
            duration_ms = int((time.monotonic() - started) * 1000)
            return ExecutionResult(
                status="ERROR",
                zone=zone.value,
                command=command,
                duration_ms=duration_ms,
                reason=f"Execution failed to launch: {exc}",
            )

        duration_ms = int((time.monotonic() - started) * 1000)
        return ExecutionResult(
            status="OK",
            zone=zone.value,
            command=command,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=duration_ms,
            reason="Executed within configured scope.",
        )
