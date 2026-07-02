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
from aios.memory.db import get_connection, init_memory_db
from aios.security.secret_scanner import scan_and_redact


_TRAVERSE_ROW_LIMIT = 256


@dataclass(frozen=True)
class FactWriteResult:
    """Outcome of attempting to write a fact."""

    committed: bool
    fact_id: Optional[int]
    reason: str  # 'committed' | 'already present' | 'reconciled' | 'contradiction' | ...
    conflict_id: Optional[int] = None
    conflict_object: Optional[str] = None


@dataclass(frozen=True)
class ProposalResult:
    """Outcome of proposing an auto-extracted fact for human review."""

    proposed: bool
    proposal_id: Optional[int]
    reason: str  # 'proposed' | 'already proposed' | 'already known' | ...


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

    def add_fact(
        self, subject: str, predicate: str, obj: str, *, approved_by: Optional[str] = None
    ) -> FactWriteResult:
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
        approved_by = scan_and_redact((approved_by or "").strip()).scrubbed or None
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
                if approved_by is not None:
                    conn.execute(
                        "UPDATE semantic_facts SET approved_by = COALESCE(approved_by, ?) "
                        "WHERE id = ?",
                        (approved_by, int(existing["id"])),
                    )
                return FactWriteResult(True, int(existing["id"]), "already present")
            cur = conn.execute(
                "INSERT INTO semantic_facts (subject, predicate, object, approved_by) "
                "VALUES (?, ?, ?, ?)",
                (subject, predicate, obj, approved_by),
            )
            return FactWriteResult(True, int(cur.lastrowid), "committed")

    def reconcile(
        self,
        subject: str,
        predicate: str,
        new_obj: str,
        *,
        approved_by: Optional[str] = None,
    ) -> FactWriteResult:
        """Resolve a contradiction: supersede every active fact on this
        subject+predicate and commit *new_obj* as the active fact."""
        subject = scan_and_redact(subject.strip()).scrubbed
        predicate = scan_and_redact(predicate.strip()).scrubbed
        new_obj = scan_and_redact(new_obj.strip()).scrubbed
        approved_by = scan_and_redact((approved_by or "").strip()).scrubbed or None
        if not (subject and predicate and new_obj):
            return FactWriteResult(False, None, "empty subject/predicate/object")
        with get_connection(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE semantic_facts SET status = 'superseded' "
                "WHERE subject = ? AND predicate = ? AND status = 'active'",
                (subject, predicate),
            )
            cur = conn.execute(
                "INSERT INTO semantic_facts (subject, predicate, object, approved_by) "
                "VALUES (?, ?, ?, ?)",
                (subject, predicate, new_obj, approved_by),
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

    def neighbors(self, subject: str) -> list[sqlite3.Row]:
        """Return ACTIVE facts adjacent to *subject* — both outgoing edges
        (where *subject* is the subject) and incoming edges (where *subject* is
        the object). This is the single-hop neighborhood used to enrich a recalled
        fact with its immediate context.

        Example: with facts ``alice --likes--> tea`` and ``bob --knows--> alice``,
        ``neighbors('alice')`` returns both rows.
        """
        subject = (subject or "").strip()
        if not subject:
            return []
        sql = """
        SELECT subject, predicate, object, 'out' AS direction
        FROM semantic_facts
        WHERE subject = ? AND status = 'active'
        UNION ALL
        SELECT subject, predicate, object, 'in' AS direction
        FROM semantic_facts
        WHERE object = ? AND status = 'active'
        ORDER BY direction, subject, predicate
        """
        with get_connection(self.db_path) as conn:
            return conn.execute(sql, (subject, subject)).fetchall()

    def traverse(self, start: str, max_depth: int = 2) -> list[sqlite3.Row]:
        """Walk the ACTIVE fact graph outward from *start*, following
        ``object -> subject`` links up to *max_depth* hops — the multi-hop
        reasoning that single-hop :meth:`facts_for` cannot do.

        Each active fact ``(s, p, o)`` is an edge ``s --p--> o``; the walk
        follows each object as the next subject. Returns rows with the hop
        ``depth`` (1 = directly stated) and a delimiter-bounded ``path``,
        ordered by depth. A path-membership check guards against cycles, and
        *max_depth* is clamped to ``[1, 4]`` (the path string grows with depth,
        so the recursion stays cheap). Example: ``traverse('project')`` can
        surface ``project --uses--> FastAPI --needs--> uvicorn`` at depth 2.

        Uses ``idx_facts_sp (subject, predicate)`` to accelerate each hop's
        ``f.subject = g.object`` join. Pure read; no writes, no security path.
        """
        start = (start or "").strip()
        if not start:
            return []
        depth = max(1, min(int(max_depth), 4))
        # Recursive CTE. ``path`` is bounded by the marker char so the cycle
        # guard matches whole nodes (not substrings): '→a→b→' contains '→a→'
        # but not '→ab→'.
        sql = """
        WITH RECURSIVE graph(subject, predicate, object, depth, path) AS (
            SELECT subject, predicate, object, 1,
                   '→' || subject || '→' || object || '→'
            FROM semantic_facts
            WHERE subject = :start AND status = 'active'
            UNION ALL
            SELECT f.subject, f.predicate, f.object, g.depth + 1,
                   g.path || f.object || '→'
            FROM semantic_facts f
            JOIN graph g ON f.subject = g.object
            WHERE g.depth < :max_depth
              AND f.status = 'active'
              AND g.path NOT LIKE '%→' || f.object || '→%'
        )
        SELECT subject, predicate, object, depth, path
        FROM graph
        ORDER BY depth, subject, predicate
        LIMIT :row_limit
        """
        with get_connection(self.db_path) as conn:
            return conn.execute(
                sql,
                {"start": start, "max_depth": depth, "row_limit": _TRAVERSE_ROW_LIMIT},
            ).fetchall()

    def search(self, query: str) -> list[sqlite3.Row]:
        """Return ACTIVE facts whose subject or object contains a token from *query*.

        This is a simple, deterministic token match (case-insensitive)
        intended for prompt-time recall. It is NOT semantic search; the semantic
        memory layer covers that. Tokens shorter than 3 characters are ignored
        to avoid noise. Returns deduplicated rows ordered by id DESC.
        """
        query = (query or "").strip().lower()
        tokens = [t for t in set(query.split()) if len(t) >= 3]
        if not tokens:
            return []
        # Build a dynamic OR clause matching any token against subject/object.
        conditions = " OR ".join(
            "(lower(subject) LIKE '%' || ? || '%' OR lower(object) LIKE '%' || ? || '%')"
            for _ in tokens
        )
        params = []
        for token in tokens:
            params.extend([token, token])
        sql = f"""
        SELECT DISTINCT subject, predicate, object
        FROM semantic_facts
        WHERE status = 'active'
          AND ({conditions})
        ORDER BY id DESC
        """
        with get_connection(self.db_path) as conn:
            return conn.execute(sql, params).fetchall()

    # ── Auto-extracted proposals (supervised memory formation) ────────────────
    #
    # Proposals live in ``fact_proposals`` — a separate table no recall path
    # reads — so an unreviewed candidate is structurally incapable of reaching
    # a prompt. Only a named human approval moves knowledge across the boundary,
    # and it moves through the same contradiction-aware ``add_fact`` gate.

    def propose(
        self, subject: str, predicate: str, obj: str, *, source: str = "auto-extract"
    ) -> ProposalResult:
        """Queue a fact candidate for human review; never enters recall.

        Idempotent: an identical active fact ('already known') or identical
        pending proposal ('already proposed') creates no new row.
        """
        subject = scan_and_redact(subject.strip()).scrubbed
        predicate = scan_and_redact(predicate.strip()).scrubbed
        obj = scan_and_redact(obj.strip()).scrubbed
        source = scan_and_redact((source or "").strip()).scrubbed or "auto-extract"
        if not (subject and predicate and obj):
            return ProposalResult(False, None, "empty subject/predicate/object")
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            active = conn.execute(
                "SELECT id FROM semantic_facts "
                "WHERE subject = ? AND predicate = ? AND object = ? AND status = 'active'",
                (subject, predicate, obj),
            ).fetchone()
            if active is not None:
                return ProposalResult(False, None, "already known")
            pending = conn.execute(
                "SELECT id FROM fact_proposals "
                "WHERE subject = ? AND predicate = ? AND object = ? AND status = 'pending'",
                (subject, predicate, obj),
            ).fetchone()
            if pending is not None:
                return ProposalResult(False, int(pending["id"]), "already proposed")
            cur = conn.execute(
                "INSERT INTO fact_proposals (subject, predicate, object, source) "
                "VALUES (?, ?, ?, ?)",
                (subject, predicate, obj, source),
            )
            return ProposalResult(True, int(cur.lastrowid), "proposed")

    def pending_proposals(self, limit: int = 100) -> list[sqlite3.Row]:
        """Return pending fact proposals, newest first."""
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            return conn.execute(
                "SELECT * FROM fact_proposals WHERE status = 'pending' "
                "ORDER BY id DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()

    def approve_proposal(self, proposal_id: int, *, approved_by: str) -> FactWriteResult:
        """Promote one pending proposal THROUGH the contradiction-aware write.

        A contradiction is returned, not committed, and the proposal stays
        pending for an explicit human ``reconcile``. Idempotent under retries:
        if the fact already landed, the proposal is still marked approved.
        """
        approver = (approved_by or "").strip()
        if not approver:
            return FactWriteResult(False, None, "approver required")
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM fact_proposals WHERE id = ?", (int(proposal_id),)
            ).fetchone()
        if row is None or str(row["status"]) != "pending":
            return FactWriteResult(False, None, "not pending")
        result = self.add_fact(
            str(row["subject"]),
            str(row["predicate"]),
            str(row["object"]),
            approved_by=approver,
        )
        if result.committed:
            with get_connection(self.db_path) as conn:
                conn.execute(
                    "UPDATE fact_proposals SET status = 'approved', resolved_by = ?, "
                    "resolved_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'pending'",
                    (approver, int(proposal_id)),
                )
        return result

    def reject_proposal(self, proposal_id: int, *, rejected_by: str) -> bool:
        """Resolve a pending proposal as rejected; ``False`` if not pending."""
        resolver = (rejected_by or "").strip()
        if not resolver:
            return False
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE fact_proposals SET status = 'rejected', resolved_by = ?, "
                "resolved_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'pending'",
                (resolver, int(proposal_id)),
            )
            return cur.rowcount == 1
