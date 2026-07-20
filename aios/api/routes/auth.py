"""Session-management routes — httpOnly Secure SameSite=Strict cookies (H2).

Extracted from ``aios/api/main.py`` (monolith split tranche 2, 2026-07-06).

SECURITY: Session IDs are managed server-side and travel in httpOnly cookies
that are completely inaccessible to JavaScript. This prevents XSS-based
session theft (OWASP A07:2021). The raw session ID is never logged or exposed.
"""

from __future__ import annotations

import hashlib
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from aios import config
from aios.api.deps import get_identity_service, get_session_manager
from aios.application.identity.service import (
    AlreadyEnrolled,
    IdentityService,
    InvalidCredential,
)
from aios.core.session_manager import SessionManager
from aios.api.action_guard import enforce_action_boundary

router = APIRouter(dependencies=[Depends(enforce_action_boundary)])


class SessionCreateResponse(BaseModel):
    """Response from POST /api/v1/auth/session — session created."""

    authenticated: bool = Field(
        ..., description="True when the session is authenticated."
    )
    cookie_based: bool = Field(
        True,
        alias="cookieBased",
        description="True when session travels via httpOnly cookie.",
    )
    csrf_token: str = Field(
        ..., alias="csrfToken", description="Session-bound proof for browser mutations."
    )

    model_config = {"populate_by_name": True}


class SessionStatusResponse(BaseModel):
    """Response from GET /api/v1/auth/session — current session status."""

    authenticated: bool = Field(..., description="True when a valid session exists.")
    cookie_based: bool = Field(
        True,
        alias="cookieBased",
        description="True when session travels via httpOnly cookie.",
    )
    operator_id: Optional[str] = Field(None, alias="operatorId")
    csrf_token: Optional[str] = Field(
        None,
        alias="csrfToken",
        description="Session-bound proof for browser mutations.",
    )

    model_config = {"populate_by_name": True}


class EnrollmentRequest(BaseModel):
    display_name: str = Field(..., alias="displayName", min_length=1, max_length=120)

    model_config = {"populate_by_name": True}


class CredentialRequest(BaseModel):
    credential: str = Field(..., min_length=1, max_length=512)


class OperatorAuthResponse(BaseModel):
    authenticated: bool
    cookie_based: bool = Field(True, alias="cookieBased")
    operator_id: str = Field(..., alias="operatorId")
    reauthenticated: bool = False

    model_config = {"populate_by_name": True}


def _set_session_cookie(response: Response, raw_session_id: str) -> str:
    """Set the session_id cookie with httpOnly, Secure, SameSite=Strict flags.

    Returns the cookie value (the SHA-256 hash) so it can be used as a
    session identifier in logs (the raw ID is never logged).
    """
    cookie_value = hashlib.sha256(raw_session_id.encode()).hexdigest()
    _set_session_hash_cookie(response, cookie_value)
    return cookie_value


def _set_session_hash_cookie(response: Response, cookie_value: str) -> None:
    """Set an already-hashed opaque session cookie."""
    # In development (loopback) Secure=False so the cookie works over HTTP.
    # In production behind HTTPS, Secure=True is enforced by config check.
    secure = config.API_HOST not in {"127.0.0.1", "localhost", "::1"}
    response.set_cookie(
        key="session_id",
        value=cookie_value,
        httponly=True,  # NOT accessible to JavaScript — prevents XSS theft
        secure=secure,  # HTTPS only in production; loopback allows HTTP
        samesite="strict",  # NOT sent cross-origin — prevents CSRF
        max_age=3600,  # 1 hour
        path="/",  # Sent for all API paths
    )


def _set_csrf_cookie(response: Response, csrf_token: str) -> None:
    """Expose only the CSRF proof to same-origin JavaScript, never the session ID."""
    secure = config.API_HOST not in {"127.0.0.1", "localhost", "::1"}
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=secure,
        samesite="strict",
        max_age=3600,
        path="/",
    )


@router.post("/api/v1/auth/session")
def create_session(
    response: Response,
    manager: SessionManager = Depends(get_session_manager),
) -> SessionCreateResponse:
    """Create a new server-side session and set the httpOnly session cookie.

    The session ID is stored in an httpOnly, Secure, SameSite=Strict cookie.
    JavaScript cannot read this cookie, preventing XSS-based session theft.

    The opaque session cookie is never echoed in JSON. Clients must retain the
    browser cookie and use the CSRF proof for same-origin mutations.
    """
    raw_id = manager.create_session()
    cookie_hash = _set_session_cookie(response, raw_id)
    csrf_token = manager.ensure_csrf_token(cookie_hash)
    if csrf_token is None:  # pragma: no cover - create_session just succeeded
        raise RuntimeError("new session did not produce a CSRF token")
    _set_csrf_cookie(response, csrf_token)
    return SessionCreateResponse(
        authenticated=True,
        cookie_based=True,
        csrf_token=csrf_token,
    )


@router.post("/api/v1/auth/enroll", status_code=201)
def enroll_operator(
    req: EnrollmentRequest,
    identity: IdentityService = Depends(get_identity_service),
) -> dict[str, Any]:
    """Bootstrap exactly one Human Sovereign and return one-time material."""
    try:
        enrollment = identity.enroll_operator(display_name=req.display_name)
    except AlreadyEnrolled as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "enrolled": True,
        "operatorId": enrollment.operator_id,
        "enrollmentCredential": enrollment.enrollment_credential,
        "recoveryCode": enrollment.recovery_code,
    }


@router.post("/api/v1/auth/login")
def login_operator(
    req: CredentialRequest,
    response: Response,
    identity: IdentityService = Depends(get_identity_service),
) -> OperatorAuthResponse:
    """Authenticate the enrolled operator and set an opaque server-side cookie."""
    try:
        result = identity.authenticate_credential(req.credential)
    except InvalidCredential as exc:
        raise HTTPException(
            status_code=401, detail="invalid operator credential"
        ) from exc
    _set_session_hash_cookie(response, result.session_cookie)
    csrf_token = identity.sessions.ensure_csrf_token(result.session_cookie)
    if csrf_token is None:  # pragma: no cover - authentication just created it
        raise HTTPException(
            status_code=401, detail="authentication session unavailable"
        )
    _set_csrf_cookie(response, csrf_token)
    return OperatorAuthResponse(
        authenticated=True,
        operator_id=result.principal.principal_id,
    )


@router.post("/api/v1/auth/reauth")
def reauthenticate_operator(
    req: CredentialRequest,
    request: Request,
    response: Response,
    identity: IdentityService = Depends(get_identity_service),
) -> OperatorAuthResponse:
    """Re-authenticate and rotate the operator's server-side session."""
    old_cookie = request.cookies.get("session_id")
    try:
        result = identity.reauthenticate(old_cookie or "", req.credential)
    except InvalidCredential as exc:
        raise HTTPException(
            status_code=401, detail="privileged re-authentication failed"
        ) from exc
    _set_session_hash_cookie(response, result.session_cookie)
    csrf_token = identity.sessions.ensure_csrf_token(result.session_cookie)
    if csrf_token is None:  # pragma: no cover - rotation just created it
        raise HTTPException(
            status_code=401, detail="rotated authentication session unavailable"
        )
    _set_csrf_cookie(response, csrf_token)
    return OperatorAuthResponse(
        authenticated=True,
        operator_id=result.principal.principal_id,
        reauthenticated=True,
    )


@router.get("/api/v1/auth/session")
def get_session_status(
    request: Request,
    response: Response,
    manager: SessionManager = Depends(get_session_manager),
    identity: IdentityService = Depends(get_identity_service),
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
        csrf_token = manager.ensure_csrf_token(session.session_hash)
        if csrf_token is not None:
            _set_csrf_cookie(response, csrf_token)
        principal = identity.get_authenticated_principal(session.session_hash)
        return SessionStatusResponse(
            authenticated=True,
            cookie_based=True,
            operator_id=principal.principal_id if principal is not None else None,
            csrf_token=csrf_token,
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
    identity: IdentityService = Depends(get_identity_service),
) -> dict[str, Any]:
    """Invalidate the current session (logout).

    Removes the session from server-side storage AND clears the cookie
    so the browser stops sending it.
    """
    cookie_hash = request.cookies.get("session_id")
    manager.invalidate_session(cookie_hash)
    identity.revoke_session(cookie_hash)
    response.delete_cookie(
        key="session_id",
        path="/",
        httponly=True,
        secure=config.API_HOST not in {"127.0.0.1", "localhost", "::1"},
        samesite="strict",
    )
    response.delete_cookie(
        key="csrf_token",
        path="/",
        secure=config.API_HOST not in {"127.0.0.1", "localhost", "::1"},
        samesite="strict",
    )
    return {"authenticated": False}
