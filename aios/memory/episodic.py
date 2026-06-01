"""L2 Episodic memory: the persistent, chronological record of agent activity.

Stores every turn (user / assistant / tool / system) keyed by session, with a
server-side timestamp. Queries support both recency (``recent``) and
time-window filtering (``since``), backed by the ``idx_episodic_session`` and
``idx_episodic_time`` indexes.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from aios import config
from aios.memory.db import get_connection


class EpisodicMemory:
    """CRUD facade over the ``episodic_memory`` table."""

    def __init__(self, db_path: Path = config.MEMORY_DB_PATH) -> None:
        self.db_path = db_path

    def record(self, session_id: str, role: str, content: str) -> int:
        """Persist one turn and return its new row id."""
        with get_connection(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO episodic_memory (session_id, role, content) "
                "VALUES (?, ?, ?)",
                (session_id, role, content),
            )
            return int(cur.lastrowid)

    def recent(self, session_id: str, limit: int = 20) -> list[sqlite3.Row]:
        """Return the most recent *limit* turns for *session_id*, oldest first.

        Internally selects the newest rows by id then reverses them, so the
        caller receives a chronologically ordered slice ready to replay.
        """
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, timestamp, session_id, role, content "
                "FROM episodic_memory WHERE session_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return list(reversed(rows))

    def since(self, session_id: str, iso_timestamp: str) -> list[sqlite3.Row]:
        """Return turns for *session_id* at or after *iso_timestamp* (UTC)."""
        with get_connection(self.db_path) as conn:
            return conn.execute(
                "SELECT id, timestamp, session_id, role, content "
                "FROM episodic_memory WHERE session_id = ? AND timestamp >= ? "
                "ORDER BY id ASC",
                (session_id, iso_timestamp),
            ).fetchall()

    def count(self, session_id: str | None = None) -> int:
        """Return the total number of turns, optionally scoped to a session."""
        with get_connection(self.db_path) as conn:
            if session_id is None:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM episodic_memory"
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM episodic_memory WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
        return int(row["n"])
