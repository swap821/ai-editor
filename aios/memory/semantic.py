"""L3 Semantic memory: durable knowledge chunks with synced vector embeddings.

Each :meth:`SemanticMemory.add` call inserts a row, embeds its text, and adds
the embedding to the FAISS index under the row's own id (via ``IndexIDMap``),
keeping the relational and vector stores in lock-step. The embedding model and
vector index are injected for testability and lazily constructed otherwise, so
no heavy model loads until the first semantic write or search.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from aios import config
from aios.memory.db import get_connection
from aios.memory.embeddings import EmbeddingModel, VectorIndex


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

        The SQLite row is committed first; the vector is then added under the
        same id and the index flushed to disk. Returns the new row/vector id.
        """
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
        vector = self.embedder.encode(text)[0]
        self.index.add(mem_id, vector)
        self.index.persist()
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
