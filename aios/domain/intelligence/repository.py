"""Durable records of governed intelligence-hiring decisions."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel, ConfigDict, Field


class HiringRecord(BaseModel):
    """A persisted hiring decision and its provider-call provenance."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    mission_id: str
    purpose: str
    task_class: str
    data_classification: str
    candidate_providers: list[str]
    eligible_providers: list[str]
    selected_provider: str | None
    selected_model: str | None
    reason: str
    redactions: list[str] = Field(default_factory=list)
    cost_class: str
    external_data_scope: str
    human_approval_required: bool
    status: str
    created_at: str
    updated_at: str
    provider_call_provenance: dict[str, Any] = Field(default_factory=dict)


class HiringRecordRepository:
    """Persist hiring records without making provider selection authoritative."""

    def __init__(self, database: Path | str) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS hiring_records (
                    request_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL
                )
                """
            )

    def save(self, record: HiringRecord) -> None:
        payload = json.dumps(record.model_dump(mode="json"), sort_keys=True)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO hiring_records (request_id, payload_json)
                VALUES (?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    payload_json = excluded.payload_json
                """,
                (record.request_id, payload),
            )

    def get(self, request_id: str) -> HiringRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM hiring_records WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        if row is None:
            return None
        return HiringRecord.model_validate(json.loads(row[0]))

    def list_records(self) -> tuple[HiringRecord, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM hiring_records "
                "ORDER BY json_extract(payload_json, '$.created_at'), request_id"
            ).fetchall()
        return tuple(HiringRecord.model_validate(json.loads(row[0])) for row in rows)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()


__all__ = ["HiringRecord", "HiringRecordRepository"]
