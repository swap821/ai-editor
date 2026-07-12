"""HTTP edge security: CORS, origin, host, token, and session binding.

This module isolates the FastAPI edge-security policy so it can be reviewed,
tested, and hardened independently of route wiring.
"""
from __future__ import annotations

import ipaddress
import json
import secrets
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse

from aios import config
from aios.api.deps import get_session_manager

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def is_private_ip(ip: str) -> bool:
    """Return True if *ip* is loopback, link-local, RFC 1918/4193, or reserved."""
    ip = ip.strip()
    if not ip:
        return True
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_reserved
    except ValueError:
        return True


def real_client_ip(request: Request) -> str:
    """Return the best-effort real client IP for auth decisions."""
    direct = request.client.host if request.client else ""
    if not config.TRUST_PROXY_HEADERS:
        return direct
    forwarded = request.headers.get("x-forwarded-for", "")
    if not forwarded:
        return direct
    chain = [h.strip() for h in forwarded.split(",") if h.strip()]
    if config.TRUSTED_PROXIES:
        for ip in reversed(chain):
            if ip not in config.TRUSTED_PROXIES:
                return ip
        return direct
    for ip in reversed(chain):
        if not is_private_ip(ip):
            return ip
    return direct


def validate_cors_origins(origins: tuple[str, ...]) -> list[str]:
    """Reject wildcard/host-less origins so credentialed CORS can't widen silently."""
    from urllib.parse import urlparse

    validated: list[str] = []
    for origin in origins:
        if "\r" in origin or "\n" in origin:
            raise RuntimeError(
                f"AIOS_CORS_ORIGINS entry contains newline characters: {origin!r}"
            )
        if origin == "*":
            raise RuntimeError(
                "AIOS_CORS_ORIGINS may not contain '*' while credentials are allowed. "
                "List explicit scheme://host[:port] origins."
            )
        parsed = urlparse(origin)
        if not parsed.scheme or not parsed.netloc:
            raise RuntimeError(
                f"AIOS_CORS_ORIGINS entry {origin!r} is not a valid origin "
                "(expected scheme://host[:port])."
            )
        validated.append(origin)
    return validated


def is_allowed_origin(origin: str, allowed_origins: Optional[list[str]] = None) -> bool:
    """Check whether *origin* is allowed (configured list or loopback)."""
    if not origin:
        return False
    allowed = allowed_origins or validate_cors_origins(config.API_CORS_ORIGINS)
    if origin in allowed:
        return True
    from urllib.parse import urlparse

    parsed = urlparse(origin)
    if parsed.hostname:
        try:
            ipaddress.ip_address(parsed.hostname)
        except ValueError:
            return False
        if is_private_ip(parsed.hostname):
            return True
    return False


def _check_host_header(request: Request) -> Optional[JSONResponse]:
    """Reject malformed or injected host headers."""
    host = request.headers.get("host", "")
    if not host:
        return None
    if host.startswith(("http://", "https://")):
        return JSONResponse(
            status_code=400,
            content={"detail": "Malformed Host header"},
        )
    cr = chr(13)
    lf = chr(10)
    if cr in host or lf in host or "," in host:
        return JSONResponse(
            status_code=400,
            content={"detail": "Malformed Host header"},
        )
    return None


def check_bearer_token(request: Request) -> bool:
    """Return True if the Authorization header bears the configured API token."""
    if not config.API_TOKEN:
        return False
    auth = request.headers.get("authorization", "")
    parts = auth.split()
    if len(parts) != 2:
        return False
    if parts[0].lower() != "bearer":
        return False
    return secrets.compare_digest(parts[1], config.API_TOKEN)


def check_api_token_or_loopback(request: Request) -> Optional[JSONResponse]:
    """Enforce API token for /api/* and docs paths; allow loopback when no token."""
    path = request.url.path
    docs_paths = {"/docs", "/redoc", "/openapi.json"}
    host_error = _check_host_header(request)
    if host_error is not None:
        return host_error
    if path in docs_paths and not config.ENABLE_DOCS:
        if request.method != "OPTIONS":
            client_ip = real_client_ip(request)
            if config.TRUST_PROXY_HEADERS or client_ip not in LOOPBACK_HOSTS:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "unauthenticated API access is loopback-only"},
                )
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    protected = path.startswith("/api/") or path in docs_paths
    if not protected or request.method == "OPTIONS":
        return None
    if check_bearer_token(request):
        return None
    if config.API_TOKEN:
        return JSONResponse(status_code=401, content={"detail": "invalid or missing API token"})
    client_ip = real_client_ip(request)
    if config.TRUST_PROXY_HEADERS or client_ip not in LOOPBACK_HOSTS:
        return JSONResponse(
            status_code=403,
            content={"detail": "unauthenticated API access is loopback-only"},
        )
    return None


def check_mutation_origin_or_token(request: Request) -> Optional[JSONResponse]:
    """CSRF/mutation protection: state-changing requests need token or browser proof."""
    if request.method not in ("POST", "PUT", "DELETE", "PATCH"):
        return None
    if check_bearer_token(request):
        return None
    sec_site = request.headers.get("sec-fetch-site")
    if sec_site in ("same-origin", "same-site"):
        return None
    origin = request.headers.get("origin")
    if origin and is_allowed_origin(origin):
        return None
    return JSONResponse(
        status_code=403,
        content={"detail": "Mutation requires valid browser Origin/Sec-Fetch-Site or API token"}
    )


_BODY_SESSION_ALLOWED_PATHS = frozenset({
    "/api/generate",
    "/api/v1/chat",
})


def is_body_session_allowed(path: str) -> bool:
    """Return True if the route may read session_id from the request body."""
    return path in _BODY_SESSION_ALLOWED_PATHS


async def extract_session_id(
    request: Request,
    *,
    allow_body_fallback: bool = False,
) -> Optional[str]:
    """Prefer validated httpOnly cookie; optionally fall back to body session id."""
    cookie_hash = request.cookies.get("session_id")
    if cookie_hash:
        session = get_session_manager().validate_session(cookie_hash)
        if session is not None:
            return session.session_hash
    if not allow_body_fallback or request.method not in ("POST", "PUT", "PATCH"):
        return None
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        return None
    try:
        body = await request.body()
        payload = json.loads(body.decode("utf-8")) if body else None
    except Exception:
        payload = None
    if isinstance(payload, dict):
        body_sid = payload.get("sessionId") or payload.get("session_id")
        if body_sid:
            return str(body_sid)
    return None
