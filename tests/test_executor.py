"""Executor tests — gateway gating, sandbox env, and audit, with no real shell.

A recording runner captures what *would* have been spawned, and a recording
audit sink keeps the real tamper-evident ledger untouched.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from aios import config
from aios.core.executor import (
    DockerRunner,
    Executor,
    approved_runner_from_config,
    validate_approved_execution_backend,
    _bounded_run,
    _default_runner,
    _parse_argv,
)
from aios.security.gateway import RateLimiter


class RecordingRunner:
    """Captures the spawn args and returns a canned result instead of running."""

    def __init__(self, out: str = "ok", err: str = "", code: int = 0) -> None:
        self.calls: list[dict] = []
        self.out, self.err, self.code = out, err, code

    def __call__(self, command, *, cwd, env, timeout_s):
        self.calls.append({"command": command, "cwd": cwd, "env": env, "timeout_s": timeout_s})
        return self.out, self.err, self.code


class RecordingAudit:
    """Captures audit calls so tests never touch the on-disk ledger."""

    def __init__(self) -> None:
        self.entries: list[tuple] = []

    def __call__(self, actor, payload, zone, **kwargs):
        self.entries.append((actor, payload, str(zone)))


def _executor(runner=None):
    return Executor(
        runner=runner or RecordingRunner(),
        rate_limiter=RateLimiter(),
        audit_log=RecordingAudit(),
    )


def test_red_command_is_blocked_and_never_runs() -> None:
    runner = RecordingRunner()
    result = _executor(runner).execute("rm -rf /")
    assert result.status == "BLOCKED"
    assert result.zone == "RED"
    assert result.exit_code is None
    assert runner.calls == []  # never spawned


def test_yellow_command_requires_approval_and_never_runs() -> None:
    runner = RecordingRunner()
    result = _executor(runner).execute("pip install flask")
    assert result.status == "REQUIRE_APPROVAL"
    assert result.zone == "YELLOW"
    assert runner.calls == []


def test_green_command_runs_in_sandbox() -> None:
    runner = RecordingRunner(out="hello\n")
    result = _executor(runner).execute("echo hello")
    assert result.status == "OK"
    assert result.zone == "GREEN"
    assert result.exit_code == 0
    assert result.stdout == "hello\n"
    assert len(runner.calls) == 1
    assert runner.calls[0]["command"] == "echo hello"


def test_scope_cwd_is_the_repo_root_not_the_scope_root(monkeypatch, tmp_path) -> None:
    # training_ground.X imports (and probe_common's training_ground/-relative
    # allowlist regexes) only resolve if commands run from the repo root that
    # training_ground/ lives under -- not from training_ground/ itself.
    scope_root = tmp_path / "training_ground"
    scope_root.mkdir()
    monkeypatch.setattr(config, "SCOPE_ROOTS", [scope_root])
    assert _executor()._scope_cwd() == tmp_path


def test_green_command_runs_from_the_repo_root(monkeypatch, tmp_path) -> None:
    scope_root = tmp_path / "training_ground"
    scope_root.mkdir()
    monkeypatch.setattr(config, "SCOPE_ROOTS", [scope_root])
    runner = RecordingRunner()
    _executor(runner).execute("echo hi")
    assert runner.calls[0]["cwd"] == str(tmp_path)


def test_default_runner_handles_safe_builtin_without_a_shell(tmp_path) -> None:
    result = _default_runner("echo hello world", cwd=str(tmp_path), env={}, timeout_s=1)
    assert result == ("hello world\n", "", 0)


def test_sandbox_strips_secret_env_vars(monkeypatch) -> None:
    monkeypatch.setenv("MY_API_KEY", "super-secret")
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "tok")
    monkeypatch.setenv("SAFE_VAR", "fine")
    runner = RecordingRunner()
    _executor(runner).execute("echo hi")
    env = runner.calls[0]["env"]
    assert "MY_API_KEY" not in env
    assert "AWS_BEARER_TOKEN_BEDROCK" not in env
    assert env.get("SAFE_VAR") == "fine"


def test_sandbox_prefers_project_venv_tools(monkeypatch, tmp_path) -> None:
    venv_bin = tmp_path / ".venv" / ("Scripts" if os.name == "nt" else "bin")
    venv_bin.mkdir(parents=True)
    monkeypatch.setattr("aios.core.executor.config.PROJECT_ROOT", tmp_path)
    runner = RecordingRunner()

    _executor(runner).execute("echo hi")

    assert runner.calls[0]["env"]["PATH"].split(os.pathsep)[0] == str(venv_bin)


def test_default_runner_resolves_bare_program_via_sanitised_path(monkeypatch, tmp_path) -> None:
    # Windows' CreateProcess searches the parent exe's directory and the cwd
    # BEFORE the child PATH, so a bare `python` could silently ignore the venv
    # that _sanitise_env put first — or hit a binary planted inside the writable
    # sandbox. The runner must resolve bare names through the sanitised PATH.
    captured: dict = {}

    def fake_bounded_run(argv, **kwargs):
        captured["argv"] = list(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    sentinel = str(tmp_path / "venv-python.exe")
    monkeypatch.setattr("aios.core.executor._bounded_run", fake_bounded_run)
    monkeypatch.setattr(
        "aios.core.executor.shutil.which", lambda name, path=None: sentinel
    )

    _default_runner("python -m pytest -q", cwd=str(tmp_path), env={"PATH": "x"}, timeout_s=1)

    assert captured["argv"][0] == sentinel
    assert captured["argv"][1:] == ["-m", "pytest", "-q"]


def test_default_runner_keeps_pathed_and_unresolvable_programs_unchanged(
    monkeypatch, tmp_path
) -> None:
    spawned: list[list[str]] = []
    which_calls: list[str] = []

    def fake_bounded_run(argv, **kwargs):
        spawned.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("aios.core.executor._bounded_run", fake_bounded_run)
    monkeypatch.setattr(
        "aios.core.executor.shutil.which",
        lambda name, path=None: which_calls.append(name) or None,
    )

    # Unresolvable bare name: keep the old spawn behaviour (argv untouched).
    _default_runner("python --version", cwd=str(tmp_path), env={}, timeout_s=1)
    assert spawned[-1][0] == "python"
    assert which_calls == ["python"]

    # A program reference that already carries a path is never re-resolved.
    pathed = f".venv{os.sep}Scripts{os.sep}python.exe --version"
    _default_runner(pathed, cwd=str(tmp_path), env={}, timeout_s=1)
    assert spawned[-1][0] == f".venv{os.sep}Scripts{os.sep}python.exe"
    assert which_calls == ["python"]


def test_parse_argv_rejects_null_bytes() -> None:
    with pytest.raises(ValueError, match="shell composition"):
        _parse_argv("echo\x00unsafe")


def test_bounded_runner_rejects_unsafe_structured_argv() -> None:
    with pytest.raises(ValueError, match="unsafe structured argv"):
        _bounded_run(["echo", "unsafe;command"], timeout=1)


def test_execute_approved_runs_yellow_command() -> None:
    runner = RecordingRunner(out="installed")
    result = _executor(runner).execute_approved("pip install flask")
    assert result.status == "OK"
    assert result.zone == "YELLOW"
    assert len(runner.calls) == 1


def test_execute_approved_uses_isolated_runner_when_configured() -> None:
    host = RecordingRunner()
    isolated = RecordingRunner(out="isolated")
    result = Executor(
        runner=host,
        approved_runner=isolated,
        rate_limiter=RateLimiter(),
        audit_log=RecordingAudit(),
    ).execute_approved("python -m pytest test_greeter.py -q")

    assert result.status == "OK"
    assert result.stdout == "isolated"
    assert "isolated container" in result.reason
    assert host.calls == []
    assert len(isolated.calls) == 1


def test_execute_approved_uses_kernel_policy_for_isolation_flag(monkeypatch) -> None:
    monkeypatch.setattr("aios.core.executor.config.APPROVED_EXECUTION_BACKEND", "host")
    host = RecordingRunner(out="host")
    isolated = RecordingRunner(out="isolated")
    result = Executor(
        runner=host,
        approved_runner=isolated,
        rate_limiter=RateLimiter(),
        audit_log=RecordingAudit(),
    ).execute_approved("pip install flask")

    assert result.status == "OK"
    assert result.stdout == "host"
    assert "Executed within configured scope" in result.reason
    assert len(host.calls) == 1
    assert host.calls[0]["command"] == "pip install flask"
    assert isolated.calls == []


def test_real_runner_retains_only_bounded_output() -> None:
    result = _bounded_run(
        [sys.executable, "-c", "print('x' * 10000)"],
        timeout=10,
        max_output_bytes=1024,
    )

    assert result.returncode == 0
    assert len(result.stdout) < 1200
    assert "[OUTPUT TRUNCATED]" in result.stdout


def test_executor_truncates_output_from_injected_runner(monkeypatch) -> None:
    monkeypatch.setattr("aios.core.executor.config.MAX_COMMAND_OUTPUT_BYTES", 1024)
    result = _executor(RecordingRunner(out="x" * 10000)).execute("echo hello")

    assert len(result.stdout) < 1200
    assert "[OUTPUT TRUNCATED]" in result.stdout


def test_executor_refuses_oversized_command_without_auditing_payload(monkeypatch) -> None:
    monkeypatch.setattr("aios.core.executor.config.MAX_COMMAND_CHARS", 8)
    audit = RecordingAudit()
    result = Executor(
        runner=RecordingRunner(),
        rate_limiter=RateLimiter(),
        audit_log=audit,
    ).execute("echo " + "x" * 100)

    assert result.status == "BLOCKED"
    assert result.command == ""
    assert "x" * 100 not in audit.entries[0][1]


def test_docker_runner_uses_locked_down_container_contract(tmp_path) -> None:
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    runner = DockerRunner(image="test-image", process_runner=fake_run)
    result = runner(
        "python -m pytest test_greeter.py -q",
        cwd=str(tmp_path),
        env={"PATH": "safe"},
        timeout_s=9,
    )

    assert result == ("ok", "", 0)
    argv, kwargs = calls[0]
    assert argv[:3] == ["docker", "run", "--rm"]
    assert ["--network", "none"] == argv[argv.index("--network"):argv.index("--network") + 2]
    assert "--read-only" in argv
    assert ["--cap-drop", "ALL"] == argv[argv.index("--cap-drop"):argv.index("--cap-drop") + 2]
    assert ["--security-opt", "no-new-privileges"] == argv[
        argv.index("--security-opt"):argv.index("--security-opt") + 2
    ]
    assert "test-image" in argv
    assert argv[-5:] == ["python", "-m", "pytest", "test_greeter.py", "-q"]
    assert kwargs["shell"] is False
    assert kwargs["timeout"] == 9
    # --mount requires EVERY comma-separated field to be key=value: a bare
    # "rw" (the -v shorthand) makes modern Docker refuse the run with exit
    # 125, fail-closing every container-backed verify (live, 2026-07-03).
    mount = argv[argv.index("--mount") + 1]
    assert all("=" in field for field in mount.split(",")), (
        f"--mount fields must all be key=value; got {mount!r}"
    )
    assert mount.startswith("type=bind,src=") and ",dst=/workspace" in mount
    assert "bind-propagation=private" in mount


def test_docker_runner_rejects_mount_breaking_cwd_characters(tmp_path) -> None:
    runner = DockerRunner(image="test-image")
    for bad in ("path,with,commas", "path=equals"):
        cwd = tmp_path / bad
        cwd.mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValueError, match="characters not permitted"):
            runner("echo hi", cwd=str(cwd), env={}, timeout_s=1)


def test_default_execution_backend_is_container() -> None:
    # Phase 2: the supported default is the container. (Skipped only when the
    # operator has explicitly overridden the backend in their environment / .env.)
    if os.environ.get("AIOS_APPROVED_EXECUTION_BACKEND"):
        pytest.skip("backend explicitly overridden in environment")
    assert config.APPROVED_EXECUTION_BACKEND == "container"


def test_container_backend_validation_degrades_when_image_is_unavailable(monkeypatch) -> None:
    # Degrade, don't brick: a container backend with no available Docker/image must
    # NOT raise at startup (that would brick the whole app); it returns a warning
    # and the exec path fails closed at call time instead.
    monkeypatch.setattr("aios.core.executor.config.APPROVED_EXECUTION_BACKEND", "container")
    monkeypatch.setattr(
        "aios.core.executor._bounded_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, stdout="", stderr="missing"),
    )

    warning = validate_approved_execution_backend()

    assert warning is not None
    assert "missing" in warning
    assert "host" in warning.lower()  # tells the operator how to opt out


def test_container_backend_validation_is_silent_when_available(monkeypatch) -> None:
    monkeypatch.setattr("aios.core.executor.config.APPROVED_EXECUTION_BACKEND", "container")
    monkeypatch.setattr(
        "aios.core.executor._bounded_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout="ok", stderr=""),
    )

    assert validate_approved_execution_backend() is None


def test_host_backend_validation_warns_development_only(monkeypatch) -> None:
    monkeypatch.setattr("aios.core.executor.config.APPROVED_EXECUTION_BACKEND", "host")

    warning = validate_approved_execution_backend()

    assert warning is not None
    assert "development only" in warning.lower()
    assert "isolation boundary" in warning.lower()


def test_unknown_backend_validation_still_raises(monkeypatch) -> None:
    monkeypatch.setattr("aios.core.executor.config.APPROVED_EXECUTION_BACKEND", "unknown")

    with pytest.raises(RuntimeError, match="unsupported AIOS_APPROVED_EXECUTION_BACKEND"):
        validate_approved_execution_backend()


def test_container_default_routes_approved_command_through_container_not_host(monkeypatch) -> None:
    # The escape boundary: with the container backend, an approved arbitrary command
    # is dispatched through the locked-down DockerRunner and NEVER the host runner.
    monkeypatch.setattr("aios.core.executor.config.APPROVED_EXECUTION_BACKEND", "container")
    docker_argv: list[list[str]] = []

    def fake_run(argv, **kwargs):
        docker_argv.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr("aios.core.executor._bounded_run", fake_run)
    host = RecordingRunner()
    executor = Executor(
        runner=host,
        approved_runner=approved_runner_from_config(),
        rate_limiter=RateLimiter(),
        audit_log=RecordingAudit(),
    )

    result = executor.execute_approved("pip install flask")

    assert result.status == "OK"
    assert host.calls == []  # the host runner is never touched under the container default
    assert docker_argv and docker_argv[0][:3] == ["docker", "run", "--rm"]
    argv = docker_argv[0]
    assert ["--network", "none"] == argv[argv.index("--network"):argv.index("--network") + 2]
    assert "--read-only" in argv and "--cap-drop" in argv


def test_container_backend_fails_closed_when_runner_raises(monkeypatch) -> None:
    # No silent host fallback: if the container cannot run, the approved-exec path
    # returns ERROR rather than dropping to the host runner.
    monkeypatch.setattr("aios.core.executor.config.APPROVED_EXECUTION_BACKEND", "container")

    def boom(*args, **kwargs):
        raise RuntimeError("docker daemon unreachable")

    monkeypatch.setattr("aios.core.executor._bounded_run", boom)
    host = RecordingRunner()
    executor = Executor(
        runner=host,
        approved_runner=approved_runner_from_config(),
        rate_limiter=RateLimiter(),
        audit_log=RecordingAudit(),
    )

    result = executor.execute_approved("pip install flask")

    assert result.status == "ERROR"
    assert host.calls == []  # fail closed, never the host


def test_invalid_approved_execution_backend_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr("aios.core.executor.config.APPROVED_EXECUTION_BACKEND", "unknown")
    result = Executor(
        runner=RecordingRunner(),
        approved_runner=approved_runner_from_config(),
        rate_limiter=RateLimiter(),
        audit_log=RecordingAudit(),
    ).execute_approved("python -m pytest test_greeter.py -q")

    assert result.status == "ERROR"
    assert "unsupported AIOS_APPROVED_EXECUTION_BACKEND" in result.reason


def test_human_reauthorisation_resets_sensitive_action_budget() -> None:
    limiter = RateLimiter(max_per_session=1)
    executor = Executor(
        runner=RecordingRunner(),
        rate_limiter=limiter,
        audit_log=RecordingAudit(),
    )
    assert executor.execute("pip install flask", session_id="s1").status == "REQUIRE_APPROVAL"
    second = executor.execute("pip install flask", session_id="s1")
    assert second.status == "REQUIRE_APPROVAL"
    assert "re-authorisation required" in second.reason

    executor.reset_sensitive_actions("s1")

    assert executor.execute("pip install flask", session_id="s1").status == "REQUIRE_APPROVAL"


def test_execute_approved_still_refuses_red() -> None:
    runner = RecordingRunner()
    result = _executor(runner).execute_approved("rm -rf /")
    assert result.status == "BLOCKED"
    assert runner.calls == []


def test_approved_bare_mkdir_no_longer_escapes_the_sandbox(monkeypatch, tmp_path) -> None:
    """Regression for the 2026-07-10 adversarial audit: because _scope_cwd()
    runs commands from the repo root (not training_ground/ itself, needed for
    training_ground.x imports -- see _scope_cwd's docstring), an approved bare
    "mkdir probe_dir" used to create probe_dir next to training_ground/
    instead of nested inside it, silently escaping the sandbox a human
    approver believed they were confining the action to. This does NOT mock
    the runner -- it exercises the real default subprocess runner end to end,
    the same way the audit's live repro did."""
    scope_root = tmp_path / "training_ground"
    scope_root.mkdir()
    monkeypatch.setattr(config, "SCOPE_ROOTS", [scope_root])
    from aios.security import scope_lock
    monkeypatch.setattr(scope_lock, "_scope_roots", [scope_root])

    executor = Executor(rate_limiter=RateLimiter(), audit_log=RecordingAudit())
    result = executor.execute_approved("mkdir probe_dir")

    assert result.status == "BLOCKED"
    assert result.zone == "RED"
    assert not (tmp_path / "probe_dir").exists(), "escaped outside the sandbox"
    assert not (scope_root / "probe_dir").exists()

    # The correctly-prefixed, sandbox-relative form still works and lands
    # exactly where a human approver expects.
    result2 = executor.execute_approved("mkdir training_ground/probe_dir")
    assert result2.status == "OK"
    assert (scope_root / "probe_dir").is_dir()


@pytest.mark.parametrize(
    "command",
    [
        "echo hello > x.txt",
        "echo hello & some-new-tool",
        "cat notes.txt | some-new-tool",
        "pytest & some-new-tool",
    ],
)
def test_shell_composition_is_blocked_and_never_runs(command: str) -> None:
    runner = RecordingRunner()
    result = _executor(runner).execute(command)
    assert result.status == "BLOCKED"
    assert result.zone == "RED"
    assert runner.calls == []


def test_every_outcome_is_audited() -> None:
    audit = RecordingAudit()
    ex = Executor(runner=RecordingRunner(), rate_limiter=RateLimiter(), audit_log=audit)
    ex.execute("rm -rf /")
    ex.execute("echo hi")
    assert len(audit.entries) == 2
