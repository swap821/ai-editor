"""Durable emergency-stop authority for the control plane.

The latch is intentionally separate from Cortex and from frontend state. A
privileged operator engages it through this service; the service persists the
latch before invoking any stop hook. Hook failures leave the latch engaged and
are reported, so a partial emergency action cannot silently resume work.
"""

from __future__ import annotations

import json
import sqlite3
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

    def clear(
        self, *, operator_id: str, authentication_event_id: str
    ) -> EmergencyStopState:
        """Clear the latch only after another privileged operator action."""
        if not operator_id or not authentication_event_id:
            raise EmergencyStopError(
                "clearing emergency stop requires privileged authentication"
            )
        with self._connect() as conn:
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
