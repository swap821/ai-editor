"""The API's HTTP middleware, registered on the app by :func:`install`.

Moved out of ``aios/api/main.py`` (2026-10-12, maintainability: that module
was 1,791 lines). Behaviour is unchanged, and so is the ORDER: Starlette wraps
each added middleware around the previous ones, so the last registered runs
first. ``install`` adds them in exactly the sequence ``main`` used to:

    CORS -> metrics -> request context -> API token -> browser-or-token for
    mutations -> approval-route rate limit

Each check here delegates to its owner (``edge_security``'s edge trust
authority, the ``PolicyKernel``); this module only wires them onto the app.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from aios import config
from aios.api.deps import get_observability_authority, get_policy_kernel
from aios.core.metrics import MetricsMiddleware
from aios.interfaces.http import edge_security
from aios.logging_config import session_log_key

# CORS: credentialed requests are allowed only from explicitly configured
# origins; the dev front-end on :5173 is included by default, production builds
# must opt them in explicitly. Origins come from config (env-overridable).
#
# P0 guard: with allow_credentials=True the CORS spec forbids a wildcard origin,
# and a "*" or host-less/malformed entry in AIOS_CORS_ORIGINS would silently
# widen credentialed cross-origin access. Validate at import/startup and FAIL
# CLOSED (refuse to serve) rather than ship a dangerous config. Methods and
# headers are also narrowed from "*" to the surface the front-end actually uses.
_CORS_METHODS = ["GET", "POST", "OPTIONS", "DELETE"]
_CORS_HEADERS = [
    "Authorization",
    "Content-Type",
    "X-AIOS-Capability",
    "X-Correlation-ID",
    "X-Request-ID",
]


def _validate_cors_origins(origins: tuple[str, ...]) -> list[str]:
    """Reject wildcard/host-less origins so credentialed CORS can't widen silently."""
    return edge_security.get_edge_trust_authority().validate_cors_origins(origins)


async def bind_request_context(request: Request, call_next):
    """Stamp every request with a correlation id and bind a hashed session id.

    Organ 52: also builds and binds the shared `TraceContext` (`aios.operations
    .tracing`) for this request's duration, reusing the SAME request_id already
    computed below rather than generating a second, independently-sourced id.
    Any synchronous call within this request's task -- including ones FastAPI
    later runs via `BackgroundTasks` in the same ASGI cycle -- sees the same
    context through `get_trace_context()` with no further wiring; a genuinely
    separate process (the Docker executor container) does not and is not
    covered by this alone.
    """
    from structlog.contextvars import bind_contextvars, clear_contextvars

    # Organ 52: built and bound through the organ's named authority rather
    # than by calling the tracing module directly, so there is one owner of
    # the correlation chain instead of several equivalent call sites.
    observability = get_observability_authority()

    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    clear_contextvars()
    bind_contextvars(
        request_id=request_id, method=request.method, path=request.url.path
    )
    trace_headers = dict(request.headers)
    trace_headers["x-request-id"] = request_id
    trace_context = observability.context_from_headers(trace_headers)
    with observability.bind(trace_context):
        try:
            session_id = (
                await edge_security.get_edge_trust_authority().extract_session_id(
                    request, allow_body_fallback=True
                )
            )
            if session_id:
                bind_contextvars(session_id_hash=session_log_key(session_id))
            response = await call_next(request)
            response.headers["x-request-id"] = request_id
            return response
        finally:
            clear_contextvars()


#: Hosts that are allowed to call the API without a token. Starlette's
#: "testclient" is deliberately NOT included — it must never be a production
#: backdoor. Tests that need unauthenticated access should use an explicit
#: loopback client address.
_LOOPBACK_HOSTS = edge_security.LOOPBACK_HOSTS


def _is_private_ip(ip: str) -> bool:
    """Return True if *ip* is loopback, link-local, or RFC 1918/4193 address."""
    return edge_security.is_private_ip(ip)


def _real_client_ip(request: Request) -> str:
    """Return the best-effort real client IP for auth decisions."""
    return edge_security.get_edge_trust_authority().real_client_ip(request)


async def require_api_token(request: Request, call_next):
    """Protect API and schema surfaces; keep unauthenticated use loopback-only."""
    error = edge_security.get_edge_trust_authority().check_api_token_or_loopback(
        request
    )
    if error is not None:
        return error
    return await call_next(request)


async def require_browser_or_token_for_mutations(request: Request, call_next):
    """CSRF/Mutation protection: block unauthenticated non-browser mutations."""
    error = edge_security.get_edge_trust_authority().check_mutation_origin_or_token(
        request
    )
    if error is not None:
        return error
    return await call_next(request)


# --------------------------------------------------------------------------- #
# In-memory sliding-window rate limiter for sensitive API endpoints.
# Protects against brute-force on approval tokens, noisy control routes, and
# expensive evidence scans. Best-effort, per-process; the durable RateLimiter
# governs RED actions. The route authority map is metadata only here: it
# centralizes API-surface posture without becoming a new security authority.
# --------------------------------------------------------------------------- #
_RATE_LIMIT_WINDOW_S = 60.0


# Route authority and per-endpoint rate limiting are owned by the PolicyKernel.
#
# `_ROUTE_AUTHORITY` / `_RATE_LIMIT_ENDPOINTS` are safe to snapshot once at
# import time: both are derived from the kernel's route table, which is a
# single shared module global in `aios.policy.kernel` that every
# `PolicyKernel` instance reuses, so their content is identical no matter
# which kernel instance is live. Kept as backward-compatible aliases so
# existing tests can import them from `main`.
#
# The endpoint-hit *bucket* is different: it is a fresh, mutable dict created
# per `PolicyKernel.__init__`. It is deliberately NOT snapshotted into a
# module global here (there used to be a `_RATE_LIMIT_HITS` alias that did
# exactly that). If the kernel singleton is ever rebuilt (see
# `aios.policy.kernel.reset_policy_kernel`), a captured reference keeps
# pointing at the OLD kernel's bucket while the live kernel counts hits into a
# new one -- clearing the stale bucket (e.g. from a test fixture) then does
# nothing, while the real bucket fills up forever, eventually producing
# spurious 429s unrelated to the endpoint actually being hit. Every rate-limit
# code path below calls `get_policy_kernel()` fresh at the point of use
# instead, so it always operates on whichever kernel is currently live; to
# clear hits, call `get_policy_kernel().clear_endpoint_hits()` at the point of
# use too (see `tests/conftest.py`), never a cached dict reference.
_ROUTE_AUTHORITY = get_policy_kernel().route_table
_RATE_LIMIT_ENDPOINTS = get_policy_kernel().rate_limit_endpoints


def _rate_limited_route_path(request: Request) -> str | None:
    """Return the literal or templated route key used by the rate limiter."""
    return get_policy_kernel().rate_limited_route_path(request.url.path)


def _check_endpoint_rate_limit(path: str, client_ip: str) -> None:
    """Backward-compatible alias for the kernel's endpoint rate-limit check."""
    return get_policy_kernel().check_endpoint_rate_limit(path, client_ip)


async def endpoint_rate_limit(request: Request, call_next):
    """Preflight only the legacy approval parser that can reject before broker.

    Ordinary routes are counted by ``PolicyKernel``.  The approval-resume
    route still inspects a bearer from its body before it can reach its broker
    call, so this uses the same kernel bucket to prevent invalid-token floods.
    """
    if request.method != "OPTIONS" and request.url.path == "/api/v1/approval/req":
        try:
            get_policy_kernel().check_endpoint_rate_limit(
                "/api/v1/approval/req", edge_security.real_client_ip(request)
            )
        except HTTPException:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded for /api/v1/approval/req"},
            )
    return await call_next(request)


#: The order `install` registers the request middlewares in. Starlette runs
#: the LAST registered first, so this order is part of the security behaviour.
REQUEST_MIDDLEWARE = (
    bind_request_context,
    require_api_token,
    require_browser_or_token_for_mutations,
    endpoint_rate_limit,
)


def install(app: FastAPI) -> None:
    """Register every API middleware on *app*, in main's original order."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_validate_cors_origins(config.API_CORS_ORIGINS),
        allow_credentials=True,
        allow_methods=_CORS_METHODS,
        allow_headers=_CORS_HEADERS,
    )
    app.add_middleware(MetricsMiddleware)
    for middleware in REQUEST_MIDDLEWARE:
        app.middleware("http")(middleware)
