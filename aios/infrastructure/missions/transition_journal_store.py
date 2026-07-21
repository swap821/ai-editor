"""Durable, idempotent mission transition journal store (Slice 35)."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from aios.domain.missions.transition_journal import (
    MISSION_TRANSITION_ESCAPES,
    MISSION_TRANSITION_ORDER,
    MISSION_TRANSITION_TERMINAL,
    MissionTransitionEntry,
)
from aios.infrastructure.storage.migrations import apply_migrations


class MissionTransitionError(RuntimeError):
    """Raised when an out-of-order or post-terminal transition is attempted."""


class MissionTransitionJournal:
    """Append-only, idempotent journal: re-appending a mission's current
    transition is a no-op; any other out-of-order transition is refused."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            apply_migrations(conn, scope="missions")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def append(self, mission_id: str, transition: str) -> MissionTransitionEntry:
        with closing(self._connect()) as conn:
            current_row = conn.execute(
                "SELECT transition, sequence FROM mission_execution_transitions "
                "WHERE mission_id = ? ORDER BY sequence DESC LIMIT 1",
                (mission_id,),
            ).fetchone()
            current = current_row["transition"] if current_row else None

            if current == transition:
                # Idempotent no-op: the exact same transition was already
                # recorded -- a retried recovery step must be safe to run
                # twice, so return the existing entry unchanged.
                return MissionTransitionEntry(
                    mission_id=mission_id,
                    transition=transition,
                    sequence=current_row["sequence"],
                )

            self._validate_next(current, transition)
            next_sequence = (current_row["sequence"] + 1) if current_row else 0
            entry = MissionTransitionEntry(
                mission_id=mission_id, transition=transition, sequence=next_sequence
            )
            conn.execute(
                "INSERT INTO mission_execution_transitions "
                "(mission_id, transition, sequence, recorded_at) "
                "VALUES (?, ?, ?, ?)",
                (mission_id, transition, next_sequence, entry.recorded_at),
            )
            conn.commit()
            return entry

    @staticmethod
    def _validate_next(current: str | None, transition: str) -> None:
        if current is None:
            if transition != MISSION_TRANSITION_ORDER[0]:
                raise MissionTransitionError(
                    f"first transition for a mission must be "
                    f"{MISSION_TRANSITION_ORDER[0]!r}, got {transition!r}"
                )
            return
        if current in MISSION_TRANSITION_TERMINAL:
            raise MissionTransitionError(
                f"mission is already in terminal state {current!r}; "
                f"cannot transition to {transition!r}"
            )
        if transition in MISSION_TRANSITION_ESCAPES:
            return
        current_index = MISSION_TRANSITION_ORDER.index(current)
        expected_next = MISSION_TRANSITION_ORDER[current_index + 1]
        if transition != expected_next:
            raise MissionTransitionError(
                f"out-of-order transition: mission is at {current!r}, "
                f"expected {expected_next!r} or an escape "
                f"{MISSION_TRANSITION_ESCAPES}, got {transition!r}"
            )

    def current_state(self, mission_id: str) -> str | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT transition FROM mission_execution_transitions "
                "WHERE mission_id = ? ORDER BY sequence DESC LIMIT 1",
                (mission_id,),
            ).fetchone()
        return row["transition"] if row else None

    def history(self, mission_id: str) -> tuple[MissionTransitionEntry, ...]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT mission_id, transition, sequence, recorded_at "
                "FROM mission_execution_transitions WHERE mission_id = ? ORDER BY sequence",
                (mission_id,),
            ).fetchall()
        return tuple(
            MissionTransitionEntry(
                mission_id=row["mission_id"],
                transition=row["transition"],
                sequence=row["sequence"],
                recorded_at=row["recorded_at"],
            )
            for row in rows
        )

    def is_terminal(self, mission_id: str) -> bool:
        state = self.current_state(mission_id)
        return state is not None and state in MISSION_TRANSITION_TERMINAL

    def resume_pending(self) -> tuple[str, ...]:
        """Mission ids whose latest recorded transition is not terminal --
        exactly the set a restart must resume or explicitly fail closed,
        rather than silently forgetting."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT mission_id, transition FROM mission_execution_transitions t1
                WHERE sequence = (
                    SELECT MAX(sequence) FROM mission_execution_transitions t2
                    WHERE t2.mission_id = t1.mission_id
                )
                """
            ).fetchall()
        return tuple(
            row["mission_id"]
            for row in rows
            if row["transition"] not in MISSION_TRANSITION_TERMINAL
        )


__all__ = ["MissionTransitionError", "MissionTransitionJournal"]
