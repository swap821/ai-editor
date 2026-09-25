"""Durable storage for authority-controlled institutional skills."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Mapping

from aios.domain.learning.skill_contracts import (
    BIRTH_STATE,
    WITHDRAWAL_STATES,
    SkillContract,
    SkillState,
    check_transition,
)
from aios.memory.learning_freeze import assert_learning_permitted


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class SkillRecord(SkillContract):
    """A skill contract with durable lifecycle timestamps."""

    created_at: str
    updated_at: str
    #: Where the record came from, e.g. ``{"source": "migrated", ...}``.
    #: Unsigned and advisory -- nothing decides on it; signed provenance is
    #: plan Phase 3. It exists so a record can say where it came from without
    #: borrowing ``source_trajectory_ids``, whose ids reuse lineage resolves.
    provenance: Mapping[str, str] = {}


class SkillRepository:
    """Persist skill contracts by immutable skill id and version.

    The lifecycle is enforced at the store, not by its callers: ``save`` writes
    a skill's evidence and never its state, and ``transition_state`` is the one
    way a state changes. Before Phase 2, ``save`` wrote whatever state it was
    handed, so the transition graph bound only the callers that chose to use
    it. Every write also asks the emergency stop first (``learning_freeze``),
    except a transition that withdraws a skill from use.
    """

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
        """Write a skill's evidence: born ``candidate``, state never changed here."""
        assert_learning_permitted("institutional_skills.save")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._read(connection, skill.skill_id, skill.version)
            expected = BIRTH_STATE if current is None else current.state
            if skill.state != expected:
                was = "a new skill" if current is None else f"state {expected!r}"
                raise ValueError(
                    f"save cannot set skill {skill.skill_id!r} v{skill.version} "
                    f"to {skill.state!r} from {was}: a skill is born "
                    f"{BIRTH_STATE!r} and changes state only through "
                    "transition_state"
                )
            self._write(connection, skill)

    def get(self, skill_id: str, version: int) -> SkillRecord | None:
        with self._connection() as connection:
            return self._read(connection, skill_id, version)

    def list_skills(self) -> tuple[SkillRecord, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM institutional_skills
                ORDER BY skill_id, version
                """
            ).fetchall()
        return tuple(SkillRecord.model_validate(json.loads(row[0])) for row in rows)

    def transition_state(
        self,
        skill_id: str,
        version: int,
        state: SkillState,
    ) -> SkillRecord:
        """Persist one lifecycle transition the policy allows.

        Read, check and write happen in one transaction, so two concurrent
        transitions cannot both start from the same state.
        """
        if state not in WITHDRAWAL_STATES:
            assert_learning_permitted(f"institutional_skills.transition -> {state}")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._read(connection, skill_id, version)
            if current is None:
                raise KeyError(f"skill {skill_id!r} version {version} not found")
            check_transition(current.state, state)
            updated = current.model_copy(
                update={"state": state, "updated_at": _utc_now()}
            )
            self._write(connection, updated)
        return updated

    @staticmethod
    def _read(
        connection: sqlite3.Connection, skill_id: str, version: int
    ) -> SkillRecord | None:
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

    @staticmethod
    def _write(connection: sqlite3.Connection, skill: SkillRecord) -> None:
        payload = json.dumps(skill.model_dump(mode="json"), sort_keys=True)
        connection.execute(
            """
            INSERT INTO institutional_skills (skill_id, version, payload_json)
            VALUES (?, ?, ?)
            ON CONFLICT(skill_id, version) DO UPDATE SET
                payload_json = excluded.payload_json
            """,
            (skill.skill_id, skill.version, payload),
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


__all__ = ["SkillRecord", "SkillRepository"]
