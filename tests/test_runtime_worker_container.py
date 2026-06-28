"""Phase 2b — the worker's run_command (verification) runs inside the container.

The worker executes its MissionContract verification_commands; those are the only
arbitrary commands a worker runs, and they must go through the Phase 2 container
boundary (container-by-default, host a loud opt-out), fail-closed — never a silent
host run when the container is unavailable.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

from aios.runtime.backends import ControlledSubprocessBackend
from aios.runtime.contracts import MissionContract
from aios.runtime.worker_api import WorkerRuntime


def _contract(workspace: Path, commands: list[str]) -> MissionContract:
    return MissionContract(
        mission_id="m-2b",
        goal="run verification",
        worker_type="deterministic_worker",
        created_by="planner",
        workspace_root=str(workspace),
        allowed_files=["x.txt"],
        allowed_tools=["run_command"],
        verification_commands=commands,
        timeout_seconds=30,
    )


def _runtime(tmp_path: Path, commands: list[str], command_runner=None) -> WorkerRuntime:
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    runtime_root = tmp_path / "runtime"
    return WorkerRuntime(
        _contract(workspace, commands),
        worker_id="w-2b",
        runtime_root=runtime_root,
        result_path=runtime_root / "result.json",
        command_runner=command_runner,
    )


def test_run_command_routes_through_the_container(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("aios.runtime.worker_api.config.APPROVED_EXECUTION_BACKEND", "container")
    docker_argv: list[list[str]] = []

    def fake_run(argv, **kwargs):
        docker_argv.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr("aios.core.executor._bounded_run", fake_run)
    rt = _runtime(tmp_path, ["echo ok"])  # no command_runner -> config-selected DockerRunner

    result = rt.run_command(["echo", "ok"])

    assert result["returncode"] == 0
    assert docker_argv, "verification did not run through the container"
    argv = docker_argv[0]
    assert argv[:3] == ["docker", "run", "--rm"]
    assert ["--network", "none"] == argv[argv.index("--network"):argv.index("--network") + 2]
    assert "--read-only" in argv and "--cap-drop" in argv
    assert any("dst=/workspace" in tok for tok in argv)  # the worker's workspace is mounted
    assert argv[-2:] == ["echo", "ok"]


def test_run_command_fails_closed_when_container_unavailable(tmp_path) -> None:
    def boom(command, *, cwd, env, timeout_s):
        raise RuntimeError("docker daemon unreachable")

    rt = _runtime(tmp_path, ["echo ok"], command_runner=boom)

    result = rt.run_command(["echo", "ok"])

    assert result["returncode"] != 0  # fail-closed, never a host fallback
    assert "unavailable" in result["stderr"].lower()


def test_run_command_host_opt_out_runs_on_host(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("aios.runtime.worker_api.config.APPROVED_EXECUTION_BACKEND", "host")
    # `--version` needs no quoting (avoids the Windows shlex quote-retention quirk)
    # and proves real host execution: a container path here would fail closed (no
    # docker), so a 0 exit with the interpreter's version is host execution.
    cmd_str = f"{sys.executable} --version"
    argv = shlex.split(cmd_str, posix=os.name != "nt")
    rt = _runtime(tmp_path, [cmd_str])  # host backend -> direct host subprocess

    result = rt.run_command(argv)

    assert result["returncode"] == 0
    assert "Python" in (result["stdout"] + result["stderr"])


def test_restricted_environment_propagates_execution_backend(tmp_path, monkeypatch) -> None:
    # The worker must honor the operator's backend choice; the var was previously
    # stripped, so a host-opt-out worker would wrongly default back to container.
    monkeypatch.setenv("AIOS_APPROVED_EXECUTION_BACKEND", "host")
    backend = ControlledSubprocessBackend(tmp_path / "runtime")
    env = backend._restricted_environment()
    assert env.get("AIOS_APPROVED_EXECUTION_BACKEND") == "host"
