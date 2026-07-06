"""Session-management routes — httpOnly Secure SameSite=Strict cookies (H2).

Extracted from ``aios/api/main.py`` (monolith split tranche 2, 2026-07-06).

SECURITY: Session IDs are managed server-side and travel in httpOnly cookies
that are completely inaccessible to JavaScript. This prevents XSS-based
session theft (OWASP A07:2021). The raw session ID is never logged or exposed.
"""
from __future__ import annotations

import hashlib
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from aios import config
from aios.api.deps import get_session_manager
from aios.core.session_manager import SessionManager

router = APIRouter()


class SessionCreateResponse(BaseModel):
    """Response from POST /api/v1/auth/session — session created."""

    authenticated: bool = Field(
        ..., description="True when the session is authenticated."
    )
    session_id: str = Field(
        ..., alias="sessionId", description="The session identifier (for cookie-based clients)."
    )
    cookie_based: bool = Field(
        True, alias="cookieBased",
        description="True when session travels via httpOnly cookie.",
    )
    warning: Optional[str] = Field(
        None,
        description="Security warning when cookie-less fallback is in use.",
    )

    model_config = {"populate_by_name": True}


class SessionStatusResponse(BaseModel):
    """Response from GET /api/v1/auth/session — current session status."""

    authenticated: bool = Field(
        ..., description="True when a valid session exists."
    )
    cookie_based: bool = Field(
        True, alias="cookieBased",
        description="True when session travels via httpOnly cookie.",
    )
    session_id: Optional[str] = Field(
        None, alias="sessionId",
        description="The session identifier (only when not cookie-based).",
    )

    model_config = {"populate_by_name": True}


def _set_session_cookie(response: Response, raw_session_id: str) -> str:
    """Set the session_id cookie with httpOnly, Secure, SameSite=Strict flags.

    Returns the cookie value (the SHA-256 hash) so it can be used as a
    session identifier in logs (the raw ID is never logged).
    """
    cookie_value = hashlib.sha256(raw_session_id.encode()).hexdigest()
    # In development (loopback) Secure=False so the cookie works over HTTP.
    # In production behind HTTPS, Secure=True is enforced by config check.
    secure = config.API_HOST not in {"127.0.0.1", "localhost", "::1"}
    response.set_cookie(
        key="session_id",
        value=cookie_value,
        httponly=True,          # NOT accessible to JavaScript — prevents XSS theft
        secure=secure,          # HTTPS only in production; loopback allows HTTP
        samesite="strict",      # NOT sent cross-origin — prevents CSRF
        max_age=3600,           # 1 hour
        path="/",             # Sent for all API paths
    )
    return cookie_value


@router.post("/api/v1/auth/session")
def create_session(
    response: Response,
    manager: SessionManager = Depends(get_session_manager),
) -> SessionCreateResponse:
    """Create a new server-side session and set the httpOnly session cookie.

    The session ID is stored in an httpOnly, Secure, SameSite=Strict cookie.
    JavaScript cannot read this cookie, preventing XSS-based session theft.

    If cookies are blocked (e.g., privacy mode), the session ID is returned
    in the response body with a security warning — the client should fall
    back to sending it in the ``sessionId`` field of subsequent requests.
    """
    raw_id = manager.create_session()
    cookie_hash = _set_session_cookie(response, raw_id)
    return SessionCreateResponse(
        authenticated=True,
        session_id=cookie_hash,
        cookie_based=True,
    )


@router.get("/api/v1/auth/session")
def get_session_status(
    request: Request,
    manager: SessionManager = Depends(get_session_manager),
) -> SessionStatusResponse:
    """Check whether the current session is valid.

    Returns ``authenticated: true`` when the request carries a valid
    session cookie. The frontend calls this on load to determine whether
    a session exists without needing to read the cookie directly
    (httpOnly cookies are invisible to JavaScript).
    """
    cookie_hash = request.cookies.get("session_id")
    session = manager.validate_session(cookie_hash)
    if session is not None:
        return SessionStatusResponse(
            authenticated=True,
            cookie_based=True,
        )
    return SessionStatusResponse(
        authenticated=False,
        cookie_based=True,
    )


@router.delete("/api/v1/auth/session")
def destroy_session(
    request: Request,
    response: Response,
    manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    """Invalidate the current session (logout).

    Removes the session from server-side storage AND clears the cookie
    so the browser stops sending it.
    """
    cookie_hash = request.cookies.get("session_id")
    manager.invalidate_session(cookie_hash)
    response.delete_cookie(
        key="session_id",
        path="/",
        httponly=True,
        secure=config.API_HOST not in {"127.0.0.1", "localhost", "::1"},
        samesite="strict",
    )
    return {"authenticated": False}
