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

P0-4 addition: ``--proxy-headers`` tells uvicorn to trust ``X-Forwarded-For`` /
``X-Forwarded-Proto`` from a reverse proxy, and disables the unauthenticated
loopback exemption because the direct peer is now a proxy. Use only when a
trusted proxy sits in front of AI-OS and always pair it with ``AIOS_API_TOKEN``.
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
    parser.add_argument(
        "--proxy-headers",
        action="store_true",
        dest="proxy_headers",
        help=(
            "Trust X-Forwarded-For / X-Forwarded-Proto headers from a reverse proxy. "
            "This disables the unauthenticated loopback exemption; AIOS_API_TOKEN is required."
        ),
    )
    args = parser.parse_args()
    # The trust flag may come from the env var (AIOS_TRUST_PROXY_HEADERS) or the
    # CLI flag. Both the AI-OS policy (lifespan/middleware) and uvicorn must see
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


if __name__ == "__main__":
    main()
