"""Durable idempotency store for authority-derived reuse outcomes."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from aios.domain.learning.contracts import ReuseOutcomeReference


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ReuseOutcomeRepository:
    """Append-only SQLite store for reuse outcome idempotency."""

    def __init__(self, db_path: Path | str) -> None:
        self.database = Path(db_path)
        self._memory_connection: sqlite3.Connection | None = None
        if str(db_path) == ":memory:":
            self.database = Path(":memory:")
            self._memory_connection = sqlite3.connect(":memory:", timeout=5.0)
            self._memory_connection.row_factory = sqlite3.Row
        else:
            self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reuse_outcomes (
                    reuse_outcome_id TEXT PRIMARY KEY,
                    lineage_key TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                )
                """
            )

    def record(self, reference: ReuseOutcomeReference) -> bool:
        payload = json.dumps(reference.model_dump(mode="json"), sort_keys=True)
        lineage_key = self.lineage_key(reference)
        try:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO reuse_outcomes (
                        reuse_outcome_id, lineage_key, payload_json, recorded_at
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        reference.reuse_outcome_id,
                        lineage_key,
                        payload,
                        _utc_now(),
                    ),
                )
        except sqlite3.IntegrityError:
            return False
        return True

    def was_recorded(self, reference: ReuseOutcomeReference) -> bool:
        lineage_key = self.lineage_key(reference)
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM reuse_outcomes
                WHERE reuse_outcome_id = ? OR lineage_key = ?
                LIMIT 1
                """,
                (reference.reuse_outcome_id, lineage_key),
            ).fetchone()
        return row is not None

    @staticmethod
    def lineage_key(reference: ReuseOutcomeReference) -> str:
        payload = json.dumps(
            reference.model_dump(mode="json", exclude={"reuse_outcome_id"}),
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        if self._memory_connection is not None:
            try:
                yield self._memory_connection
                self._memory_connection.commit()
            except Exception:
                self._memory_connection.rollback()
                raise
            return
        connection = sqlite3.connect(self.database, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


__all__ = ["ReuseOutcomeRepository"]
