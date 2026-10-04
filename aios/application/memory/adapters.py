"""Compatibility adapters for existing specialized memory stores."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from aios.application.memory import write_budget
from aios.application.memory.provenance_policy import (
    fact_digest,
    lesson_digest,
    semantic_digest,
)
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

#: How many candidates a gated recall reads per slot it fills: refused rows
#: must not silently shrink recall when admitted ones sit just below the cut.
_GATED_OVERFETCH = 3

if TYPE_CHECKING:
    from aios.application.memory.provenance_policy import (
        ProvenanceWriter,
        RecallGate,
    )
    from aios.core.cerebellum import Cerebellum
    from aios.council.council_memory import CouncilMemory
    from aios.memory.curriculum import CurriculumManager


class LegacySemanticMemoryAdapter:
    """Route semantic similarity through the existing FAISS/BM25 store.

    The legacy semantic table has no project column.  It is therefore exposed
    only when the caller has not requested project-scoped recall; project-aware
    memory must be migrated through a project-aware adapter before it is used.
    """

    memory_types = ("semantic", "chat", "lesson", "fact", "preference", "procedure")

    def __init__(
        self,
        store: SemanticMemory,
        *,
        provenance: Optional["ProvenanceWriter"] = None,
        gate: Optional["RecallGate"] = None,
    ) -> None:
        if not isinstance(store, SemanticMemory):
            raise RuntimeError("an explicit SemanticMemory store is required")
        self.store = store
        self.db_path = Path(store.db_path)
        #: Plan Phase 3c: recall admits only a memory whose provenance verifies.
        #: None: recall exactly as before (tests, fakes).
        self.gate = gate
        #: Plan Phase 3b: each write that changes what a memory's recall shows
        #: appends a signed record of its new state. None: write as before.
        self.provenance = provenance

    def _admits(self, result: Any, principal: Optional[str]) -> bool:
        """A retrieved memory is admitted only if its provenance verifies, for
        the principal it names (plan Phase 4c)."""
        mem_id = getattr(result, "id", None)
        if mem_id is None or self.gate is None:
            return False
        row = self.store.get(int(mem_id))
        return row is not None and self.gate.admits(
            "semantic_memory", mem_id, semantic_digest(row), principal=principal
        )

    def _prior(self, target: Any, text: Any, principal: Optional[str]) -> Any:
        """The row a write of *text* would consolidate into, read BEFORE it."""
        if self.provenance is None or not isinstance(text, str):
            return None
        finder = getattr(target, "duplicate_of", None)
        return finder(text, principal_id=principal) if callable(finder) else None

    def _attest(
        self,
        mem_id: int,
        transition: str,
        *,
        prior: Any = None,
        existed: bool,
        source: Any = None,
        principal: Optional[str],
    ) -> None:
        """A new row is attested as new; a repeat or a promotion extends the
        prior state, and is signed only if that state verifies. The record
        names the principal the row belongs to (plan Phase 4c), under the
        signature."""
        if self.provenance is None:
            return
        target = source if source is not None else self.store
        getter = getattr(target, "get", None)
        row = getter(int(mem_id)) if callable(getter) else None
        if row is None:
            return
        if not existed:
            self.provenance.attest_new(
                "semantic_memory",
                mem_id,
                semantic_digest(row),
                transition,
                principal=principal,
            )
            return
        prior_digest = (
            semantic_digest(prior)
            if prior is not None and int(prior["id"]) == int(mem_id)
            else None
        )
        self.provenance.attest_transition(
            "semantic_memory",
            mem_id,
            semantic_digest(row),
            transition,
            prior_digest=prior_digest,
            principal=principal,
        )

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
        top_k = context.limit * (_GATED_OVERFETCH if self.gate is not None else 1)
        results = retrieval_fn(query, top_k=top_k)
        if self.gate is not None:
            results = [r for r in results if self._admits(r, context.principal_id)][
                : context.limit
            ]
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

    def record_chat(
        self,
        content: str,
        *,
        indexer: Any | None = None,
        principal: Optional[str],
    ) -> int:
        """Persist a scrubbed unverified chat observation via the semantic store,
        as *principal*'s (plan Phase 4c)."""
        write_budget.spend(self, "semantic_memory")
        target = indexer if indexer is not None else self.store
        prior = self._prior(target, content, principal)
        try:
            mem_id = int(
                target.add(
                    content,
                    memory_type="chat",
                    verification_status="unverified",
                    principal_id=principal,
                )
            )
        except TypeError:
            # A legacy indexer that takes no keywords writes the row with no
            # principal: recall withholds it from everyone (plan Phase 4c), so
            # the fallback can never widen recall.
            mem_id = int(target.add(content))
        self._attest(
            mem_id,
            "recorded",
            prior=prior,
            existed=prior is not None,
            source=target,
            principal=principal,
        )
        return mem_id

    def add(self, *args: Any, principal: Optional[str], **kwargs: Any) -> int:
        write_budget.spend(self, "semantic_memory")
        prior = self._prior(
            self.store, args[0] if args else kwargs.get("text"), principal
        )
        mem_id = int(self.store.add(*args, principal_id=principal, **kwargs))
        self._attest(
            mem_id,
            "recorded",
            prior=prior,
            existed=prior is not None,
            principal=principal,
        )
        return mem_id

    def promote(self, mem_id: int, *, principal: Optional[str]) -> None:
        prior = self.store.get(int(mem_id)) if self.provenance is not None else None
        self.store.promote(mem_id, principal_id=principal)
        self._attest(
            int(mem_id), "promoted", prior=prior, existed=True, principal=principal
        )

    def supersede_text(self, text: str, *, principal: Optional[str]) -> int:
        return int(self.store.supersede_text(text, principal_id=principal))

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

    def __init__(
        self,
        store: SemanticFacts,
        *,
        provenance: Optional["ProvenanceWriter"] = None,
        gate: Optional["RecallGate"] = None,
    ) -> None:
        self.store = store
        #: Plan Phase 3b: a committed fact appends a signed record naming its
        #: approver. None: write as before.
        self.provenance = provenance
        #: Plan Phase 3c-2: the reads that feed a prompt -- search, neighbours,
        #: the operator block (facts_for) and the weighted traversal -- admit a
        #: fact only if its provenance verifies. A fact with no approver is
        #: recorded unsigned (3b), so it is never admitted. None: as before.
        #: Maintenance reads (rows_by_status) and the UI graph (traverse) are
        #: not recall, and stay ungated.
        self.gate = gate

    def _admits_row(self, row: Any, principal: Optional[str]) -> bool:
        if self.gate is None:
            return True
        return self.gate.admits(
            "semantic_facts", row["id"], fact_digest(row), principal=principal
        )

    def _admits_triple(
        self, subject: Any, predicate: Any, obj: Any, principal: Optional[str]
    ) -> bool:
        """An ACTIVE triple is unique per principal (add_fact refuses duplicates
        and contradictions within one principal's facts), so a triple and a
        principal name one row to verify."""
        if self.gate is None:
            return True
        init_memory_db(self.store.db_path)
        with get_connection(self.store.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM semantic_facts WHERE subject = ? AND predicate = ? "
                "AND object = ? AND status = 'active' AND principal_id IS ? "
                "ORDER BY id DESC LIMIT 1",
                (str(subject), str(predicate), str(obj), principal),
            ).fetchone()
        return row is not None and self._admits_row(row, principal)

    def _attest(self, result: Any, transition: str, principal: Optional[str]) -> Any:
        fact_id = getattr(result, "fact_id", None)
        if (
            self.provenance is None
            or not getattr(result, "committed", False)
            or fact_id is None
        ):
            return result
        row = self.store.get(int(fact_id))
        if row is None:
            return result
        if row["approved_by"]:
            # A named human approved exactly this triple: that act, not any
            # earlier record, is what the signature attests.
            self.provenance.attest_new(
                "semantic_facts",
                fact_id,
                fact_digest(row),
                transition,
                approver=row["approved_by"],
                principal=principal,
            )
        else:
            # No approver: recall never admits it anyway, and nothing earlier
            # can vouch for it. Recorded, unsigned.
            self.provenance.attest_transition(
                "semantic_facts",
                fact_id,
                fact_digest(row),
                transition,
                prior_digest=None,
                principal=principal,
            )
        return result

    def recall(self, query: str, context: MemoryRecallContext) -> tuple[MemoryHit, ...]:
        hits: list[MemoryHit] = []
        for position, row in enumerate(
            self.search(query, principal=context.principal_id)[: context.limit]
        ):
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

    def search(self, query: str, *, principal: Optional[str]) -> list[Any]:
        init_memory_db(self.store.db_path)
        return [
            row
            for row in self.store.search(query, principal_id=principal)
            if self._admits_triple(
                row["subject"], row["predicate"], row["object"], principal
            )
        ]

    def strengthen_or_propose(
        self,
        subject: str,
        predicate: str,
        obj: str,
        *,
        source: str = "auto-extract",
        principal: Optional[str],
    ) -> Any:
        write_budget.spend(self, "semantic_facts")
        return self.store.strengthen_or_propose(
            subject, predicate, obj, source=source, principal_id=principal
        )

    def add_fact(self, *args: Any, principal: Optional[str], **kwargs: Any) -> Any:
        write_budget.spend(self, "semantic_facts")
        return self._attest(
            self.store.add_fact(*args, principal_id=principal, **kwargs),
            "created",
            principal,
        )

    def reconcile(self, *args: Any, principal: Optional[str], **kwargs: Any) -> Any:
        return self._attest(
            self.store.reconcile(*args, principal_id=principal, **kwargs),
            "reconciled",
            principal,
        )

    def pending_proposals(
        self, limit: int = 100, *, principal: Optional[str]
    ) -> list[Any]:
        init_memory_db(self.store.db_path)
        return self.store.pending_proposals(limit, principal_id=principal)

    def approve_proposal(
        self, proposal_id: int, *, approved_by: str, principal: Optional[str]
    ) -> Any:
        return self._attest(
            self.store.approve_proposal(
                proposal_id, approved_by=approved_by, principal_id=principal
            ),
            "approved",
            principal,
        )

    def reject_proposal(
        self, proposal_id: int, *, rejected_by: str, principal: Optional[str]
    ) -> bool:
        return self.store.reject_proposal(
            proposal_id, rejected_by=rejected_by, principal_id=principal
        )

    def neighbors(self, subject: str, *, principal: Optional[str]) -> list[Any]:
        init_memory_db(self.store.db_path)
        return [
            row
            for row in self.store.neighbors(subject, principal_id=principal)
            if self._admits_triple(
                row["subject"], row["predicate"], row["object"], principal
            )
        ]

    def facts_for(
        self,
        subject: str,
        predicate: str | None = None,
        *,
        principal: Optional[str],
    ) -> list[Any]:
        init_memory_db(self.store.db_path)
        return [
            row
            for row in self.store.facts_for(subject, predicate, principal_id=principal)
            if self._admits_row(row, principal)
        ]

    def operator_model(self, *, principal: Optional[str]) -> dict[str, Any]:
        """Build *principal*'s operator snapshot from authority-owned fact reads."""
        operator_facts = self.facts_for("operator", principal=principal)
        project_facts = self.facts_for("project", principal=principal)
        init_memory_db(self.store.db_path)
        with get_connection(self.store.db_path) as conn:
            attr_rows = conn.execute(
                "SELECT * FROM semantic_facts "
                "WHERE subject LIKE 'operator.%' AND status = 'active' "
                "AND principal_id IS ? "
                "ORDER BY id DESC",
                (principal,),
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
        principal: Optional[str],
    ) -> list[Any]:
        init_memory_db(self.store.db_path)
        edges = self.store.traverse_weighted(
            subject,
            max_depth=max_depth,
            min_path_confidence=min_path_confidence,
            principal_id=principal,
        )
        if self.gate is None:
            return edges
        # The path records nodes, not predicates, so a hop cannot be rebuilt
        # exactly. The sound rule: an edge is kept only if its own triple
        # verifies AND an admitted edge already reached its subject from the
        # start. Every kept edge is verified, and connected to the start
        # through verified edges only.
        reached = {str(subject).strip()}
        kept: set[int] = set()
        for index, edge in sorted(enumerate(edges), key=lambda pair: pair[1].depth):
            if edge.subject in reached and self._admits_triple(
                edge.subject, edge.predicate, edge.object, principal
            ):
                kept.add(index)
                reached.add(edge.object)
        return [edge for index, edge in enumerate(edges) if index in kept]

    def traverse(
        self, subject: str, max_depth: int = 2, *, principal: Optional[str]
    ) -> list[Any]:
        """The UI graph: not recall, so ungated -- but only *principal*'s graph."""
        init_memory_db(self.store.db_path)
        return self.store.traverse(subject, max_depth=max_depth, principal_id=principal)

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


class CerebellumAdapter:
    """Authority adapter for compiled reflexes (`compiled_playbooks`).

    Phase 2 slice 1: the cerebellum was built per request outside the
    authority. It is now one process-wide store owned here. Reflexes are not
    recalled into prompts, so recall is empty; replay stays on the cerebellum,
    which callers obtain from the authority rather than build.
    """

    memory_types = ("reflex",)

    def __init__(self, store: "Cerebellum") -> None:
        self.store = store

    def recall(self, query: str, context: MemoryRecallContext) -> tuple[MemoryHit, ...]:
        return ()

    def rebuild_derived_indexes(self) -> None:
        self.store._refresh_cache()


class CurriculumAdapter:
    """Authority adapter for curriculum evidence (`curriculum_tasks`)."""

    memory_types = ("curriculum",)

    def __init__(self, store: "CurriculumManager") -> None:
        self.store = store

    def recall(self, query: str, context: MemoryRecallContext) -> tuple[MemoryHit, ...]:
        return ()

    def rebuild_derived_indexes(self) -> None:
        return None


class MistakeMemoryAdapter:
    """Authority adapter for pending and verified lessons.

    With a provenance writer (plan Phase 3b), every write that changes what a
    lesson's recall shows -- creation, a recurrence, a promotion -- appends a
    signed record of the lesson's new state. Without one (tests, fakes) it
    writes exactly as before.
    """

    memory_types = ("lesson", "mistake")

    def __init__(
        self,
        store: MistakeMemory,
        *,
        provenance: Optional["ProvenanceWriter"] = None,
        gate: Optional["RecallGate"] = None,
    ) -> None:
        self.store = store
        self.provenance = provenance
        #: Plan Phase 3c: every read that feeds a prompt -- task lessons,
        #: verified cross-task lessons, the self-model's recurring cautions --
        #: admits only a lesson whose provenance verifies. None: as before.
        self.gate = gate

    def _admitted(
        self, items: list[Any], limit: int, principal: Optional[str]
    ) -> list[Any]:
        if self.gate is None:
            return list(items)[:limit]
        kept: list[Any] = []
        for item in items:
            mistake_id = int(
                item["mistake_id"] if "mistake_id" in item.keys() else item["id"]
            )
            row = self.store.get(mistake_id)
            if row is not None and self.gate.admits(
                "mistake_pool", mistake_id, lesson_digest(row), principal=principal
            ):
                kept.append(item)
            if len(kept) >= limit:
                break
        return kept

    def _fetch(self, limit: int) -> int:
        return limit * (_GATED_OVERFETCH if self.gate is not None else 1)

    def _attest(
        self,
        mistake_id: int,
        transition: str,
        *,
        prior: Any = None,
        existed: bool,
        principal: Optional[str],
    ) -> None:
        """A new lesson is attested as new. A recurrence or a promotion extends
        the prior state and is signed only if that state verifies: a recurrence
        keeps the EXISTING row's text, so signing it unconditionally would sign
        whatever text an unsigned row held."""
        if self.provenance is None:
            return
        row = self.store.get(mistake_id)
        if row is None:
            return
        if not existed:
            self.provenance.attest_new(
                "mistake_pool",
                mistake_id,
                lesson_digest(row),
                transition,
                session_id=row["task_id"],
                principal=principal,
            )
            return
        prior_digest = (
            lesson_digest(prior)
            if prior is not None and int(prior["id"]) == int(mistake_id)
            else None
        )
        self.provenance.attest_transition(
            "mistake_pool",
            mistake_id,
            lesson_digest(row),
            transition,
            prior_digest=prior_digest,
            session_id=row["task_id"],
            principal=principal,
        )

    def _recurrence_prior(
        self, args: tuple, kwargs: dict, principal: Optional[str]
    ) -> Any:
        """The row a recurrence would increment, read BEFORE the write."""
        if self.provenance is None:
            return None
        finder = getattr(self.store, "recurrence_candidate", None)
        if not callable(finder):
            return None
        bound = inspect.signature(self.store.record_or_increment).bind(*args, **kwargs)
        return finder(
            bound.arguments["task_id"],
            bound.arguments["error_type"],
            principal_id=principal,
        )

    def recall_relevant(
        self, query: str, task_id: str, limit: int, *, principal: Optional[str]
    ) -> list[dict[str, Any]]:
        pending = [
            {
                "mistake_id": int(row["id"]),
                "error_type": str(row["error_type"]),
                "lesson_text": str(row["lesson_text"]),
                "verification_status": "pending",
                "relevance": 1.0,
            }
            for row in self._admitted(
                self.store.pending_for_task(
                    task_id, self._fetch(limit), principal_id=principal
                ),
                limit,
                principal,
            )
        ]
        remaining = max(limit - len(pending), 0)
        verified = self.relevant_verified(query, remaining, principal=principal)
        pending_ids = {lesson["mistake_id"] for lesson in pending}
        return pending + [
            lesson for lesson in verified if lesson["mistake_id"] not in pending_ids
        ]

    def recurring(
        self, limit: int = 3, *, principal: Optional[str]
    ) -> list[dict[str, Any]]:
        return self._admitted(
            self.store.recurring(limit=self._fetch(limit), principal_id=principal),
            limit,
            principal,
        )

    def record_or_increment(
        self, *args: Any, principal: Optional[str], **kwargs: Any
    ) -> tuple[int, bool]:
        write_budget.spend(self, "mistake_pool")
        prior = self._recurrence_prior(args, kwargs, principal)
        mistake_id, recurrence = self.store.record_or_increment(
            *args, principal_id=principal, **kwargs
        )
        self._attest(
            int(mistake_id),
            "recurred" if recurrence else "created",
            prior=prior,
            existed=bool(recurrence),
            principal=principal,
        )
        return mistake_id, recurrence

    def record(self, *args: Any, principal: Optional[str], **kwargs: Any) -> int:
        write_budget.spend(self, "mistake_pool")
        mistake_id = int(self.store.record(*args, principal_id=principal, **kwargs))
        self._attest(mistake_id, "created", existed=False, principal=principal)
        return mistake_id

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

    def promote(
        self, mistake_id: int, *, principal: Optional[str], **kwargs: Any
    ) -> None:
        row = self.store.get(mistake_id)
        if row is None or row["principal_id"] != principal:
            # Plan Phase 4c: never another principal's lesson. Nothing changes,
            # so nothing is attested.
            return
        prior = row if self.provenance is not None else None
        self.store.promote(mistake_id, principal_id=principal, **kwargs)
        # Attested even when the evidence was below the floor and nothing
        # changed: the record then restates the same state. Signed only if the
        # state it restates, or promotes, was signed.
        self._attest(
            int(mistake_id), "promoted", prior=prior, existed=True, principal=principal
        )

    def pending_command_pairs(
        self, task_id: str, *, principal: Optional[str]
    ) -> list[tuple[int, str]]:
        return self.store.pending_command_pairs(task_id, principal_id=principal)

    def pending_for_task(
        self, task_id: str, limit: int = 5, *, principal: Optional[str]
    ) -> list[Any]:
        return self.store.pending_for_task(task_id, limit, principal_id=principal)

    def relevant_verified(
        self, query: str, limit: int = 5, *, principal: Optional[str]
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        return self._admitted(
            self.store.relevant_verified(
                query, self._fetch(limit), principal_id=principal
            ),
            limit,
            principal,
        )

    def recall(self, query: str, context: MemoryRecallContext) -> tuple[MemoryHit, ...]:
        rows = self.recall_relevant(
            query,
            context.session_id or "",
            context.limit,
            principal=context.principal_id,
        )
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
