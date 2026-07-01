"""Server-issued, expiring, single-use approval capabilities.

The browser may display and approve an action, but it may not authorise an
arbitrary payload by posting it back. The server records the exact pending
action and returns an opaque token. Production uses a local SQLite store so
capabilities survive a backend restart and coordinate across workers. Only
SHA-256 digests of the bearer token and caller-supplied session id are persisted.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from aios import config
from aios.security.secret_scanner import scan_and_redact


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
    """Short-lived approval store, optionally durable and multi-process safe."""

    def __init__(
        self,
        *,
        timeout_ms: int = config.YELLOW_APPROVAL_TIMEOUT_MS,
        clock: Callable[[], float] = time.time,
        db_path: Optional[Path] = None,
    ) -> None:
        self.timeout_s = max(timeout_ms, 1) / 1000.0
        self._clock = clock
        self.db_path = db_path
        self._pending: dict[str, _PendingApproval] = {}
        self._grants: dict[str, list[_PendingApproval]] = {}
        self._lock = threading.Lock()
        if self.db_path is not None:
            self._init_db()

    @staticmethod
    def _token_digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _session_digest(session_id: str) -> str:
        return hashlib.sha256(session_id.encode("utf-8")).hexdigest()

    @staticmethod
    def _payload_for_secret_scan(action_type: str, payload: dict[str, Any]) -> str:
        scan_payload = dict(payload)
        if action_type == "rollback":
            snapshot_id = scan_payload.get("snapshot_id")
            if isinstance(snapshot_id, str) and re.fullmatch(
                r"[0-9a-f]{40}", snapshot_id
            ):
                scan_payload["snapshot_id"] = "<rollback-snapshot-sha>"
            mission_id = scan_payload.get("mission_id")
            if isinstance(mission_id, str) and re.fullmatch(
                r"mission-[0-9a-f]{12}", mission_id
            ):
                scan_payload["mission_id"] = "<council-mission-id>"
        return json.dumps(scan_payload, separators=(",", ":"), sort_keys=True)

    def _connect(self) -> sqlite3.Connection:
        assert self.db_path is not None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = FULL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS approval_pending (
                    token_digest TEXT PRIMARY KEY,
                    action_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approval_grants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_approval_pending_expiry
                    ON approval_pending(expires_at);
                CREATE INDEX IF NOT EXISTS idx_approval_grants_session_expiry
                    ON approval_grants(session_id, expires_at);
                """
            )
            for table in ("approval_pending", "approval_grants"):
                rows = conn.execute(f"SELECT DISTINCT session_id FROM {table}").fetchall()
                for row in rows:
                    session_id = str(row["session_id"])
                    digest = self._session_digest(session_id)
                    if not re.fullmatch(r"[0-9a-f]{64}", session_id):
                        conn.execute(
                            f"UPDATE {table} SET session_id = ? WHERE session_id = ?",
                            (digest, session_id),
                        )

    @staticmethod
    def _row_action(row: sqlite3.Row, session_id: Optional[str] = None) -> ApprovedAction:
        return ApprovedAction(
            action_type=str(row["action_type"]),
            payload=json.loads(str(row["payload_json"])),
            session_id=session_id or str(row["session_id"]),
        )

    def issue(self, action_type: str, payload: dict[str, Any], session_id: str) -> str:
        """Record an exact action and return its opaque approval token."""
        if action_type not in {"command", "edit", "create", "rollback"}:
            raise ApprovalError(f"unsupported approval action: {action_type}")
        if not session_id:
            raise ApprovalError("approval requires a session id")
        token = secrets.token_urlsafe(32)
        action = ApprovedAction(action_type, dict(payload), session_id)
        expires_at = self._clock() + self.timeout_s
        if self.db_path is not None:
            serialized = json.dumps(action.payload, separators=(",", ":"), sort_keys=True)
            scan = scan_and_redact(
                self._payload_for_secret_scan(action.action_type, action.payload)
            )
            if scan.detected:
                raise ApprovalError(
                    "approval payload contains credential-like data and cannot be persisted"
                )
            with self._connect() as conn:
                self._prune_db(conn)
                conn.execute(
                    "INSERT INTO approval_pending "
                    "(token_digest, action_type, payload_json, session_id, expires_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        self._token_digest(token),
                        action.action_type,
                        serialized,
                        self._session_digest(action.session_id),
                        expires_at,
                    ),
                )
            return token
        with self._lock:
            self._prune_locked()
            self._pending[token] = _PendingApproval(action=action, expires_at=expires_at)
        return token

    def consume(self, token: str, session_id: str) -> ApprovedAction:
        """Consume one capability; it cannot be replayed even if invalid/expired.

        Uses atomic DELETE ... RETURNING in SQL mode so concurrent requests
        with the same token race safely — only one wins. In-memory mode holds
        the class lock for the entire check-and-delete to prevent TOCTOU.
        """
        if not token:
            raise ApprovalError("approval token is required")
        if self.db_path is not None:
            digest = self._token_digest(token)
            with self._connect() as conn:
                # Atomic DELETE ... RETURNING eliminates the SELECT-then-DELETE
                # race: two concurrent connections cannot both see the row.
                row = conn.execute(
                    "DELETE FROM approval_pending WHERE token_digest = ? RETURNING "
                    "action_type, payload_json, session_id, expires_at",
                    (digest,),
                ).fetchone()
            if row is None:
                raise ApprovalError("approval token is unknown or already used")
            if float(row["expires_at"]) < self._clock():
                raise ApprovalError("approval token expired")
            stored_session = str(row["session_id"])
            if stored_session not in {session_id, self._session_digest(session_id)}:
                raise ApprovalError("approval token belongs to a different session")
            return self._row_action(row, session_id)
        # In-memory: hold the lock for the full check-and-delete to prevent
        # a second thread from seeing the token after the first has validated
        # but before it has been removed.
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
        if self.db_path is not None:
            with self._connect() as conn:
                conn.execute("DELETE FROM approval_pending")
                conn.execute("DELETE FROM approval_grants")
            return
        with self._lock:
            self._pending.clear()
            self._grants.clear()

    def redeem(self, token: str, session_id: str) -> ApprovedAction:
        """Exchange a one-use capability for a replay-chain server-side grant."""
        action = self.consume(token, session_id)
        expires_at = self._clock() + self.timeout_s
        if self.db_path is not None:
            with self._connect() as conn:
                self._prune_db(conn)
                conn.execute(
                    "INSERT INTO approval_grants "
                    "(action_type, payload_json, session_id, expires_at) VALUES (?, ?, ?, ?)",
                    (
                        action.action_type,
                        json.dumps(action.payload, separators=(",", ":"), sort_keys=True),
                        self._session_digest(action.session_id),
                        expires_at,
                    ),
                )
            return action
        with self._lock:
            self._prune_locked()
            self._grants.setdefault(session_id, []).append(
                _PendingApproval(action=action, expires_at=expires_at)
            )
        return action

    def grants(self, session_id: str) -> list[ApprovedAction]:
        """Return the actions redeemed during the current paused replay chain."""
        if self.db_path is not None:
            with self._connect() as conn:
                self._prune_db(conn)
                rows = conn.execute(
                    "SELECT action_type, payload_json, session_id FROM approval_grants "
                    "WHERE session_id IN (?, ?) ORDER BY id",
                    (self._session_digest(session_id), session_id),
                ).fetchall()
            return [self._row_action(row, session_id) for row in rows]
        with self._lock:
            self._prune_locked()
            return [row.action for row in self._grants.get(session_id, [])]

    def clear_session(self, session_id: str) -> None:
        """End a replay chain and discard all of its redeemed approvals."""
        if self.db_path is not None:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM approval_grants WHERE session_id IN (?, ?)",
                    (self._session_digest(session_id), session_id),
                )
            return
        with self._lock:
            self._grants.pop(session_id, None)

    def grant_count(self) -> int:
        """Total number of redeemed approval grants currently on record."""
        if self.db_path is not None:
            with self._connect() as conn:
                self._prune_db(conn)
                row = conn.execute("SELECT COUNT(*) AS n FROM approval_grants").fetchone()
            return int(row["n"])
        with self._lock:
            self._prune_locked()
            return sum(len(rows) for rows in self._grants.values())

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

    def _prune_db(self, conn: sqlite3.Connection) -> None:
        now = self._clock()
        conn.execute("DELETE FROM approval_pending WHERE expires_at < ?", (now,))
        conn.execute("DELETE FROM approval_grants WHERE expires_at < ?", (now,))
