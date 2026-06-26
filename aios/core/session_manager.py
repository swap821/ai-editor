"""Secure session management with httpOnly cookies.

Replaces client-side sessionStorage with server-side sessions
to prevent XSS-based session theft. Session IDs are stored as
SHA-256 hashes in httpOnly, Secure, SameSite=Strict cookies.

OWASP A07:2021 — Authentication Failures mitigation:
  * Session IDs are cryptographically random (secrets.token_urlsafe)
  * Session IDs are NEVER exposed to JavaScript (httpOnly cookie)
  * Cookie is only sent over HTTPS (Secure flag)
  * Cookie is not sent cross-origin (SameSite=Strict)
  * Session is invalidated on logout (server-side deletion)
  * Session ID is regenerated on privilege change (fixation prevention)
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Session:
    """An in-memory server-side session."""

    session_id: str  # Raw ID (only in memory, never logged)
    session_hash: str  # SHA-256 hash stored in cookie
    created_at: float
    last_accessed: float
    data: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self, max_age: float = 3600) -> bool:
        """Return True if the session has been inactive longer than *max_age* seconds."""
        return time.time() - self.last_accessed > max_age


class SessionManager:
    """Server-side session manager with httpOnly cookie support.

    Usage::

        manager = SessionManager()

        # On login — create session, set cookie
        raw_id = manager.create_session()
        response.set_cookie(
            "session_id", hashlib.sha256(raw_id.encode()).hexdigest(),
            httponly=True, secure=True, samesite="strict",
        )

        # On request — validate session from cookie hash
        cookie_hash = request.cookies.get("session_id")
        session = manager.validate_session(cookie_hash)
        if session is None:
            raise HTTPException(status_code=401)

        # On logout — invalidate session
        manager.invalidate_session(cookie_hash)

        # On privilege upgrade — regenerate session ID (fixation prevention)
        new_raw_id = manager.upgrade_session(old_cookie_hash)
    """

    def __init__(
        self,
        max_age: float = 3600,
        cleanup_interval: float = 300,
    ) -> None:
        self._sessions: Dict[str, Session] = {}  # keyed by hash
        self._max_age = max_age
        self._cleanup_interval = cleanup_interval
        self._last_cleanup = time.time()

    def create_session(self, data: Optional[Dict[str, Any]] = None) -> str:
        """Create a new session and return the RAW session ID.

        The caller MUST set the raw ID in an httpOnly cookie after hashing::

            raw = manager.create_session()
            cookie_value = hashlib.sha256(raw.encode()).hexdigest()
            response.set_cookie("session_id", cookie_value, httponly=True, ...)

        The raw ID is returned ONLY so the cookie can be set; it must
        never be logged, sent to the client in any other form, or
        exposed to JavaScript.
        """
        raw_id = secrets.token_urlsafe(32)
        session_hash = hashlib.sha256(raw_id.encode()).hexdigest()
        now = time.time()
        self._sessions[session_hash] = Session(
            session_id=raw_id,
            session_hash=session_hash,
            created_at=now,
            last_accessed=now,
            data=dict(data) if data else {},
        )
        return raw_id

    def validate_session(self, cookie_hash: Optional[str]) -> Optional[Session]:
        """Validate a session from the cookie hash.

        Returns the :class:`Session` if valid and not expired, ``None``
        otherwise. Updates the ``last_accessed`` timestamp on success.
        """
        if not cookie_hash:
            return None
        self._cleanup_expired()
        session = self._sessions.get(cookie_hash)
        if session and not session.is_expired(self._max_age):
            session.last_accessed = time.time()
            return session
        return None

    def invalidate_session(self, cookie_hash: Optional[str]) -> None:
        """Remove a session (logout). No-op if the session does not exist."""
        if cookie_hash:
            self._sessions.pop(cookie_hash, None)

    def upgrade_session(self, old_hash: str) -> str:
        """Regenerate session ID on privilege change.

        Prevents session fixation attacks: when a user authenticates
        (or upgrades privileges), the old session is destroyed and a
        new one is created carrying the same data but a fresh ID.

        Returns the NEW raw session ID (caller must update the cookie).
        """
        old_session = self._sessions.pop(old_hash, None)
        if old_session is not None:
            new_raw = secrets.token_urlsafe(32)
            new_hash = hashlib.sha256(new_raw.encode()).hexdigest()
            self._sessions[new_hash] = Session(
                session_id=new_raw,
                session_hash=new_hash,
                created_at=old_session.created_at,
                last_accessed=time.time(),
                data=old_session.data,
            )
            return new_raw
        return self.create_session()

    def session_count(self) -> int:
        """Return the number of active (non-expired) sessions."""
        self._cleanup_expired()
        return len(self._sessions)

    def _cleanup_expired(self) -> None:
        """Remove expired sessions. Best-effort; never raises."""
        if time.time() - self._last_cleanup < self._cleanup_interval:
            return
        expired = [
            h for h, s in self._sessions.items() if s.is_expired(self._max_age)
        ]
        for h in expired:
            del self._sessions[h]
        self._last_cleanup = time.time()
