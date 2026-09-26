"""Phase 2, slice 1: every learning store has exactly one owner.

Ground truth before this slice (docs/learning/PHASE2_DESIGN.md): the cerebellum
and the curriculum were built outside the memory authority, fresh per request,
invisible to both R11 checks; the skill store had no cerebellum, so
compile-on-promotion happened a request later while a docstring said the
opposite; and nothing stopped a new module writing a learning table directly.
"""

from __future__ import annotations

import ast
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

import pytest

from aios import config
from aios.application.memory.bootstrap import build_memory_authority
from aios.core.cerebellum import Cerebellum
from aios.core.verification_strength import VerificationStrength
from aios.memory.curriculum import CurriculumManager
from aios.memory.skills import SkillMemory

REPO = Path(config.PROJECT_ROOT)


class TestTheAuthorityOwnsEveryLearningStore:
    def test_the_api_serves_the_authoritys_one_cerebellum(self) -> None:
        from aios.api import deps

        first, second = deps.get_cerebellum(), deps.get_cerebellum()
        assert first is second, "a fresh cerebellum per request is back"
        assert first is deps.get_memory_authority().adapters["cerebellum"].store

    def test_the_api_serves_the_authoritys_one_curriculum(self) -> None:
        from aios.api import deps

        first, second = deps.get_curriculum_manager(), deps.get_curriculum_manager()
        assert first is second
        assert first is deps.get_memory_authority().adapters["curriculum"].store

    def test_the_skill_store_is_wired_to_that_cerebellum(self) -> None:
        authority = build_memory_authority()
        skills = authority.adapters["skills"].store
        assert isinstance(skills, SkillMemory)
        assert skills._cerebellum is authority.adapters["cerebellum"].store

    def test_the_facts_hook_stays_unwired(self) -> None:
        """Wiring it would write learned text into facts recalled as
        human-approved (threat T16, red-team RT-18)."""
        authority = build_memory_authority()
        assert authority.adapters["skills"].store._facts is None
        assert authority.adapters["lessons"].store._facts is None


class TestCompileOnPromotionIsReal:
    def test_a_promoted_skill_compiles_in_the_same_request(self) -> None:
        """No sweep runs here: only the store's own promotion hook can compile."""
        authority = build_memory_authority()
        skills = authority.adapters["skills"].store
        goal = "phase two compile on promotion probe"
        with sqlite3.connect(config.MEMORY_DB_PATH) as conn:
            before = conn.execute("SELECT COUNT(*) FROM compiled_playbooks").fetchone()[
                0
            ]
        for _ in range(3):
            skills.record_attempt(
                goal,
                ["read_file: filepath=README.md"],
                success=True,
                strength=VerificationStrength.STRONG,
            )
        with sqlite3.connect(config.MEMORY_DB_PATH) as conn:
            after = conn.execute("SELECT COUNT(*) FROM compiled_playbooks").fetchone()[
                0
            ]
        assert after == before + 1, "promotion did not compile its reflex"


class TestTheSharedCerebellumIsSafeUnderConcurrency:
    def test_a_refresh_swaps_the_cache_whole(self, tmp_path: Path) -> None:
        """Refilling in place let a concurrent `match` iterate a dict that was
        changing size -- which raises, and every caller reads as 'no reflex'."""
        cerebellum = Cerebellum(tmp_path / "memory.db")
        before = cerebellum._cache
        cerebellum._refresh_cache()
        assert cerebellum._cache is not before


class TestTheR11TrackerSeesTheNewStores:
    @pytest.mark.parametrize("store", [Cerebellum, CurriculumManager])
    def test_construction_is_recorded(self, store, tmp_path, monkeypatch) -> None:
        from aios.memory import construction_ledger

        ledger = tmp_path / "memory-construction.jsonl"
        monkeypatch.setattr(construction_ledger, "ledger_path", lambda: ledger)
        monkeypatch.setattr(construction_ledger, "_seen", set())
        store(tmp_path / "memory.db")
        assert any(
            entry["type"] == store.__name__
            for entry in construction_ledger.entries(ledger)
        )


#: Every production module that may write each learning table. Discovered from
#: the code (2026-09-25), not assumed. db.py holds schema migrations and
#: compaction.py is semantic memory's maintenance store; everything else is one
#: owner per table. A new writer anywhere in aios/ fails here.
_OWNERS: dict[str, set[str]] = {
    "procedural_skills": {"aios/memory/skills.py", "aios/memory/db.py"},
    "compiled_playbooks": {"aios/core/cerebellum.py", "aios/memory/db.py"},
    "mistake_pool": {"aios/memory/mistake.py"},
    "curriculum_tasks": {"aios/memory/curriculum.py"},
    "semantic_memory": {
        "aios/memory/semantic.py",
        "aios/memory/compaction.py",
        "aios/memory/db.py",
    },
    "semantic_facts": {"aios/memory/facts.py"},
    "fact_proposals": {"aios/memory/facts.py"},
    "playbook_blobs": {"aios/core/replay_writes.py"},
    "approved_write_decisions": {"aios/core/replay_writes.py"},
    "approved_edit_decisions": {"aios/core/replay_writes.py"},
    "learning_events": {"aios/memory/learning_journal.py"},
    "institutional_skills": {"aios/domain/learning/repository.py"},
    "expert_trajectories": {"aios/domain/learning/trajectory_repository.py"},
    "reuse_outcomes": {"aios/domain/learning/reuse_outcome_repository.py"},
}

_WRITE = re.compile(
    r"\b(?:INSERT\s+(?:OR\s+\w+\s+)?INTO|REPLACE\s+INTO|UPDATE|DELETE\s+FROM)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


def _sql_strings(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value
        elif isinstance(node, ast.JoinedStr):
            yield "".join(
                part.value
                for part in node.values
                if isinstance(part, ast.Constant) and isinstance(part.value, str)
            )


def _writers(root: Path) -> dict[str, set[str]]:
    found: dict[str, set[str]] = defaultdict(set)
    for path in (root / "aios").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for text in _sql_strings(tree):
            for match in _WRITE.finditer(text):
                table = match.group(1).lower()
                if table in _OWNERS:
                    found[table].add(path.relative_to(root).as_posix())
    return found


class TestOneWriterPerLearningTable:
    def test_no_module_writes_a_learning_table_it_does_not_own(self) -> None:
        strays = {
            table: sorted(writers - _OWNERS[table])
            for table, writers in _writers(REPO).items()
            if writers - _OWNERS[table]
        }
        assert not strays, (
            "a learning table is written outside its owner -- route the write "
            f"through the owning store and the memory authority: {strays}"
        )

    def test_the_scan_sees_a_stray_writer(self, tmp_path: Path) -> None:
        """The guard can fire: a planted module writing mistake_pool is caught."""
        planted = tmp_path / "aios" / "rogue.py"
        planted.parent.mkdir(parents=True)
        planted.write_text(
            "SQL = \"UPDATE mistake_pool SET verification_status = 'verified'\"\n",
            encoding="utf-8",
        )
        assert _writers(tmp_path) == {"mistake_pool": {"aios/rogue.py"}}

    def test_every_owner_still_writes(self) -> None:
        """An owner that no longer writes its table would make the map stale."""
        found = _writers(REPO)
        for table, owners in _OWNERS.items():
            assert found.get(table), f"nothing writes {table}; the owner map is stale"
