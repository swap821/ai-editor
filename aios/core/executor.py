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
from aios.security.scope_lock import (
    command_cwd as scope_lock_command_cwd,
    get_scope_roots,
)
from aios.security.gateway import (
    RateLimiter,
    Zone,
    reset_sensitive_actions,
)
from aios.infrastructure.executor.argv import (
    argv_is_safe as _argv_is_safe,
    parse_argv as _parse_argv,
)
from aios.operations.tracing import get_trace_context

if TYPE_CHECKING:
    from aios.policy.kernel import PolicyKernel
    from aios.security.scope_lock import ScopeContext

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
#: uid:gid used when the invoking uid is unavailable or unsafe. `nobody`
#: exists in the worker image, so `getpwuid` resolves and HOME lookups work.
_UNPRIVILEGED_FALLBACK_USER = "65534:65534"


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
    #: WHICH control refused, when ``status == "BLOCKED"``.
    #:
    #: A refusal used to carry only free text, so nothing downstream could tell
    #: a genuine RED refusal from an incidental one (an oversize command, a
    #: malformed argument). Organ 55's M1 turns on that distinction: refusing
    #: for an unrelated reason is a classification accident, and counting it as
    #: a governance win would let the system pass by luck.
    #:
    #: `security_gateway` | `execute_approved` | `emergency_stop` |
    #: `command_limit` (a resource guard, deliberately NOT a RED control).
    control: str = ""


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
        # SIGCONT/SIGKILL/killpg/getpgid are POSIX-ONLY. Guarding them with
        # `except (OSError, ProcessLookupError)` did not cover Windows, where the
        # names do not exist at all: `signal.SIGCONT` raised AttributeError,
        # which is not in that tuple, so it escaped `_bounded_run`, the
        # `process.kill()` fallback below was unreachable, and a timed-out child
        # was left RUNNING while the caller saw an attribute error instead of a
        # timeout. Found by the mypy gate; reproduced in
        # tests/test_executor_timeout_kill_is_cross_platform.py.
        #
        # The group kill stays the preferred path where it exists -- killing only
        # the immediate child leaves the process GROUP alive, which is how a
        # forking command outlives its own timeout.
        sigcont = getattr(signal, "SIGCONT", None)
        if sigcont is not None:
            # SIGSTOP bypass: wake stopped processes so they can receive the
            # fatal signal.
            try:
                os.kill(process.pid, sigcont)
            except (OSError, ProcessLookupError):
                pass

        killpg = getattr(os, "killpg", None)
        getpgid = getattr(os, "getpgid", None)
        sigkill = getattr(signal, "SIGKILL", None)
        killed_group = False
        if killpg is not None and getpgid is not None and sigkill is not None:
            # Kill the entire process group — not just the immediate child.
            try:
                killpg(getpgid(process.pid), sigkill)
                killed_group = True
            except (OSError, ProcessLookupError):
                killed_group = False
        if not killed_group:
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


def _mount_spec_safe(path: str) -> bool:
    """Is `path` safe to interpolate into a Docker ``--mount`` spec?

    H4 — commas, equals and non-drive-letter colons are field separators in the
    ``--mount`` syntax, so a path containing one can break out of the spec and
    append fields of its own. A normal Windows root ("C:\\...") is allowed.

    A function rather than an inline block because the writable scope mounts
    below must be validated by the SAME rule as the workspace mount. Two copies
    of a containment check kept in step by comment is the exact shape that has
    already produced escapes in this repo.
    """
    colon_scan = (
        path[2:] if len(path) >= 2 and path[1] == ":" and path[0].isalpha() else path
    )
    return not (any(ch in path for ch in ",=") or ":" in colon_scan)


def _container_user() -> str:
    """The ``uid:gid`` the disposable sandbox runs as.

    Derived from the INVOKING process rather than hardcoded to 65534 (nobody).

    The hardcode predates the read-only-workspace fix. When the whole repository
    was bind-mounted read-write, limiting the uid genuinely limited the damage a
    sandboxed command could do. It no longer does: the workspace bind is
    ``readonly=true`` and only declared scope roots are remounted writable, and
    Docker enforces mount permissions independently of the uid. The reachable set
    is defined by the MOUNTS.

    What the hardcode did still do was break the sandbox. The scope roots on the
    host belong to whoever checked the repository out, so on Linux uid 65534
    could not write them and no file-creating mission could succeed::

        touch: cannot touch '/workspace/training_ground/x': Permission denied

    Docker Desktop on Windows translates bind-mount ownership itself, which is
    why this was invisible on the operator's machine until the containment suite
    ran on CI (inventory item 84b). It also meant any file the sandbox DID create
    would be owned by nobody -- files the operator cannot edit or delete without
    root, in a workspace whose whole purpose is to be host-visible.

    The trade-off, stated rather than buried: a container escape now holds the
    invoking user's privileges instead of nobody's. That is bounded by
    ``--cap-drop ALL``, ``--security-opt no-new-privileges``, a read-only rootfs
    and ``--network none`` -- and the parent backend process already runs as that
    user.

    Two fallbacks, both fail-safe:

    * **No POSIX uid** (Windows). Docker Desktop maps ownership itself, so the
      historical unprivileged id remains correct there.
    * **Running as root.** A sandbox must never be root even if the backend is.
      The old hardcode had no such guard; this one does.
    """
    getuid = getattr(os, "getuid", None)
    getgid = getattr(os, "getgid", None)
    if getuid is None or getgid is None:
        return _UNPRIVILEGED_FALLBACK_USER
    uid, gid = getuid(), getgid()
    if uid == 0:
        return _UNPRIVILEGED_FALLBACK_USER
    return f"{uid}:{gid}"


def _is_windows_style(path: str) -> bool:
    r"""True only for a real Windows path: a drive (``C:\...``) or a UNC share.

    NOT `ntpath.isabs`. That was the original discriminator and it is wrong for
    POSIX paths in a way that depends on the Python version:

        Python 3.12:  ntpath.isabs("/home/runner/x")  ->  True
        Python 3.13+: ntpath.isabs("/home/runner/x")  ->  False

    A leading slash is "absolute" under Windows semantics (drive-relative), so
    on Python 3.12 -- which CI runs -- every POSIX absolute path took the
    Windows branch and `ntpath.normpath` rewrote `/home/runner/...` into
    `\home\runner\...`. Docker then refused the whole container:

        invalid mount config for type "bind": bind source path does not exist

    That broke `DockerRunner` outright on Linux from 2026-08-19 until it was
    caught by the first REAL container run on 2026-09-01. Nothing noticed
    because the unit tests assert the constructed argv on Windows (where the
    branch happens to be right), the executor-service integration tests use a
    different code path, and the operator's machine is Windows on 3.14.

    A drive prefix is the property that actually requires ntpath semantics, so
    that is what this tests.
    """
    drive, _ = ntpath.splitdrive(path)
    return bool(drive) or path.startswith("\\\\")


def _writable_scope_mounts(resolved_cwd: str) -> list[str]:
    """``--mount`` args remounting each scope root read-write inside /workspace.

    The workspace bind is read-only (see :meth:`DockerRunner.__call__`), so the
    sandbox needs its own roots handed back writable or no mission could create
    a file. The writable set is derived from
    :func:`aios.security.scope_lock.get_scope_roots` -- the live, re-declarable
    authority -- and never from a second list kept here. A second derivation of
    "what is in scope" is how containment escapes happen; `command_cwd()` exists
    for the same reason.

    A root that is not under the mounted workspace is SKIPPED rather than
    mounted somewhere invented: silently widening the mount to reach it would
    hand the sandbox a path the workspace never contained.
    """
    mounts: list[str] = []
    try:
        roots = get_scope_roots()
    except Exception:  # noqa: BLE001 - fail closed: no roots means nothing writable
        return mounts

    base = (
        PureWindowsPath(resolved_cwd)
        if _is_windows_style(resolved_cwd)
        else Path(resolved_cwd)
    )
    for root in roots:
        src = (
            ntpath.normpath(str(root))
            if _is_windows_style(str(root))
            else str(Path(root).resolve())
        )
        if not _mount_spec_safe(src):
            continue
        try:
            relative = (
                PureWindowsPath(src).relative_to(base)
                if isinstance(base, PureWindowsPath)
                else Path(src).relative_to(base)
            )
        except ValueError:
            continue  # outside the workspace: skip, never widen
        rel_posix = "/".join(relative.parts)
        if not rel_posix or rel_posix.startswith(".."):
            continue
        mounts.extend(
            [
                "--mount",
                f"type=bind,src={src},dst=/workspace/{rel_posix},"
                "bind-propagation=private",
            ]
        )
    return mounts


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
            len(cwd) >= 3 and cwd[1] == ":" and cwd[0].isalpha()
        ) or cwd.startswith("\\\\")
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
        if not _mount_spec_safe(resolved_cwd):
            raise ValueError(
                "working directory path contains characters not permitted in Docker mount spec"
            )
        # --mount requires every field to be key=value: a bare "rw" (the -v
        # volume shorthand) is rejected by modern Docker with exit 125
        # ("invalid field 'rw' must be a key=value pair"), which fail-closed
        # every container-backed verify the moment a real daemon was present
        # (first observed live 2026-07-03). bind-propagation=private prevents
        # mounts created inside the sandbox from leaking back to the host.
        #
        # `readonly` added 2026-08-19. Bind mounts are read-write by DEFAULT, and
        # `cwd` here is the REPO ROOT -- `command_cwd()` returns the scope root's
        # parent on purpose, so `training_ground` imports as a package. The
        # container is otherwise well sealed (no network, read-only rootfs, all
        # caps dropped, no-new-privileges, uid 65534), which made this bind the
        # entire writable surface: a sandboxed command could write
        # `aios/security/*` -- the frozen spine that adjudicates it -- and
        # `.aios/state/ORGAN_GREEN_LEDGER.json`, the record of its own status.
        # Reproduced before the fix; both writes succeeded.
        #
        # The repo is mounted read-only and only the scope roots are remounted
        # writable on top, so the sandbox keeps exactly the write access its
        # missions need and no more.
        mount = (
            f"type=bind,src={resolved_cwd},dst=/workspace,readonly=true,"
            "bind-propagation=private"
        )
        writable_mounts = _writable_scope_mounts(resolved_cwd)
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
            _container_user(),
            "--mount",
            mount,
            *writable_mounts,
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=64m",
            "--workdir",
            "/workspace",
            "--env",
            # An arbitrary uid has no /etc/passwd entry, so `getpwuid` raises
            # and `os.path.expanduser` -- plus anything in pytest/pip that
            # resolves a home -- fails. HOME is stripped from the child
            # environment by design (see _STRIPPED_NAMES), so set a
            # container-local one explicitly. /tmp is already the
            # noexec,nosuid,nodev tmpfs. This is NOT the host's home, which
            # stays stripped.
            "HOME=/tmp",
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
        ]
        # Organ 52: propagate the current trace context (correlation metadata
        # only -- never authority, per aios.operations.tracing's own module
        # docstring) as fixed --env entries, distinct from the job's own
        # security-reviewed environment_allowlist mechanism, which this must
        # not bypass or widen.
        for key, value in get_trace_context().as_env().items():
            docker_argv.extend(["--env", f"{key}={value}"])
        docker_argv.extend([self.image, *argv])
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
        if policy_kernel is None:
            from aios.application.governance.constitution_authority import (
                get_constitution_authority,
            )

            policy_kernel = PolicyKernel(
                rate_limiter=self.rate_limiter,
                constitution_authority=get_constitution_authority(),
            )
        self.policy_kernel = policy_kernel
        self.timeout_s = timeout_s
        self.actor = actor
        self.emergency_stop = emergency_stop
        #: Audit sink; defaults to the real tamper-evident ledger. Injectable so
        #: tests can record actions without touching the on-disk ledger.
        self._audit: Callable[..., object] = audit_log or log_action

    def _scope_cwd(self, scope: "ScopeContext | None" = None) -> Path:
        """The working directory for child processes.

        This is the repo root that the primary scope root (``training_ground``)
        lives under, NOT the scope root itself — so ``training_ground`` is
        importable as a package (``from training_ground.x import y``) rather
        than being mounted/spawned as if it were the root itself.

        Delegates to :func:`aios.security.scope_lock.command_cwd` rather than
        deriving the directory again here. The scope CHECK resolves relative
        command tokens against that same function, so the base that is checked
        and the base that is executed cannot drift apart — a drift is a
        containment escape, not a cosmetic mismatch, and this pair has drifted
        once already (this method read the process-start default
        ``config.SCOPE_ROOTS`` while the check read the live, re-declarable
        ``get_scope_roots()``). Asserted by
        ``tests/adversarial/test_control_consistency.py``.
        """
        cwd = scope_lock_command_cwd(scope)
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
                    control="command_limit",
                )
            self._audit(self.actor, f"BLOCKED: {command}", decision.zone)
            return ExecutionResult(
                status="BLOCKED",
                zone=decision.zone.value,
                command=command,
                reason=decision.reason,
                control=decision.control or "security_gateway",
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
                    control="emergency_stop",
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
                    control="command_limit",
                )
            self._audit(self.actor, f"APPROVAL DENIED (RED): {command}", Zone.RED)
            return ExecutionResult(
                status="BLOCKED",
                zone=Zone.RED.value,
                command=command,
                reason=decision.reason,
                control=decision.control or "execute_approved",
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
                    control="emergency_stop",
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
