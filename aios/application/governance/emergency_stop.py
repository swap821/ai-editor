"""Durable emergency-stop authority for the control plane.

The latch is intentionally separate from Cortex and from frontend state. A
privileged operator engages it through this service; the service persists the
latch before invoking any stop hook. Hook failures leave the latch engaged and
are reported, so a partial emergency action cannot silently resume work.
"""

from __future__ import annotations

import json
import hashlib
import logging
import secrets
import sqlite3
import threading
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


_LOGGER = logging.getLogger(__name__)

#: Turn ids already recorded as incomplete, so the pipeline and the coordinator
#: cannot both write a row for the same turn.
_RECORDED_TURNS: list[str] = []

#: Guards the check-then-append on _RECORDED_TURNS above.
#:
#: The two callers are on DIFFERENT THREADS. `generate_pipeline` runs inside a
#: threadpool (the sync generator is iterated via `iterate_in_threadpool` so it
#: cannot block the event loop), while `TurnCoordinator`'s `finally` runs on the
#: loop. Without this lock both can pass the membership test before either
#: appends, and both write a row -- for the one fact the function's own
#: docstring says must appear exactly once. A governance audit would then see
#: two rows for one interrupted turn and could not tell which was authoritative.
_RECORDED_TURNS_LOCK = threading.Lock()


def latch_is_engaged() -> bool:
    """True when the emergency stop is currently engaged.

    Best-effort and deliberately fail-open as an OBSERVATION: an unreadable
    latch is not a claim that work was revoked, so callers treat False as
    "no evidence of revocation" rather than "definitely running".
    """
    try:
        from aios.api.deps import get_emergency_stop

        return bool(getattr(get_emergency_stop().state(), "engaged", False))
    except Exception:  # noqa: BLE001 - unknown latch state is not a claim
        return False


def halt_requires_stop() -> bool:
    """True when in-flight work MUST stop. Fails CLOSED, unlike the observation.

    THE SPLIT THIS FUNCTION EXISTS TO MAKE. `latch_is_engaged` is an
    observation and fails OPEN on purpose: an unreadable latch is not evidence
    that work was revoked, and recording a revocation that never happened would
    put a false row in the governance record.

    Deciding whether to STOP is the opposite question, and the same answer is
    wrong for it. `generate_pipeline` used the observation to make its
    step-boundary halt decision, so an unreadable latch meant "keep working" --
    on the one control that exists to make work stop when the human says stop.
    Nobody has to attack anything for that to matter: a locked SQLite file
    during a checkpoint is enough.

    So: engaged -> stop. Unreadable -> ALSO stop, loudly. The cost of a false
    stop is an aborted turn the operator can retry; the cost of a false
    continue is work proceeding after a human said halt. Those are not
    comparable, and this follows the precedent
    `EmergencyStopHardWiringAuthority.assert_operational` already sets, which
    refuses rather than proceeding when the stop dependency cannot be checked.
    """
    try:
        from aios.api.deps import get_emergency_stop

        return bool(getattr(get_emergency_stop().state(), "engaged", False))
    except Exception:  # noqa: BLE001 - unreadable stop control means STOP
        _LOGGER.warning(
            "emergency-stop state unreadable; halting in-flight work rather "
            "than assuming it may continue",
            exc_info=True,
        )
        return True


def record_turn_incomplete_if_revoked(
    bus: Any = None,
    *,
    session_id: str,
    turn_id: str,
    reason: str = "emergency stop engaged while this turn was in flight",
) -> bool:
    """Record that a turn's work was left incomplete by a revocation.

    ONE DERIVATION, TWO CALLERS. `generate_pipeline` records this when it
    stops itself at a step boundary, and `TurnCoordinator` records it from the
    `finally` that fires when a turn dies without reaching a terminal frame.
    Both must emit the SAME row or a governance audit would see two different
    shapes for one fact -- and organ 55's M4 reads exactly this row to answer
    "what became of the work?".

    Returns True when a row was written, so a caller can avoid duplicating it.
    Never raises: an observation must not change whether work stops.
    """
    if not latch_is_engaged():
        return False
    # Idempotent per turn. Both the pipeline (when it stops itself at a step
    # boundary) and the coordinator's `finally` may reach here for the same
    # turn, and a governance audit must see one row per interrupted turn, not
    # two contradictory ones.
    key = str(turn_id)
    # Check and claim ATOMICALLY -- see _RECORDED_TURNS_LOCK.
    if key:
        with _RECORDED_TURNS_LOCK:
            if key in _RECORDED_TURNS:
                return False
            _RECORDED_TURNS.append(key)
            if len(_RECORDED_TURNS) > 512:  # bounded; this is a dedupe cache
                del _RECORDED_TURNS[:256]
    if bus is None:
        try:
            from aios.api.deps import get_cortex_observation_bus

            bus = get_cortex_observation_bus()
        except Exception:  # noqa: BLE001 - no bus means no observation
            return False
    if not bus:
        return False
    try:
        from aios.core.events import (
            CanonicalEvent,
            CanonicalEventType,
            EventPhase,
            TrustLevel,
        )

        bus.append(
            CanonicalEvent(
                event_type=CanonicalEventType.WORKER_WORK_INCOMPLETE.value,
                phase=EventPhase.REFLEX.value,
                status="incomplete",
                trust=TrustLevel.VERIFIED.value,
                source="generate",
                session_id=session_id,
                turn_id=turn_id,
                payload={
                    "disposition": "marked_incomplete",
                    "reason": reason,
                    "scope": "turn",
                },
            )
        )
        return True
    except Exception:  # noqa: BLE001 - observation is best-effort, never fatal
        import logging

        logging.getLogger(__name__).warning(
            "Failed to record turn disposition", exc_info=True
        )
        return False


__all__ = [
    "EmergencyStopController",
    "EmergencyStopError",
    "EmergencyStopHooks",
    "halt_requires_stop",
    "latch_is_engaged",
    "record_turn_incomplete_if_revoked",
]
