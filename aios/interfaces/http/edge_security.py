"""HTTP edge security: CORS, origin, host, token, and session binding.

This module isolates the FastAPI edge-security policy so it can be reviewed,
tested, and hardened independently of route wiring.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import re
import secrets
from typing import Optional
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse

from aios import config
from aios.api.deps import get_session_manager

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_MUTATION_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})
_SESSION_CREATE_PATH = "/api/v1/auth/session"
_BOOTSTRAP_AUTH_PATHS = frozenset(
    {_SESSION_CREATE_PATH, "/api/v1/auth/enroll", "/api/v1/auth/login"}
)
_LOGGER = logging.getLogger(__name__)


def _parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Parse a syntactically valid IP, returning ``None`` for unknown input."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def _configured_proxy_ips() -> frozenset[str]:
    return frozenset(
        str(parsed)
        for raw in config.TRUSTED_PROXIES
        if (parsed := _parse_ip(raw)) is not None
    )


def is_private_ip(ip: str) -> bool:
    """Return whether a valid IP is private; malformed input is never trusted."""
    addr = _parse_ip(ip)
    if addr is None:
        return False
    return addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_reserved


def real_client_ip(request: Request) -> str:
    """Return the direct peer unless a configured proxy may vouch for XFF."""
    direct = request.client.host if request.client else ""
    if not config.TRUST_PROXY_HEADERS:
        return direct
    trusted_proxies = _configured_proxy_ips()
    direct_ip = _parse_ip(direct)
    if direct_ip is None or str(direct_ip) not in trusted_proxies:
        return direct
    forwarded = request.headers.get("x-forwarded-for", "")
    if not forwarded:
        return direct
    chain = [str(parsed) for raw in forwarded.split(",") if (parsed := _parse_ip(raw))]
    for ip in reversed(chain):
        if ip not in trusted_proxies:
            return ip
    return direct


def _normalize_origin(origin: str) -> str | None:
    """Normalize an HTTP Origin without accepting user-info or path tricks."""
    if not isinstance(origin, str) or not origin or origin != origin.strip():
        return None
    try:
        parsed = urlsplit(origin)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"} or not parsed.netloc:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        if parsed.path or parsed.query or parsed.fragment:
            return None
        hostname = parsed.hostname
        if not hostname or hostname.endswith("."):
            return None
        hostname = hostname.lower()
        try:
            port = parsed.port
        except ValueError:
            return None
        if port is None:
            port = 443 if scheme == "https" else 80
        if not 1 <= port <= 65535:
            return None
        host = f"[{hostname}]" if ":" in hostname else hostname
        return f"{scheme}://{host}:{port}"
    except ValueError:
        return None


def validate_cors_origins(origins: tuple[str, ...]) -> list[str]:
    """Reject wildcard/host-less origins so credentialed CORS can't widen silently."""
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
        if _normalize_origin(origin) is None:
            raise RuntimeError(
                f"AIOS_CORS_ORIGINS entry {origin!r} is not a valid origin "
                "(expected scheme://host[:port])."
            )
        validated.append(origin)
    return validated


def is_allowed_origin(origin: str, allowed_origins: Optional[list[str]] = None) -> bool:
    """Check only exact normalized configured origins; private IPs get no bypass."""
    normalized = _normalize_origin(origin)
    if normalized is None:
        return False
    allowed = (
        allowed_origins
        if allowed_origins is not None
        else validate_cors_origins(config.API_CORS_ORIGINS)
    )
    return any(_normalize_origin(candidate) == normalized for candidate in allowed)


def _normalize_host_header(host: str) -> str | None:
    """Normalize a Host header to a strict host[:port] representation."""
    if not isinstance(host, str) or not host or host != host.strip():
        return None
    if any(char in host for char in "\r\n,\\/@"):
        return None
    if host.startswith("["):
        closing = host.find("]")
        if closing < 0:
            return None
        name = host[: closing + 1].lower()
        suffix = host[closing + 1 :]
        if suffix and not re.fullmatch(r":\d+", suffix):
            return None
        port = suffix[1:] if suffix else ""
    else:
        if host.count(":") > 1:
            return None
        if ":" in host:
            name, port = host.rsplit(":", 1)
            if not name or not port.isdigit():
                return None
        else:
            name, port = host, ""
        if not re.fullmatch(r"[A-Za-z0-9.-]+", name):
            return None
    if port and not 1 <= int(port) <= 65535:
        return None
    return f"{name}:{port}".lower() if port else name.lower()


def allowed_host_headers() -> frozenset[str]:
    """Return the exact host forms accepted by the API edge."""
    port = int(config.API_PORT)
    allowed = {
        f"localhost:{port}",
        f"127.0.0.1:{port}",
        f"[::1]:{port}",
    }
    gateway = _normalize_host_header(
        str(getattr(config, "PACKAGED_GATEWAY_HOST", "gateway"))
    )
    if gateway:
        allowed.add(gateway)
    api_host = _normalize_host_header(str(config.API_HOST))
    if api_host and api_host not in {"0.0.0.0", "::"}:
        allowed.add(api_host)
        if ":" not in api_host:
            allowed.add(f"{api_host}:{port}")
    return frozenset(allowed)


def _check_host_header(request: Request) -> Optional[JSONResponse]:
    """Reject malformed or unconfigured host headers."""
    host = request.headers.get("host", "")
    normalized = _normalize_host_header(host)
    if normalized is None or normalized not in allowed_host_headers():
        return JSONResponse(
            status_code=400,
            content={"detail": "Host header is not configured for this API"},
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
    """Require bearer auth or a valid session, exact Origin, and CSRF proof."""
    if request.method not in _MUTATION_METHODS:
        return None
    if check_bearer_token(request):
        return None
    origin = request.headers.get("origin")
    if request.url.path in _BOOTSTRAP_AUTH_PATHS:
        if origin and is_allowed_origin(origin):
            return None
    elif origin and is_allowed_origin(origin):
        cookie_hash = request.cookies.get("session_id")
        session = get_session_manager().validate_session(cookie_hash)
        expected = session.data.get("csrf_token") if session is not None else None
        # The readable SameSite CSRF cookie keeps existing browser clients
        # functional; a header is accepted as the stronger explicit form.
        supplied = request.headers.get("x-csrf-token") or request.cookies.get(
            "csrf_token", ""
        )
        if isinstance(expected, str) and expected and isinstance(supplied, str):
            if secrets.compare_digest(supplied, expected):
                return None
    return JSONResponse(
        status_code=403,
        content={
            "detail": (
                "Mutation requires a bearer token or a valid session, exact Origin, "
                "and session-bound CSRF proof"
            )
        },
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
    if (
        not allow_body_fallback
        or request.method not in ("POST", "PUT", "PATCH")
        or not is_body_session_allowed(request.url.path)
    ):
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
            _LOGGER.warning(
                "body_session_fallback_deprecated",
                extra={"path": request.url.path},
            )
            return str(body_sid)
    return None
