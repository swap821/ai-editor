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
import sys

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

    args = parser.parse_args(argv)

    command: str | None = args.command
    if command == "bootstrap":
        return _cmd_bootstrap(args)
    # Default / no subcommand => serve the API (backwards compatible with ``python -m aios``).
    return _cmd_serve(args)


if __name__ == "__main__":
    sys.exit(main())
