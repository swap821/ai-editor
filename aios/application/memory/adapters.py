"""Compatibility adapters for existing specialized memory stores."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from aios.domain.memory import MemoryHit, MemoryRecallContext
from aios.memory.db import get_connection, init_memory_db
from aios.memory.consolidation import MemoryConsolidator
from aios.memory.compaction import MemoryCompactor
from aios.memory.development import DevelopmentTracker
from aios.memory.episodic import EpisodicMemory
from aios.memory.facts import SemanticFacts
from aios.memory.mistake import MistakeMemory
from aios.memory.retrieval import hybrid_search
from aios.memory.semantic import SemanticMemory
from aios.memory.skills import SkillMemory
from aios.memory.working import WorkingMemory

if TYPE_CHECKING:
    from aios.council.council_memory import CouncilMemory


class LegacySemanticMemoryAdapter:
    """Route semantic similarity through the existing FAISS/BM25 store.

    The legacy semantic table has no project column.  It is therefore exposed
    only when the caller has not requested project-scoped recall; project-aware
    memory must be migrated through a project-aware adapter before it is used.
    """

    memory_types = ("semantic", "chat", "lesson", "fact", "preference", "procedure")

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.store = SemanticMemory(self.db_path)

    @property
    def index(self) -> Any:
        """Expose the specialist's vector index through the authority seam."""
        return self.store.index

    def recall(
        self,
        query: str,
        context: MemoryRecallContext,
        *,
        retrieval_fn: Any = hybrid_search,
    ) -> tuple[MemoryHit, ...]:
        if context.project_id:
            return ()
        results = retrieval_fn(query, top_k=context.limit)
        hits: list[MemoryHit] = []
        for position, result in enumerate(results):
            external_id = getattr(result, "id", None)
            stable_id = external_id if external_id is not None else position
            hits.append(
                MemoryHit(
                    record_id=f"semantic:{stable_id}",
                    external_id=external_id,
                    memory_type=str(getattr(result, "memory_type", "chat")),
                    content_reference=f"semantic_memory:{stable_id}",
                    text=str(getattr(result, "text", "")),
                    score=float(getattr(result, "score", 0.0)),
                    bm25=float(getattr(result, "bm25", 0.0)),
                    faiss=float(getattr(result, "faiss", 0.0)),
                    recency=float(getattr(result, "recency", 0.0)),
                    verification_status=str(
                        getattr(result, "verification_status", "unverified")
                    ),
                    source="legacy.semantic_memory",
                )
            )
        return tuple(hits)

    def record_chat(self, content: str, *, indexer: Any | None = None) -> int:
        """Persist a scrubbed unverified chat observation via the semantic store."""
        target = indexer if indexer is not None else self.store
        try:
            return int(
                target.add(
                    content,
                    memory_type="chat",
                    verification_status="unverified",
                )
            )
        except TypeError:
            return int(target.add(content))

    def add(self, *args: Any, **kwargs: Any) -> int:
        return int(self.store.add(*args, **kwargs))

    def promote(self, mem_id: int) -> None:
        self.store.promote(mem_id)

    def supersede_text(self, text: str) -> int:
        return int(self.store.supersede_text(text))

    def rebuild_derived_indexes(self) -> None:
        """The existing semantic store owns its index rebuild operation."""
        return None


class EpisodicMemoryAdapter:
    """Authority adapter for the chronological session memory store."""

    memory_types = ("episodic", "chat")

    def __init__(self, store: EpisodicMemory) -> None:
        self.store = store

    def _ensure_schema(self) -> None:
        """Make the adapter safe before API lifespan startup or test setup."""
        init_memory_db(self.store.db_path)

    def record(self, session_id: str, role: str, content: str) -> int:
        self._ensure_schema()
        return self.store.record(session_id, role, content)

    def recent(self, session_id: str, limit: int) -> list[Any]:
        self._ensure_schema()
        return self.store.recent(session_id, limit)

    def count(self, session_id: str | None = None) -> int:
        self._ensure_schema()
        return self.store.count(session_id)

    def recall(self, query: str, context: MemoryRecallContext) -> tuple[MemoryHit, ...]:
        if not context.session_id:
            return ()
        self._ensure_schema()
        query_lower = query.casefold().strip()
        hits: list[MemoryHit] = []
        for row in self.store.recent(context.session_id, context.limit):
            content = str(row["content"])
            if query_lower and query_lower not in content.casefold():
                continue
            hits.append(
                MemoryHit(
                    record_id=f"episodic:{row['id']}",
                    external_id=int(row["id"]),
                    memory_type="episodic",
                    content_reference=f"episodic_memory:{row['id']}",
                    text=content,
                    verification_status="unverified",
                    source="episodic_memory",
                )
            )
        return tuple(hits)

    def rebuild_derived_indexes(self) -> None:
        return None


class WorkingMemoryAdapter:
    """Authority-owned facade for the process-local working-memory store."""

    memory_types = ("working",)

    def __init__(self, store: WorkingMemory) -> None:
        self.store = store

    def set(self, *args: Any, **kwargs: Any) -> None:
        self.store.set(*args, **kwargs)

    def get(self, *args: Any, **kwargs: Any) -> Any:
        return self.store.get(*args, **kwargs)

    def append_message(self, *args: Any, **kwargs: Any) -> None:
        self.store.append_message(*args, **kwargs)

    def history(self, *args: Any, **kwargs: Any) -> list[dict[str, str]]:
        return list(self.store.history(*args, **kwargs))

    def clear(self, *args: Any, **kwargs: Any) -> None:
        self.store.clear(*args, **kwargs)

    def sessions(self) -> list[str]:
        return list(self.store.sessions())

    def recall(self, query: str, context: MemoryRecallContext) -> tuple[MemoryHit, ...]:
        return ()

    def rebuild_derived_indexes(self) -> None:
        return None


class SemanticFactsAdapter:
    """Authority adapter for contradiction-aware, human-approved facts."""

    memory_types = ("fact", "facts", "preference")

    def __init__(self, store: SemanticFacts) -> None:
        self.store = store

    def recall(self, query: str, context: MemoryRecallContext) -> tuple[MemoryHit, ...]:
        hits: list[MemoryHit] = []
        for position, row in enumerate(self.store.search(query)[: context.limit]):
            subject = str(row["subject"])
            predicate = str(row["predicate"])
            obj = str(row["object"])
            hits.append(
                MemoryHit(
                    record_id=f"fact:{position}",
                    memory_type="fact",
                    content_reference=f"semantic_facts:{subject}:{predicate}:{obj}",
                    text=f"{subject} {predicate} {obj}",
                    verification_status="verified",
                    source="semantic_facts",
                )
            )
        return tuple(hits)

    def search(self, query: str) -> list[Any]:
        init_memory_db(self.store.db_path)
        return self.store.search(query)

    def strengthen_or_propose(
        self, subject: str, predicate: str, obj: str, *, source: str = "auto-extract"
    ) -> Any:
        return self.store.strengthen_or_propose(subject, predicate, obj, source=source)

    def add_fact(self, *args: Any, **kwargs: Any) -> Any:
        return self.store.add_fact(*args, **kwargs)

    def reconcile(self, *args: Any, **kwargs: Any) -> Any:
        return self.store.reconcile(*args, **kwargs)

    def pending_proposals(self, limit: int = 100) -> list[Any]:
        init_memory_db(self.store.db_path)
        return self.store.pending_proposals(limit)

    def approve_proposal(self, proposal_id: int, *, approved_by: str) -> Any:
        return self.store.approve_proposal(proposal_id, approved_by=approved_by)

    def reject_proposal(self, proposal_id: int, *, rejected_by: str) -> bool:
        return self.store.reject_proposal(proposal_id, rejected_by=rejected_by)

    def neighbors(self, subject: str) -> list[Any]:
        init_memory_db(self.store.db_path)
        return self.store.neighbors(subject)

    def facts_for(self, subject: str, predicate: str | None = None) -> list[Any]:
        init_memory_db(self.store.db_path)
        return self.store.facts_for(subject, predicate)

    def operator_model(self) -> dict[str, Any]:
        """Build the operator snapshot from authority-owned fact reads."""
        operator_facts = self.facts_for("operator")
        project_facts = self.facts_for("project")
        init_memory_db(self.store.db_path)
        with get_connection(self.store.db_path) as conn:
            attr_rows = conn.execute(
                "SELECT * FROM semantic_facts "
                "WHERE subject LIKE 'operator.%' AND status = 'active' "
                "ORDER BY id DESC",
            ).fetchall()

        preferences = [
            {
                "predicate": str(row["predicate"]),
                "object": str(row["object"]),
            }
            for row in operator_facts
        ]
        attributes = {
            str(row["subject"]).removeprefix("operator."): str(row["object"])
            for row in attr_rows
        }
        project_context = [
            {
                "predicate": str(row["predicate"]),
                "object": str(row["object"]),
            }
            for row in project_facts
        ]
        return {
            "preferences": preferences,
            "attributes": attributes,
            "project_context": project_context,
        }

    def rows_by_status(self, status: str) -> list[Any]:
        init_memory_db(self.store.db_path)
        with get_connection(self.store.db_path) as conn:
            return list(
                conn.execute(
                    "SELECT * FROM semantic_facts WHERE status = ? ORDER BY id",
                    (status,),
                ).fetchall()
            )

    def traverse_weighted(
        self,
        subject: str,
        *,
        max_depth: int = 3,
        min_path_confidence: float = 0.3,
    ) -> list[Any]:
        init_memory_db(self.store.db_path)
        return self.store.traverse_weighted(
            subject,
            max_depth=max_depth,
            min_path_confidence=min_path_confidence,
        )

    def traverse(self, subject: str, max_depth: int = 2) -> list[Any]:
        init_memory_db(self.store.db_path)
        return self.store.traverse(subject, max_depth=max_depth)

    def rebuild_derived_indexes(self) -> None:
        return None


class SkillMemoryAdapter:
    """Authority adapter for repeatedly verified reusable workflows."""

    memory_types = ("skill", "workflow")

    def __init__(self, store: SkillMemory) -> None:
        self.store = store

    def relevant_verified(self, query: str, limit: int) -> list[dict[str, Any]]:
        return self.store.relevant_verified(query, limit)

    def record_attempt(self, *args: Any, **kwargs: Any) -> int:
        return int(self.store.record_attempt(*args, **kwargs))

    def record_reuse(self, *args: Any, **kwargs: Any) -> list[int]:
        return list(self.store.record_reuse(*args, **kwargs))

    def list(self, *, status: str | None = None) -> list[dict[str, Any]]:
        return list(self.store.list(status=status))

    def trail_map(self) -> dict[str, Any]:
        return dict(self.store.trail_map())

    def recall(self, query: str, context: MemoryRecallContext) -> tuple[MemoryHit, ...]:
        rows = self.relevant_verified(query, context.limit)
        return tuple(
            MemoryHit(
                record_id=f"skill:{row['skill_id']}",
                external_id=int(row["skill_id"]),
                memory_type="workflow",
                content_reference=f"procedural_skills:{row['skill_id']}",
                text=str(row["goal_pattern"]),
                score=float(row.get("relevance", 0.0)),
                verification_status="verified",
                source="procedural_skills",
            )
            for row in rows
        )

    def rebuild_derived_indexes(self) -> None:
        return None


class MistakeMemoryAdapter:
    """Authority adapter for pending and verified lessons."""

    memory_types = ("lesson", "mistake")

    def __init__(self, store: MistakeMemory) -> None:
        self.store = store

    def recall_relevant(
        self, query: str, task_id: str, limit: int
    ) -> list[dict[str, Any]]:
        pending = [
            {
                "mistake_id": int(row["id"]),
                "error_type": str(row["error_type"]),
                "lesson_text": str(row["lesson_text"]),
                "verification_status": "pending",
                "relevance": 1.0,
            }
            for row in self.store.pending_for_task(task_id, limit)
        ]
        remaining = max(limit - len(pending), 0)
        verified = self.store.relevant_verified(query, remaining)
        pending_ids = {lesson["mistake_id"] for lesson in pending}
        return pending + [
            lesson for lesson in verified if lesson["mistake_id"] not in pending_ids
        ]

    def recurring(self, limit: int = 3) -> list[dict[str, Any]]:
        return self.store.recurring(limit=limit)

    def record_or_increment(self, *args: Any, **kwargs: Any) -> tuple[int, bool]:
        return self.store.record_or_increment(*args, **kwargs)

    def record(self, *args: Any, **kwargs: Any) -> int:
        return int(self.store.record(*args, **kwargs))

    def get(self, mistake_id: int) -> Any:
        return self.store.get(mistake_id)

    def rows_by_status(self, status: str) -> list[Any]:
        init_memory_db(self.store.db_path)
        with get_connection(self.store.db_path) as conn:
            return list(
                conn.execute(
                    "SELECT * FROM mistake_pool WHERE verification_status = ? ORDER BY id",
                    (status,),
                ).fetchall()
            )

    def promote(self, mistake_id: int, **kwargs: Any) -> None:
        self.store.promote(mistake_id, **kwargs)

    def pending_command_pairs(self, task_id: str) -> list[tuple[int, str]]:
        return self.store.pending_command_pairs(task_id)

    def pending_for_task(self, task_id: str, limit: int = 5) -> list[Any]:
        return self.store.pending_for_task(task_id, limit)

    def relevant_verified(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        return self.store.relevant_verified(query, limit)

    def recall(self, query: str, context: MemoryRecallContext) -> tuple[MemoryHit, ...]:
        rows = self.recall_relevant(query, context.session_id or "", context.limit)
        return tuple(
            MemoryHit(
                record_id=f"lesson:{row['mistake_id']}",
                external_id=int(row["mistake_id"]),
                memory_type="lesson",
                content_reference=f"mistake_pool:{row['mistake_id']}",
                text=str(row["lesson_text"]),
                score=float(row.get("relevance", 0.0)),
                verification_status=str(row.get("verification_status", "pending")),
                source="mistake_pool",
            )
            for row in rows
        )

    def rebuild_derived_indexes(self) -> None:
        return None


class DevelopmentHistoryAdapter:
    """Authority adapter for evidence-backed developmental history."""

    memory_types = ("development", "history")

    def __init__(self, store: DevelopmentTracker) -> None:
        self.store = store

    def task_profile(self) -> dict[str, tuple[int, float]]:
        return self.store.task_profile()

    def record(self, *args: Any, **kwargs: Any) -> int:
        return int(self.store.record(*args, **kwargs))

    def relevant_success_rate(self, *args: Any, **kwargs: Any) -> Any:
        return self.store.relevant_success_rate(*args, **kwargs)

    def model_task_success_rates(self, *args: Any, **kwargs: Any) -> Any:
        return self.store.model_task_success_rates(*args, **kwargs)

    def summary(self) -> dict[str, Any]:
        return dict(self.store.summary())


class MemoryConsolidationAdapter:
    """Route trusted-memory consolidation through the authority boundary."""

    memory_types = ("consolidation", "promotion")

    def __init__(self, service: MemoryConsolidator) -> None:
        self.service = service
        # Expose the wrapped service as the canonical store for the authority's
        # dependency-injection ownership check.
        self.store = service

    def bind_authority(self, authority: Any) -> None:
        self.service.memory_authority = authority

    def consolidate_lesson(self, *args: Any, **kwargs: Any) -> Any:
        return self.service.consolidate_lesson(*args, **kwargs)

    def promote_fact(self, *args: Any, **kwargs: Any) -> Any:
        return self.service.promote_fact(*args, **kwargs)

    def reconcile_fact(self, *args: Any, **kwargs: Any) -> Any:
        return self.service.reconcile_fact(*args, **kwargs)

    def run(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return dict(self.service.run(*args, **kwargs))

    def recall(self, query: str, context: MemoryRecallContext) -> tuple[MemoryHit, ...]:
        return ()

    def rebuild_derived_indexes(self) -> None:
        return None


class MemoryCompactionAdapter:
    """Route operator-triggered forgetting through MemoryAuthority."""

    memory_types = ("compaction",)

    def __init__(self, service: MemoryCompactor) -> None:
        self.service = service
        self.store = service

    def compact(self, *, dry_run: bool = True) -> dict[str, Any]:
        return dict(self.service.compact(dry_run=dry_run))

    def preview(self) -> Any:
        return self.service.preview()

    def touch_working_session(self, session_id: str) -> None:
        self.service.touch_working_session(session_id)

    def recall(self, query: str, context: MemoryRecallContext) -> tuple[MemoryHit, ...]:
        return ()

    def rebuild_derived_indexes(self) -> None:
        return None


class CouncilMemoryAdapter:
    """Route mission-local advisory deliberation evidence through authority."""

    memory_types = ("council", "deliberation")

    def __init__(self, store: "CouncilMemory") -> None:
        self.store = store

    def record_deliberation(self, *args: Any, **kwargs: Any) -> int:
        return int(self.store.record_deliberation(*args, **kwargs))

    def deliberations_for(self, mission_id: str) -> list[dict[str, Any]]:
        return list(self.store.deliberations_for(mission_id))

    def recall(self, query: str, context: MemoryRecallContext) -> tuple[MemoryHit, ...]:
        return ()

    def rebuild_derived_indexes(self) -> None:
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

    def query(self, *args: Any, **kwargs: Any) -> list[Any]:
        return list(self.store.query(*args, **kwargs))

    def for_contract(self, allowed_files: list[str]) -> list[str]:
        return list(self.store.for_contract(allowed_files))

    def deposit(self, *args: Any, **kwargs: Any) -> int:
        return int(self.store.deposit(*args, **kwargs))

    def reinforce(self, *args: Any, **kwargs: Any) -> None:
        self.store.reinforce(*args, **kwargs)

    def decay_all(self) -> int:
        return int(self.store.decay_all())

    def rebuild_derived_indexes(self) -> None:
        return None


__all__ = [
    "AdvisoryPheromoneAdapter",
    "EpisodicMemoryAdapter",
    "WorkingMemoryAdapter",
    "LegacySemanticMemoryAdapter",
    "MistakeMemoryAdapter",
    "DevelopmentHistoryAdapter",
    "MemoryConsolidationAdapter",
    "MemoryCompactionAdapter",
    "CouncilMemoryAdapter",
    "SemanticFactsAdapter",
    "SkillMemoryAdapter",
]
