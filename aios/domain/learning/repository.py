"""Durable storage for authority-controlled institutional skills."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from aios.domain.learning.skill_contracts import SkillContract


class SkillRecord(SkillContract):
    """A skill contract with durable lifecycle timestamps."""

    created_at: str
    updated_at: str


class SkillRepository:
    """Persist skill contracts by immutable skill id and version."""

    def __init__(self, database: Path | str) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS institutional_skills (
                    skill_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (skill_id, version)
                )
                """
            )

    def save(self, skill: SkillRecord) -> None:
        payload = json.dumps(skill.model_dump(mode="json"), sort_keys=True)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO institutional_skills (skill_id, version, payload_json)
                VALUES (?, ?, ?)
                ON CONFLICT(skill_id, version) DO UPDATE SET
                    payload_json = excluded.payload_json
                """,
                (skill.skill_id, skill.version, payload),
            )

    def get(self, skill_id: str, version: int) -> SkillRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM institutional_skills
                WHERE skill_id = ? AND version = ?
                """,
                (skill_id, version),
            ).fetchone()
        if row is None:
            return None
        return SkillRecord.model_validate(json.loads(row[0]))

    def list_skills(self) -> tuple[SkillRecord, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM institutional_skills
                ORDER BY skill_id, version
                """
            ).fetchall()
        return tuple(SkillRecord.model_validate(json.loads(row[0])) for row in rows)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()


__all__ = ["SkillRecord", "SkillRepository"]
