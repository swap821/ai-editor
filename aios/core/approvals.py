"""Server-issued, expiring, single-use approval capabilities.

The browser may display and approve an action, but it may not authorise an
arbitrary payload by posting it back. The server records the exact pending
action and returns an opaque token. Consuming the token yields that original
payload exactly once, only for the session it was issued to, before expiry.
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from aios import config


class ApprovalError(RuntimeError):
    """Raised when an approval capability is missing, expired, or invalid."""


@dataclass(frozen=True)
class ApprovedAction:
    action_type: str
    payload: dict[str, Any]
    session_id: str


@dataclass(frozen=True)
class _PendingApproval:
    action: ApprovedAction
    expires_at: float


class ApprovalStore:
    """Thread-safe in-memory store for local, short-lived approval capabilities."""

    def __init__(
        self,
        *,
        timeout_ms: int = config.YELLOW_APPROVAL_TIMEOUT_MS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.timeout_s = max(timeout_ms, 1) / 1000.0
        self._clock = clock
        self._pending: dict[str, _PendingApproval] = {}
        self._grants: dict[str, list[_PendingApproval]] = {}
        self._lock = threading.Lock()

    def issue(self, action_type: str, payload: dict[str, Any], session_id: str) -> str:
        """Record an exact action and return its opaque approval token."""
        if action_type not in {"command", "edit", "create"}:
            raise ApprovalError(f"unsupported approval action: {action_type}")
        if not session_id:
            raise ApprovalError("approval requires a session id")
        token = secrets.token_urlsafe(32)
        action = ApprovedAction(action_type, dict(payload), session_id)
        with self._lock:
            self._prune_locked()
            self._pending[token] = _PendingApproval(
                action=action,
                expires_at=self._clock() + self.timeout_s,
            )
        return token

    def consume(self, token: str, session_id: str) -> ApprovedAction:
        """Consume one capability; it cannot be replayed even if invalid/expired."""
        if not token:
            raise ApprovalError("approval token is required")
        with self._lock:
            pending = self._pending.pop(token, None)
        if pending is None:
            raise ApprovalError("approval token is unknown or already used")
        if pending.expires_at < self._clock():
            raise ApprovalError("approval token expired")
        if pending.action.session_id != session_id:
            raise ApprovalError("approval token belongs to a different session")
        return pending.action

    def clear(self) -> None:
        """Clear pending capabilities (tests / controlled restart)."""
        with self._lock:
            self._pending.clear()
            self._grants.clear()

    def redeem(self, token: str, session_id: str) -> ApprovedAction:
        """Exchange a one-use capability for a replay-chain server-side grant."""
        action = self.consume(token, session_id)
        with self._lock:
            self._prune_locked()
            self._grants.setdefault(session_id, []).append(
                _PendingApproval(action=action, expires_at=self._clock() + self.timeout_s)
            )
        return action

    def grants(self, session_id: str) -> list[ApprovedAction]:
        """Return the actions redeemed during the current paused replay chain."""
        with self._lock:
            self._prune_locked()
            return [row.action for row in self._grants.get(session_id, [])]

    def clear_session(self, session_id: str) -> None:
        """End a replay chain and discard all of its redeemed approvals."""
        with self._lock:
            self._grants.pop(session_id, None)

    def _prune_locked(self) -> None:
        now = self._clock()
        expired = [token for token, row in self._pending.items() if row.expires_at < now]
        for token in expired:
            self._pending.pop(token, None)
        for session_id, rows in list(self._grants.items()):
            active = [row for row in rows if row.expires_at >= now]
            if active:
                self._grants[session_id] = active
            else:
                self._grants.pop(session_id, None)
