"""Canonical entrypoint for GAGOS.

``python -m aios`` serves the API; ``python -m aios bootstrap`` runs environment
health checks before first use.

P0-6 fix. ``AIOS_API_HOST`` / ``AIOS_API_PORT`` are read by the startup policy and
CORS, but nothing bound them — there was no ``uvicorn.run`` / ``__main__`` anywhere,
so the documented launch was a hand-typed ``python -m uvicorn ... --host``. That
decouples the REAL bind from the policy the lifespan validates: a public
``--host 0.0.0.0`` while ``AIOS_API_HOST`` stays ``127.0.0.1`` yields a public
bind with the loopback token-exemption still active (no token enforced).

This entrypoint binds EXACTLY ``config.API_HOST`` / ``config.API_PORT`` — the same
host the lifespan policy checks (``main.py``: a non-loopback host requires a
>=32-char ``AIOS_API_TOKEN``) — so the bind and the policy can never disagree.
Launch with ``python -m aios`` (optionally ``--reload`` for dev via the flag below).

P0-4 addition: ``--proxy-headers`` tells uvicorn to trust ``X-Forwarded-For`` /
``X-Forwarded-Proto`` from a reverse proxy, and disables the unauthenticated
loopback exemption because the direct peer is now a proxy. Use only when a
trusted proxy sits in front of GAGOS and always pair it with ``AIOS_API_TOKEN``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import uvicorn

from aios import config
from aios.bootstrap import run_bootstrap, write_env_template


def _cmd_serve(args: argparse.Namespace) -> int:
    # The trust flag may come from the env var (AIOS_TRUST_PROXY_HEADERS) or the
    # CLI flag. Both the GAGOS policy (lifespan/middleware) and uvicorn must see
    # the SAME value, otherwise we could enforce proxy semantics while uvicorn
    # still reports the direct peer, or vice versa.
    trust_proxy_headers = bool(args.proxy_headers or config.TRUST_PROXY_HEADERS)
    config.TRUST_PROXY_HEADERS = trust_proxy_headers
    # Bind the POLICY host/port (config), never a CLI-supplied host, so the real
    # bind stays in lockstep with the lifespan token policy. The import string +
    # reload combo is required by uvicorn for the reloader to work.
    uvicorn.run(
        "aios.api.main:app",
        host=config.API_HOST,
        port=config.API_PORT,
        reload=args.reload,
        proxy_headers=trust_proxy_headers,
    )
    return 0


def _cmd_bootstrap(args: argparse.Namespace) -> int:
    if args.create_env:
        env_path = config.PROJECT_ROOT / ".env"
        created = write_env_template(env_path)
        if created:
            print(f"Created template {env_path}")
        else:
            print(f"{env_path} already exists; skipped")
    result = run_bootstrap(project_root=config.PROJECT_ROOT, data_dir=config.DATA_DIR)
    if args.json:
        payload = {
            "ok": result.ok,
            "summary": result.summary,
            "checks": [
                {"name": c.name, "passed": c.passed, "required": c.required, "message": c.message}
                for c in result.checks
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(result.summary)
        for check in result.checks:
            status = "OK" if check.passed else "FAIL"
            req = "required" if check.required else "advisory"
            print(f"  [{status}] {check.name} ({req}): {check.message}")
    return 0 if result.ok else 1


def _print_payload(payload: object, *, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, default=str))
    elif isinstance(payload, dict):
        for key, value in payload.items():
            print(f"{key}: {value}")
    else:
        print(payload)


def _cmd_doctor(args: argparse.Namespace) -> int:
    from aios.operations.doctor import doctor_report

    report = doctor_report()
    if args.json:
        _print_payload(report.as_dict(), as_json=True)
    else:
        print(f"GAGOS doctor: {'OK' if report.ok else 'FAILED'} ({report.profile})")
        for check in report.checks:
            print(f"  [{check.status.upper()}] {check.name}: {check.message}")
        if report.disabled_capabilities:
            print(f"  disabled: {', '.join(report.disabled_capabilities)}")
    return 0 if report.ok else 1


def _cmd_backup(args: argparse.Namespace) -> int:
    from aios.operations.recovery import create_backup, restore_backup, verify_backup

    if args.backup_command == "create":
        destination = Path(args.output) if args.output else config.DATA_DIR / "backups" / (
            f"gagos-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.tar.gz"
        )
        manifest = create_backup(destination=destination)
        payload = {"output": str(destination.resolve()), "manifest": manifest.as_dict()}
        _print_payload(payload, as_json=args.json)
        return 0
    if args.backup_command == "verify":
        manifest = verify_backup(Path(args.input))
        _print_payload({"valid": True, "manifest": manifest.as_dict()}, as_json=args.json)
        return 0
    if args.backup_command == "restore":
        bundle = Path(args.input)
        safety = Path(args.safety_backup) if args.safety_backup else config.DATA_DIR / "backups" / (
            f"pre-restore-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.tar.gz"
        )
        old_dir = restore_backup(bundle=bundle, safety_backup=safety)
        _print_payload({"restored": True, "safety_backup": str(safety.resolve()), "old_data": str(old_dir) if old_dir else None}, as_json=args.json)
        return 0
    raise ValueError(f"unknown backup command: {args.backup_command}")


def _cmd_audit(args: argparse.Namespace) -> int:
    from aios.operations.recovery import verify_audit

    result = verify_audit()
    _print_payload(result, as_json=args.json)
    return 0 if result["valid"] else 1


def _cmd_cortex(args: argparse.Namespace) -> int:
    from aios.operations.recovery import rebuild_projections

    processed = rebuild_projections()
    _print_payload({"replayed_events": processed, "status": "ok"}, as_json=args.json)
    return 0


def _cmd_memory(args: argparse.Namespace) -> int:
    from aios.api.deps import get_memory_authority

    get_memory_authority().rebuild_derived_indexes()
    _print_payload({"status": "ok", "operation": "memory_index_rebuild"}, as_json=args.json)
    return 0


def _cmd_executor(args: argparse.Namespace) -> int:
    profile = os.environ.get("AIOS_PROFILE", "development").strip().lower()
    if profile in {"production", "demo"}:
        from aios.application.executor.service import StructuredExecutorClient

        client = StructuredExecutorClient(
            base_url=config.EXECUTOR_URL,
            token=config.EXECUTOR_TOKEN,
            timeout_s=config.EXECUTOR_HTTP_TIMEOUT_S,
        )
        try:
            client.health()
        except Exception as exc:  # noqa: BLE001 - CLI reports a truthful refusal
            payload = {
                "available": False,
                "backend": "private_service",
                "reason": str(exc),
            }
            _print_payload(payload, as_json=args.json)
            return 1
        _print_payload({"available": True, "backend": "private_service"}, as_json=args.json)
        return 0

    from aios.core.executor import DockerRunner

    if config.APPROVED_EXECUTION_BACKEND != "container":
        payload = {"available": False, "backend": config.APPROVED_EXECUTION_BACKEND, "reason": "container backend is required"}
        _print_payload(payload, as_json=args.json)
        return 1
    try:
        DockerRunner().ensure_available()
    except Exception as exc:  # noqa: BLE001 - CLI reports probe failures
        payload = {"available": False, "backend": "container", "reason": str(exc)}
        _print_payload(payload, as_json=args.json)
        return 1
    _print_payload({"available": True, "backend": "container"}, as_json=args.json)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m aios", description="GAGOS CLI.")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (development only).",
    )
    parser.add_argument(
        "--proxy-headers",
        action="store_true",
        dest="proxy_headers",
        help=(
            "Trust X-Forwarded-For / X-Forwarded-Proto headers from a reverse proxy. "
            "This disables the unauthenticated loopback exemption; AIOS_API_TOKEN is required."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    bootstrap_parser = subparsers.add_parser("bootstrap", help="Run environment health checks.")
    bootstrap_parser.add_argument(
        "--create-env",
        action="store_true",
        dest="create_env",
        help="Write a commented .env template if one does not already exist.",
    )
    bootstrap_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of plain text.",
    )

    doctor_parser = subparsers.add_parser("doctor", help="Report measured runtime posture.")
    doctor_parser.add_argument("--json", action="store_true", help="Emit JSON.")

    backup_parser = subparsers.add_parser("backup", help="Create, verify or restore state backups.")
    backup_subparsers = backup_parser.add_subparsers(dest="backup_command", required=True)
    backup_create = backup_subparsers.add_parser("create", help="Create a verified state archive.")
    backup_create.add_argument("--output", help="Archive path; defaults to data/backups.")
    backup_create.add_argument("--json", action="store_true", help="Emit JSON.")
    backup_verify = backup_subparsers.add_parser("verify", help="Verify an archive manifest and hashes.")
    backup_verify.add_argument("--input", required=True, help="Archive path.")
    backup_verify.add_argument("--json", action="store_true", help="Emit JSON.")
    backup_restore = backup_subparsers.add_parser("restore", help="Restore an archive after verification.")
    backup_restore.add_argument("--input", required=True, help="Archive path.")
    backup_restore.add_argument("--safety-backup", help="Pre-restore archive path.")
    backup_restore.add_argument("--json", action="store_true", help="Emit JSON.")

    audit_parser = subparsers.add_parser("audit", help="Audit-chain operations.")
    audit_subparsers = audit_parser.add_subparsers(dest="audit_command", required=True)
    audit_verify = audit_subparsers.add_parser("verify", help="Verify the tamper-evident audit chain.")
    audit_verify.add_argument("--json", action="store_true", help="Emit JSON.")

    cortex_parser = subparsers.add_parser("cortex", help="Cortex observation recovery operations.")
    cortex_subparsers = cortex_parser.add_subparsers(dest="cortex_command", required=True)
    cortex_rebuild = cortex_subparsers.add_parser("rebuild-projections", help="Rebuild derived read models.")
    cortex_rebuild.add_argument("--json", action="store_true", help="Emit JSON.")

    memory_parser = subparsers.add_parser("memory", help="Memory maintenance operations.")
    memory_subparsers = memory_parser.add_subparsers(dest="memory_command", required=True)
    memory_rebuild = memory_subparsers.add_parser("rebuild-index", help="Rebuild derived memory indexes.")
    memory_rebuild.add_argument("--json", action="store_true", help="Emit JSON.")

    executor_parser = subparsers.add_parser("executor", help="Executor isolation operations.")
    executor_subparsers = executor_parser.add_subparsers(dest="executor_command", required=True)
    executor_probe = executor_subparsers.add_parser("probe", help="Probe the configured isolated executor.")
    executor_probe.add_argument("--json", action="store_true", help="Emit JSON.")

    args = parser.parse_args(argv)

    command: str | None = args.command
    if command == "bootstrap":
        return _cmd_bootstrap(args)
    if command == "doctor":
        return _cmd_doctor(args)
    if command == "backup":
        return _cmd_backup(args)
    if command == "audit" and args.audit_command == "verify":
        return _cmd_audit(args)
    if command == "cortex" and args.cortex_command == "rebuild-projections":
        return _cmd_cortex(args)
    if command == "memory" and args.memory_command == "rebuild-index":
        return _cmd_memory(args)
    if command == "executor" and args.executor_command == "probe":
        return _cmd_executor(args)
    # Default / no subcommand => serve the API (backwards compatible with ``python -m aios``).
    return _cmd_serve(args)


if __name__ == "__main__":
    sys.exit(main())
