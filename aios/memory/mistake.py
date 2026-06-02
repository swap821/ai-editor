"""L4 Mistake pool: structured, queryable post-mortems for self-correction.

This is the layer that makes the agent *learn*, not just log. Each record
captures the causal story of a failure — ``error_type``, ``root_cause``,
``fix_applied``, ``lesson_text`` — plus a bounded ``confidence_delta`` used to
recalibrate the Planner on similar future tasks. Lessons start ``pending`` and
are promoted to ``verified`` only after a fix proves itself, or marked
``superseded`` when a better lesson replaces them.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from aios import config
from aios.memory.db import get_connection


class MistakeMemory:
    """CRUD + lifecycle facade over the ``mistake_pool`` table."""

    def __init__(self, db_path: Path = config.MEMORY_DB_PATH) -> None:
        self.db_path = db_path

    def record(
        self,
        task_id: str,
        error_type: str,
        root_cause: str,
        fix_applied: str,
        lesson_text: str,
        confidence_delta: float,
    ) -> int:
        """Insert a new post-mortem and return its id.

        ``confidence_delta`` is clamped to ``[-1.0, 0.0]`` so a lesson can only
        *reduce* confidence, never inflate it — an unverified lesson must never
        make the Planner more sure of itself.
        """
        clamped_delta = max(-1.0, min(0.0, float(confidence_delta)))
        with get_connection(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO mistake_pool "
                "(task_id, error_type, root_cause, fix_applied, lesson_text, "
                " confidence_delta) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    task_id,
                    error_type,
                    root_cause,
                    fix_applied,
                    lesson_text,
                    clamped_delta,
                ),
            )
            return int(cur.lastrowid)

    def get(self, mistake_id: int) -> Optional[sqlite3.Row]:
        """Return the row for *mistake_id*, or ``None`` if absent."""
        with get_connection(self.db_path) as conn:
            return conn.execute(
                "SELECT * FROM mistake_pool WHERE id = ?", (mistake_id,)
            ).fetchone()

    def find_by_type(
        self, error_type: str, *, verified_only: bool = False, limit: int = 10
    ) -> list[sqlite3.Row]:
        """Return recent lessons matching *error_type*, newest first."""
        sql = "SELECT * FROM mistake_pool WHERE error_type = ?"
        params: list[object] = [error_type]
        if verified_only:
            sql += " AND verification_status = 'verified'"
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        with get_connection(self.db_path) as conn:
            return conn.execute(sql, params).fetchall()

    def pending_for_task(self, task_id: str, limit: int = 5) -> list[sqlite3.Row]:
        """Return this task's still-``pending`` lessons, newest first.

        Used to carry a session's unverified lessons forward into later turns so
        the agent reasons with them (and can prove them) across the session.
        """
        with get_connection(self.db_path) as conn:
            return conn.execute(
                "SELECT * FROM mistake_pool "
                "WHERE task_id = ? AND verification_status = 'pending' "
                "ORDER BY timestamp DESC, id DESC LIMIT ?",
                (task_id, limit),
            ).fetchall()

    def find_recurrence(self, task_id: str, error_type: str) -> Optional[sqlite3.Row]:
        """Return an existing non-superseded lesson for the same task+error.

        Used to detect repeated failures so :meth:`increment_occurrence` can be
        called instead of inserting a duplicate.
        """
        with get_connection(self.db_path) as conn:
            return conn.execute(
                "SELECT * FROM mistake_pool "
                "WHERE task_id = ? AND error_type = ? "
                "AND verification_status != 'superseded' "
                "ORDER BY timestamp DESC LIMIT 1",
                (task_id, error_type),
            ).fetchone()

    def increment_occurrence(self, mistake_id: int) -> None:
        """Bump the occurrence counter for a repeated mistake."""
        with get_connection(self.db_path) as conn:
            conn.execute(
                "UPDATE mistake_pool SET occurrence_count = occurrence_count + 1 "
                "WHERE id = ?",
                (mistake_id,),
            )

    def promote(self, mistake_id: int) -> None:
        """Promote a lesson from ``pending`` to ``verified``."""
        with get_connection(self.db_path) as conn:
            conn.execute(
                "UPDATE mistake_pool SET verification_status = 'verified' "
                "WHERE id = ? AND verification_status = 'pending'",
                (mistake_id,),
            )

    def supersede(self, old_id: int, new_id: int) -> None:
        """Mark *old_id* as superseded by *new_id*."""
        with get_connection(self.db_path) as conn:
            conn.execute(
                "UPDATE mistake_pool "
                "SET verification_status = 'superseded', superseded_by = ? "
                "WHERE id = ?",
                (new_id, old_id),
            )

    def count(self) -> int:
        """Return the total number of recorded mistakes."""
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM mistake_pool"
            ).fetchone()
        return int(row["n"])
