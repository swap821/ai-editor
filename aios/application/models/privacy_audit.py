"""PrivacyAuditTracker: durable record of PrivacyFilter audits (organ 50).

Organ 50's second half: "what was sent / what was removed" for recent cloud
calls. ``PrivacyFilter.filter()`` already computes a real per-call audit dict;
the five real call sites (`FailoverChatClient` + four direct cloud clients)
record it here.

Phase 3 (condition 3): audits survive process restart via SQLite when a
``database_path`` is supplied. Process-local-only mode remains available for
unit tests that deliberately exercise the ring buffer without a disk.

Phase 3 (condition 4): each durable row carries a content digest; a silently
edited row fails verification rather than being trusted.

Phase 3 (condition 5): durable-status and verify helpers report ``unavailable``
/ raise on corruption — never invent a reassuring empty history.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections import deque
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PrivacyAuditRecord:
    """One real `PrivacyFilter.filter()` call's outcome."""

    provider: str
    audit: dict[str, Any] = field(default_factory=dict)
    recorded_at: str = field(default_factory=_utc_now)
    record_digest: str | None = None


class PrivacyAuditTamperedError(RuntimeError):
    """Raised when a durable privacy-audit row no longer matches its digest."""


class PrivacyAuditUnavailableError(RuntimeError):
    """Raised when durable privacy-audit storage cannot be read honestly."""


class PrivacyAuditTracker:
    """Bounded privacy-audit history.

    With ``database_path``: SQLite-backed, restart-durable, digest-verified.
    Without: process-local deque (test / diagnostic fallback only).
    """

    def __init__(
        self,
        *,
        max_records: int = 50,
        database_path: Path | str | None = None,
    ) -> None:
        self._max_records = max(1, int(max_records))
        self._records: deque[PrivacyAuditRecord] = deque(maxlen=self._max_records)
        self._db_path = Path(database_path) if database_path is not None else None
        self._lock = threading.Lock()
        self._db_error: str | None = None
        if self._db_path is not None:
            try:
                self._init_db()
                self._hydrate_from_db()
            except Exception as exc:  # noqa: BLE001 - never block callers
                self._db_error = str(exc)

    def _connect(self) -> sqlite3.Connection:
        assert self._db_path is not None
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS privacy_audits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    audit_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    record_digest TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_privacy_audits_recorded_at "
                "ON privacy_audits(recorded_at DESC)"
            )
            conn.commit()

    def _row_digest(
        self, *, provider: str, audit: dict[str, Any], recorded_at: str
    ) -> str:
        return _digest(
            {
                "provider": provider,
                "audit": audit,
                "recorded_at": recorded_at,
            }
        )

    def _hydrate_from_db(self) -> None:
        rows = self._load_verified_rows(limit=self._max_records)
        self._records.clear()
        for record in rows:
            self._records.append(record)

    def _load_verified_rows(self, *, limit: int) -> list[PrivacyAuditRecord]:
        assert self._db_path is not None
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT provider, audit_json, recorded_at, record_digest
                FROM privacy_audits
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(int(limit), 0),),
            ).fetchall()
        records: list[PrivacyAuditRecord] = []
        for row in rows:
            audit = json.loads(row["audit_json"])
            expected = self._row_digest(
                provider=row["provider"],
                audit=audit,
                recorded_at=row["recorded_at"],
            )
            if expected != row["record_digest"]:
                raise PrivacyAuditTamperedError(
                    f"privacy audit row digest mismatch for provider="
                    f"{row['provider']!r}: stored={row['record_digest']!r} "
                    f"expected={expected!r}"
                )
            records.append(
                PrivacyAuditRecord(
                    provider=row["provider"],
                    audit=audit,
                    recorded_at=row["recorded_at"],
                    record_digest=row["record_digest"],
                )
            )
        return records

    def is_projection_available(self) -> bool:
        """Whether recent audits can be read honestly from durable storage."""
        if self._db_path is None:
            return True
        return self._db_error is None

    def record(self, provider: str, audit: dict[str, Any]) -> None:
        """Append one real audit. Never raises — a write failure is reported
        via ``durable_status()`` rather than crashing a cloud turn."""
        payload = dict(audit or {})
        recorded_at = _utc_now()
        digest = self._row_digest(
            provider=str(provider), audit=payload, recorded_at=recorded_at
        )
        record = PrivacyAuditRecord(
            provider=str(provider),
            audit=payload,
            recorded_at=recorded_at,
            record_digest=digest,
        )
        with self._lock:
            self._records.appendleft(record)
            if self._db_path is None:
                return
            try:
                with closing(self._connect()) as conn:
                    conn.execute(
                        """
                        INSERT INTO privacy_audits (
                            provider, audit_json, recorded_at, record_digest
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (
                            record.provider,
                            json.dumps(record.audit, sort_keys=True),
                            record.recorded_at,
                            record.record_digest,
                        ),
                    )
                    # Bound on-disk history to the same cap as the ring buffer.
                    conn.execute(
                        """
                        DELETE FROM privacy_audits
                        WHERE id NOT IN (
                            SELECT id FROM privacy_audits
                            ORDER BY id DESC
                            LIMIT ?
                        )
                        """,
                        (self._max_records,),
                    )
                    conn.commit()
                self._db_error = None
            except Exception as exc:  # noqa: BLE001 - observability must not crash turns
                self._db_error = str(exc)

    def recent(self, *, limit: int = 10) -> list[PrivacyAuditRecord]:
        """The most recent audits, newest first."""
        cap = max(int(limit), 0)
        with self._lock:
            if self._db_path is None:
                return list(self._records)[:cap]
            try:
                records = self._load_verified_rows(limit=cap)
                self._db_error = None
                return records
            except PrivacyAuditTamperedError:
                raise
            except Exception as exc:  # noqa: BLE001
                self._db_error = str(exc)
                raise PrivacyAuditUnavailableError(str(exc)) from exc

    def durable_status(self) -> dict[str, Any]:
        """Condition 3 / 5: whether privacy audits currently survive a restart."""
        if self._db_path is None:
            return {
                "durable": False,
                "reason": "no database_path configured (process-local only)",
            }
        if self._db_error is not None:
            return {
                "durable": False,
                "path": str(self._db_path),
                "status": "unavailable",
                "error": self._db_error,
            }
        try:
            exists = self._db_path.exists()
            size = self._db_path.stat().st_size if exists else 0
        except OSError as exc:
            return {
                "durable": False,
                "path": str(self._db_path),
                "status": "unavailable",
                "error": str(exc),
            }
        return {
            "durable": True,
            "path": str(self._db_path),
            "status": "available",
            "bytes": size,
            "max_records": self._max_records,
        }

    def verify_durable_chain(self) -> dict[str, Any]:
        """Condition 4: re-read every durable row and recompute digests."""
        if self._db_path is None:
            return {
                "status": "unavailable",
                "reason": "no database_path configured",
                "verified": 0,
            }
        try:
            rows = self._load_verified_rows(limit=self._max_records)
        except PrivacyAuditTamperedError as exc:
            return {"status": "tampered", "error": str(exc), "verified": 0}
        except Exception as exc:  # noqa: BLE001
            return {"status": "unavailable", "error": str(exc), "verified": 0}
        return {"status": "verified", "verified": len(rows)}


__all__ = [
    "PrivacyAuditRecord",
    "PrivacyAuditTamperedError",
    "PrivacyAuditTracker",
    "PrivacyAuditUnavailableError",
]
