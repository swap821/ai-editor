"""Durable metadata for bounded maintenance scans."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Literal

from pydantic import BaseModel, ConfigDict

from aios.domain.maintenance.scan_contracts import BoundedScanContract


class MaintenanceScan(BaseModel):
    """A scan execution record; it does not claim findings were resolved."""

    model_config = ConfigDict(frozen=True)

    scan_id: str
    scanner_id: str
    scanner_version: str
    target_id: str
    source_digest: str
    contract: BoundedScanContract
    status: Literal["started", "completed", "failed", "incomplete"]
    started_at: str
    completed_at: str | None = None
    finding_count: int = 0
    failure_reason: str | None = None
    rescan_of: str | None = None


class MaintenanceScanRepository:
    """Persist bounded scan metadata in the operational state database."""

    def __init__(self, database: Path | str) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS maintenance_scans (
                    scan_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL
                )
                """
            )

    def save(self, scan: MaintenanceScan) -> None:
        payload = json.dumps(scan.model_dump(mode="json"), sort_keys=True)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO maintenance_scans (scan_id, payload_json)
                VALUES (?, ?)
                ON CONFLICT(scan_id) DO UPDATE SET
                    payload_json = excluded.payload_json
                """,
                (scan.scan_id, payload),
            )

    def get(self, scan_id: str) -> MaintenanceScan | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM maintenance_scans WHERE scan_id = ?",
                (scan_id,),
            ).fetchone()
        if row is None:
            return None
        return MaintenanceScan.model_validate(json.loads(row[0]))

    def list_scans(self) -> tuple[MaintenanceScan, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM maintenance_scans ORDER BY scan_id"
            ).fetchall()
        return tuple(MaintenanceScan.model_validate(json.loads(row[0])) for row in rows)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()


__all__ = ["MaintenanceScan", "MaintenanceScanRepository"]
