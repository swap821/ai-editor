"""Evidence-gated promotion from observations into trusted semantic memory."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from aios import config
from aios.memory.db import get_connection, init_memory_db
from aios.memory.facts import FactWriteResult, SemanticFacts
from aios.memory.mistake import MistakeMemory
from aios.memory.semantic import SemanticMemory


class MemoryConsolidator:
    """Promote only verified lessons and human-approved facts into trusted L3."""

    def __init__(
        self,
        db_path: Path = config.MEMORY_DB_PATH,
        *,
        semantic: Optional[SemanticMemory] = None,
        mistakes: Optional[MistakeMemory] = None,
        facts: Optional[SemanticFacts] = None,
    ) -> None:
        self.db_path = db_path
        self.semantic = semantic or SemanticMemory(db_path)
        self.mistakes = mistakes or MistakeMemory(db_path)
        self.facts = facts or SemanticFacts(db_path)

    def _add_verified(
        self, text: str, memory_type: str, *, count_occurrence: bool = True
    ) -> int:
        """Index trusted content and explicitly promote an existing exact match."""
        mem_id = self.semantic.add(
            text,
            memory_type=memory_type,
            verification_status="verified",
            count_occurrence=count_occurrence,
        )
        self.semantic.promote(mem_id)
        return mem_id

    def consolidate_lesson(
        self, mistake_id: int, *, count_occurrence: bool = True
    ) -> Optional[int]:
        """Index a verified lesson; refuse pending or superseded lessons."""
        row = self.mistakes.get(mistake_id)
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
        result = self.facts.add_fact(subject, predicate, obj, approved_by=approved_by)
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
        old_rows = self.facts.facts_for(subject.strip(), predicate.strip())
        result = self.facts.reconcile(subject, predicate, obj, approved_by=approved_by)
        if not result.committed:
            return result
        for row in old_rows:
            self.semantic.supersede_text(
                f"VERIFIED FACT\n{row['subject']} {row['predicate']} {row['object']}"
            )
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
        with get_connection(self.db_path) as conn:
            lessons = conn.execute(
                "SELECT id FROM mistake_pool WHERE verification_status = 'verified'"
            ).fetchall()
            facts = conn.execute(
                "SELECT id, subject, predicate, object FROM semantic_facts "
                "WHERE status = 'active' AND approved_by IS NOT NULL"
            ).fetchall()
            superseded_lessons = conn.execute(
                "SELECT * FROM mistake_pool WHERE verification_status = 'superseded'"
            ).fetchall()
            superseded_facts = conn.execute(
                "SELECT * FROM semantic_facts WHERE status = 'superseded'"
            ).fetchall()
        for row in superseded_lessons:
            superseded_memories += self.semantic.supersede_text(self._lesson_text(row))
        for row in superseded_facts:
            superseded_memories += self.semantic.supersede_text(
                f"VERIFIED FACT\n{row['subject']} {row['predicate']} {row['object']}"
            )
        for row in lessons:
            mem_id = self.consolidate_lesson(
                int(row["id"]), count_occurrence=False
            )
            if mem_id is not None:
                lesson_ids.append(mem_id)
        for row in facts:
            memory_type = "preference" if str(row["subject"]).lower() == "user" else "fact"
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
