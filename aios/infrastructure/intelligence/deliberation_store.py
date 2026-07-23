"""SQLite persistence for `DeliberationRecord` (Slice 34 / organ 39).

`synthesize_deliberation()` already computes a real `deliberation_digest`
(sha256 of the canonical-JSON payload) at construction time -- this store
reuses that digest for tamper detection at read time rather than
recomputing a second one, matching `GovernanceAmendmentStore`'s own
append-only-per-revision convention (Slice 37) instead of inventing a new
persistence shape.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from aios.application.intelligence.deliberation import deliberation_record_digest
from aios.domain.intelligence.deliberation import DeliberationRecord, ModelPosition
from aios.infrastructure.storage.migrations import apply_migrations


class RecordTamperedError(RuntimeError):
    """Raised when a stored record's digest no longer matches its content."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class DeliberationStore:
    """Durable, append-only history for `DeliberationRecord`. Each `save()`
    call adds one new revision row; it never overwrites a prior one."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            apply_migrations(conn, scope="council")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def save(self, record: DeliberationRecord) -> int:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(revision), 0) FROM deliberation_records "
                "WHERE deliberation_id = ?",
                (record.deliberation_id,),
            ).fetchone()
            revision = int(row[0]) + 1
            conn.execute(
                """
                INSERT INTO deliberation_records (
                    deliberation_id, revision, mission_id, trigger_reasons_json,
                    positions_json, disagreements_json,
                    unresolved_minority_concerns_json, final_disposition,
                    created_at, deliberation_digest, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.deliberation_id,
                    revision,
                    record.mission_id,
                    json.dumps(list(record.trigger_reasons)),
                    json.dumps([p.as_dict() for p in record.positions]),
                    json.dumps(list(record.disagreements)),
                    json.dumps(list(record.unresolved_minority_concerns)),
                    record.final_disposition,
                    record.created_at,
                    record.deliberation_digest,
                    _utc_now(),
                ),
            )
            conn.commit()
        return revision

    def get_current(self, deliberation_id: str) -> DeliberationRecord | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM deliberation_records WHERE deliberation_id = ? "
                "ORDER BY revision DESC LIMIT 1",
                (deliberation_id,),
            ).fetchone()
        if row is None:
            return None
        return _record_from_row(row)

    def get_history(self, deliberation_id: str) -> tuple[DeliberationRecord, ...]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM deliberation_records WHERE deliberation_id = ? "
                "ORDER BY revision ASC",
                (deliberation_id,),
            ).fetchall()
        return tuple(_record_from_row(row) for row in rows)

    def for_mission(self, mission_id: str) -> tuple[DeliberationRecord, ...]:
        """Every current (latest-revision) deliberation recorded for a real
        mission, newest first."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT d.* FROM deliberation_records d
                INNER JOIN (
                    SELECT deliberation_id, MAX(revision) AS max_revision
                    FROM deliberation_records WHERE mission_id = ?
                    GROUP BY deliberation_id
                ) latest
                ON d.deliberation_id = latest.deliberation_id
                AND d.revision = latest.max_revision
                ORDER BY d.recorded_at DESC
                """,
                (mission_id,),
            ).fetchall()
        return tuple(_record_from_row(row) for row in rows)


def _record_from_row(row: sqlite3.Row) -> DeliberationRecord:
    trigger_reasons = tuple(json.loads(row["trigger_reasons_json"]))
    positions = tuple(ModelPosition(**p) for p in json.loads(row["positions_json"]))
    disagreements = tuple(json.loads(row["disagreements_json"]))
    unresolved_minority_concerns = tuple(
        json.loads(row["unresolved_minority_concerns_json"])
    )
    final_disposition = row["final_disposition"]
    stored_digest = row["deliberation_digest"]

    recomputed = deliberation_record_digest(
        deliberation_id=row["deliberation_id"],
        mission_id=row["mission_id"],
        trigger_reasons=trigger_reasons,
        positions=positions,
        disagreements=disagreements,
        unresolved_minority_concerns=unresolved_minority_concerns,
        final_disposition=final_disposition,
    )
    if recomputed != stored_digest:
        raise RecordTamperedError(
            f"stored deliberation record digest mismatch for "
            f"{row['deliberation_id']!r}: the row was altered outside this store"
        )

    return DeliberationRecord(
        deliberation_id=row["deliberation_id"],
        mission_id=row["mission_id"],
        trigger_reasons=trigger_reasons,
        positions=positions,
        disagreements=disagreements,
        unresolved_minority_concerns=unresolved_minority_concerns,
        final_disposition=final_disposition,
        created_at=row["created_at"],
        deliberation_digest=stored_digest,
    )


__all__ = ["DeliberationStore", "RecordTamperedError"]
