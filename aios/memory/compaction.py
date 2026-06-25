"""Audited memory compaction (the "sleep" sweep): forgetting with reversibility.

A `MemoryCompactor` performs three independent sweeps, each gated by operator
config and each safe to run as a dry-run preview first:

1. Working memory: drop in-process sessions whose last activity is older than
   ``MEMORY_COMPACT_WORKING_IDLE_MINUTES``.
2. Episodic memory: delete rows older than ``MEMORY_COMPACT_EPISODIC_DAYS``.
3. Semantic memory: (a) delete unverified ``chat`` rows older than
   ``MEMORY_COMPACT_UNVERIFIED_CHAT_DAYS``; (b) cap each active memory_type to
   ``MEMORY_COMPACT_SEMANTIC_MAX_PER_TYPE``, keeping newest first. Verified and
   superseded rows are never deleted.

Every real (non-dry-run) compaction writes one audit entry under actor
``sleep-consolidation`` summarising the batch.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from aios import config
from aios.logging_config import get_logger
from aios.memory.db import get_connection, init_memory_db
from aios.memory.embeddings import VectorIndex
from aios.memory.episodic import EpisodicMemory
from aios.memory.semantic import SemanticMemory
from aios.memory.working import WorkingMemory
from aios.security.audit_logger import log_action
from aios.security.gateway import Zone

logger = get_logger(__name__)


@dataclass(frozen=True)
class CompactionPreview:
    """What a compaction sweep would remove, without touching storage."""

    working_sessions: list[str]
    working_sessions_count: int
    episodic_row_count: int
    semantic_chat_old_count: int
    semantic_per_type_cap_rows: dict[str, int]
    semantic_vector_ids_to_remove: list[int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "working_sessions": self.working_sessions,
            "working_sessions_count": self.working_sessions_count,
            "episodic_row_count": self.episodic_row_count,
            "semantic_chat_old_count": self.semantic_chat_old_count,
            "semantic_per_type_cap_rows": self.semantic_per_type_cap_rows,
            "semantic_vector_ids_to_remove": self.semantic_vector_ids_to_remove,
        }


class MemoryCompactor:
    """Operator-triggered memory forgetting with dry-run preview."""

    def __init__(
        self,
        db_path: Path = config.MEMORY_DB_PATH,
        audit_db_path: Path = config.AUDIT_DB_PATH,
        working: Optional[WorkingMemory] = None,
        semantic: Optional[SemanticMemory] = None,
        episodic: Optional[EpisodicMemory] = None,
        index: Optional[VectorIndex] = None,
        *,
        unverified_chat_days: float = config.MEMORY_COMPACT_UNVERIFIED_CHAT_DAYS,
        episodic_days: float = config.MEMORY_COMPACT_EPISODIC_DAYS,
        semantic_max_per_type: int = config.MEMORY_COMPACT_SEMANTIC_MAX_PER_TYPE,
        working_idle_minutes: int = config.MEMORY_COMPACT_WORKING_IDLE_MINUTES,
    ) -> None:
        self.db_path = db_path
        self.audit_db_path = audit_db_path
        self.working = working
        self.semantic = semantic
        self.episodic = episodic
        self.index = index
        self.unverified_chat_days = max(0.0, unverified_chat_days)
        self.episodic_days = max(0.0, episodic_days)
        self.semantic_max_per_type = max(0, semantic_max_per_type)
        self.working_idle_minutes = max(0, working_idle_minutes)
        self._working_last_seen: dict[str, float] = {}
        self._working_lock = threading.Lock()

    # --------------------------------------------------------------------- #
    # Working memory hooks
    # --------------------------------------------------------------------- #
    def touch_working_session(self, session_id: str) -> None:
        """Record latest activity so idle TTL can be computed."""
        with self._working_lock:
            self._working_last_seen[session_id] = time.monotonic()

    def _stale_working_sessions(self) -> list[str]:
        if self.working is None:
            return []
        cutoff = time.monotonic() - (self.working_idle_minutes * 60)
        with self._working_lock:
            return [
                sid
                for sid in self.working.sessions()
                if self._working_last_seen.get(sid, 0) < cutoff
            ]

    # --------------------------------------------------------------------- #
    # Episodic sweep
    # --------------------------------------------------------------------- #
    def _old_episodic_cutoff(self) -> str:
        dt = datetime.now(timezone.utc) - timedelta(days=self.episodic_days)
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def _preview_episodic(self, conn: Any) -> int:
        if self.episodic_days <= 0:
            return 0
        cutoff = self._old_episodic_cutoff()
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM episodic_memory WHERE timestamp < ?",
            (cutoff,),
        ).fetchone()
        return int(row["n"])

    def _compact_episodic(self, conn: Any, dry_run: bool) -> int:
        count = self._preview_episodic(conn)
        if count and not dry_run:
            cutoff = self._old_episodic_cutoff()
            conn.execute(
                "DELETE FROM episodic_memory WHERE timestamp < ?", (cutoff,)
            )
        return count

    # --------------------------------------------------------------------- #
    # Semantic sweep
    # --------------------------------------------------------------------- #
    def _old_unverified_chat_ids(self, conn: Any) -> list[int]:
        if self.unverified_chat_days <= 0:
            return []
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=self.unverified_chat_days)
        ).strftime("%Y-%m-%d %H:%M:%S")
        rows = conn.execute(
            "SELECT id FROM semantic_memory "
            "WHERE memory_type = 'chat' AND verification_status = 'unverified' "
            "AND timestamp < ?",
            (cutoff,),
        ).fetchall()
        return [int(r["id"]) for r in rows]

    def _per_type_cap_ids(self, conn: Any) -> list[int]:
        if self.semantic_max_per_type <= 0:
            return []
        ids: list[int] = []
        # Only cap unverified rows; verified evidence and superseded lineage are
        # never evicted.
        for mem_type in ("chat", "lesson", "fact", "preference", "procedure"):
            rows = conn.execute(
                "SELECT id FROM semantic_memory "
                "WHERE memory_type = ? AND verification_status = 'unverified' "
                "ORDER BY COALESCE(last_seen_at, timestamp) DESC, id DESC "
                "LIMIT -1 OFFSET ?",
                (mem_type, self.semantic_max_per_type),
            ).fetchall()
            ids.extend(int(r["id"]) for r in rows)
        return ids

    def _preview_semantic(
        self, conn: Any
    ) -> tuple[list[int], dict[str, int]]:
        old_chat = self._old_unverified_chat_ids(conn)
        cap_ids = self._per_type_cap_ids(conn)
        # Avoid double-counting ids that appear in both sets.
        all_ids = list(dict.fromkeys(old_chat + cap_ids))
        per_type: dict[str, int] = {}
        if self.semantic_max_per_type > 0:
            for mem_type in ("chat", "lesson", "fact", "preference", "procedure"):
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM semantic_memory "
                    "WHERE memory_type = ? AND verification_status = 'unverified'",
                    (mem_type,),
                ).fetchone()
                total = int(row["n"]) if row else 0
                per_type[mem_type] = max(0, total - self.semantic_max_per_type)
        return all_ids, per_type

    def _compact_semantic(
        self, conn: Any, dry_run: bool
    ) -> tuple[list[int], dict[str, int]]:
        ids, per_type = self._preview_semantic(conn)
        if ids and not dry_run:
            placeholders = ",".join("?" * len(ids))
            conn.execute(
                f"DELETE FROM semantic_memory WHERE id IN ({placeholders})",
                tuple(ids),
            )
        return ids, per_type

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def preview(self) -> CompactionPreview:
        """Return what would be removed without mutating any store."""
        init_memory_db(self.db_path)
        working = self._stale_working_sessions()
        with get_connection(self.db_path) as conn:
            episodic = self._preview_episodic(conn)
            old_chat_ids = self._old_unverified_chat_ids(conn)
            semantic_ids, per_type = self._preview_semantic(conn)
        return CompactionPreview(
            working_sessions=working,
            working_sessions_count=len(working),
            episodic_row_count=episodic,
            semantic_chat_old_count=len(old_chat_ids),
            semantic_per_type_cap_rows=per_type,
            semantic_vector_ids_to_remove=semantic_ids,
        )

    def compact(self, dry_run: bool = True) -> dict[str, Any]:
        """Run the compaction sweep.

        Args:
            dry_run: When True (the safe default), report what would change but
                do not mutate durable stores.

        Returns:
            A dict summarising the sweep, including the same keys a caller would
            use for preview plus the ``dry_run`` flag.
        """
        init_memory_db(self.db_path)
        working_removed: list[str] = []
        if self.working is not None:
            working_removed = self._stale_working_sessions()
            if not dry_run:
                for sid in working_removed:
                    self.working.clear(sid)

        with get_connection(self.db_path) as conn:
            episodic_count = self._compact_episodic(conn, dry_run)
            old_chat_count = len(self._old_unverified_chat_ids(conn))
            semantic_ids, per_type = self._compact_semantic(conn, dry_run)

        # FAISS cleanup happens outside the SQLite transaction.
        if not dry_run and semantic_ids and self.index is not None:
            try:
                self.index.rebuild_without(semantic_ids)
            except Exception as exc:  # noqa: BLE001 - vector cleanup must not crash the sweep
                logger.warning("Semantic vector cleanup failed", exc_info=exc)

        result = {
            "dry_run": dry_run,
            "working_sessions_removed": len(working_removed),
            "episodic_rows_removed": episodic_count,
            "semantic_unverified_chat_removed": old_chat_count,
            "semantic_per_type_cap_rows": per_type,
            "semantic_vector_ids_removed": semantic_ids,
        }

        if not dry_run:
            self._audit(result)

        return result

    def _audit(self, result: dict[str, Any]) -> None:
        """Write one tamper-evident audit entry for the batch."""
        payload = json.dumps(result, sort_keys=True, default=str)
        try:
            log_action(
                actor="sleep-consolidation",
                payload=payload,
                zone=Zone.YELLOW,
                db_path=self.audit_db_path,
            )
        except Exception as exc:  # noqa: BLE001 - audit failure is logged but does not rollback memory
            logger.warning("Compaction audit entry failed", exc_info=exc)
