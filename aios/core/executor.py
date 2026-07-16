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
  * **Hard timeout** — the launched process is killed and reported. Host mode
    cannot guarantee process-tree containment; use the container backend for
    the stronger execution boundary.
  * **Bounded command/output size** — oversized commands are refused and process
    pipes are drained without retaining unbounded output in backend memory.

This is not an OS/container isolation boundary. Approved arbitrary-code
commands run as the backend OS user. The process spawn is injected
(:class:`Runner`) so tests can drive the full gateway+audit pipeline
deterministically without spawning a process.
"""

from __future__ import annotations

import os
import ntpath
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING, Any, Callable, Optional, Protocol

from aios import config
from aios.security.audit_logger import log_action
from aios.security.gateway import (
    RateLimiter,
    Zone,
    reset_sensitive_actions,
)
from aios.infrastructure.executor.argv import (
    argv_is_safe as _argv_is_safe,
    parse_argv as _parse_argv,
)

if TYPE_CHECKING:
    from aios.policy.kernel import PolicyKernel

#: Environment variables whose *names* indicate a secret; stripped from children.
_SECRET_NAME_HINTS = (
    "KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
    "BEARER",
    "AUTH",
    "APIKEY",
    "PIN",
    "PASSPHRASE",
    "DATABASE",
    "CONNECTION",
    "WEBHOOK",
    "MNEMONIC",
    "KEYSTORE",
    "CERTIFICATE",
    "PRIVATE",
    "SIGNING",
    "ENCRYPTION",
    "ACCESS",
    "REFRESH",
    "SESSION",
)
#: Variables removed regardless of value (no home/identity propagation).
# fmt: off
_STRIPPED_NAMES = (
    # Identity / home propagation (C17)
    "HOME", "USERPROFILE",
    # Dynamic linker injection vectors (C19)
    "LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT", "LD_PROFILE",
    "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH",
    # Python module search path injection (H6)
    "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONIOENCODING",
    # Identity / credential leak vectors (H17-H18)
    "SSH_AUTH_SOCK", "GNUPGHOME", "HISTFILE", "MAIL", "HOSTNAME",
    # AWS-specific bearer token
    "AWS_BEARER_TOKEN_BEDROCK",
    # AWS credential leak vectors (C5 hardening)
    "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
    # Database connection string leak (C5 hardening)
    "DATABASE_URL",
)
# fmt: on
_OUTPUT_TRUNCATED = "\n[OUTPUT TRUNCATED]\n"


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
    ) -> tuple[str, str, int]: ...


def _bounded_run(
    argv: list[str],
    *,
    shell: bool = False,
    cwd: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
    capture_output: bool = True,
    text: bool = True,
    timeout: Optional[int] = None,
    max_output_bytes: Optional[int] = None,
) -> subprocess.CompletedProcess[str]:
    """Run argv while draining pipes but retaining only a bounded prefix."""
    if shell or not capture_output or not text:
        raise ValueError(
            "bounded runner requires shell=False, capture_output=True, text=True"
        )
    if not _argv_is_safe(argv):
        raise ValueError("unsafe structured argv")
    limit = max(max_output_bytes or config.MAX_COMMAND_OUTPUT_BYTES, 1024)
    process = subprocess.Popen(
        argv,
        shell=False,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    streams = [process.stdout, process.stderr]
    captured = [bytearray(), bytearray()]
    truncated = [False, False]

    def drain(index: int) -> None:
        stream = streams[index]
        assert stream is not None
        try:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    return
                remaining = limit - len(captured[index])
                if remaining > 0:
                    captured[index].extend(chunk[:remaining])
                if len(chunk) > max(remaining, 0):
                    truncated[index] = True
        except (OSError, ValueError):
            return

    readers = [
        threading.Thread(target=drain, args=(index,), daemon=True) for index in range(2)
    ]
    for reader in readers:
        reader.start()
    try:
        return_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        # SIGSTOP bypass: wake stopped processes so they can receive the fatal signal
        try:
            os.kill(process.pid, signal.SIGCONT)
        except (OSError, ProcessLookupError):
            pass
        # Kill the entire process group — not just the immediate child
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            process.kill()
        process.wait()
        raise
    finally:
        for reader in readers:
            reader.join(timeout=2)
        for stream in streams:
            if stream is not None:
                stream.close()

    outputs = []
    for index in range(2):
        output = captured[index].decode("utf-8", "replace")
        outputs.append(output + (_OUTPUT_TRUNCATED if truncated[index] else ""))
    return subprocess.CompletedProcess(argv, return_code, outputs[0], outputs[1])


class DockerRunner:
    """Run an approved command in a locked-down, ephemeral Docker container."""

    def __init__(
        self,
        *,
        runtime: str = config.CONTAINER_RUNTIME,
        image: str = config.CONTAINER_IMAGE,
        memory_mb: int = config.CONTAINER_MEMORY_MB,
        cpus: float = config.CONTAINER_CPUS,
        pids_limit: int = config.CONTAINER_PIDS_LIMIT,
        process_runner: Optional[
            Callable[..., subprocess.CompletedProcess[str]]
        ] = None,
    ) -> None:
        self.runtime = runtime
        self.image = image
        self.memory_mb = max(memory_mb, 128)
        self.cpus = max(cpus, 0.1)
        self.pids_limit = max(pids_limit, 16)
        self._process_runner = process_runner or _bounded_run

    def ensure_available(self) -> None:
        """Fail clearly when the configured daemon or executor image is unavailable."""
        try:
            completed = self._process_runner(
                [self.runtime, "image", "inspect", self.image],
                shell=False,
                env=_sanitise_env(),
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception as exc:  # noqa: BLE001 - converted to configuration failure
            raise RuntimeError(f"isolated execution unavailable: {exc}") from exc
        if completed.returncode != 0:
            detail = (
                completed.stderr or completed.stdout or "image inspection failed"
            ).strip()
            raise RuntimeError(f"isolated execution unavailable: {detail}")

    def __call__(
        self, command: str, *, cwd: str, env: dict[str, str], timeout_s: int
    ) -> tuple[str, str, int]:
        argv = _parse_argv(command)
        # ``ntpath.isabs`` accepts POSIX-looking roots on some Python versions;
        # use the host platform plus explicit drive/UNC syntax as the
        # discriminator so Linux/macOS paths never get rewritten into
        # backslashes before entering the Docker mount spec. Explicit Windows
        # daemon paths remain supported for cross-platform Docker clients.
        explicit_windows_path = (
            (len(cwd) >= 3 and cwd[1] == ":" and cwd[0].isalpha())
            or cwd.startswith("\\\\")
        )
        windows_daemon_path = ntpath.isabs(cwd) and (
            os.name == "nt" or explicit_windows_path
        )
        if windows_daemon_path:
            cwd_parts = PureWindowsPath(cwd).parts
            if ".." in cwd_parts:
                raise ValueError("executor cwd must be an absolute, normalized path")
            resolved_cwd = ntpath.normpath(cwd)
        else:
            cwd_path = Path(cwd)
            if not cwd_path.is_absolute() or ".." in cwd_path.parts:
                raise ValueError("executor cwd must be an absolute, normalized path")
            resolved_cwd = str(cwd_path.resolve())
        # The scope-lock and structured executor adapters resolve cwd before
        # crossing this runner boundary. Keep that canonical value unchanged;
        # re-normalizing a request-derived string is itself a CodeQL path sink.
        # H4 — Docker mount spec characters can break out of the mount string.
        # Commas, equals, and non-drive-letter colons are separators in the
        # --mount syntax. A normal Windows root ("C:\...") is allowed.
        colon_scan = (
            resolved_cwd[2:]
            if len(resolved_cwd) >= 2
            and resolved_cwd[1] == ":"
            and resolved_cwd[0].isalpha()
            else resolved_cwd
        )
        if any(ch in resolved_cwd for ch in ",=") or ":" in colon_scan:
            raise ValueError(
                "working directory path contains characters not permitted in Docker mount spec"
            )
        # --mount requires every field to be key=value: a bare "rw" (the -v
        # volume shorthand) is rejected by modern Docker with exit 125
        # ("invalid field 'rw' must be a key=value pair"), which fail-closed
        # every container-backed verify the moment a real daemon was present
        # (first observed live 2026-07-03). Bind mounts are read-write by
        # default, so simply omit the field. bind-propagation=private prevents
        # mounts created inside the sandbox from leaking back to the host.
        mount = f"type=bind,src={resolved_cwd},dst=/workspace,bind-propagation=private"
        docker_argv = [
            self.runtime,
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            str(self.pids_limit),
            "--memory",
            f"{self.memory_mb}m",
            "--cpus",
            str(self.cpus),
            "--user",
            "65534:65534",
            "--mount",
            mount,
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=64m",
            "--workdir",
            "/workspace",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            # Sandbox verification runs a single sandbox-local pytest file. The
            # repo's pytest.ini addopts (--cov=aios --cov-report=term-missing)
            # are meaningless here (the sandbox test does not import aios, so
            # coverage collects nothing) AND actively harmful: in the container's
            # non-TTY output the coverage report DISPLACES pytest's "N passed"
            # summary line, so the Verifier's count parser reads 0 passed and
            # downgrades a real green to WEAK strength (below the STRONG
            # promotion floor). `-o addopts=` clears the ini addopts for the
            # sandbox run so the summary line is present and counts parse.
            "PYTEST_ADDOPTS=-p no:cacheprovider -o addopts=",
            self.image,
            *argv,
        ]
        completed = self._process_runner(
            docker_argv,
            shell=False,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return completed.stdout or "", completed.stderr or "", completed.returncode


class UnavailableIsolationRunner:
    """Fail closed for invalid isolated-execution configuration."""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def __call__(
        self, command: str, *, cwd: str, env: dict[str, str], timeout_s: int
    ) -> tuple[str, str, int]:
        raise RuntimeError(self.reason)


def approved_runner_from_config() -> Optional[Runner]:
    """Build the configured runner for human-approved arbitrary-code commands."""
    profile = os.environ.get("AIOS_PROFILE", "development").strip().lower()
    if profile in {"production", "demo"}:
        # Production never constructs a local Docker or host runner.  Keep the
        # import lazy so this compatibility module remains usable by tests and
        # development callers without creating an application-layer cycle.
        from aios.application.executor.service import (
            private_executor_runner_from_config,
        )

        return private_executor_runner_from_config()
    if config.APPROVED_EXECUTION_BACKEND == "host":
        return None
    if config.APPROVED_EXECUTION_BACKEND == "container":
        return DockerRunner()
    return UnavailableIsolationRunner(
        f"unsupported AIOS_APPROVED_EXECUTION_BACKEND: {config.APPROVED_EXECUTION_BACKEND}"
    )


def validate_approved_execution_backend() -> Optional[str]:
    """Announce/validate the approved-exec backend at startup; return a warning to log.

    Degrade, don't brick (Phase 2): a *configured-but-unavailable* container backend
    does NOT abort startup — it returns a warning, and the approved-arbitrary-exec
    and self-apply paths fail closed at call time instead. Host mode returns a loud
    development-only warning. Only an UNKNOWN backend value (real misconfiguration)
    still raises. Returns ``None`` when the container backend is ready and silent.
    """
    profile = os.environ.get("AIOS_PROFILE", "development").strip().lower()
    if profile in {"production", "demo"}:
        if not config.EXECUTOR_URL or not config.EXECUTOR_TOKEN:
            return (
                "private Executor Service is not configured; approved and worker "
                "execution will FAIL CLOSED"
            )
        return None

    runner = approved_runner_from_config()
    if isinstance(runner, DockerRunner):
        try:
            runner.ensure_available()
        except RuntimeError as exc:
            return (
                f"container execution backend unavailable ({exc}); approved arbitrary "
                "execution and self-apply will FAIL CLOSED until the container is "
                "available. Set AIOS_APPROVED_EXECUTION_BACKEND=host to run on the host "
                "instead (development only)."
            )
        return None
    if isinstance(runner, UnavailableIsolationRunner):
        raise RuntimeError(runner.reason)
    # Host mode (runner is None): a conscious, loud opt-out.
    return (
        "host execution backend selected: approved commands run as the backend OS "
        "user — DEVELOPMENT ONLY, not an OS/container isolation boundary. Set "
        "AIOS_APPROVED_EXECUTION_BACKEND=container (the supported path) to isolate."
    )


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
        clean["PATH"] = str(venv_bin) + (
            os.pathsep + current_path if current_path else ""
        )
    return clean


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
    if executable in {"mkdir", "md"}:
        return _run_mkdir_builtin(argv, cwd)
    if not Path(argv[0]).is_absolute() and os.sep not in argv[0]:
        # Resolve a bare program name through the SANITISED env's PATH (where
        # _sanitise_env put this project's venv first). Without this, Windows'
        # CreateProcess searches the parent executable's directory and the
        # scope-locked cwd BEFORE the child PATH — so a bare `python` could hit
        # the base interpreter (venv silently ignored) or even a binary planted
        # inside the writable sandbox. Resolving via PATH alone is deterministic
        # and removes both. Unresolvable names keep the old spawn behaviour.
        resolved = shutil.which(argv[0], path=env.get("PATH", ""))
        if resolved:
            argv[0] = resolved
    completed = _bounded_run(
        argv,
        shell=False,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    return completed.stdout or "", completed.stderr or "", completed.returncode


def _path_within_roots(path: Path, roots: list[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
        except ValueError:
            continue
        return True
    return False


def _run_mkdir_builtin(argv: list[str], cwd: str) -> tuple[str, str, int]:
    """Implement mkdir/md without a shell while preserving scope containment."""
    parents = False
    targets: list[str] = []
    for raw in argv[1:]:
        arg = raw.strip("\"'")
        if arg in {"-p", "--parents"}:
            parents = True
            continue
        if arg.startswith("-"):
            raise ValueError(f"unsupported mkdir flag: {arg}")
        if arg:
            targets.append(arg)
    if not targets:
        raise ValueError("mkdir requires at least one target directory")

    roots = [Path(root).resolve() for root in config.SCOPE_ROOTS]
    if not roots:
        raise ValueError("no configured scope roots")
    cwd_path = Path(cwd).resolve()
    for raw in targets:
        target = Path(raw)
        resolved = (target if target.is_absolute() else cwd_path / target).resolve()
        if not _path_within_roots(resolved, roots):
            raise ValueError(f"mkdir target escapes configured scope: {raw}")
        resolved.mkdir(parents=parents, exist_ok=parents)
    return "", "", 0


def _truncate_output(value: str) -> str:
    """Bound output returned by injected runners as well as the real runner."""
    limit = max(config.MAX_COMMAND_OUTPUT_BYTES, 1024)
    encoded = value.encode("utf-8", "replace")
    if len(encoded) <= limit:
        return value
    return encoded[:limit].decode("utf-8", "replace") + _OUTPUT_TRUNCATED


class Executor:
    """Gateway-guarded, scope-locked, audited command executor."""

    def __init__(
        self,
        *,
        runner: Optional[Runner] = None,
        approved_runner: Optional[Runner] = None,
        rate_limiter: Optional[RateLimiter] = None,
        policy_kernel: Optional["PolicyKernel"] = None,
        timeout_s: int = 30,
        actor: str = "executor",
        audit_log: Optional[Callable[..., object]] = None,
        emergency_stop: Any | None = None,
    ) -> None:
        # Imported lazily to break the api-deps -> executor -> policy cycle.
        from aios.policy.kernel import PolicyKernel

        profile = os.environ.get("AIOS_PROFILE", "development").strip().lower()
        if runner is None and profile in {"production", "demo"}:
            from aios.application.executor.service import (
                private_executor_runner_from_config,
            )

            runner = private_executor_runner_from_config()
        self.runner: Runner = runner or _default_runner
        self.approved_runner = approved_runner
        if self.approved_runner is None and getattr(
            self.runner, "is_private_service", False
        ):
            self.approved_runner = self.runner
        self.rate_limiter = rate_limiter
        self.policy_kernel = policy_kernel or PolicyKernel(
            rate_limiter=self.rate_limiter
        )
        self.timeout_s = timeout_s
        self.actor = actor
        self.emergency_stop = emergency_stop
        #: Audit sink; defaults to the real tamper-evident ledger. Injectable so
        #: tests can record actions without touching the on-disk ledger.
        self._audit: Callable[..., object] = audit_log or log_action

    def _scope_cwd(self) -> Path:
        """The working directory for child processes.

        This is the repo root that the primary scope root (``training_ground``)
        lives under, NOT the scope root itself — so ``training_ground`` is
        importable as a package (``from training_ground.x import y``) rather
        than being mounted/spawned as if it were the root itself. The
        scope-lock security boundary (``aios/security/scope_lock.py``) resolves
        path tokens against ``config.SCOPE_ROOTS`` independently of this cwd, so
        this is safe to change without touching containment.
        """
        roots = config.SCOPE_ROOTS
        cwd = roots[0].resolve().parent if roots else Path.cwd()
        cwd.mkdir(parents=True, exist_ok=True)
        return cwd

    def execute(
        self, command: str, *, session_id: Optional[str] = None
    ) -> ExecutionResult:
        """Classify, gate, audit, and (if allowed) run *command*.

        A RED command is blocked and never run; a YELLOW command is reported as
        requiring approval and never run here (use the approval flow); a GREEN
        command runs inside the configured scope. Every outcome is audited.
        """
        decision = self.policy_kernel.evaluate_action(command, session_id=session_id)

        if decision.blocked:
            # Size blocks are treated specially: never echo the oversized payload
            # back in the result or audit log.
            if "character limit" in decision.reason:
                reason = f"[SECURITY BLOCK] {decision.reason}"
                self._audit(self.actor, reason, Zone.RED)
                return ExecutionResult(
                    status="BLOCKED",
                    zone=Zone.RED.value,
                    command="",
                    reason=reason,
                )
            self._audit(self.actor, f"BLOCKED: {command}", decision.zone)
            return ExecutionResult(
                status="BLOCKED",
                zone=decision.zone.value,
                command=command,
                reason=decision.reason,
            )

        if decision.requires_approval:
            self._audit(self.actor, f"ESCALATED: {command}", decision.zone)
            return ExecutionResult(
                status="REQUIRE_APPROVAL",
                zone=decision.zone.value,
                command=command,
                reason=decision.reason,
            )

        if self.emergency_stop is not None:
            try:
                self.emergency_stop.assert_operational()
            except Exception:  # noqa: BLE001 - emergency latch blocks dispatch
                reason = "emergency stop is engaged; execution is disabled"
                self._audit(self.actor, f"BLOCKED: {reason}", Zone.RED)
                return ExecutionResult(
                    status="BLOCKED",
                    zone=Zone.RED.value,
                    command=command,
                    reason=reason,
                )

        # GREEN (or earned-autonomy YELLOW) -> ALLOW: run it inside the configured scope.
        self._audit(self.actor, f"EXECUTING: {command}", decision.zone)
        return self._run_in_sandbox(command, decision.zone)

    def execute_approved(self, command: str) -> ExecutionResult:
        """Run a command that a human has explicitly approved.

        Used by the approval flow after a YELLOW escalation. RED commands are
        still refused — destructive actions cannot be granted by one-click
        approval. GREEN/YELLOW commands are audited as approved and run inside
        the configured scope.
        """
        decision = self.policy_kernel.evaluate_approved(command)
        if decision.blocked:
            if "character limit" in decision.reason:
                reason = f"[SECURITY BLOCK] {decision.reason}"
                self._audit(self.actor, reason, Zone.RED)
                return ExecutionResult(
                    status="BLOCKED",
                    zone=Zone.RED.value,
                    command="",
                    reason=reason,
                )
            self._audit(self.actor, f"APPROVAL DENIED (RED): {command}", Zone.RED)
            return ExecutionResult(
                status="BLOCKED",
                zone=Zone.RED.value,
                command=command,
                reason=decision.reason,
            )
        policy = self.policy_kernel.execution_policy(approved=True)
        # Actual isolation requires both the policy to request it AND a runner
        # that provides the boundary; injection tests may omit the runner.
        isolated = policy.isolated and (self.approved_runner is not None)
        runner = self.approved_runner if isolated else self.runner
        if self.emergency_stop is not None:
            try:
                self.emergency_stop.assert_operational()
            except Exception:  # noqa: BLE001 - emergency latch blocks dispatch
                reason = "emergency stop is engaged; execution is disabled"
                self._audit(self.actor, f"BLOCKED: {reason}", Zone.RED)
                return ExecutionResult(
                    status="BLOCKED",
                    zone=Zone.RED.value,
                    command=command,
                    reason=reason,
                )
        self._audit(self.actor, f"APPROVED+EXECUTING: {command}", decision.zone)
        return self._run_in_sandbox(
            command,
            decision.zone,
            runner=runner,
            isolated=isolated,
        )

    def reset_sensitive_actions(self, session_id: Optional[str]) -> None:
        """Record that a human re-authorised this session's caution budget."""
        reset_sensitive_actions(session_id, self.rate_limiter)

    def _run_in_sandbox(
        self,
        command: str,
        zone: Zone,
        *,
        runner: Optional[Runner] = None,
        isolated: bool = False,
    ) -> ExecutionResult:
        """Run *command* in the scope-locked working directory."""
        cwd = self._scope_cwd()
        env = _sanitise_env()
        started = time.monotonic()
        try:
            _parse_argv(command)
            stdout, stderr, exit_code = (runner or self.runner)(
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

        stdout = _truncate_output(stdout)
        stderr = _truncate_output(stderr)
        duration_ms = int((time.monotonic() - started) * 1000)
        return ExecutionResult(
            status="OK",
            zone=zone.value,
            command=command,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=duration_ms,
            reason=(
                "Executed in isolated container with configured scope."
                if isolated
                else "Executed within configured scope."
            ),
        )
