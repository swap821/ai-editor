"""Rollback Registry — centralized catalog of all rollback-capable snapshot points."""

from __future__ import annotations

import fnmatch
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class RegistryEntry:
    snapshot_id: str
    mission_id: str
    workspace_root: str
    created_at: str
    files_covered: list[str]
    metadata: dict[str, Any]


class RollbackRegistry:
    """Centralized catalog of all rollback-capable snapshot points.

    Indexes what :class:`aios.runtime.snapshots.SnapshotManager` and
    :class:`aios.agents.rollback_engine.RollbackEngine` already create; this
    class never stores or moves snapshot payloads itself.
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS rollback_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_id TEXT NOT NULL UNIQUE,
        mission_id TEXT NOT NULL,
        workspace_root TEXT NOT NULL,
        created_at TEXT NOT NULL,
        files_covered_json TEXT NOT NULL DEFAULT '[]',
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_rollback_mission ON rollback_entries(mission_id);
    CREATE INDEX IF NOT EXISTS idx_rollback_created ON rollback_entries(created_at);
    CREATE INDEX IF NOT EXISTS idx_rollback_workspace ON rollback_entries(workspace_root);
    """

    def __init__(self, db_path: Path | None = None, retention_days: int = 30):
        self._db_path = db_path or Path(":memory:")
        self._retention_days = retention_days
        self._is_memory = str(self._db_path) == ":memory:"
        self._mem_conn: sqlite3.Connection | None = None
        self._init_db()

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def _conn(self) -> sqlite3.Connection:
        if self._is_memory:
            if self._mem_conn is None:
                mem_conn = sqlite3.connect(":memory:")
                mem_conn.row_factory = sqlite3.Row
                self._mem_conn = mem_conn
            return self._mem_conn
        return self._open()

    def _close(self, conn: sqlite3.Connection) -> None:
        if not self._is_memory:
            conn.close()

    def _init_db(self) -> None:
        if not self._is_memory:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._conn()
        try:
            conn.executescript(self._SCHEMA)
            conn.commit()
        finally:
            self._close(conn)

    def register(
        self,
        snapshot_id: str,
        mission_id: str,
        workspace_root: str,
        files_covered: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO rollback_entries "
                "(snapshot_id, mission_id, workspace_root, created_at, "
                " files_covered_json, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    snapshot_id,
                    mission_id,
                    workspace_root,
                    created_at or _utc_now(),
                    json.dumps(files_covered or []),
                    json.dumps(metadata or {}),
                ),
            )
            conn.commit()
        finally:
            self._close(conn)

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> RegistryEntry:
        return RegistryEntry(
            snapshot_id=row["snapshot_id"],
            mission_id=row["mission_id"],
            workspace_root=row["workspace_root"],
            created_at=row["created_at"],
            files_covered=json.loads(row["files_covered_json"]),
            metadata=json.loads(row["metadata_json"]),
        )

    def query(
        self,
        *,
        mission_id: str | None = None,
        after: str | None = None,
        before: str | None = None,
        file_pattern: str | None = None,
        workspace_root: str | None = None,
        limit: int = 100,
    ) -> list[RegistryEntry]:
        clauses: list[str] = []
        params: list[Any] = []
        if mission_id is not None:
            clauses.append("mission_id = ?")
            params.append(mission_id)
        if workspace_root is not None:
            clauses.append("workspace_root = ?")
            params.append(workspace_root)
        if after is not None:
            clauses.append("created_at >= ?")
            params.append(after)
        if before is not None:
            clauses.append("created_at <= ?")
            params.append(before)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM rollback_entries {where} ORDER BY created_at ASC, id ASC"

        conn = self._conn()
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            self._close(conn)

        entries = [self._row_to_entry(row) for row in rows]

        if file_pattern is not None:
            entries = [
                entry
                for entry in entries
                if any(fnmatch.fnmatch(f, file_pattern) for f in entry.files_covered)
            ]

        return entries[:limit]

    def get(self, snapshot_id: str) -> RegistryEntry | None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM rollback_entries WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
        finally:
            self._close(conn)
        return self._row_to_entry(row) if row is not None else None

    def prune(self) -> int:
        cutoff = (
            (datetime.now(timezone.utc) - timedelta(days=self._retention_days))
            .replace(microsecond=0)
            .isoformat()
        )
        conn = self._conn()
        try:
            cur = conn.execute(
                "DELETE FROM rollback_entries WHERE created_at < ?",
                (cutoff,),
            )
            conn.commit()
            return cur.rowcount
        finally:
            self._close(conn)

    def health(self) -> dict[str, Any]:
        conn = self._conn()
        try:
            total_row = conn.execute(
                "SELECT COUNT(*) AS c FROM rollback_entries"
            ).fetchone()
            workspace_rows = conn.execute(
                "SELECT workspace_root, COUNT(*) AS c FROM rollback_entries "
                "GROUP BY workspace_root"
            ).fetchall()
            bounds = conn.execute(
                "SELECT MIN(created_at) AS oldest, MAX(created_at) AS newest "
                "FROM rollback_entries"
            ).fetchone()
        finally:
            self._close(conn)

        workspaces = {row["workspace_root"]: int(row["c"]) for row in workspace_rows}
        return {
            "total": int(total_row["c"]),
            "workspaces": workspaces,
            "oldest": bounds["oldest"],
            "newest": bounds["newest"],
            "retention_days": self._retention_days,
        }

    def count(self) -> int:
        conn = self._conn()
        try:
            row = conn.execute("SELECT COUNT(*) AS c FROM rollback_entries").fetchone()
            return int(row["c"])
        finally:
            self._close(conn)


__all__ = ["RegistryEntry", "RollbackRegistry"]
