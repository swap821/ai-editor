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
#: Methods the Invariant I bond gate applies to. Reads are the whole hole:
#: mutations were already covered by the mutation guard and action_guard.
_READ_METHODS = frozenset({"GET", "HEAD"})
_SESSION_CREATE_PATH = "/api/v1/auth/session"
_BOOTSTRAP_AUTH_PATHS = frozenset(
    {_SESSION_CREATE_PATH, "/api/v1/auth/enroll", "/api/v1/auth/login"}
)

#: Routes readable WITHOUT a bonded operator session (Invariant I).
#:
#: Deliberately tiny, and derived rather than guessed: the bond ceremony has to
#: be reachable before anyone can bond, or the system is a locked door with the
#: key inside. These are exactly what `SovereigntyPanel` and the shell touch on
#: first paint --
#:
#:   /api/v1/auth/session   GET reports whether an operator is bonded; POST
#:                          mints the pre-bond conversation session
#:   .../enroll|login|reauth  the ceremony itself
#:   /api/v1/models/*       the model picker, so an unbonded shell still renders
#:
#: Everything else under /api/ needs the bond. Adding to this set widens the
#: unauthenticated read surface, so it is the one place to look when M6 regresses.
_PUBLIC_API_PATHS = frozenset(
    {
        _SESSION_CREATE_PATH,
        "/api/v1/auth/enroll",
        "/api/v1/auth/login",
        "/api/v1/auth/reauth",
        # `/mirror/governance` and NOT the rest of `/mirror/*`. This one route
        # already resolves the principal itself (`routes/mirror.py`) and
        # includes constitution data only for an OPERATOR, degrading to
        # `status: "unavailable"` otherwise -- a per-field authorization that is
        # strictly better than a blanket refusal, and one the project tests on
        # purpose. It does disclose one thing to an unbonded caller: whether the
        # emergency stop is engaged, which its own docstring calls
        # always-renderable by design.
        #
        # Its siblings are deliberately NOT exempt: /snapshot, /executor and
        # /stream take no identity at all, so they would hand the bus journal,
        # skills and executor state to any local process. A prefix exemption
        # here would have reopened the hole this gate exists to close.
        "/api/v1/mirror/governance",
    }
)

#: Prefixes treated as public. Kept separate from the exact-match set so a new
#: `/api/v1/models/<provider>` route does not silently need an allowlist edit.
_PUBLIC_API_PREFIXES: tuple[str, ...] = ("/api/v1/models/",)


def _is_public_path(path: str) -> bool:
    """True when *path* may be read without a bonded operator session."""
    return path in _PUBLIC_API_PATHS or path.startswith(_PUBLIC_API_PREFIXES)


_LOGGER = logging.getLogger(__name__)

_API_TOKEN_AUTHORITY: "ApiTokenAuthority | None" = None


def get_api_token_authority() -> "ApiTokenAuthority":
    """Lazily construct the process-wide API bearer-token rotation authority.

    Organ 53: the authority only wraps the durable rotation-state db path
    (genuinely process-lifetime-stable, safe to cache) -- it never caches
    ``config.API_TOKEN``'s value itself. Callers pass that in fresh at each
    call, so a later reassignment (production restart, or a test
    monkeypatch) is always respected.
    """
    global _API_TOKEN_AUTHORITY
    if _API_TOKEN_AUTHORITY is None:
        from aios import config as _real_config
        from aios.application.security.api_token_authority import InstallationConfigurationAuthority

        # Read the db path from the REAL config module rather than this
        # module's `config` name. The path is process-lifetime-stable (see
        # above), while `config.API_TOKEN`'s VALUE must stay swappable -- and
        # tests legitimately swap `edge_security.config` wholesale to control
        # that value. Resolving the path through the swapped name made those
        # tests fail with AttributeError on a fake that only models API_TOKEN.
        _API_TOKEN_AUTHORITY = InstallationConfigurationAuthority(
            db_path=_real_config.API_TOKEN_ROTATION_DB_PATH,
        )
    return _API_TOKEN_AUTHORITY


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
    """Return True if the Authorization header bears a currently-valid API token.

    Organ 53: the env token is RETIRABLE, not permanent.

    This previously accepted ``config.API_TOKEN`` unconditionally, BEFORE the
    rotation authority was consulted at all -- so the env value was a bearer
    credential that could never be revoked without restarting the process. The
    operator's plan forbids exactly that ("no permanent unrevocable bearer
    credential"), and it made rotation actively misleading: an operator who
    rotated reasonably believed the old credential was gone.

    The mechanism to retire it already existed and was simply bypassed.
    ``ApiTokenAuthority.rotate()`` records the live env token as
    ``previous_token_digest`` with a grace-period expiry on the first
    rotation; the short-circuit meant that recorded expiry never applied to it.

    So:

    * before any rotation has ever happened, the env token is the ONLY
      credential and is accepted directly (unchanged -- a fresh install must
      never be locked out);
    * once a rotation exists, the authority is the single source of truth,
      including for the env token, which it holds as the superseded value.
      After the grace period elapses the env token stops working, with no
      restart required.
    """
    auth = request.headers.get("authorization", "")
    parts = auth.split()
    if len(parts) != 2:
        return False
    if parts[0].lower() != "bearer":
        return False
    candidate = parts[1]
    authority = get_api_token_authority()
    env_token = getattr(config, "API_TOKEN", "") or ""
    if env_token and secrets.compare_digest(candidate, env_token):
        # The env value still authenticates UNLESS this exact token is one the
        # authority has retired (superseded by a rotation, past its grace
        # window). Retiring the specific token rather than the mechanism means
        # an operator who rotates and then sets a genuinely NEW env token is
        # not locked out -- only the value they replaced stops working.
        return not authority.is_retired(candidate)
    return authority.is_valid(candidate)


_BODY_SESSION_ALLOWED_PATHS = frozenset(
    {
        "/api/generate",
        "/api/v1/chat",
    }
)


def is_body_session_allowed(path: str) -> bool:
    """Return True if the route may read session_id from the request body."""
    return path in _BODY_SESSION_ALLOWED_PATHS


class EdgeTrustAuthority:
    """Own the API edge's request-level trust decisions.

    Parsing helpers stay module-level because they are pure reusable
    primitives. This authority owns the live ordering of host, token, origin,
    session, and CSRF checks that the FastAPI middleware invokes.
    """

    def validate_cors_origins(self, origins: tuple[str, ...]) -> list[str]:
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

    def real_client_ip(self, request: Request) -> str:
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

    async def extract_session_id(
        self,
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

    def check_api_token_or_loopback(self, request: Request) -> Optional[JSONResponse]:
        """Enforce API token for /api/* and docs paths; allow loopback when no token."""
        path = request.url.path
        docs_paths = {"/docs", "/redoc", "/openapi.json"}
        host_error = _check_host_header(request)
        if host_error is not None:
            return host_error
        if path in docs_paths and not config.ENABLE_DOCS:
            if request.method != "OPTIONS":
                client_ip = self.real_client_ip(request)
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
        if get_api_token_authority().is_configured(current_env_token=config.API_TOKEN):
            return JSONResponse(
                status_code=401, content={"detail": "invalid or missing API token"}
            )
        client_ip = self.real_client_ip(request)
        if config.TRUST_PROXY_HEADERS or client_ip not in LOOPBACK_HOSTS:
            return JSONResponse(
                status_code=403,
                content={"detail": "unauthenticated API access is loopback-only"},
            )
        return self._require_bond_for_privileged_read(request, path)

    def _require_bond_for_privileged_read(
        self, request: Request, path: str
    ) -> Optional[JSONResponse]:
        """INVARIANT I: being on the machine is not being the operator.

        Everything above this point has established only that the caller reached
        us over loopback and that no API token is configured. That was, until
        2026-09-06, the whole check -- so on a default install any local process
        was the operator. Measured that day: **39 of 68 privileged GET routes
        answered 200** to a caller holding no token, no cookie and no Origin,
        `/api/v1/security/audit` among them. A package postinstall script, or
        anything the operator ran once, could read the governance record.

        Loopback is a network path, not an identity. The only honest fix is to
        ask for a credential, so this requires the same bonded operator
        principal that `action_guard` already demands of `server-session`
        routes. The Sovereign Bond ceremony (`SovereigntyPanel`) is how a human
        obtains one.

        Scope note: YELLOW actions were never in this hole --
        `action_guard` requires `authentication_level == "privileged"`, and a
        self-bootstrapped session carries no `operator_id`. Reads were the hole,
        and reads are what this closes.
        """
        # READS ONLY, and that is a deliberate boundary rather than timidity.
        #
        # Mutations already have two guards this does not duplicate:
        # `check_mutation_origin_or_token` demands a session and CSRF proof, and
        # `action_guard` demands `authentication_level == "privileged"` for
        # anything YELLOW. Reads had neither -- that asymmetry WAS the hole.
        #
        # Extending this to mutations would also break a contract the system
        # states on purpose: `action_guard` keeps chat and the other GREEN
        # session routes usable with the legacy conversation cookie. Measured --
        # applying it to every method broke six throttle tests whose subject is
        # rate limiting, not identity.
        if request.method not in _READ_METHODS or _is_public_path(path):
            return None
        raw_cookie = request.cookies.get("session_id")
        if raw_cookie:
            try:
                from aios.api.deps import get_identity_service

                # Resolve through `dependency_overrides` exactly as the routes
                # do. Middleware does not participate in FastAPI's DI graph, so
                # calling the provider directly would read a DIFFERENT identity
                # service than the route it is guarding -- a test that injects a
                # real operator would be refused at the edge while the route
                # behind it considered that same operator authenticated. The
                # override map is empty in production, so this is a test seam,
                # not a bypass.
                provider = request.app.dependency_overrides.get(
                    get_identity_service, get_identity_service
                )
                if provider().get_authenticated_principal(raw_cookie):
                    return None
            except Exception:  # noqa: BLE001 - degraded identity is not trust
                # ORGAN 24: a store-level failure is not "no session". It means
                # identity resolution itself is degraded, and saying 401 would
                # tell the operator their bond is bad when in truth we cannot
                # read it. Both answers refuse -- only one is honest, and this
                # matches the EmergencyStopError precedent the app already sets.
                _LOGGER.warning(
                    "identity_resolution_degraded_refusing_request",
                    extra={"path": path},
                )
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": (
                            "identity resolution is degraded; refusing to "
                            "authorize anything new"
                        )
                    },
                )
        # FAIL CLOSED. An identity layer that did not answer "the operator" has
        # not answered at all, and the pre-2026-09-06 behaviour of falling back
        # to loopback trust is exactly the bug being fixed.
        return JSONResponse(
            status_code=401,
            content={
                "detail": (
                    "this route requires a bonded operator session; loopback "
                    "alone is a network path, not an identity"
                )
            },
        )

    def check_mutation_origin_or_token(
        self,
        request: Request,
    ) -> Optional[JSONResponse]:
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


_EDGE_TRUST_AUTHORITY = EdgeTrustAuthority()


def get_edge_trust_authority() -> EdgeTrustAuthority:
    """Return the one process-wide owner used by the API edge middleware."""
    return _EDGE_TRUST_AUTHORITY


def validate_cors_origins(origins: tuple[str, ...]) -> list[str]:
    return _EDGE_TRUST_AUTHORITY.validate_cors_origins(origins)


def real_client_ip(request: Request) -> str:
    return _EDGE_TRUST_AUTHORITY.real_client_ip(request)


async def extract_session_id(
    request: Request,
    *,
    allow_body_fallback: bool = False,
) -> Optional[str]:
    return await _EDGE_TRUST_AUTHORITY.extract_session_id(
        request,
        allow_body_fallback=allow_body_fallback,
    )


def check_api_token_or_loopback(request: Request) -> Optional[JSONResponse]:
    return _EDGE_TRUST_AUTHORITY.check_api_token_or_loopback(request)


def check_mutation_origin_or_token(request: Request) -> Optional[JSONResponse]:
    return _EDGE_TRUST_AUTHORITY.check_mutation_origin_or_token(request)


__all__ = [
    "EdgeTrustAuthority",
    "get_edge_trust_authority",
    "get_api_token_authority",
    "check_api_token_or_loopback",
    "check_mutation_origin_or_token",
    "extract_session_id",
    "is_allowed_origin",
    "real_client_ip",
    "validate_cors_origins",
]
