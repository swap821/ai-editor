"""Durable storage for governed maintenance findings."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from aios.domain.maintenance.contracts import MaintenanceFinding


class MaintenanceFindingRepository:
    """Persist findings by their stable scanner fingerprint.

    The repository owns storage only. Lifecycle transitions remain the
    responsibility of :class:`MaintenanceLifecycleEngine`, so a persisted
    record cannot be closed merely by being written.
    """

    def __init__(self, database: Path | str) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS maintenance_findings (
                    fingerprint TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL
                )
                """
            )

    def save(self, finding: MaintenanceFinding) -> None:
        payload = json.dumps(finding.model_dump(mode="json"), sort_keys=True)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO maintenance_findings (fingerprint, payload_json)
                VALUES (?, ?)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    payload_json = excluded.payload_json
                """,
                (finding.fingerprint, payload),
            )

    def get(self, fingerprint: str) -> MaintenanceFinding | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM maintenance_findings WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
        if row is None:
            return None
        return MaintenanceFinding.model_validate(json.loads(row[0]))

    def list_findings(self) -> tuple[MaintenanceFinding, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM maintenance_findings ORDER BY fingerprint"
            ).fetchall()
        return tuple(
            MaintenanceFinding.model_validate(json.loads(row[0])) for row in rows
        )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()


__all__ = ["MaintenanceFindingRepository"]
