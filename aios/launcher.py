"""Product launcher for the single-developer GAGOS installation.

The launcher is deliberately small and policy-aware.  Production and demo
profiles use the Compose topology, while development may run the API directly
for local debugging.  A missing container runtime is a refusal in production,
never an implicit host-execution fallback.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any


VALID_PROFILES = frozenset({"development", "demo", "production", "test"})
_SECRET_NAMES = ("AIOS_API_TOKEN", "AIOS_EXECUTOR_TOKEN", "AIOS_GRAFANA_ADMIN_PASSWORD")


class LauncherError(RuntimeError):
    """A safe, user-facing launcher refusal."""


@dataclass(frozen=True, slots=True)
class LauncherConfig:
    repo_root: Path
    data_dir: Path
    profile: str
    api_port: int
    gateway_port: int
    compose_file: Path
    state_file: Path
    log_file: Path

    @classmethod
    def from_environment(
        cls,
        *,
        repo_root: Path | None = None,
        profile: str | None = None,
    ) -> "LauncherConfig":
        root = (repo_root or Path(__file__).resolve().parents[1]).resolve()
        selected = (profile or os.getenv("AIOS_PROFILE", "production")).strip().lower()
        if selected not in VALID_PROFILES:
            raise LauncherError(
                f"unknown profile {selected!r}; choose one of "
                f"{', '.join(sorted(VALID_PROFILES))}"
            )
        data_dir = (
            Path(os.getenv("AIOS_DATA_DIR", str(root / "data"))).expanduser().resolve()
        )
        data_dir.mkdir(parents=True, exist_ok=True)
        return cls(
            repo_root=root,
            data_dir=data_dir,
            profile=selected,
            api_port=_int_env("AIOS_API_PORT", 8000),
            gateway_port=_int_env("AIOS_GATEWAY_PORT", 3000),
            compose_file=root / "docker-compose.yml",
            state_file=data_dir / "launcher-state.json",
            log_file=data_dir / "launcher.log",
        )


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise LauncherError(f"{name} must be an integer") from exc
    if not 1 <= value <= 65535:
        raise LauncherError(f"{name} must be between 1 and 65535")
    return value


def _env_file_values(path: Path) -> dict[str, str]:
    """Read only simple KEY=value entries, without ever logging their values."""
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", maxsplit=1)
        name = name.strip()
        value = value.strip().strip("\"'")
        if name in _SECRET_NAMES:
            values[name] = value
    return values


def _secret_value(config: LauncherConfig, name: str) -> str:
    return os.getenv(name, "") or _env_file_values(config.repo_root / ".env").get(
        name, ""
    )


def _is_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return not lowered or any(
        marker in lowered for marker in ("change-me", "replace-me", "example")
    )


def _production_preflight(config: LauncherConfig) -> None:
    if not config.compose_file.is_file():
        raise LauncherError(f"Compose file is missing: {config.compose_file}")
    if shutil.which("docker") is None:
        raise LauncherError(
            "production start refused: Docker is unavailable; host execution "
            "is not a production fallback"
        )
    if (
        os.getenv("AIOS_APPROVED_EXECUTION_BACKEND", "container").strip().lower()
        == "host"
    ):
        raise LauncherError(
            "production start refused: host execution backend is forbidden; "
            "use the private Executor Service"
        )
    missing = [
        name for name in _SECRET_NAMES if _is_placeholder(_secret_value(config, name))
    ]
    if missing:
        raise LauncherError(
            "production start refused: configure non-default " + ", ".join(missing)
        )


def _child_environment(config: LauncherConfig) -> dict[str, str]:
    env = os.environ.copy()
    env["AIOS_PROFILE"] = config.profile
    env.setdefault("AIOS_API_PORT", str(config.api_port))
    env.setdefault("AIOS_GATEWAY_PORT", str(config.gateway_port))
    return env


def _compose_command(config: LauncherConfig, *args: str) -> list[str]:
    return ["docker", "compose", "-f", str(config.compose_file), *args]


def _write_state(config: LauncherConfig, payload: dict[str, Any]) -> None:
    config.state_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = config.state_file.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, config.state_file)


def _read_state(config: LauncherConfig) -> dict[str, Any] | None:
    try:
        payload = json.loads(config.state_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _pid_is_launcher(pid: int) -> bool:
    if pid <= 0:
        return False
    proc_cmdline = Path(f"/proc/{pid}/cmdline")
    if proc_cmdline.is_file():
        try:
            command = (
                proc_cmdline.read_bytes()
                .replace(b"\0", b" ")
                .decode("utf-8", "replace")
            )
        except OSError:
            return False
        return "-m aios" in command
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _start_local(config: LauncherConfig, *, foreground: bool) -> int:
    if config.profile == "production":
        raise LauncherError("production cannot use the local host process")
    existing = _read_state(config)
    if (
        existing
        and existing.get("mode") == "local"
        and _pid_is_launcher(int(existing.get("pid", 0)))
    ):
        print(f"GAGOS is already running (pid {existing['pid']})")
        return 0
    env = _child_environment(config)
    command = [sys.executable, "-m", "aios"]
    if foreground:
        return subprocess.call(command, cwd=config.repo_root, env=env)
    config.log_file.parent.mkdir(parents=True, exist_ok=True)
    with config.log_file.open("ab") as log:
        process = subprocess.Popen(
            command,
            cwd=config.repo_root,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=(os.name != "nt"),
        )
    _write_state(
        config,
        {
            "mode": "local",
            "pid": process.pid,
            "profile": config.profile,
            "started_at": time.time(),
        },
    )
    print(f"GAGOS started locally (pid {process.pid})")
    return 0


def start(config: LauncherConfig, *, foreground: bool = False) -> int:
    if config.profile in {"production", "demo"}:
        _production_preflight(config) if config.profile == "production" else None
        command = _compose_command(config, "up", "-d", "--build")
        result = subprocess.run(
            command, cwd=config.repo_root, env=_child_environment(config), check=False
        )
        if result.returncode != 0:
            raise LauncherError(
                f"Compose start failed with exit code {result.returncode}"
            )
        _write_state(
            config,
            {"mode": "compose", "profile": config.profile, "started_at": time.time()},
        )
        print(f"GAGOS started with Compose at http://127.0.0.1:{config.gateway_port}")
        return 0
    return _start_local(config, foreground=foreground)


def stop(config: LauncherConfig) -> int:
    state = _read_state(config)
    if not state:
        print("GAGOS is not running (no launcher state)")
        return 0
    if state.get("mode") == "compose":
        if shutil.which("docker") is None:
            raise LauncherError(
                "cannot stop the Compose deployment: Docker is unavailable"
            )
        result = subprocess.run(
            _compose_command(config, "down"),
            cwd=config.repo_root,
            env=_child_environment(config),
            check=False,
        )
        if result.returncode != 0:
            raise LauncherError(
                f"Compose stop failed with exit code {result.returncode}"
            )
    elif state.get("mode") == "local":
        pid = int(state.get("pid", 0))
        if _pid_is_launcher(pid):
            os.kill(pid, signal.SIGTERM)
            print(f"Stopped local GAGOS process {pid}")
        else:
            print("Local GAGOS process is no longer running")
    else:
        raise LauncherError("unknown launcher state; refusing to guess what to stop")
    config.state_file.unlink(missing_ok=True)
    return 0


def status(config: LauncherConfig, *, as_json: bool = False) -> int:
    state = _read_state(config)
    payload: dict[str, Any] = {
        "running": bool(state),
        "profile": config.profile,
        "gateway_url": f"http://127.0.0.1:{config.gateway_port}",
        "state": state,
    }
    if state and state.get("mode") == "local":
        payload["running"] = _pid_is_launcher(int(state.get("pid", 0)))
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        state_label = "running" if payload["running"] else "stopped"
        print(f"GAGOS {state_label} ({config.profile})")
        print(f"  gateway: {payload['gateway_url']}")
        if state:
            print(f"  mode: {state.get('mode')}")
    return 0 if payload["running"] else 1


def open_gateway(config: LauncherConfig) -> int:
    url = f"http://127.0.0.1:{config.gateway_port}"
    if not webbrowser.open(url):
        raise LauncherError(f"could not open browser; use {url}")
    return 0


def v1_check(config: LauncherConfig, *, strict: bool, as_json: bool) -> int:
    from aios.application.governance import evaluate_release
    from aios.application.governance.runtime_proof import run_runtime_proofs

    proof_report = run_runtime_proofs(config.repo_root)
    declaration = evaluate_release(
        root=config.repo_root,
        profile=config.profile,
        executor_available=proof_report.proofs["executor_runtime_available"].passed,
        runtime_proofs=proof_report.boolean_map(),
        runtime_evidence=proof_report.evidence_map(),
    )
    if as_json:
        payload = declaration.as_dict()
        payload["runtime_proof"] = proof_report.as_dict()
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            f"GAGOS v1 declaration: "
            f"{'READY' if declaration.ready else 'NOT READY'} ({config.profile})"
        )
        for gate in declaration.gates:
            print(f"  [{gate.status}] {gate.name}: {gate.evidence}")
        print(f"  runtime probes: {'PASS' if proof_report.all_passed else 'FAIL'}")
        for proof in proof_report.proofs.values():
            print(
                f"    [{'PASS' if proof.passed else 'FAIL'}] "
                f"{proof.name}: {proof.evidence}"
            )
    return 0 if declaration.ready or not strict else 1


def _delegate_maintenance(command: str, arguments: list[str]) -> int:
    """Keep the Slice 21 maintenance commands under the one product CLI."""
    from aios.__main__ import main as aios_main

    return aios_main([command, *arguments])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gagos", description="Launch the local-first GAGOS product."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    start_parser = subparsers.add_parser(
        "start", help="Start the configured product profile."
    )
    start_parser.add_argument("--profile", choices=sorted(VALID_PROFILES), default=None)
    start_parser.add_argument(
        "--foreground",
        action="store_true",
        help="Keep a development API in the foreground.",
    )
    stop_parser = subparsers.add_parser(
        "stop", help="Stop the current product deployment."
    )
    stop_parser.add_argument("--profile", choices=sorted(VALID_PROFILES), default=None)
    status_parser = subparsers.add_parser("status", help="Show launcher state.")
    status_parser.add_argument(
        "--profile", choices=sorted(VALID_PROFILES), default=None
    )
    status_parser.add_argument("--json", action="store_true")
    open_parser = subparsers.add_parser(
        "open", help="Open the local gateway in a browser."
    )
    open_parser.add_argument("--profile", choices=sorted(VALID_PROFILES), default=None)
    doctor_parser = subparsers.add_parser(
        "doctor", help="Report measured runtime posture."
    )
    doctor_parser.add_argument("--json", action="store_true")
    v1_parser = subparsers.add_parser(
        "v1-check", help="Report the evidence-backed v1 release declaration."
    )
    v1_parser.add_argument("--strict", action="store_true")
    v1_parser.add_argument("--json", action="store_true")
    for maintenance_command in ("backup", "audit", "cortex", "memory", "executor"):
        maintenance_parser = subparsers.add_parser(
            maintenance_command,
            help=f"Run the {maintenance_command} maintenance command.",
        )
        maintenance_parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        config = LauncherConfig.from_environment(profile=getattr(args, "profile", None))
        if args.command == "start":
            return start(config, foreground=args.foreground)
        if args.command == "stop":
            return stop(config)
        if args.command == "status":
            return status(config, as_json=args.json)
        if args.command == "open":
            return open_gateway(config)
        if args.command == "doctor":
            from aios.operations.doctor import doctor_report

            report = doctor_report(profile=config.profile)
            if args.json:
                print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
            else:
                print(
                    f"GAGOS doctor: {'OK' if report.ok else 'FAILED'} "
                    f"({report.profile})"
                )
                for check in report.checks:
                    print(f"  [{check.status.upper()}] {check.name}: {check.message}")
            return 0 if report.ok else 1
        if args.command == "v1-check":
            return v1_check(config, strict=args.strict, as_json=args.json)
        if args.command in {"backup", "audit", "cortex", "memory", "executor"}:
            return _delegate_maintenance(args.command, args.arguments)
    except LauncherError as exc:
        print(f"gagos: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
