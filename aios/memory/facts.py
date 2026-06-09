"""L3 semantic facts: entity-relation triples with contradiction detection.

Stores ``(subject, predicate, object)`` facts — project entities, user
preferences, codebase facts — and, before committing a new fact, checks for an
existing **active** fact on the same ``(subject, predicate)`` with a *different*
object. A contradiction is **not** silently committed: it is surfaced so the
caller can route it to the Reflection Agent or a human for reconciliation
(Blueprint 5.3 contradiction-detection flow). Exact duplicates are idempotent.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from aios import config
from aios.memory.db import get_connection
from aios.security.secret_scanner import scan_and_redact


@dataclass(frozen=True)
class FactWriteResult:
    """Outcome of attempting to write a fact."""

    committed: bool
    fact_id: Optional[int]
    reason: str  # 'committed' | 'already present' | 'reconciled' | 'contradiction' | ...
    conflict_id: Optional[int] = None
    conflict_object: Optional[str] = None


class SemanticFacts:
    """CRUD + contradiction-aware writes over the ``semantic_facts`` table."""

    def __init__(self, db_path: Path = config.MEMORY_DB_PATH) -> None:
        self.db_path = db_path

    def find_conflict(self, subject: str, predicate: str, obj: str) -> Optional[sqlite3.Row]:
        """Return an active fact with the same subject+predicate but a *different*
        object (the contradiction), or ``None``."""
        with get_connection(self.db_path) as conn:
            return conn.execute(
                "SELECT * FROM semantic_facts "
                "WHERE subject = ? AND predicate = ? AND object <> ? AND status = 'active' "
                "ORDER BY id DESC LIMIT 1",
                (subject, predicate, obj),
            ).fetchone()

    def add_fact(self, subject: str, predicate: str, obj: str) -> FactWriteResult:
        """Commit a fact unless it contradicts an existing active fact.

        - Empty component -> not committed.
        - Same subject+predicate, *different* object -> ``contradiction`` (not
          committed); the caller reconciles (Blueprint 5.3).
        - Exact ``(subject, predicate, object)`` already present -> idempotent,
          returns the existing id.
        - Otherwise -> inserted.
        """
        subject = scan_and_redact(subject.strip()).scrubbed
        predicate = scan_and_redact(predicate.strip()).scrubbed
        obj = scan_and_redact(obj.strip()).scrubbed
        if not (subject and predicate and obj):
            return FactWriteResult(False, None, "empty subject/predicate/object")

        with get_connection(self.db_path) as conn:
            # Serialize contradiction check + insert across local workers. Without
            # this transaction, two concurrent writers can both observe no active
            # fact and commit conflicting objects.
            conn.execute("BEGIN IMMEDIATE")
            conflict = conn.execute(
                "SELECT * FROM semantic_facts "
                "WHERE subject = ? AND predicate = ? AND object <> ? AND status = 'active' "
                "ORDER BY id DESC LIMIT 1",
                (subject, predicate, obj),
            ).fetchone()
            if conflict is not None:
                return FactWriteResult(
                    committed=False,
                    fact_id=None,
                    reason="contradiction",
                    conflict_id=int(conflict["id"]),
                    conflict_object=str(conflict["object"]),
                )
            existing = conn.execute(
                "SELECT id FROM semantic_facts "
                "WHERE subject = ? AND predicate = ? AND object = ? AND status = 'active'",
                (subject, predicate, obj),
            ).fetchone()
            if existing is not None:
                return FactWriteResult(True, int(existing["id"]), "already present")
            cur = conn.execute(
                "INSERT INTO semantic_facts (subject, predicate, object) VALUES (?, ?, ?)",
                (subject, predicate, obj),
            )
            return FactWriteResult(True, int(cur.lastrowid), "committed")

    def reconcile(self, subject: str, predicate: str, new_obj: str) -> FactWriteResult:
        """Resolve a contradiction: supersede every active fact on this
        subject+predicate and commit *new_obj* as the active fact."""
        subject = scan_and_redact(subject.strip()).scrubbed
        predicate = scan_and_redact(predicate.strip()).scrubbed
        new_obj = scan_and_redact(new_obj.strip()).scrubbed
        if not (subject and predicate and new_obj):
            return FactWriteResult(False, None, "empty subject/predicate/object")
        with get_connection(self.db_path) as conn:
            conn.execute(
                "UPDATE semantic_facts SET status = 'superseded' "
                "WHERE subject = ? AND predicate = ? AND status = 'active'",
                (subject, predicate),
            )
            cur = conn.execute(
                "INSERT INTO semantic_facts (subject, predicate, object) VALUES (?, ?, ?)",
                (subject, predicate, new_obj),
            )
            return FactWriteResult(True, int(cur.lastrowid), "reconciled")

    def get(self, fact_id: int) -> Optional[sqlite3.Row]:
        """Return the row for *fact_id*, or ``None``."""
        with get_connection(self.db_path) as conn:
            return conn.execute(
                "SELECT * FROM semantic_facts WHERE id = ?", (fact_id,)
            ).fetchone()

    def facts_for(self, subject: str, predicate: Optional[str] = None) -> list[sqlite3.Row]:
        """Return active facts for *subject* (optionally filtered by *predicate*)."""
        sql = "SELECT * FROM semantic_facts WHERE subject = ? AND status = 'active'"
        params: list[object] = [subject]
        if predicate is not None:
            sql += " AND predicate = ?"
            params.append(predicate)
        sql += " ORDER BY id DESC"
        with get_connection(self.db_path) as conn:
            return conn.execute(sql, params).fetchall()
