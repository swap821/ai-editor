"""Executor tests — gateway gating, sandbox env, and audit, with no real shell.

A recording runner captures what *would* have been spawned, and a recording
audit sink keeps the real tamper-evident ledger untouched.
"""
from __future__ import annotations

import os

import pytest

from aios.core.executor import Executor, _default_runner
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


def test_execute_approved_runs_yellow_command() -> None:
    runner = RecordingRunner(out="installed")
    result = _executor(runner).execute_approved("pip install flask")
    assert result.status == "OK"
    assert result.zone == "YELLOW"
    assert len(runner.calls) == 1


def test_execute_approved_still_refuses_red() -> None:
    runner = RecordingRunner()
    result = _executor(runner).execute_approved("rm -rf /")
    assert result.status == "BLOCKED"
    assert runner.calls == []


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
