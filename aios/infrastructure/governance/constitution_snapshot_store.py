"""SQLite persistence for `ConstitutionSnapshotV1` (organ 45).

Closes the gap `build_constitution_snapshot()`'s own docstring names: "this
function... does not persist a chain across process restarts". Snapshots
are content-addressed (keyed by `snapshot_digest`); a separate "current
pointer" table tracks which snapshot is live per `constitution_id`, so
`rollback_amendment()`'s "revert to the exact predecessor" can move the
pointer back to an already-existing row instead of inserting a duplicate.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from aios.domain.governance.constitution import (
    ConstitutionSnapshotV1,
    snapshot_digest_from_record,
)
from aios.infrastructure.storage.migrations import apply_migrations


class RecordTamperedError(RuntimeError):
    """Raised when a stored record's digest no longer matches its content."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ConstitutionSnapshotStore:
    """Durable, content-addressed history of constitution snapshots, plus
    the current live pointer per `constitution_id`."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            apply_migrations(conn, scope="constitution")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def save(self, snapshot: ConstitutionSnapshotV1) -> None:
        """Record `snapshot` (a no-op if this exact digest is already
        stored) and point `constitution_id`'s current snapshot at it."""
        payload = snapshot.as_dict()
        now = _utc_now()
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO constitution_snapshots (
                    snapshot_digest, constitution_id, version, snapshot_json,
                    recorded_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_digest,
                    snapshot.constitution_id,
                    snapshot.version,
                    json.dumps(payload, sort_keys=True),
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO constitution_current_pointer (
                    constitution_id, snapshot_digest, updated_at
                ) VALUES (?, ?, ?)
                ON CONFLICT(constitution_id) DO UPDATE SET
                    snapshot_digest = excluded.snapshot_digest,
                    updated_at = excluded.updated_at
                """,
                (snapshot.constitution_id, snapshot.snapshot_digest, now),
            )
            conn.commit()

    def get_current(self, constitution_id: str) -> ConstitutionSnapshotV1 | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT s.* FROM constitution_snapshots s
                INNER JOIN constitution_current_pointer p
                    ON p.snapshot_digest = s.snapshot_digest
                WHERE p.constitution_id = ?
                """,
                (constitution_id,),
            ).fetchone()
        if row is None:
            return None
        return _snapshot_from_row(row)

    def get_by_digest(self, snapshot_digest: str) -> ConstitutionSnapshotV1 | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM constitution_snapshots WHERE snapshot_digest = ?",
                (snapshot_digest,),
            ).fetchone()
        if row is None:
            return None
        return _snapshot_from_row(row)

    def get_history(self, constitution_id: str) -> tuple[ConstitutionSnapshotV1, ...]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM constitution_snapshots WHERE constitution_id = ? "
                "ORDER BY version ASC",
                (constitution_id,),
            ).fetchall()
        return tuple(_snapshot_from_row(row) for row in rows)


def _snapshot_from_row(row: sqlite3.Row) -> ConstitutionSnapshotV1:
    payload = json.loads(row["snapshot_json"])
    record = ConstitutionSnapshotV1.model_validate(payload)
    recomputed = snapshot_digest_from_record(record)
    if recomputed != row["snapshot_digest"]:
        raise RecordTamperedError(
            f"stored constitution snapshot digest mismatch for "
            f"{row['constitution_id']!r} version {row['version']}: the row "
            "was altered outside this store"
        )
    return record


__all__ = ["ConstitutionSnapshotStore", "RecordTamperedError"]
