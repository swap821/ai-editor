"""A journal nothing can rewrite — otherwise it is a log with better branding.

Every other learning table stores the CURRENT state, which means an UPDATE
destroys the transition that produced it. `compiled_playbooks.status` says a
reflex is retired; it cannot say it was retired after two replay failures with
four promotable successes banked. That history is what LC4 asks for, and the
only way to have it is a table nothing edits.

So the load-bearing test here is not "we can append" — it is
`test_no_code_path_updates_or_deletes_the_journal`, a source-level check. An
append-only table with one UPDATE somewhere is not append-only, and the defect
would be invisible in behaviour until someone went looking for history that had
quietly been rewritten.

Second rule: journalling must never break learning. It observes a transition;
it is not part of one. A compile that failed because writing *about* the
compile failed is the tail wagging the dog.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from aios.core.cerebellum import Cerebellum
from aios.core.verification_strength import VerificationStrength
from aios.memory import learning_journal
from aios.memory.db import get_connection, init_memory_db
from aios.memory.skills import SkillMemory

REPO_ROOT = Path(__file__).resolve().parents[1]
GOAL = "read the source and run the tests"
STEPS = ["read_file: filepath=a.py", "verify: command=pytest tests/a.py"]


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "memory.sqlite"
    init_memory_db(path)
    return path


def _earn(db, times: int = 3) -> int:
    skills = SkillMemory(db_path=db)
    skill_id = 0
    for _ in range(times):
        skill_id = skills.record_attempt(
            GOAL, STEPS, success=True, strength=VerificationStrength.STRONG
        )
    return skill_id


class TestNothingCanRewriteIt:
    def test_no_code_path_updates_or_deletes_the_journal(self) -> None:
        """The whole guarantee, checked at the source rather than assumed.

        Behavioural tests cannot catch this: an UPDATE added later would keep
        every other test green while silently making the history editable.
        """
        offenders: list[str] = []
        pattern = re.compile(
            r"(UPDATE\s+learning_events|DELETE\s+FROM\s+learning_events"
            r"|DROP\s+TABLE\s+learning_events)",
            re.IGNORECASE,
        )
        for path in (REPO_ROOT / "aios").rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if pattern.search(text):
                offenders.append(str(path.relative_to(REPO_ROOT)))
        assert not offenders, (
            "learning_events is append-only; these write a mutation against it "
            f"and turn the journal back into an overwritable log: {offenders}"
        )

    def test_the_module_exposes_no_edit_helper(self) -> None:
        """No `update()`, no `delete()`, no 'fix a bad entry'. Corrections are
        appended, the way the audit ledger does it."""
        public = {n for n in dir(learning_journal) if not n.startswith("_")}
        assert not {"update", "delete", "edit", "amend", "purge"} & public


class TestItRecordsRealTransitions:
    def test_compiling_a_reflex_is_journalled(self, db) -> None:
        _earn(db)
        assert Cerebellum(db).try_compile_all() == 1

        entries = learning_journal.history("L4", db_path=db)
        assert [e["transition"] for e in entries] == ["compiled"]
        assert entries[0]["detail"]["steps"] == 2

    def test_retiring_a_reflex_records_WHY(self, db) -> None:
        """The reason is the part the mutable table cannot keep."""
        skill_id = _earn(db)
        cerebellum = Cerebellum(db)
        cerebellum.try_compile_all()
        cerebellum.invalidate_for_skill(skill_id)

        retired = [
            e
            for e in learning_journal.history("L5", db_path=db)
            if e["transition"] == "decompiled"
        ]
        assert retired, "a retirement that leaves no trace is the LC4 gap"
        assert retired[0]["detail"]["reason"]

    def test_the_entry_is_rolled_back_with_its_transition(self, db) -> None:
        """Journalled inside the caller's transaction, so an entry cannot
        survive a rolled-back compile and describe something that never was."""
        with pytest.raises(RuntimeError):
            with get_connection(db) as conn:
                learning_journal.record("L4", "compiled", subject_id=1, conn=conn)
                raise RuntimeError("the transition failed after journalling")

        assert learning_journal.history("L4", db_path=db) == []

    def test_history_is_newest_first_and_filterable(self, db) -> None:
        learning_journal.record("L4", "compiled", db_path=db)
        learning_journal.record("L5", "replayed", db_path=db)
        learning_journal.record("L4", "decompiled", db_path=db)

        assert [
            e["transition"] for e in learning_journal.history("L4", db_path=db)
        ] == [
            "decompiled",
            "compiled",
        ]
        assert len(learning_journal.history(db_path=db)) == 3


class TestObservingMustNotBreakTheThingObserved:
    def test_a_broken_journal_does_not_break_a_compile(self, db, monkeypatch) -> None:
        """A compile that fails because writing ABOUT it failed is absurd."""
        monkeypatch.setattr(
            learning_journal,
            "get_connection",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("journal is down")),
        )
        learning_journal.record("L4", "compiled", db_path=db)  # must not raise

    def test_an_unknown_faculty_is_warned_about_not_dropped(self, db) -> None:
        """A typo'd faculty must still be recorded — losing the entry entirely
        would be a worse outcome than filing it under an odd name."""
        learning_journal.record("LX", "something", db_path=db)
        assert len(learning_journal.history(db_path=db)) == 1

    def test_reading_a_store_without_the_table_returns_nothing(self, tmp_path) -> None:
        """A database predating this table must not crash a reader."""
        assert learning_journal.history(db_path=tmp_path / "absent.sqlite") == []
