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
from aios.core.verification_strength import VerificationStrength, meets_promotion_floor
from aios.memory.db import get_connection, init_memory_db
from aios.memory.relevance import relevance
from aios.security.secret_scanner import scan_and_redact


class MistakeMemory:
    """CRUD + lifecycle facade over the ``mistake_pool`` table."""

    def __init__(self, db_path: Path = config.MEMORY_DB_PATH) -> None:
        self.db_path = db_path

    def recurring(self, *, limit: int = 5) -> list[dict]:
        """Return VERIFIED lessons that have recurred (``occurrence_count > 1``).

        The narrative self-model's cautions: a lesson must be BOTH verified AND
        repeated before it is allowed to characterize the system. Most-recurring
        first; a pending/superseded or one-off lesson is excluded (fail-closed).
        """
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT lesson_text, error_type, occurrence_count FROM mistake_pool "
                "WHERE verification_status = 'verified' AND occurrence_count > 1 "
                "ORDER BY occurrence_count DESC, id DESC LIMIT ?",
                (max(int(limit), 1),),
            ).fetchall()
        return [
            {
                "lesson_text": str(row["lesson_text"]),
                "error_type": str(row["error_type"]),
                "occurrence_count": int(row["occurrence_count"]),
            }
            for row in rows
        ]

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
        task_id = scan_and_redact(task_id).scrubbed
        error_type = scan_and_redact(error_type).scrubbed
        root_cause = scan_and_redact(root_cause).scrubbed
        fix_applied = scan_and_redact(fix_applied).scrubbed
        lesson_text = scan_and_redact(lesson_text).scrubbed
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

    def relevant_verified(self, query: str, limit: int = 5) -> list[dict]:
        """Return verified lessons relevant to *query*, regardless of session.

        The score is deterministic lexical overlap. A lesson must already be
        verified before it can influence a different future task.
        """
        if not query or not query.strip() or limit <= 0:
            return []
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM mistake_pool WHERE verification_status = 'verified'"
            ).fetchall()
        ranked: list[dict] = []
        for row in rows:
            document = " ".join(
                str(row[key])
                for key in ("error_type", "root_cause", "fix_applied", "lesson_text")
            )
            score = relevance(query, document)
            if score <= 0:
                continue
            ranked.append(
                {
                    "mistake_id": int(row["id"]),
                    "error_type": str(row["error_type"]),
                    "lesson_text": str(row["lesson_text"]),
                    "confidence_delta": float(row["confidence_delta"]),
                    "occurrence_count": int(row["occurrence_count"]),
                    "verification_status": "verified",
                    "relevance": score,
                }
            )
        ranked.sort(
            key=lambda item: (
                item["relevance"],
                item["occurrence_count"],
                item["mistake_id"],
            ),
            reverse=True,
        )
        return ranked[:limit]

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

    def record_or_increment(
        self,
        task_id: str,
        error_type: str,
        root_cause: str,
        fix_applied: str,
        lesson_text: str,
        confidence_delta: float,
    ) -> tuple[int, bool]:
        """Atomically record a lesson or increment its active recurrence.

        Returns ``(mistake_id, recurrence)``. The immediate transaction prevents
        concurrent reflection workers from inserting duplicate active lessons.
        """
        clamped_delta = max(-1.0, min(0.0, float(confidence_delta)))
        task_id = scan_and_redact(task_id).scrubbed
        error_type = scan_and_redact(error_type).scrubbed
        root_cause = scan_and_redact(root_cause).scrubbed
        fix_applied = scan_and_redact(fix_applied).scrubbed
        lesson_text = scan_and_redact(lesson_text).scrubbed
        with get_connection(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT id FROM mistake_pool "
                "WHERE task_id = ? AND error_type = ? "
                "AND verification_status != 'superseded' "
                "ORDER BY timestamp DESC LIMIT 1",
                (task_id, error_type),
            ).fetchone()
            if existing is not None:
                mistake_id = int(existing["id"])
                conn.execute(
                    "UPDATE mistake_pool SET occurrence_count = occurrence_count + 1 "
                    "WHERE id = ?",
                    (mistake_id,),
                )
                return mistake_id, True
            cur = conn.execute(
                "INSERT INTO mistake_pool "
                "(task_id, error_type, root_cause, fix_applied, lesson_text, confidence_delta) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (task_id, error_type, root_cause, fix_applied, lesson_text, clamped_delta),
            )
            return int(cur.lastrowid), False

    def increment_occurrence(self, mistake_id: int) -> None:
        """Bump the occurrence counter for a repeated mistake."""
        with get_connection(self.db_path) as conn:
            conn.execute(
                "UPDATE mistake_pool SET occurrence_count = occurrence_count + 1 "
                "WHERE id = ?",
                (mistake_id,),
            )

    def promote(
        self,
        mistake_id: int,
        *,
        strength: VerificationStrength = VerificationStrength.STRONG,
    ) -> None:
        """Promote a lesson from ``pending`` to ``verified``.

        Below-floor evidence leaves the lesson pending. Verified mistake lessons
        feed planner confidence, so a weak green must not graduate into that
        cross-task calibration path.
        """
        if not meets_promotion_floor(strength):
            return
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
