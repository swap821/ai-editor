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
#: The pinned learning public keys, mounted read-only into the production
#: container (``.aios`` is not in the image).
_LEARNING_PINS = Path(".aios") / "state" / "LEARNING_PUBLIC_KEYS.json"


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


def _keystore() -> Any:
    """The OS credential store (AGENTS.md §VII.4, amended 2026-10-11), or None
    where there is none -- CI, Linux -- and keys can only be volatile env."""
    from aios.operations.keystore import KeystoreUnavailable, default_keystore

    try:
        return default_keystore()
    except KeystoreUnavailable:
        return None


def _secret_value(config: LauncherConfig, name: str) -> str:
    """A volatile env var wins; otherwise the OS credential store. Never
    ``.env``: §VII.4 keeps keys off disk, and the store is the one exception."""
    value = os.getenv(name, "")
    if value:
        return value
    store = _keystore()
    return (store.get(name) or "") if store is not None else ""


def _learning_key_pinned(config: LauncherConfig) -> bool:
    """Is the stored learning key's public half pinned? Unpinned, the
    production verifier refuses every row it signs."""
    from aios.operations.keystore import learning_public_key

    seed = _secret_value(config, "AIOS_LEARNING_KEY_LIVE")
    pins = config.repo_root / _LEARNING_PINS
    if not seed or not pins.is_file():
        return False
    try:
        pinned = json.loads(pins.read_text(encoding="utf-8"))["keys"]["live"]
        return learning_public_key(seed) in pinned
    except (ValueError, KeyError, TypeError):
        return False


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
    from aios.operations.keystore import REQUIRED

    missing = [
        name for name in REQUIRED if _is_placeholder(_secret_value(config, name))
    ]
    if missing:
        raise LauncherError(
            "production start refused: configure non-default "
            + ", ".join(missing)
            + " (`gagos keys generate --missing` stores them in the OS credential store)"
        )
    if not _learning_key_pinned(config):
        raise LauncherError(
            "production start refused: the learning key's public half is not pinned "
            f"in {_LEARNING_PINS} (`gagos keys pin`); unpinned, everything production "
            "learns is refused at recall"
        )


def _child_environment(config: LauncherConfig) -> dict[str, str]:
    env = os.environ.copy()
    if config.profile == "production":
        # The stored keys, handed to Compose in memory only; Compose passes
        # each to the container that names it. A volatile env var wins.
        store = _keystore()
        if store is not None:
            from aios.operations.keystore import production_environment

            for name, value in production_environment(store).items():
                env.setdefault(name, value)
    env["AIOS_PROFILE"] = config.profile
    # Compose mounts the launcher's data directory, wherever AIOS_DATA_DIR put it.
    env["AIOS_HOST_DATA_DIR"] = str(config.data_dir)
    if config.profile == "production":
        # Compose refuses to start the executor without a host job workspace
        # (`:?` in docker-compose.yml). Default it beside the data, absolute.
        jobs = config.data_dir / "executor-jobs"
        env.setdefault("AIOS_EXECUTOR_HOST_WORKSPACE_ROOT", str(jobs))
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


def organ_check(config: LauncherConfig, *, strict: bool, as_json: bool) -> int:
    from aios.application.governance.organ_ledger import evaluate_organs

    report = evaluate_organs(config.repo_root)
    if as_json:
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    else:
        print(
            f"GAGOS organ ledger: {report.green_count}/{report.total_organs} green"
            f" ({'CONFORMANT' if report.conformant else 'NON-CONFORMANT'})"
        )
        if report.violations:
            print("  violations:")
            for violation in report.violations:
                print(f"    - {violation}")
        else:
            print("  no ledger violations")
    if report.violations:
        return 1
    return 0 if report.all_green or not strict else 1


def provenance_clerk_job(config: LauncherConfig, *, job_id: str, as_json: bool) -> int:
    from aios import config as aios_config
    from aios.application.local_workforce import get_clerk_job_provenance
    from aios.infrastructure.local_workforce import LocalWorkforceProvenanceStore

    store = LocalWorkforceProvenanceStore(
        aios_config.DATA_DIR / "local_workforce_provenance.db"
    )
    trace = get_clerk_job_provenance(store, job_id)
    if as_json:
        payload = {
            "job_id": trace.job_id,
            "status": trace.status,
            "request": trace.request.model_dump(mode="json") if trace.request else None,
            "model_calls": [call.model_dump(mode="json") for call in trace.model_calls],
            "result": trace.result.model_dump(mode="json") if trace.result else None,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(trace.render())
    return 0 if trace.request is not None else 1


def keys_command(config: LauncherConfig, args: argparse.Namespace) -> int:
    """``gagos keys``: the production keys in the OS credential store. No
    subcommand prints a value; storing one is the operator's act."""
    from aios.operations import keystore as ks

    store = _keystore()
    if store is None:
        raise LauncherError(
            "there is no OS credential store here; production keys can only be "
            "volatile env vars"
        )
    try:
        if args.keys_command == "status":
            report = ks.presence(store)
            for name in ks.NAMES:
                kind = "required" if name in ks.REQUIRED else "optional"
                state = "stored " if report[name] else "MISSING"
                print(f"  {state}  {name} ({kind})")
            pinned = _learning_key_pinned(config)
            print(f"  learning key pinned: {'yes' if pinned else 'NO'}")
            return 0 if pinned and all(report[n] for n in ks.REQUIRED) else 1
        if args.keys_command == "generate":
            names = (
                [n for n in ks.REQUIRED if not store.get(n)]
                if args.missing
                else list(args.names)
            )
            if not names:
                print("nothing to generate")
                return 0
            for name in names:
                public = ks.generate(store, name, rotate=args.rotate)
                print(f"  stored {name} (value not shown)")
                if public:
                    print(
                        f"  learning public key {public}: pin it with `gagos keys pin`"
                    )
            return 0
        if args.keys_command == "pin":
            seed = store.get("AIOS_LEARNING_KEY_LIVE")
            if not seed:
                raise LauncherError(
                    "no learning key is stored: `gagos keys generate AIOS_LEARNING_KEY_LIVE`"
                )
            public = ks.learning_public_key(seed)
            path = config.repo_root / _LEARNING_PINS
            data = (
                json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
            )
            live = data.setdefault("keys", {}).setdefault("live", [])
            if public not in live:
                live.append(public)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((json.dumps(data, indent=2) + "\n").encode("utf-8"))
            print(
                f"pinned {public} in {path}: commit it, it is what the verifier trusts"
            )
            return 0
        if args.keys_command == "set":
            if not sys.stdin.isatty():
                raise LauncherError(
                    "`gagos keys set` reads a hidden prompt: run it in your own terminal"
                )
            import getpass

            value = getpass.getpass(f"{args.name} (hidden): ").strip()
            if not value:
                raise LauncherError("empty value: nothing stored")
            store.set(args.name, value)
            print(f"stored {args.name} (value not shown)")
            return 0
        if args.keys_command == "delete":
            gone = store.delete(args.name)
            print(f"{'deleted' if gone else 'was not stored'}: {args.name}")
            return 0
    except ValueError as exc:
        raise LauncherError(str(exc)) from exc
    return 2


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
    organ_parser = subparsers.add_parser(
        "organ-check", help="Report the 55-organ truth ledger conformance."
    )
    organ_parser.add_argument("--strict", action="store_true")
    organ_parser.add_argument("--json", action="store_true")
    provenance_parser = subparsers.add_parser(
        "provenance", help="Inspect durable provenance records."
    )
    provenance_subparsers = provenance_parser.add_subparsers(
        dest="provenance_command", required=True
    )
    clerk_job_parser = provenance_subparsers.add_parser(
        "clerk-job", help="Reconstruct one local-clerk job's provenance trace."
    )
    clerk_job_parser.add_argument("job_id")
    clerk_job_parser.add_argument("--json", action="store_true")
    keys_parser = subparsers.add_parser(
        "keys", help="Production keys in the OS credential store (never shown)."
    )
    keys_subparsers = keys_parser.add_subparsers(dest="keys_command", required=True)
    keys_subparsers.add_parser("status", help="Which keys are stored, never values.")
    generate_parser = keys_subparsers.add_parser(
        "generate", help="Make keys straight into the store."
    )
    generate_parser.add_argument("names", nargs="*")
    generate_parser.add_argument(
        "--missing", action="store_true", help="every required key not yet stored"
    )
    generate_parser.add_argument("--rotate", action="store_true")
    keys_subparsers.add_parser("pin", help="Pin the stored learning key's public half.")
    set_parser = keys_subparsers.add_parser(
        "set", help="Store a key you hold (a cloud key) from a hidden prompt."
    )
    set_parser.add_argument("name")
    delete_parser = keys_subparsers.add_parser("delete", help="Remove a stored key.")
    delete_parser.add_argument("name")
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
        if args.command == "organ-check":
            return organ_check(config, strict=args.strict, as_json=args.json)
        if args.command == "provenance" and args.provenance_command == "clerk-job":
            return provenance_clerk_job(config, job_id=args.job_id, as_json=args.json)
        if args.command == "keys":
            return keys_command(config, args)
        if args.command in {"backup", "audit", "cortex", "memory", "executor"}:
            return _delegate_maintenance(args.command, args.arguments)
    except LauncherError as exc:
        print(f"gagos: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
