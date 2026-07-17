"""Durable emergency-stop authority for the control plane.

The latch is intentionally separate from Cortex and from frontend state. A
privileged operator engages it through this service; the service persists the
latch before invoking any stop hook. Hook failures leave the latch engaged and
are reported, so a partial emergency action cannot silently resume work.
"""

from __future__ import annotations

import json
import hashlib
import secrets
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from aios import config
from aios.domain.governance import EmergencyStopRequest, EmergencyStopState
from aios.infrastructure.storage.migrations import apply_migrations
from aios.security.secret_scanner import scan_and_redact


class EmergencyStopError(RuntimeError):
    """Raised when the emergency latch cannot complete safely."""


@dataclass(frozen=True, slots=True)
class EmergencyStopHooks:
    """The five explicit side-effect boundaries controlled by the latch."""

    revoke_capabilities: Callable[[], Any]
    cancel_queued_missions: Callable[[], Any]
    kill_active_workers: Callable[[], Any]
    disable_autonomy: Callable[[], Any]
    preserve_evidence: Callable[[str], Any]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class EmergencyStopController:
    """Persist and enforce one fail-closed emergency-stop latch."""

    _HOOK_NAMES = (
        "revoke_capabilities",
        "cancel_queued_missions",
        "kill_active_workers",
        "disable_autonomy",
        "preserve_evidence",
    )

    def __init__(
        self,
        db_path: str | Path = config.DATA_DIR / "emergency_stop.db",
        *,
        hooks: EmergencyStopHooks,
    ) -> None:
        self.db_path = Path(db_path)
        self.hooks = hooks
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            apply_migrations(conn, scope="governance")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = FULL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def state(self) -> EmergencyStopState:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM emergency_stop_state WHERE singleton = 1"
            ).fetchone()
        if row is None:
            return EmergencyStopState()
        try:
            actions = json.loads(str(row["actions_json"]))
        except json.JSONDecodeError:
            actions = {}
        if not isinstance(actions, dict):
            actions = {}
        return EmergencyStopState(
            engaged=bool(row["engaged"]),
            generation=int(row["generation"]),
            operator_id=row["operator_id"],
            authentication_event_id=row["authentication_event_id"],
            reason=str(row["reason"]),
            actions={str(key): str(value) for key, value in actions.items()},
            failure=row["failure"],
            engaged_at=row["engaged_at"],
            cleared_at=row["cleared_at"],
        )

    def is_engaged(self) -> bool:
        return self.state().engaged

    def assert_operational(self) -> None:
        if self.is_engaged():
            raise EmergencyStopError(
                "emergency stop is engaged; side effects are disabled"
            )

    def engage(self, request: EmergencyStopRequest) -> EmergencyStopState:
        """Latch the stop before revoking capabilities and killing work."""
        safe_reason = scan_and_redact(request.reason).scrubbed[:1000]
        now = _utc_now()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM emergency_stop_state WHERE singleton = 1"
            ).fetchone()
            if row is not None and bool(row["engaged"]):
                conn.commit()
                return self.state()
            generation = int(row["generation"]) + 1 if row is not None else 1
            conn.execute(
                """
                INSERT INTO emergency_stop_state (
                    singleton, engaged, generation, operator_id,
                    authentication_event_id, reason, actions_json, failure,
                    engaged_at, cleared_at
                ) VALUES (1, 1, ?, ?, ?, ?, ?, NULL, ?, NULL)
                ON CONFLICT(singleton) DO UPDATE SET
                    engaged = 1,
                    generation = excluded.generation,
                    operator_id = excluded.operator_id,
                    authentication_event_id = excluded.authentication_event_id,
                    reason = excluded.reason,
                    actions_json = excluded.actions_json,
                    failure = NULL,
                    engaged_at = excluded.engaged_at,
                    cleared_at = NULL
                """,
                (
                    generation,
                    request.operator_id,
                    request.authentication_event_id,
                    safe_reason,
                    json.dumps({}, sort_keys=True),
                    now,
                ),
            )

        actions: dict[str, str] = {}
        failures: list[str] = []
        for name in self._HOOK_NAMES:
            callback = getattr(self.hooks, name)
            try:
                result = (
                    callback(safe_reason) if name == "preserve_evidence" else callback()
                )
                if result is False:
                    raise RuntimeError("hook returned false")
                actions[name] = self._result_label(result)
            except Exception as exc:  # noqa: BLE001 - latch stays engaged
                actions[name] = f"failed:{type(exc).__name__}"
                failures.append(name)

        failure = ",".join(failures) if failures else None
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE emergency_stop_state
                SET actions_json = ?, failure = ?
                WHERE singleton = 1
                """,
                (json.dumps(actions, sort_keys=True), failure),
            )
        result = self.state()
        if failure:
            raise EmergencyStopError(
                "emergency stop engaged, but one or more stop hooks failed: " + failure
            )
        return result

    def issue_clear_capability(
        self,
        *,
        operator_id: str,
        authentication_event_id: str,
        session_id: str,
        ttl_seconds: float = 300.0,
    ) -> str:
        """Mint one opaque clear capability for a fresh privileged session.

        Ordinary capability issuance is blocked while the latch is engaged.
        This narrow issuance path is the sole exception: it can only mint a
        generation-bound clear token after a new privileged authentication
        event, and the token is consumed atomically by :meth:`clear`.
        """
        if not operator_id or not authentication_event_id or not session_id:
            raise EmergencyStopError(
                "emergency-clear capability requires privileged identity, event, and session"
            )
        ttl = max(float(ttl_seconds), 0.001)
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT engaged, generation, authentication_event_id "
                "FROM emergency_stop_state WHERE singleton = 1"
            ).fetchone()
            if row is None or not bool(row["engaged"]):
                raise EmergencyStopError("emergency stop is not engaged")
            if str(row["authentication_event_id"] or "") == authentication_event_id:
                raise EmergencyStopError(
                    "emergency-clear capability requires a new privileged authentication event"
                )
            generation = int(row["generation"])
            conn.execute(
                """
                INSERT INTO emergency_clear_capabilities (
                    capability_digest, generation, operator_id,
                    authentication_event_id, session_id, issued_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    digest,
                    generation,
                    operator_id,
                    authentication_event_id,
                    session_id,
                    now,
                    now + ttl,
                ),
            )
        try:
            self.hooks.preserve_evidence(
                "emergency-clear capability issued; "
                f"generation={generation}, operator={operator_id}, "
                f"authentication_event={authentication_event_id}"
            )
        except Exception as exc:  # noqa: BLE001 - issuance fails closed
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM emergency_clear_capabilities "
                    "WHERE capability_digest = ? AND consumed_at IS NULL",
                    (digest,),
                )
            raise EmergencyStopError(
                "emergency-clear capability evidence preservation failed"
            ) from exc
        return token

    def clear(
        self,
        *,
        operator_id: str,
        authentication_event_id: str,
        session_id: str,
        clear_capability: str,
    ) -> EmergencyStopState:
        """Clear only with a fresh privileged identity and exact one-use token."""
        if (
            not operator_id
            or not authentication_event_id
            or not session_id
            or not clear_capability
        ):
            raise EmergencyStopError(
                "clearing emergency stop requires privileged identity, event, session, and exact capability"
            )
        digest = hashlib.sha256(clear_capability.encode("utf-8")).hexdigest()
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            state = conn.execute(
                "SELECT engaged, generation, authentication_event_id "
                "FROM emergency_stop_state WHERE singleton = 1"
            ).fetchone()
            if state is None or not bool(state["engaged"]):
                raise EmergencyStopError("emergency stop is not engaged")
            if str(state["authentication_event_id"] or "") == authentication_event_id:
                raise EmergencyStopError(
                    "clearing emergency stop requires a new privileged authentication event"
                )
            capability = conn.execute(
                """
                SELECT capability_digest FROM emergency_clear_capabilities
                WHERE capability_digest = ?
                  AND generation = ?
                  AND operator_id = ?
                  AND authentication_event_id = ?
                  AND session_id = ?
                  AND consumed_at IS NULL
                  AND expires_at > ?
                """,
                (
                    digest,
                    int(state["generation"]),
                    operator_id,
                    authentication_event_id,
                    session_id,
                    now,
                ),
            ).fetchone()
            if capability is None:
                raise EmergencyStopError("exact emergency-clear capability required")
            try:
                self.hooks.preserve_evidence(
                    "emergency stop cleared; "
                    f"generation={int(state['generation'])}, operator={operator_id}, "
                    f"authentication_event={authentication_event_id}"
                )
            except Exception as exc:  # noqa: BLE001 - clear fails closed
                raise EmergencyStopError(
                    "emergency-clear evidence preservation failed"
                ) from exc
            conn.execute(
                "UPDATE emergency_clear_capabilities SET consumed_at = ? "
                "WHERE capability_digest = ? AND consumed_at IS NULL",
                (now, digest),
            )
            conn.execute(
                """
                UPDATE emergency_stop_state
                SET engaged = 0, failure = NULL, cleared_at = ?,
                    operator_id = ?, authentication_event_id = ?
                WHERE singleton = 1
                """,
                (_utc_now(), operator_id, authentication_event_id),
            )
        return self.state()

    @staticmethod
    def _result_label(result: Any) -> str:
        if isinstance(result, int) and not isinstance(result, bool):
            return f"completed:{result}"
        return "completed"


__all__ = ["EmergencyStopController", "EmergencyStopError", "EmergencyStopHooks"]
