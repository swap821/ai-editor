"""Evidence-gated promotion from observations into trusted semantic memory."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from aios import config
from aios.memory.db import get_connection, init_memory_db
from aios.memory.facts import FactWriteResult, SemanticFacts
from aios.memory.mistake import MistakeMemory
from aios.memory.semantic import SemanticMemory


def _authority_store(authority: Any | None, name: str) -> Any | None:
    """Return a registered specialist store without constructing a shadow store."""
    if authority is None:
        return None
    adapters = getattr(authority, "adapters", {})
    adapter = adapters.get(name) if hasattr(adapters, "get") else None
    return getattr(adapter, "store", None)


class MemoryConsolidator:
    """Promote only verified lessons and human-approved facts into trusted L3."""

    def __init__(
        self,
        db_path: Path = config.MEMORY_DB_PATH,
        *,
        semantic: Optional[SemanticMemory] = None,
        mistakes: Optional[MistakeMemory] = None,
        facts: Optional[SemanticFacts] = None,
        memory_authority: Any | None = None,
    ) -> None:
        self.db_path = db_path
        self.memory_authority = memory_authority
        self.semantic = semantic or _authority_store(memory_authority, "semantic")
        self.mistakes = mistakes or _authority_store(memory_authority, "lessons")
        self.facts = facts or _authority_store(memory_authority, "facts")
        # A caller supplying explicit specialist fakes may intentionally omit
        # the unrelated lesson store; retain that narrow compatibility seam.
        if self.mistakes is None and (
            memory_authority is None or semantic is not None or facts is not None
        ):
            self.mistakes = MistakeMemory(db_path)
        if memory_authority is None:
            # Explicit standalone/compatibility path. The process authority
            # bootstrap supplies all three stores before binding this service.
            self.semantic = self.semantic or SemanticMemory(db_path)
            self.mistakes = self.mistakes or MistakeMemory(db_path)
            self.facts = self.facts or SemanticFacts(db_path)
        elif self.semantic is None or self.mistakes is None or self.facts is None:
            raise RuntimeError("memory authority specialist stores are unavailable")

    def _authority_owns(self, name: str, store: Any) -> bool:
        authority = self.memory_authority
        owns_store = getattr(authority, "owns_store", None)
        return bool(callable(owns_store) and owns_store(name, store))

    def _add_verified(
        self, text: str, memory_type: str, *, count_occurrence: bool = True
    ) -> int:
        """Index trusted content and explicitly promote an existing exact match."""
        if self._authority_owns("semantic", self.semantic):
            return int(
                self.memory_authority.semantic_add_verified(
                    text,
                    memory_type=memory_type,
                    count_occurrence=count_occurrence,
                )
            )
        mem_id = self.semantic.add(
            text,
            memory_type=memory_type,
            verification_status="verified",
            count_occurrence=count_occurrence,
        )
        self.semantic.promote(mem_id)
        return mem_id

    def _supersede_semantic_text(self, text: str) -> int:
        if self._authority_owns("semantic", self.semantic):
            return int(self.memory_authority.semantic_supersede_text(text))
        return int(self.semantic.supersede_text(text))

    def consolidate_lesson(
        self, mistake_id: int, *, count_occurrence: bool = True
    ) -> Optional[int]:
        """Index a verified lesson; refuse pending or superseded lessons."""
        row = (
            self.memory_authority.lesson_get(mistake_id)
            if self._authority_owns("lessons", self.mistakes)
            else self.mistakes.get(mistake_id)
        )
        if row is None or row["verification_status"] != "verified":
            return None
        text = self._lesson_text(row)
        return self._add_verified(text, "lesson", count_occurrence=count_occurrence)

    @staticmethod
    def _lesson_text(row: Any) -> str:
        return (
            f"VERIFIED LESSON\nError type: {row['error_type']}\n"
            f"Root cause: {row['root_cause']}\nPrevention: {row['lesson_text']}"
        )

    def promote_fact(
        self, subject: str, predicate: str, obj: str, *, approved_by: str
    ) -> FactWriteResult:
        """Commit and index a human-approved fact, surfacing contradictions."""
        if not approved_by or not approved_by.strip():
            return FactWriteResult(False, None, "human approval required")
        if self._authority_owns("facts", self.facts):
            result = self.memory_authority.facts_add_fact(
                subject, predicate, obj, approved_by=approved_by
            )
        else:
            result = self.facts.add_fact(
                subject, predicate, obj, approved_by=approved_by
            )
        if result.committed:
            memory_type = "preference" if subject.strip().lower() == "user" else "fact"
            self._add_verified(
                f"VERIFIED FACT\n{subject.strip()} {predicate.strip()} {obj.strip()}",
                memory_type,
            )
        return result

    def reconcile_fact(
        self, subject: str, predicate: str, obj: str, *, approved_by: str
    ) -> FactWriteResult:
        """Human-approved contradiction resolution with vector supersession."""
        if not approved_by or not approved_by.strip():
            return FactWriteResult(False, None, "human approval required")
        if self._authority_owns("facts", self.facts):
            old_rows = self.memory_authority.facts_for(
                subject.strip(), predicate.strip()
            )
            result = self.memory_authority.facts_reconcile(
                subject, predicate, obj, approved_by=approved_by
            )
        else:
            old_rows = self.facts.facts_for(subject.strip(), predicate.strip())
            result = self.facts.reconcile(
                subject, predicate, obj, approved_by=approved_by
            )
        if not result.committed:
            return result
        for row in old_rows:
            text = f"VERIFIED FACT\n{row['subject']} {row['predicate']} {row['object']}"
            self._supersede_semantic_text(text)
        memory_type = "preference" if subject.strip().lower() == "user" else "fact"
        self._add_verified(
            f"VERIFIED FACT\n{subject.strip()} {predicate.strip()} {obj.strip()}",
            memory_type,
        )
        return result

    def run(self) -> dict[str, Any]:
        """Consolidate all current verified lessons and active facts idempotently."""
        init_memory_db(self.db_path)
        lesson_ids: list[int] = []
        fact_ids: list[int] = []
        superseded_memories = 0
        if self._authority_owns("lessons", self.mistakes):
            lessons = self.memory_authority.lessons_by_status("verified")
            superseded_lessons = self.memory_authority.lessons_by_status("superseded")
        else:
            with get_connection(self.db_path) as conn:
                lessons = conn.execute(
                    "SELECT id FROM mistake_pool WHERE verification_status = 'verified'"
                ).fetchall()
                superseded_lessons = conn.execute(
                    "SELECT * FROM mistake_pool WHERE verification_status = 'superseded'"
                ).fetchall()

        if self._authority_owns("facts", self.facts):
            facts = [
                row
                for row in self.memory_authority.facts_by_status("active")
                if row["approved_by"] is not None
            ]
            superseded_facts = self.memory_authority.facts_by_status("superseded")
        else:
            with get_connection(self.db_path) as conn:
                facts = conn.execute(
                    "SELECT id, subject, predicate, object FROM semantic_facts "
                    "WHERE status = 'active' AND approved_by IS NOT NULL"
                ).fetchall()
                superseded_facts = conn.execute(
                    "SELECT * FROM semantic_facts WHERE status = 'superseded'"
                ).fetchall()
        for row in superseded_lessons:
            superseded_memories += self._supersede_semantic_text(self._lesson_text(row))
        for row in superseded_facts:
            superseded_memories += self._supersede_semantic_text(
                f"VERIFIED FACT\n{row['subject']} {row['predicate']} {row['object']}"
            )
        for row in lessons:
            mem_id = self.consolidate_lesson(int(row["id"]), count_occurrence=False)
            if mem_id is not None:
                lesson_ids.append(mem_id)
        for row in facts:
            memory_type = (
                "preference" if str(row["subject"]).lower() == "user" else "fact"
            )
            fact_ids.append(
                self._add_verified(
                    f"VERIFIED FACT\n{row['subject']} {row['predicate']} {row['object']}",
                    memory_type,
                    count_occurrence=False,
                )
            )
        return {
            "verified_lessons_consolidated": len(lesson_ids),
            "active_facts_consolidated": len(fact_ids),
            "superseded_memories": superseded_memories,
            "semantic_ids": lesson_ids + fact_ids,
        }
