"""Tests for the memory compaction sweep."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from aios.memory import db as memdb
from aios.memory.compaction import CompactionPreview, MemoryCompactor
from aios.memory.episodic import EpisodicMemory
from aios.memory.semantic import SemanticMemory
from aios.memory.working import WorkingMemory
from aios.security import audit_logger


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """An initialised, isolated memory database in a temp directory."""
    path = tmp_path / "memory.db"
    memdb.init_memory_db(path)
    return path


@pytest.fixture()
def audit_db(tmp_path: Path) -> Path:
    """An initialised, isolated audit ledger."""
    path = tmp_path / "audit.db"
    audit_logger.init_audit_db(path)
    return path


class FakeIndex:
    """Records removes without loading sentence-transformers/FAISS."""

    def __init__(self, tmp_path: Path) -> None:
        self.path = tmp_path / "fake.faiss"
        self.added: list[int] = []
        self.removed: list[int] = []

    def add(self, vector_id, vector):
        self.added.append(vector_id)

    def remove(self, ids):
        self.removed.extend(ids)

    def rebuild_without(self, ids):
        self.removed.extend(ids)

    def persist(self):
        pass


class FakeEmbedder:
    dim = 2

    def encode(self, texts):
        return np.asarray([[0.0, 1.0]], dtype="float32")


def _add_unverified_chat(sem: SemanticMemory, text: str) -> int:
    return sem.add(text, memory_type="chat", verification_status="unverified")


def test_preview_returns_compaction_preview(db_path: Path, audit_db: Path, tmp_path: Path) -> None:
    wm = WorkingMemory()
    wm.set("s1", "k", "v")
    comp = MemoryCompactor(
        db_path=db_path,
        audit_db_path=audit_db,
        working=wm,
        unverified_chat_days=0.0,
        episodic_days=0.0,
        semantic_max_per_type=0,
        working_idle_minutes=0,
    )
    preview = comp.preview()
    assert isinstance(preview, CompactionPreview)
    assert preview.working_sessions_count == 1


def test_preview_never_mutates(db_path: Path, audit_db: Path, tmp_path: Path) -> None:
    wm = WorkingMemory()
    wm.set("s1", "k", "v")
    ep = EpisodicMemory(db_path)
    ep.record("s1", "user", "hello")
    sem = SemanticMemory(db_path, index=FakeIndex(tmp_path), embedder=FakeEmbedder())
    _add_unverified_chat(sem, "old chat")

    comp = MemoryCompactor(
        db_path=db_path,
        audit_db_path=audit_db,
        working=wm,
        semantic=sem,
        episodic=ep,
        index=FakeIndex(tmp_path),
        unverified_chat_days=0.0,
        episodic_days=0.0,
        semantic_max_per_type=0,
        working_idle_minutes=0,
    )
    comp.preview()
    assert wm.get("s1", "k") == "v"
    assert ep.count() == 1
    assert sem.count() == 1


def test_dry_run_reports_but_does_not_delete(db_path: Path, audit_db: Path, tmp_path: Path) -> None:
    wm = WorkingMemory()
    wm.set("s1", "k", "v")
    comp = MemoryCompactor(
        db_path=db_path,
        audit_db_path=audit_db,
        working=wm,
        unverified_chat_days=9999.0,
        episodic_days=9999.0,
        semantic_max_per_type=9999,
        working_idle_minutes=0,
    )
    result = comp.compact(dry_run=True)
    assert result["dry_run"] is True
    assert result["working_sessions_removed"] == 1
    assert wm.get("s1", "k") == "v"


def test_compact_removes_idle_working_session(db_path: Path, audit_db: Path, tmp_path: Path) -> None:
    wm = WorkingMemory()
    wm.set("s1", "k", "v")
    comp = MemoryCompactor(
        db_path=db_path,
        audit_db_path=audit_db,
        working=wm,
        unverified_chat_days=9999.0,
        episodic_days=9999.0,
        semantic_max_per_type=9999,
        working_idle_minutes=0,
    )
    result = comp.compact(dry_run=False)
    assert result["dry_run"] is False
    assert result["working_sessions_removed"] == 1
    assert wm.get("s1", "k") is None


def test_compact_deletes_old_episodic_rows(db_path: Path, audit_db: Path, tmp_path: Path) -> None:
    ep = EpisodicMemory(db_path)
    ep.record("s", "user", "hello")
    with memdb.get_connection(db_path) as conn:
        conn.execute(
            "UPDATE episodic_memory SET timestamp = '1970-01-01 00:00:00'"
        )

    comp = MemoryCompactor(
        db_path=db_path,
        audit_db_path=audit_db,
        episodic=ep,
        unverified_chat_days=9999.0,
        episodic_days=1.0,
        semantic_max_per_type=9999,
        working_idle_minutes=9999,
    )
    result = comp.compact(dry_run=False)
    assert result["episodic_rows_removed"] == 1
    assert ep.count() == 0


def test_compact_deletes_old_unverified_chat(db_path: Path, audit_db: Path, tmp_path: Path) -> None:
    fake = FakeIndex(tmp_path)
    sem = SemanticMemory(db_path, index=fake, embedder=FakeEmbedder())
    _add_unverified_chat(sem, "old chat")
    with memdb.get_connection(db_path) as conn:
        conn.execute(
            "UPDATE semantic_memory SET timestamp = '1970-01-01 00:00:00' "
            "WHERE verification_status = 'unverified'"
        )

    comp = MemoryCompactor(
        db_path=db_path,
        audit_db_path=audit_db,
        semantic=sem,
        index=fake,
        unverified_chat_days=1.0,
        episodic_days=9999.0,
        semantic_max_per_type=9999,
        working_idle_minutes=9999,
    )
    result = comp.compact(dry_run=False)
    assert result["semantic_unverified_chat_removed"] == 1
    assert sem.count() == 0


def test_compact_keeps_verified_rows(db_path: Path, audit_db: Path, tmp_path: Path) -> None:
    fake = FakeIndex(tmp_path)
    sem = SemanticMemory(db_path, index=fake, embedder=FakeEmbedder())
    sem.add("verified fact", memory_type="fact", verification_status="verified")

    comp = MemoryCompactor(
        db_path=db_path,
        audit_db_path=audit_db,
        semantic=sem,
        index=fake,
        unverified_chat_days=9999.0,
        episodic_days=9999.0,
        semantic_max_per_type=9999,
        working_idle_minutes=9999,
    )
    result = comp.compact(dry_run=False)
    assert result["semantic_vector_ids_removed"] == []
    assert sem.count() == 1


def test_compact_caps_unverified_per_type(db_path: Path, audit_db: Path, tmp_path: Path) -> None:
    fake = FakeIndex(tmp_path)
    sem = SemanticMemory(db_path, index=fake, embedder=FakeEmbedder())
    ids = [_add_unverified_chat(sem, f"chat {i}") for i in range(3)]

    comp = MemoryCompactor(
        db_path=db_path,
        audit_db_path=audit_db,
        semantic=sem,
        index=fake,
        unverified_chat_days=9999.0,
        episodic_days=9999.0,
        semantic_max_per_type=1,
        working_idle_minutes=9999,
    )
    result = comp.compact(dry_run=False)
    # Two oldest unverified chat rows should be removed; the newest remains.
    assert result["semantic_per_type_cap_rows"]["chat"] == 2
    assert len(result["semantic_vector_ids_removed"]) == 2
    assert sem.count() == 1


def test_compact_cleans_vector_index(db_path: Path, audit_db: Path, tmp_path: Path) -> None:
    fake = FakeIndex(tmp_path)
    sem = SemanticMemory(db_path, index=fake, embedder=FakeEmbedder())
    _add_unverified_chat(sem, "old chat")
    with memdb.get_connection(db_path) as conn:
        conn.execute(
            "UPDATE semantic_memory SET timestamp = '1970-01-01 00:00:00' "
            "WHERE verification_status = 'unverified'"
        )

    comp = MemoryCompactor(
        db_path=db_path,
        audit_db_path=audit_db,
        semantic=sem,
        index=fake,
        unverified_chat_days=1.0,
        episodic_days=9999.0,
        semantic_max_per_type=9999,
        working_idle_minutes=9999,
    )
    comp.compact(dry_run=False)
    assert fake.removed


def test_compact_writes_one_audit_entry(db_path: Path, audit_db: Path, tmp_path: Path) -> None:
    wm = WorkingMemory()
    wm.set("s1", "k", "v")
    comp = MemoryCompactor(
        db_path=db_path,
        audit_db_path=audit_db,
        working=wm,
        unverified_chat_days=9999.0,
        episodic_days=9999.0,
        semantic_max_per_type=9999,
        working_idle_minutes=0,
    )
    comp.compact(dry_run=False)
    status = audit_logger.verify_chain(db_path=audit_db)
    assert status.valid is True
    assert status.total_entries == 1  # the single action entry


def test_compact_no_audit_entry_on_dry_run(db_path: Path, audit_db: Path, tmp_path: Path) -> None:
    wm = WorkingMemory()
    wm.set("s1", "k", "v")
    comp = MemoryCompactor(
        db_path=db_path,
        audit_db_path=audit_db,
        working=wm,
        unverified_chat_days=9999.0,
        episodic_days=9999.0,
        semantic_max_per_type=9999,
        working_idle_minutes=0,
    )
    comp.compact(dry_run=True)
    status = audit_logger.verify_chain(db_path=audit_db)
    assert status.valid is True
    assert status.total_entries == 0  # nothing written
