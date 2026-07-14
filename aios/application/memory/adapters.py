"""Compatibility adapters for existing specialized memory stores."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from aios.domain.memory import MemoryHit, MemoryRecallContext
from aios.memory.retrieval import hybrid_search


class LegacySemanticMemoryAdapter:
    """Route semantic similarity through the existing FAISS/BM25 store.

    The legacy semantic table has no project column.  It is therefore exposed
    only when the caller has not requested project-scoped recall; project-aware
    memory must be migrated through a project-aware adapter before it is used.
    """

    memory_types = ("semantic", "chat", "lesson", "fact", "preference", "procedure")

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def recall(self, query: str, context: MemoryRecallContext) -> tuple[MemoryHit, ...]:
        if context.project_id:
            return ()
        results = hybrid_search(query, top_k=context.limit, db_path=self.db_path)
        return tuple(
            MemoryHit(
                record_id=f"semantic:{result.id}",
                external_id=result.id,
                memory_type=result.memory_type,
                content_reference=f"semantic_memory:{result.id}",
                text=result.text,
                score=result.score,
                bm25=result.bm25,
                faiss=result.faiss,
                recency=result.recency,
                verification_status=result.verification_status,
                source="legacy.semantic_memory",
            )
            for result in results
        )

    def rebuild_derived_indexes(self) -> None:
        """The existing semantic store owns its index rebuild operation."""
        return None


class AdvisoryPheromoneAdapter:
    """Expose decaying pheromones as routing hints, never as authority."""

    memory_types = ("pheromone",)

    def __init__(self, store: Any) -> None:
        self.store = store

    def recall(self, query: str, context: MemoryRecallContext) -> tuple[MemoryHit, ...]:
        if not context.project_id:
            return ()
        pheromones = self.store.query(resource=query, limit=context.limit)
        return tuple(
            MemoryHit(
                memory_type="pheromone",
                content_reference=f"pheromone:{item.pheromone_id}",
                text=str(item.payload.get("summary", "")),
                score=item.strength,
                verification_status="advisory",
                project_id=context.project_id,
                source="pheromone_store",
                advisory=True,
            )
            for item in pheromones
        )

    def rebuild_derived_indexes(self) -> None:
        return None


__all__ = ["AdvisoryPheromoneAdapter", "LegacySemanticMemoryAdapter"]
