"""Tests for the four-layer memory system and hybrid retrieval.

Each test uses an isolated temporary database and FAISS index, so the suite
never touches the real ``data/`` artifacts and runs deterministically. The
embedding model is the only shared, network/cache-dependent resource; it is
loaded once at module scope and the embedding-dependent tests are skipped
gracefully if the model cannot be obtained (e.g. fully offline first run).
"""
from __future__ import annotations

import time
import threading
from pathlib import Path

import pytest

from aios.memory import db as memdb
from aios.memory.embeddings import EmbeddingModel, VectorIndex
from aios.memory.episodic import EpisodicMemory
from aios.memory.facts import SemanticFacts
from aios.memory.mistake import MistakeMemory
from aios.memory.retrieval import hybrid_search
from aios.memory.semantic import SemanticMemory
from aios.memory.working import WorkingMemory


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """An initialised, isolated memory database in a temp directory."""
    path = tmp_path / "memory.db"
    memdb.init_memory_db(path)
    return path


@pytest.fixture(scope="module")
def embedder() -> EmbeddingModel:
    """Shared embedding model, or skip the whole module if unavailable."""
    try:
        return EmbeddingModel.instance()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"embedding model unavailable: {exc}")


# --------------------------------------------------------------------------- #
# L1 Working memory
# --------------------------------------------------------------------------- #
def test_working_memory_kv_and_history_isolated_per_session() -> None:
    wm = WorkingMemory()
    wm.set("s1", "goal", "build memory layer")
    wm.append_message("s1", "user", "hello")
    wm.append_message("s1", "assistant", "hi")

    assert wm.get("s1", "goal") == "build memory layer"
    assert wm.get("s2", "goal", default="none") == "none"
    assert [m["role"] for m in wm.history("s1")] == ["user", "assistant"]
    assert wm.history("s2") == []

    wm.clear("s1")
    assert wm.get("s1", "goal") is None
    assert wm.history("s1") == []


# --------------------------------------------------------------------------- #
# L2 Episodic memory
# --------------------------------------------------------------------------- #
def test_episodic_records_and_returns_in_chronological_order(db_path: Path) -> None:
    ep = EpisodicMemory(db_path)
    ep.record("sess", "user", "first")
    ep.record("sess", "assistant", "second")
    ep.record("other", "user", "elsewhere")

    recent = ep.recent("sess", limit=10)
    assert [r["content"] for r in recent] == ["first", "second"]
    assert ep.count("sess") == 2
    assert ep.count() == 3


# --------------------------------------------------------------------------- #
# L4 Mistake pool
# --------------------------------------------------------------------------- #
def test_mistake_clamps_delta_and_lifecycle_transitions(db_path: Path) -> None:
    mm = MistakeMemory(db_path)
    # A positive delta must be clamped to 0.0 (lessons can only reduce confidence).
    mid = mm.record(
        task_id="t1",
        error_type="TypeError",
        root_cause="None passed where dict expected",
        fix_applied="Added a guard clause",
        lesson_text="Validate inputs before use",
        confidence_delta=0.5,
    )
    row = mm.get(mid)
    assert row is not None
    assert row["confidence_delta"] == 0.0
    assert row["verification_status"] == "pending"

    mm.promote(mid)
    assert mm.get(mid)["verification_status"] == "verified"

    # Recurrence detection + occurrence increment.
    found = mm.find_recurrence("t1", "TypeError")
    assert found is not None and found["id"] == mid
    mm.increment_occurrence(mid)
    assert mm.get(mid)["occurrence_count"] == 2

    # Out-of-range negative delta is clamped to -1.0.
    mid2 = mm.record("t2", "Timeout", "slow net", "retry", "add timeout", -5.0)
    assert mm.get(mid2)["confidence_delta"] == -1.0
    mm.supersede(mid, mid2)
    assert mm.get(mid)["verification_status"] == "superseded"
    assert mm.get(mid)["superseded_by"] == mid2


# --------------------------------------------------------------------------- #
# L3 Semantic memory + hybrid retrieval (embedding-dependent)
# --------------------------------------------------------------------------- #
def test_semantic_add_and_hybrid_search_ranks_relevant_first(
    db_path: Path, tmp_path: Path, embedder: EmbeddingModel
) -> None:
    index = VectorIndex(path=tmp_path / "index.faiss", dim=embedder.dim)
    sem = SemanticMemory(db_path, index=index, embedder=embedder)

    sem.add("The security gateway classifies actions into GREEN, YELLOW, and RED zones.")
    sem.add("FAISS performs approximate nearest-neighbour vector search.")
    sem.add("My favourite breakfast is buttered toast with jam.")

    assert sem.count() == 3
    assert index.size == 3

    results = hybrid_search(
        "How does the security zone classifier work?",
        top_k=2,
        db_path=db_path,
        index=index,
        embedder=embedder,
    )
    assert results, "expected at least one hit"
    # The security-gateway chunk should rank first for a security query.
    assert "security" in results[0].text.lower()
    # Sub-scores are exposed and the composite is the weighted sum.
    top = results[0]
    assert 0.0 <= top.faiss <= 1.0
    assert 0.0 <= top.recency <= 1.0
    assert results == sorted(results, key=lambda r: r.score, reverse=True)


def test_hybrid_search_empty_index_returns_empty(
    db_path: Path, tmp_path: Path, embedder: EmbeddingModel
) -> None:
    index = VectorIndex(path=tmp_path / "empty.faiss", dim=embedder.dim)
    assert (
        hybrid_search("anything", db_path=db_path, index=index, embedder=embedder)
        == []
    )


def test_semantic_add_removes_db_row_when_embedding_fails(db_path: Path) -> None:
    class BrokenEmbedder:
        def encode(self, text):
            raise RuntimeError("embedding failed")

    sem = SemanticMemory(db_path, index=object(), embedder=BrokenEmbedder())

    with pytest.raises(RuntimeError, match="embedding failed"):
        sem.add("must not remain in the database")

    assert sem.count() == 0


def test_semantic_add_removes_db_row_when_index_persist_fails(db_path: Path) -> None:
    class FakeEmbedder:
        def encode(self, text):
            return [[0.0, 1.0]]

    class BrokenIndex:
        def add(self, vector_id, vector):
            pass

        def persist(self):
            raise RuntimeError("persist failed")

    sem = SemanticMemory(db_path, index=BrokenIndex(), embedder=FakeEmbedder())

    with pytest.raises(RuntimeError, match="persist failed"):
        sem.add("must be compensated")

    assert sem.count() == 0


def test_semantic_add_serialises_index_mutations(db_path: Path) -> None:
    active = 0
    max_active = 0
    guard = threading.Lock()

    class FakeEmbedder:
        def encode(self, text):
            return [[0.0, 1.0]]

    class RecordingIndex:
        def add(self, vector_id, vector):
            nonlocal active, max_active
            with guard:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.03)
            with guard:
                active -= 1

        def persist(self):
            pass

    index = RecordingIndex()
    memories = [
        SemanticMemory(db_path, index=index, embedder=FakeEmbedder()),
        SemanticMemory(db_path, index=index, embedder=FakeEmbedder()),
    ]
    threads = [threading.Thread(target=mem.add, args=(f"row-{i}",)) for i, mem in enumerate(memories)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert max_active == 1
    assert memories[0].count() == 2


def test_recency_term_decays_over_time() -> None:
    """The exponential recency term must be monotonically decreasing in dt."""
    from aios import config
    from aios.memory.retrieval import _hours_since
    from datetime import datetime, timedelta, timezone
    import math

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    older = (now - timedelta(hours=10)).strftime("%Y-%m-%d %H:%M:%S")
    newer = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")

    decay_old = math.exp(-config.RETRIEVAL_LAMBDA_DECAY_PER_HOUR * _hours_since(older, now))
    decay_new = math.exp(-config.RETRIEVAL_LAMBDA_DECAY_PER_HOUR * _hours_since(newer, now))
    assert decay_new > decay_old


# --------------------------------------------------------------------------- #
# L3 Semantic facts + contradiction detection (Blueprint 5.3)
# --------------------------------------------------------------------------- #
def test_fact_commits_when_no_conflict(db_path: Path) -> None:
    facts = SemanticFacts(db_path)
    res = facts.add_fact("api", "listens_on_port", "8000")
    assert res.committed is True and res.fact_id is not None
    assert [r["object"] for r in facts.facts_for("api", "listens_on_port")] == ["8000"]


def test_fact_exact_duplicate_is_idempotent(db_path: Path) -> None:
    facts = SemanticFacts(db_path)
    first = facts.add_fact("user", "prefers", "dark mode")
    again = facts.add_fact("user", "prefers", "dark mode")
    assert again.committed is True
    assert again.fact_id == first.fact_id            # no duplicate row created
    assert len(facts.facts_for("user", "prefers")) == 1


def test_contradiction_is_detected_and_not_committed(db_path: Path) -> None:
    facts = SemanticFacts(db_path)
    facts.add_fact("api", "listens_on_port", "8000")
    conflict = facts.add_fact("api", "listens_on_port", "9000")  # same subj+pred, diff obj
    assert conflict.committed is False
    assert conflict.reason == "contradiction"
    assert conflict.conflict_object == "8000"
    # The conflicting fact was NOT silently written; only the original stays active.
    assert [r["object"] for r in facts.facts_for("api", "listens_on_port")] == ["8000"]


def test_reconcile_supersedes_old_and_commits_new(db_path: Path) -> None:
    facts = SemanticFacts(db_path)
    facts.add_fact("api", "listens_on_port", "8000")
    facts.add_fact("api", "listens_on_port", "9000")             # contradiction, not committed
    res = facts.reconcile("api", "listens_on_port", "9000")
    assert res.committed is True
    assert [r["object"] for r in facts.facts_for("api", "listens_on_port")] == ["9000"]


def test_reconcile_rejects_empty_object(db_path: Path) -> None:
    facts = SemanticFacts(db_path)
    facts.add_fact("api", "listens_on_port", "8000")
    res = facts.reconcile("api", "listens_on_port", "   ")
    assert res.committed is False
    # The existing fact is untouched (not superseded by a blank value).
    assert [r["object"] for r in facts.facts_for("api", "listens_on_port")] == ["8000"]
