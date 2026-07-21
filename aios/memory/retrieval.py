"""Hybrid memory retrieval: lexical (BM25) + semantic (FAISS) + temporal decay.

Implements the blueprint relevance score::

    R(q, m, t) = alpha * S_BM25(q, m)
               + beta  * S_FAISS(q, m)
               + gamma * exp(-lambda * delta_t_hours)

with the weights and decay constant sourced from :mod:`aios.config`
(alpha=0.25, beta=0.45, gamma=0.30, lambda=0.05/hr by default).

The pipeline first retrieves a candidate pool from FAISS (``top_k *
candidate_multiplier``), then re-ranks those candidates with real Okapi BM25
(via ``rank-bm25``) over the candidate corpus, a cosine-similarity term from
FAISS, and an exponential recency term. This improves on the legacy
implementation in three ways: real BM25 instead of naive term overlap, explicit
id mapping instead of positional coupling, and UTC-correct decay timing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rank_bm25 import BM25Okapi

from aios import config
from aios.memory.db import get_connection
from aios.memory.embeddings import EmbeddingModel, VectorIndex

#: SQLite ``CURRENT_TIMESTAMP`` formats we may encounter when parsing rows.
_TIMESTAMP_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
)


@dataclass(frozen=True)
class RetrievalResult:
    """One ranked memory hit with its component sub-scores (for explainability)."""

    id: int
    text: str
    score: float
    bm25: float
    faiss: float
    recency: float
    memory_type: str = "chat"
    verification_status: str = "unverified"


def _hours_since(timestamp: str, now: datetime) -> float:
    """Return hours elapsed between a SQLite UTC timestamp and *now* (>= 0)."""
    parsed: Optional[datetime] = None
    for fmt in _TIMESTAMP_FORMATS:
        try:
            parsed = datetime.strptime(timestamp, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(timestamp)
        except ValueError:
            return 0.0
    return max((now - parsed).total_seconds() / 3600.0, 0.0)


def hybrid_search(
    query: str,
    top_k: int = 3,
    *,
    candidate_multiplier: int = 4,
    db_path: Path = config.MEMORY_DB_PATH,
    index: Optional[VectorIndex] = None,
    embedder: Optional[EmbeddingModel] = None,
) -> list[RetrievalResult]:
    """Return the top-*k* semantic memories for *query*, hybrid-ranked.

    Args:
        query: Natural-language search string.
        top_k: Number of results to return.
        candidate_multiplier: FAISS candidate pool size as a multiple of
            *top_k* before re-ranking. Larger values trade latency for recall.
        db_path: Memory database to read ``semantic_memory`` rows from.
        index: Vector index to search (constructed lazily if omitted).
        embedder: Embedding model to encode the query (singleton if omitted).

    Returns:
        Up to *top_k* :class:`RetrievalResult` objects, highest score first.
        Empty when the query is blank or the index holds no vectors.
    """
    if not query or not query.strip() or top_k <= 0:
        return []

    # Construct the index first and short-circuit on an empty store, so we never
    # pay the cost of loading the embedding model just to return no results.
    index = index or VectorIndex()
    if index.size == 0:
        return []
    embedder = embedder or EmbeddingModel.instance()

    query_vector = embedder.encode(query)[0]
    candidate_count = min(max(top_k * candidate_multiplier, top_k, 1), index.size)
    rows = []
    faiss_by_id: dict[int, float] = {}
    while candidate_count > 0:
        candidates = index.search(query_vector, candidate_count)
        if not candidates:
            return []
        faiss_by_id = {cid: score for cid, score in candidates}
        candidate_ids = list(faiss_by_id.keys())
        placeholders = ",".join("?" for _ in candidate_ids)
        with get_connection(db_path) as conn:
            rows = conn.execute(
                "SELECT id, text_content, timestamp, memory_type, verification_status "
                "FROM semantic_memory WHERE id IN (" + placeholders + ") "
                "AND verification_status != 'superseded'",
                candidate_ids,
            ).fetchall()
        if len(rows) >= top_k or candidate_count >= index.size:
            break
        candidate_count = min(index.size, candidate_count * 2)
    if not rows:
        return []

    # Real Okapi BM25 over the candidate corpus, normalised to [0, 1].
    corpus_tokens = [row["text_content"].lower().split() for row in rows]
    bm25 = BM25Okapi(corpus_tokens)
    raw_bm25 = bm25.get_scores(query.lower().split())
    max_bm25 = float(max(raw_bm25)) if len(raw_bm25) else 0.0
    bm25_norm = max_bm25 if max_bm25 > 0.0 else 1.0

    # Naive UTC to match SQLite CURRENT_TIMESTAMP strings (which carry no tz).
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    results: list[RetrievalResult] = []
    for row, raw in zip(rows, raw_bm25):
        mem_id = int(row["id"])
        s_bm25 = float(raw) / bm25_norm
        # Cosine similarity from FAISS, clamped into [0, 1].
        s_faiss = max(0.0, min(1.0, faiss_by_id.get(mem_id, 0.0)))
        delta_t_hours = _hours_since(row["timestamp"], now)
        s_recency = math.exp(-config.RETRIEVAL_LAMBDA_DECAY_PER_HOUR * delta_t_hours)

        score = (
            config.RETRIEVAL_ALPHA_BM25 * s_bm25
            + config.RETRIEVAL_BETA_FAISS * s_faiss
            + config.RETRIEVAL_GAMMA_RECENCY * s_recency
        )
        results.append(
            RetrievalResult(
                id=mem_id,
                text=row["text_content"],
                score=round(score, 6),
                bm25=round(s_bm25, 6),
                faiss=round(s_faiss, 6),
                recency=round(s_recency, 6),
                memory_type=str(row["memory_type"]),
                verification_status=str(row["verification_status"]),
            )
        )

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:top_k]
