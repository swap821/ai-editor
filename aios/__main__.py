"""Canonical entrypoint: ``python -m aios`` serves the API.

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
"""
from __future__ import annotations

import argparse

import uvicorn

from aios import config


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m aios", description="Serve the AI-OS API.")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (development only).",
    )
    args = parser.parse_args()
    # Bind the POLICY host/port (config), never a CLI-supplied host, so the real
    # bind stays in lockstep with the lifespan token policy. The import string +
    # reload combo is required by uvicorn for the reloader to work.
    uvicorn.run(
        "aios.api.main:app",
        host=config.API_HOST,
        port=config.API_PORT,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
