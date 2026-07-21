"""Durable storage for verifier-qualified expert trajectories."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from pydantic import ConfigDict

from aios.domain.learning.contracts import ExpertTrajectory


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class TrajectoryRecord(ExpertTrajectory):
    """A trajectory with durable lifecycle timestamps."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    created_at: str
    updated_at: str


class TrajectoryRepository:
    """Persist qualified trajectories in the shared operational store."""

    def __init__(self, database: Path | str) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS expert_trajectories (
                    trajectory_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL
                )
                """
            )

    def save(self, trajectory: TrajectoryRecord) -> None:
        payload = json.dumps(trajectory.model_dump(mode="json"), sort_keys=True)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO expert_trajectories (trajectory_id, payload_json)
                VALUES (?, ?)
                ON CONFLICT(trajectory_id) DO UPDATE SET
                    payload_json = excluded.payload_json
                """,
                (trajectory.trajectory_id, payload),
            )

    def get(self, trajectory_id: str) -> TrajectoryRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM expert_trajectories WHERE trajectory_id = ?",
                (trajectory_id,),
            ).fetchone()
        if row is None:
            return None
        return TrajectoryRecord.model_validate(json.loads(row[0]))

    def list_trajectories(self) -> tuple[TrajectoryRecord, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM expert_trajectories ORDER BY trajectory_id"
            ).fetchall()
        return tuple(
            TrajectoryRecord.model_validate(json.loads(row[0])) for row in rows
        )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
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


__all__ = ["TrajectoryRecord", "TrajectoryRepository"]
