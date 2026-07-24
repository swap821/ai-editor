"""SQLite persistence for `RepresentativeContextV1` (organ 31).

`compile_representative_context()` (Slice 29) already computes a real,
canonical `context_digest` at construction time -- this store reuses that
digest for tamper detection at read time rather than recomputing a second
one, matching `DeliberationStore`'s own established convention instead of
inventing a new persistence shape. One row per `request_id`; a second save
for the same `request_id` is rejected rather than silently overwritten,
since a `RepresentativeContextV1` is defined as the complete, immutable
context for exactly one request -- there is no legitimate reason to save
the same request_id twice with different content.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from aios.application.intelligence.context_compiler import context_digest_from_record
from aios.domain.intelligence.representative_context import RepresentativeContextV1
from aios.infrastructure.storage.migrations import apply_migrations


class RecordTamperedError(RuntimeError):
    """Raised when a stored record's digest no longer matches its content."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class RepresentativeContextStore:
    """Durable, append-only history of compiled representative contexts."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            apply_migrations(conn, scope="intelligence")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def save(self, context: RepresentativeContextV1) -> None:
        payload = context.as_dict()
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO representative_contexts (
                    request_id, operator_identity_digest, constitution_digest,
                    privacy_classification, context_json, context_digest,
                    recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    context.request_id,
                    context.operator_identity_digest,
                    context.constitution_digest,
                    context.privacy_classification,
                    json.dumps(payload, sort_keys=True),
                    context.context_digest,
                    _utc_now(),
                ),
            )
            conn.commit()

    def get(self, request_id: str) -> RepresentativeContextV1 | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM representative_contexts WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        if row is None:
            return None
        return _context_from_row(row)

    def list_recent(self, limit: int = 20) -> tuple[RepresentativeContextV1, ...]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM representative_contexts "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return tuple(_context_from_row(row) for row in rows)


def _context_from_row(row: sqlite3.Row) -> RepresentativeContextV1:
    payload = json.loads(row["context_json"])
    record = RepresentativeContextV1.model_validate(payload)
    recomputed = context_digest_from_record(record)
    if recomputed != row["context_digest"]:
        raise RecordTamperedError(
            f"stored representative context digest mismatch for "
            f"{row['request_id']!r}: the row was altered outside this store"
        )
    return record


__all__ = ["RepresentativeContextStore", "RecordTamperedError"]
