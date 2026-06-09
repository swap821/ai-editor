"""Embedding model + FAISS vector index for the semantic memory layer.

Two collaborators live here:

* :class:`EmbeddingModel` — a thread-safe lazy singleton around a
  sentence-transformers encoder. The ~90 MB ``all-MiniLM-L6-v2`` weights are
  loaded on first use (not at import), so importing this module stays cheap and
  test collection is fast. Embeddings are L2-normalised, so inner product
  equals cosine similarity.

* :class:`VectorIndex` — a persistent HNSW FAISS index wrapped in an
  ``IndexIDMap`` so each vector is bound explicitly to its owning
  ``semantic_memory.id``. This removes the fragile positional coupling the
  legacy implementation relied on (where the FAISS ordinal was assumed to equal
  the SQLite row id). Inner-product metric over normalised vectors means search
  scores ARE cosine similarities in ``[-1, 1]``.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional, Sequence, Union

import faiss
import numpy as np

from aios import config

#: HNSW neighbour count (graph connectivity). 32 matches the legacy index.
_HNSW_M: int = 32
#: Build-time and query-time search breadth (higher = more accurate, slower).
_HNSW_EF_CONSTRUCTION: int = 200
_HNSW_EF_SEARCH: int = 128


class EmbeddingModel:
    """Thread-safe lazy singleton wrapping a sentence-transformers encoder."""

    _instance: Optional["EmbeddingModel"] = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        # Imported lazily so that importing this module does not pull in torch.
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(config.EMBEDDING_MODEL)
        self.dim: int = config.EMBEDDING_DIM

    @classmethod
    def instance(cls) -> "EmbeddingModel":
        """Return the process-wide singleton, constructing it on first call."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def encode(self, texts: Union[str, Sequence[str]]) -> np.ndarray:
        """Encode text(s) into L2-normalised float32 embeddings.

        Args:
            texts: A single string or a sequence of strings.

        Returns:
            A ``(n, dim)`` float32 array of unit-norm row vectors, where ``n``
            is 1 for a single string input.
        """
        batch = [texts] if isinstance(texts, str) else list(texts)
        vectors = self._model.encode(batch, normalize_embeddings=True)
        return np.asarray(vectors, dtype="float32")


class VectorIndex:
    """Persistent FAISS HNSW index mapping vector ids to ``semantic_memory.id``.

    Loaded from :data:`aios.config.FAISS_INDEX_PATH` if present, otherwise
    created empty. Not internally locked: callers that mutate it concurrently
    must serialise access and reload after acquiring their cross-process lock.
    """

    def __init__(
        self,
        path: Path = config.FAISS_INDEX_PATH,
        dim: int = config.EMBEDDING_DIM,
    ) -> None:
        self.path: Path = path
        self.dim: int = dim
        self._lock = threading.RLock()
        self._index = self._load_or_create()
        self._loaded_mtime_ns = self._mtime_ns()

    def _mtime_ns(self) -> Optional[int]:
        """Current durable index timestamp, or ``None`` when it does not exist."""
        try:
            return self.path.stat().st_mtime_ns
        except FileNotFoundError:
            return None

    def _load_or_create(self) -> "faiss.Index":
        """Read the index from disk, or build a fresh empty IDMap+HNSW index."""
        if self.path.exists():
            return faiss.read_index(str(self.path))
        base = faiss.IndexHNSWFlat(self.dim, _HNSW_M, faiss.METRIC_INNER_PRODUCT)
        base.hnsw.efConstruction = _HNSW_EF_CONSTRUCTION
        base.hnsw.efSearch = _HNSW_EF_SEARCH
        return faiss.IndexIDMap(base)

    def add(self, vector_id: int, vector: np.ndarray) -> None:
        """Add one ``dim``-length vector under an explicit integer id."""
        row = np.ascontiguousarray(vector.reshape(1, -1), dtype="float32")
        ids = np.asarray([vector_id], dtype="int64")
        with self._lock:
            self._index.add_with_ids(row, ids)

    def reload(self) -> None:
        """Reload the latest durable index while the caller holds its write lock."""
        with self._lock:
            self._index = self._load_or_create()
            self._loaded_mtime_ns = self._mtime_ns()

    def _refresh_if_changed(self) -> None:
        """Make long-lived readers observe an index persisted by another process."""
        if self._mtime_ns() != self._loaded_mtime_ns:
            self.reload()

    def search(self, query_vector: np.ndarray, k: int) -> list[tuple[int, float]]:
        """Return up to ``k`` ``(semantic_memory.id, cosine_similarity)`` pairs.

        Returns an empty list when the index is empty. Sentinel ids of ``-1``
        (FAISS "no result") are filtered out.
        """
        with self._lock:
            self._refresh_if_changed()
            if self.size == 0 or k <= 0:
                return []
            query = np.ascontiguousarray(query_vector.reshape(1, -1), dtype="float32")
            scores, ids = self._index.search(query, min(k, self.size))
            return [
                (int(idx), float(score))
                for idx, score in zip(ids[0], scores[0])
                if idx != -1
            ]

    def persist(self) -> None:
        """Atomically flush the index to its on-disk path."""
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            faiss.write_index(self._index, str(tmp))
            tmp.replace(self.path)
            self._loaded_mtime_ns = self._mtime_ns()

    @property
    def size(self) -> int:
        """Number of vectors currently stored in the index."""
        with self._lock:
            return int(self._index.ntotal)
