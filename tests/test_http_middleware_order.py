"""The API's middleware stack is security behaviour, so its order is pinned.

Starlette runs the LAST registered middleware first. Moving the middleware out
of aios/api/main.py (2026-10-12) had to reproduce this exact stack; a later
edit that reorders it -- e.g. letting the rate limit run inside the token
check -- must fail here, not in production.
"""

from __future__ import annotations

from aios.api import http_middleware
from aios.api.main import app

#: Outermost first, as Starlette holds them in ``app.user_middleware``.
EXPECTED = [
    "BaseHTTPMiddleware:endpoint_rate_limit",
    "BaseHTTPMiddleware:require_browser_or_token_for_mutations",
    "BaseHTTPMiddleware:require_api_token",
    "BaseHTTPMiddleware:bind_request_context",
    "MetricsMiddleware:",
    "CORSMiddleware:",
]


def _stack() -> list[str]:
    out = []
    for m in app.user_middleware:
        options = getattr(m, "kwargs", None) or getattr(m, "options", None) or {}
        dispatch = options.get("dispatch")
        out.append(f"{m.cls.__name__}:{getattr(dispatch, '__name__', '')}")
    return out


def test_the_middleware_stack_is_exactly_the_original_order() -> None:
    assert _stack() == EXPECTED


def test_main_still_exports_what_tests_and_callers_import() -> None:
    from aios.api import main

    for name in (
        "_validate_cors_origins",
        "bind_request_context",
        "_is_private_ip",
        "_real_client_ip",
        "_RATE_LIMIT_ENDPOINTS",
        "_ROUTE_AUTHORITY",
        "_check_endpoint_rate_limit",
    ):
        assert getattr(main, name) is getattr(http_middleware, name), name
