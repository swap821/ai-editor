"""L3 Semantic memory: durable knowledge chunks with synced vector embeddings.

Each :meth:`SemanticMemory.add` call inserts a row, embeds its text, and adds
the embedding to the FAISS index under the row's own id (via ``IndexIDMap``),
keeping the relational and vector stores in lock-step. The embedding model and
vector index are injected for testability and lazily constructed otherwise, so
no heavy model loads until the first semantic write or search.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Optional

from filelock import FileLock

from aios import config
from aios.memory.db import get_connection
from aios.memory.embeddings import EmbeddingModel, VectorIndex
from aios.security.secret_scanner import scan_and_redact

_SEMANTIC_WRITE_LOCK = threading.Lock()
_LOCK_TIMEOUT_S = 30


class SemanticMemory:
    """CRUD facade over ``semantic_memory`` plus its FAISS vector index."""

    def __init__(
        self,
        db_path: Path = config.MEMORY_DB_PATH,
        *,
        index: Optional[VectorIndex] = None,
        embedder: Optional[EmbeddingModel] = None,
    ) -> None:
        self.db_path = db_path
        self._index = index
        self._embedder = embedder

    @property
    def write_lock_path(self) -> Path:
        """Lock file shared by every process writing this durable vector index."""
        index_path = getattr(self.index, "path", config.FAISS_INDEX_PATH)
        return Path(index_path).with_suffix(Path(index_path).suffix + ".lock")

    @property
    def index(self) -> VectorIndex:
        """The FAISS index, constructed on first access."""
        if self._index is None:
            self._index = VectorIndex()
        return self._index

    @property
    def embedder(self) -> EmbeddingModel:
        """The embedding model singleton, constructed on first access."""
        if self._embedder is None:
            self._embedder = EmbeddingModel.instance()
        return self._embedder

    def add(self, text: str) -> int:
        """Persist *text*, embed it, and add the vector to the index.

        The SQLite row supplies the stable vector id. If embedding, vector add,
        or index persistence fails afterward, the row is deleted again so the
        relational store never claims a semantic memory that cannot be retrieved.
        Returns the new row/vector id.
        """
        text = scan_and_redact(text).scrubbed
        self.write_lock_path.parent.mkdir(parents=True, exist_ok=True)
        with _SEMANTIC_WRITE_LOCK, FileLock(str(self.write_lock_path), timeout=_LOCK_TIMEOUT_S):
            with get_connection(self.db_path) as conn:
                cur = conn.execute(
                    "INSERT INTO semantic_memory (text_content) VALUES (?)",
                    (text,),
                )
                mem_id = int(cur.lastrowid)
                # Denormalise vector_id == id for legacy-tool compatibility.
                conn.execute(
                    "UPDATE semantic_memory SET vector_id = ? WHERE id = ?",
                    (mem_id, mem_id),
                )
            try:
                vector = self.embedder.encode(text)[0]
                # Another process may have persisted since this object loaded.
                # Reload under the shared lock before mutating to avoid lost updates.
                reload_index = getattr(self.index, "reload", None)
                if callable(reload_index):
                    reload_index()
                self.index.add(mem_id, vector)
                self.index.persist()
            except Exception:
                # Compensate the already-committed id allocation. A failed persist is
                # atomic on disk (VectorIndex writes a temp file then replaces), so
                # removing the DB row prevents durable DB/index drift. An in-process
                # orphan vector is harmless because retrieval joins candidates back
                # to existing DB rows and therefore filters it out.
                with get_connection(self.db_path) as conn:
                    conn.execute("DELETE FROM semantic_memory WHERE id = ?", (mem_id,))
                raise
        return mem_id

    def get(self, mem_id: int) -> Optional[sqlite3.Row]:
        """Return the row for *mem_id*, or ``None`` if it does not exist."""
        with get_connection(self.db_path) as conn:
            return conn.execute(
                "SELECT id, text_content, vector_id, timestamp "
                "FROM semantic_memory WHERE id = ?",
                (mem_id,),
            ).fetchone()

    def all(self) -> list[sqlite3.Row]:
        """Return every semantic row (used to assemble the BM25 corpus)."""
        with get_connection(self.db_path) as conn:
            return conn.execute(
                "SELECT id, text_content, vector_id, timestamp "
                "FROM semantic_memory ORDER BY id ASC"
            ).fetchall()

    def count(self) -> int:
        """Return the number of stored semantic chunks."""
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM semantic_memory"
            ).fetchone()
        return int(row["n"])
