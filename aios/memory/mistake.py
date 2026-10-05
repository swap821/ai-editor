"""L4 Mistake pool: structured, queryable post-mortems for self-correction.

This is the layer that makes the agent *learn*, not just log. Each record
captures the causal story of a failure — ``error_type``, ``root_cause``,
``fix_applied``, ``lesson_text`` — plus a bounded ``confidence_delta`` used to
recalibrate the Planner on similar future tasks. Lessons start ``pending`` and
are promoted to ``verified`` only after a fix proves itself, or marked
``superseded`` when a better lesson replaces them.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

from aios.memory.learning_freeze import assert_learning_permitted
from aios import config
from aios.core.verification_strength import (
    VerificationStrength,
    meets_learning_floor,
)
from aios.memory.db import get_connection, init_memory_db
from aios.memory.relevance import relevance
from aios.security.secret_scanner import scan_and_redact
from aios.memory.construction_ledger import record_construction

if TYPE_CHECKING:
    from aios.memory.facts import SemanticFacts

logger = logging.getLogger(__name__)


#: The row a recurrence increments: one derivation for the write and for the
#: read that captures the state it extends (``recurrence_candidate``).
#: The same task, error AND principal (plan Phase 4c): one principal's
#: recurrence never increments another's lesson. NULL-safe (``IS``).
_RECURRENCE_MATCH = (
    "SELECT id FROM mistake_pool "
    "WHERE task_id = ? AND error_type = ? "
    "AND verification_status != 'superseded' "
    "AND principal_id IS ? "
    "ORDER BY timestamp DESC LIMIT 1"
)


class MistakeMemory:
    """CRUD + lifecycle facade over the ``mistake_pool`` table."""

    def __init__(
        self,
        db_path: Path = config.MEMORY_DB_PATH,
        *,
        facts: Optional["SemanticFacts"] = None,
    ) -> None:
        record_construction("MistakeMemory")
        self.db_path = db_path
        self._facts = facts

    def recurring(
        self, *, limit: int = 5, principal_id: Optional[str] = None
    ) -> list[dict]:
        """Return VERIFIED lessons that have recurred (``occurrence_count > 1``).

        The narrative self-model's cautions: a lesson must be BOTH verified AND
        repeated before it is allowed to characterize the system. Most-recurring
        first; a pending/superseded or one-off lesson is excluded (fail-closed).
        """
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, lesson_text, error_type, occurrence_count FROM mistake_pool "
                "WHERE verification_status = 'verified' AND occurrence_count > 1 "
                "AND principal_id IS ? "
                "ORDER BY occurrence_count DESC, id DESC LIMIT ?",
                (principal_id, max(int(limit), 1)),
            ).fetchall()
        return [
            {
                # The id lets a reader verify the row's provenance (Phase 3c).
                "mistake_id": int(row["id"]),
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
        principal_id: Optional[str] = None,
    ) -> int:
        """Insert a new post-mortem and return its id.

        ``confidence_delta`` is clamped to ``[-1.0, 0.0]`` so a lesson can only
        *reduce* confidence, never inflate it — an unverified lesson must never
        make the Planner more sure of itself.
        """
        assert_learning_permitted("lessons.record")
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
                " confidence_delta, principal_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    task_id,
                    error_type,
                    root_cause,
                    fix_applied,
                    lesson_text,
                    clamped_delta,
                    principal_id,
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

    def relevant_verified(
        self, query: str, limit: int = 5, principal_id: Optional[str] = None
    ) -> list[dict]:
        """Return verified lessons relevant to *query*, regardless of session.

        The score is deterministic lexical overlap. A lesson must already be
        verified before it can influence a different future task.
        """
        if not query or not query.strip() or limit <= 0:
            return []
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM mistake_pool WHERE verification_status = 'verified' "
                "AND principal_id IS ?",
                (principal_id,),
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

    def pending_for_task(
        self, task_id: str, limit: int = 5, principal_id: Optional[str] = None
    ) -> list[sqlite3.Row]:
        """Return this task's still-``pending`` lessons, newest first.

        Used to carry a session's unverified lessons forward into later turns so
        the agent reasons with them (and can prove them) across the session.
        """
        with get_connection(self.db_path) as conn:
            return conn.execute(
                # A lesson with no `failed_command` can NEVER be confirmed: the
                # promotion path matches a later success against that exact
                # command, so an empty one has nothing to match. Recalling it
                # spends the limited recall budget on something structurally
                # incapable of graduating, and crowds out lessons that can.
                #
                # This is not hypothetical. Every one of the 87 lessons in the
                # live pool has an empty `failed_command` -- the column landed
                # in the same change that started populating it, so everything
                # written before that day is permanently unpromotable. Reading
                # "0 verified lessons" as a broken promotion path is the wrong
                # conclusion; the path works and had nothing to work on.
                "SELECT * FROM mistake_pool "
                "WHERE task_id = ? AND verification_status = 'pending' "
                "  AND failed_command IS NOT NULL AND TRIM(failed_command) != '' "
                "  AND principal_id IS ? "
                "ORDER BY timestamp DESC, id DESC LIMIT ?",
                (task_id, principal_id, limit),
            ).fetchall()

    def find_recurrence(
        self, task_id: str, error_type: str, principal_id: Optional[str] = None
    ) -> Optional[sqlite3.Row]:
        """Return an existing non-superseded lesson for the same task+error.

        Used to detect repeated failures so :meth:`increment_occurrence` can be
        called instead of inserting a duplicate.
        """
        with get_connection(self.db_path) as conn:
            return conn.execute(
                "SELECT * FROM mistake_pool "
                "WHERE task_id = ? AND error_type = ? "
                "AND verification_status != 'superseded' "
                "AND principal_id IS ? "
                "ORDER BY timestamp DESC LIMIT 1",
                (task_id, error_type, principal_id),
            ).fetchone()

    def record_or_increment(
        self,
        task_id: str,
        error_type: str,
        root_cause: str,
        fix_applied: str,
        lesson_text: str,
        confidence_delta: float,
        failed_command: str = "",
        principal_id: Optional[str] = None,
    ) -> tuple[int, bool]:
        """Atomically record a lesson or increment its active recurrence.

        Returns ``(mistake_id, recurrence)``. The immediate transaction prevents
        concurrent reflection workers from inserting duplicate active lessons.

        *failed_command* is the exact command whose failure produced the lesson,
        stored so a later turn can rebuild the fail->confirm tracker. It is
        scrubbed like every other stored field (a failing command can embed a
        credential, e.g. ``curl -H "Authorization: Bearer ..."``, and this row is
        the same secrets-at-rest surface as the rest of the pool — the audit
        ledger itself redacts, so this must too). Scrubbing is a no-op for the
        ordinary secret-free verify command (``pytest ... -q``), so the exact
        byte-match against the live command still holds; a secret-bearing command
        simply won't confirm across a boundary (safe — no false promotion).
        """
        assert_learning_permitted("lessons.record_or_increment")
        clamped_delta = max(-1.0, min(0.0, float(confidence_delta)))
        task_id = scan_and_redact(task_id).scrubbed
        error_type = scan_and_redact(error_type).scrubbed
        root_cause = scan_and_redact(root_cause).scrubbed
        fix_applied = scan_and_redact(fix_applied).scrubbed
        lesson_text = scan_and_redact(lesson_text).scrubbed
        failed_command = scan_and_redact(failed_command).scrubbed
        with get_connection(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                _RECURRENCE_MATCH, (task_id, error_type, principal_id)
            ).fetchone()
            if existing is not None:
                mistake_id = int(existing["id"])
                # Refresh failed_command to the MOST RECENT recurrence so the
                # command the tracker can confirm is the one last observed failing
                # (a stale first command would never match the eventual fix).
                conn.execute(
                    "UPDATE mistake_pool "
                    "SET occurrence_count = occurrence_count + 1, failed_command = ? "
                    "WHERE id = ?",
                    (failed_command, mistake_id),
                )
                return mistake_id, True
            cur = conn.execute(
                "INSERT INTO mistake_pool "
                "(task_id, error_type, root_cause, fix_applied, lesson_text, "
                " confidence_delta, failed_command, principal_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    task_id,
                    error_type,
                    root_cause,
                    fix_applied,
                    lesson_text,
                    clamped_delta,
                    failed_command,
                    principal_id,
                ),
            )
            return int(cur.lastrowid), False

    def recurrence_candidate(
        self, task_id: str, error_type: str, principal_id: Optional[str] = None
    ) -> Optional[sqlite3.Row]:
        """The row ``record_or_increment`` would increment now, or ``None``.

        The same scrub and the same query as the write, so a caller can read the
        state a recurrence is about to change (plan Phase 3b: a transition is
        signed only if the state it extends was). Read-only.
        """
        task_id = scan_and_redact(task_id).scrubbed
        error_type = scan_and_redact(error_type).scrubbed
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                _RECURRENCE_MATCH, (task_id, error_type, principal_id)
            ).fetchone()
            if row is None:
                return None
            return conn.execute(
                "SELECT * FROM mistake_pool WHERE id = ?", (int(row["id"]),)
            ).fetchone()

    def increment_occurrence(
        self, mistake_id: int, principal_id: Optional[str] = None
    ) -> None:
        """Bump the occurrence counter for a repeated mistake of *principal_id*."""
        assert_learning_permitted("lessons.increment_occurrence")
        with get_connection(self.db_path) as conn:
            conn.execute(
                "UPDATE mistake_pool SET occurrence_count = occurrence_count + 1 "
                "WHERE id = ? AND principal_id IS ?",
                (mistake_id, principal_id),
            )

    def pending_command_pairs(
        self, task_id: str, principal_id: Optional[str] = None
    ) -> list[tuple[int, str]]:
        """Return ``(mistake_id, failed_command)`` for this task's still-pending
        lessons that carry a command.

        Lets a later turn (or an approval-replayed continuation) rebuild the
        fail->confirm tracking that the agent's per-run() in-memory list loses
        across an approval pause, so the lesson is promoted when its exact
        command finally succeeds. Verified lessons are excluded — they are
        already promoted and must not be re-confirmed.
        """
        task_id = scan_and_redact(task_id).scrubbed
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, failed_command FROM mistake_pool "
                "WHERE task_id = ? AND verification_status = 'pending' "
                "AND failed_command != '' AND principal_id IS ? ORDER BY id",
                (task_id, principal_id),
            ).fetchall()
        return [(int(row["id"]), str(row["failed_command"])) for row in rows]

    def promote(
        self,
        mistake_id: int,
        *,
        strength: VerificationStrength = VerificationStrength.STRONG,
        principal_id: Optional[str] = None,
    ) -> None:
        """Promote a lesson of *principal_id* from ``pending`` to ``verified``
        (plan Phase 4c: never another principal's).

        Below-floor evidence leaves the lesson pending. Verified mistake lessons
        feed planner confidence, so a weak green must not graduate into that
        cross-task calibration path.

        The floor asked here is the LEARNING floor (MEDIUM), not the authority
        one. A lesson recorded when ``mypy aios/`` failed, and confirmed when
        that same command later passes, has transferred in exactly the sense
        this mechanism exists to capture -- but MEDIUM is the ceiling for
        checker evidence, so under the authority floor it could never be
        confirmed at all. WEAK still cannot promote anything.
        """
        assert_learning_permitted("lessons.promote")
        if not meets_learning_floor(strength):
            return
        with get_connection(self.db_path) as conn:
            promoted = conn.execute(
                "UPDATE mistake_pool SET verification_status = 'verified' "
                "WHERE id = ? AND verification_status = 'pending' "
                "AND principal_id IS ?",
                (mistake_id, principal_id),
            ).rowcount
            row = (
                conn.execute(
                    "SELECT error_type, root_cause, lesson_text FROM mistake_pool "
                    "WHERE id = ?",
                    (mistake_id,),
                ).fetchone()
                if promoted
                else None
            )

        # S2: ingest verified mistake edges into the knowledge graph.
        # OUTSIDE the `with` block — same SQLite deadlock avoidance as
        # SkillMemory's cerebellum/ingestion triggers.
        if row is not None and self._facts is not None:
            try:
                from aios.core.graph_ingestion import edges_from_mistake

                for s, p, o, conf in edges_from_mistake(
                    str(row["error_type"]),
                    str(row["root_cause"]),
                    str(row["lesson_text"]),
                ):
                    self._facts.add_fact(
                        s, p, o, confidence=conf, principal_id=principal_id
                    )
            except Exception:
                logger.warning(
                    "graph ingestion from mistake failed (swallowed)", exc_info=True
                )

    def supersede(
        self, old_id: int, new_id: int, principal_id: Optional[str] = None
    ) -> None:
        """Mark *old_id* as superseded by *new_id* -- both of *principal_id*."""
        with get_connection(self.db_path) as conn:
            conn.execute(
                "UPDATE mistake_pool "
                "SET verification_status = 'superseded', superseded_by = ? "
                "WHERE id = ? AND principal_id IS ? "
                "AND EXISTS (SELECT 1 FROM mistake_pool AS n "
                "            WHERE n.id = ? AND n.principal_id IS ?)",
                (new_id, old_id, principal_id, new_id, principal_id),
            )

    def record_recall_outcome(
        self,
        mistake_ids: Any,
        *,
        success: bool,
        principal_id: Optional[str],
    ) -> list[dict[str, Any]]:
        """Count a verifier-judged outcome into each recalled VERIFIED lesson
        of *principal_id* (plan Phase 6d). Returns, per lesson counted, its row
        and its (successes, failures) since its last re-admission. Pending,
        superseded and other principals' lessons are not counted."""
        assert_learning_permitted("lessons.record_recall_outcome")
        column_sql = (
            "UPDATE lesson_outcomes SET successes = successes + 1 WHERE mistake_id = ?"
            if success
            else "UPDATE lesson_outcomes SET failures = failures + 1 WHERE mistake_id = ?"
        )
        counted: list[dict[str, Any]] = []
        with get_connection(self.db_path) as conn:
            for mistake_id in dict.fromkeys(int(i) for i in mistake_ids):
                row = conn.execute(
                    "SELECT * FROM mistake_pool WHERE id = ? AND principal_id IS ? "
                    "AND verification_status = 'verified'",
                    (mistake_id, principal_id),
                ).fetchone()
                if row is None:
                    continue
                conn.execute(
                    "INSERT INTO lesson_outcomes (mistake_id, principal_id) "
                    "VALUES (?, ?) ON CONFLICT(mistake_id) DO NOTHING",
                    (mistake_id, principal_id),
                )
                conn.execute(column_sql, (mistake_id,))
                counts = conn.execute(
                    "SELECT successes, failures FROM lesson_outcomes "
                    "WHERE mistake_id = ?",
                    (mistake_id,),
                ).fetchone()
                counted.append(
                    {
                        "row": row,
                        "successes": int(counts["successes"]),
                        "failures": int(counts["failures"]),
                    }
                )
        return counted

    def reset_recall_outcomes(self, mistake_ids: Any) -> None:
        """The operator re-admitted these lessons: their windows start now."""
        assert_learning_permitted("lessons.reset_recall_outcomes")
        with get_connection(self.db_path) as conn:
            for mistake_id in dict.fromkeys(int(i) for i in mistake_ids):
                conn.execute(
                    "DELETE FROM lesson_outcomes WHERE mistake_id = ?", (mistake_id,)
                )

    def stale_pending(self, older_than_days: float) -> list[int]:
        """Plan Phase 6f (GC): pending lessons CREATED over *older_than_days* ago.

        Read-only. Creation is not last activity -- a recurrence leaves the
        timestamp alone -- so the caller decides, from provenance, which of
        these are really idle. Zero (or fewer) days: none.
        """
        if older_than_days <= 0:
            return []
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=older_than_days)
        ).strftime("%Y-%m-%d %H:%M:%S")
        with get_connection(self.db_path) as conn:
            return [
                int(r["id"])
                for r in conn.execute(
                    "SELECT id FROM mistake_pool WHERE verification_status = 'pending' "
                    "AND timestamp < ? ORDER BY id",
                    (cutoff,),
                ).fetchall()
            ]

    def forget_pending(self, mistake_ids: Any) -> list[int]:
        """Delete the named lessons that are STILL pending; return those removed.

        Verified, superseded and quarantined lessons are never touched: they
        are recalled, are lineage, or are evidence. A lesson promoted between
        the read and this delete stays. Their provenance records stay, as
        history. Forgetting is the safe direction, so the stop does not refuse it.
        """
        ids = sorted({int(i) for i in mistake_ids})
        marks = ",".join("?" * len(ids))
        with get_connection(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            removed = [
                int(r["id"])
                for r in conn.execute(
                    f"SELECT id FROM mistake_pool WHERE id IN ({marks}) "  # noqa: S608
                    "AND verification_status = 'pending' ORDER BY id",
                    tuple(ids),
                ).fetchall()
            ]
            conn.execute(
                f"DELETE FROM mistake_pool WHERE id IN ({marks}) "  # noqa: S608
                "AND verification_status = 'pending'",
                tuple(ids),
            )
        return removed

    def count(self) -> int:
        """Return the total number of recorded mistakes."""
        with get_connection(self.db_path) as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM mistake_pool").fetchone()
        return int(row["n"])
