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

import numpy as np
import pytest

from aios.memory import db as memdb
from aios.memory.conversation import ConversationStateStore
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


def test_episodic_memory_redacts_secrets_before_persistence(db_path: Path) -> None:
    secret = "sk-" + "a" * 40
    ep = EpisodicMemory(db_path)
    ep.record("sess", "user", f"use {secret}")

    stored = ep.recent("sess")[0]["content"]
    assert secret not in stored
    assert "REDACTED" in stored


def test_episodic_memory_hashes_session_id_before_persistence(db_path: Path) -> None:
    session_id = "private-session-id"
    ep = EpisodicMemory(db_path)
    ep.record(session_id, "user", "hello")

    assert ep.count(session_id) == 1
    assert session_id.encode() not in db_path.read_bytes()


def test_memory_migration_hashes_legacy_episodic_session_id(db_path: Path) -> None:
    session_id = "legacy-session"
    with memdb.get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO episodic_memory (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, "user", "hello"),
        )

    memdb.init_memory_db(db_path)

    assert EpisodicMemory(db_path).count(session_id) == 1
    assert session_id.encode() not in db_path.read_bytes()


def test_conversation_state_persists_latest_frame_under_hashed_session(db_path: Path) -> None:
    session_id = "private-conversation-session"
    store = ConversationStateStore(db_path)
    store.save(session_id, {"goal": "first", "intent": "plan"})
    store.save(session_id, {"goal": "second", "intent": "execute"})

    assert store.get(session_id) == {"goal": "second", "intent": "execute"}
    assert session_id.encode() not in db_path.read_bytes()


def test_conversation_state_redacts_secrets_before_persistence(db_path: Path) -> None:
    secret = "sk-" + "c" * 40
    store = ConversationStateStore(db_path)
    store.save("sess", {"goal": f"do not persist {secret}"})

    restored = store.get("sess")
    assert restored is not None
    assert secret not in restored["goal"]
    assert "REDACTED" in restored["goal"]
    assert secret.encode() not in db_path.read_bytes()


def test_conversation_correction_revision_supersedes_and_clears_to_base(
    db_path: Path,
) -> None:
    session_id = "correction-session"
    store = ConversationStateStore(db_path)
    base = {"goal": "Plan the API", "correction": {"active": False}}
    first = {"goal": "Implement the API", "correction": {"active": True, "revision": 1}}
    revision, persisted = store.record_correction(
        session_id,
        before_frame=base,
        after_frame=first,
        corrections={"goal": "Implement the API"},
        corrected_fields=["goal"],
    )
    second = {
        "goal": "Implement the public API",
        "correction": {"active": True, "revision": 1},
    }
    second_revision, second_persisted = store.record_correction(
        session_id,
        before_frame=persisted,
        after_frame=second,
        corrections={"goal": "Implement the public API"},
        corrected_fields=["goal"],
        expected_revision=revision,
    )

    assert persisted["correction"]["revision"] == revision
    assert second_persisted["correction"]["revision"] == second_revision
    assert store.active_correction(session_id)["corrections"]["goal"] == "Implement the public API"
    assert [item["status"] for item in store.correction_history(session_id)] == [
        "active",
        "superseded",
    ]
    assert store.clear_correction(session_id) == base
    assert store.get(session_id) == base
    assert store.active_correction(session_id) is None
    assert store.correction_history(session_id)[0]["status"] == "cleared"
    assert session_id.encode() not in db_path.read_bytes()


def test_active_correction_refresh_makes_clear_restore_latest_interpretation(
    db_path: Path,
) -> None:
    store = ConversationStateStore(db_path)
    store.record_correction(
        "sess",
        before_frame={"goal": "Old base"},
        after_frame={"goal": "Corrected old base", "correction": {"active": True}},
        corrections={"goal": "Corrected goal"},
        corrected_fields=["goal"],
    )

    store.refresh_active_correction(
        "sess",
        base_frame={"goal": "Latest interpreted base"},
        corrected_frame={"goal": "Corrected goal", "correction": {"active": True}},
    )

    assert store.clear_correction("sess") == {"goal": "Latest interpreted base"}


def test_conversation_correction_rejects_stale_concurrent_revision(db_path: Path) -> None:
    store = ConversationStateStore(db_path)
    revision, _ = store.record_correction(
        "sess",
        before_frame={"goal": "base"},
        after_frame={"goal": "first", "correction": {"active": True}},
        corrections={"goal": "first"},
        corrected_fields=["goal"],
    )

    with pytest.raises(ValueError, match="changed; retry"):
        store.record_correction(
            "sess",
            before_frame={"goal": "first"},
            after_frame={"goal": "stale", "correction": {"active": True}},
            corrections={"goal": "stale"},
            corrected_fields=["goal"],
            expected_revision=revision + 1,
        )


def test_conversation_correction_redacts_secrets_in_history(db_path: Path) -> None:
    secret = "sk-" + "d" * 40
    store = ConversationStateStore(db_path)
    store.record_correction(
        "sess",
        before_frame={"goal": "base"},
        after_frame={"goal": f"use {secret}", "correction": {"active": True}},
        corrections={"goal": f"use {secret}"},
        corrected_fields=["goal"],
    )

    history = store.correction_history("sess")
    assert secret not in history[0]["corrections"]["goal"]
    assert "REDACTED" in history[0]["corrections"]["goal"]
    assert secret.encode() not in db_path.read_bytes()


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


def test_mistake_memory_redacts_secrets_before_persistence(db_path: Path) -> None:
    secret = "sk-" + "a" * 40
    mm = MistakeMemory(db_path)
    mistake_id = mm.record("t1", "Failure", secret, "fixed", secret, -0.1)

    row = mm.get(mistake_id)
    assert secret not in row["root_cause"]
    assert secret not in row["lesson_text"]
    assert "REDACTED" in row["root_cause"]


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


def test_hybrid_search_expands_past_inactive_vector_candidates(db_path: Path) -> None:
    with memdb.get_connection(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO semantic_memory "
            "(text_content, vector_id, content_hash, memory_type, verification_status) "
            "VALUES ('active memory', 1, 'active-hash', 'fact', 'verified')"
        )
        active_id = int(cur.lastrowid)
        conn.execute(
            "UPDATE semantic_memory SET vector_id = ? WHERE id = ?",
            (active_id, active_id),
        )

    class FakeEmbedder:
        def encode(self, text):
            return np.asarray([[0.0, 1.0]], dtype="float32")

    class StaleFirstIndex:
        size = 5

        def search(self, vector, k):
            candidates = [(99, 1.0), (98, 0.9), (97, 0.8), (96, 0.7), (active_id, 0.6)]
            return candidates[:k]

    results = hybrid_search(
        "active memory",
        top_k=1,
        candidate_multiplier=1,
        db_path=db_path,
        index=StaleFirstIndex(),
        embedder=FakeEmbedder(),
    )

    assert results and results[0].id == active_id


def test_semantic_add_removes_db_row_when_embedding_fails(db_path: Path) -> None:
    class BrokenEmbedder:
        def encode(self, text):
            raise RuntimeError("embedding failed")

    sem = SemanticMemory(db_path, index=object(), embedder=BrokenEmbedder())

    with pytest.raises(RuntimeError, match="embedding failed"):
        sem.add("must not remain in the database")

    assert sem.count() == 0


def test_semantic_add_redacts_secrets_before_embedding_and_persistence(db_path: Path) -> None:
    seen: list[str] = []

    class FakeEmbedder:
        def encode(self, text):
            seen.append(text)
            return np.asarray([[0.0, 1.0]], dtype="float32")

    class FakeIndex:
        path = db_path.with_suffix(".faiss")

        def add(self, vector_id, vector):
            pass

        def persist(self):
            pass

    secret = "sk-" + "a" * 40
    sem = SemanticMemory(db_path, index=FakeIndex(), embedder=FakeEmbedder())
    mem_id = sem.add(f"remember {secret}")

    assert secret not in seen[0]
    assert "REDACTED" in seen[0]
    assert secret not in sem.get(mem_id)["text_content"]


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


def test_semantic_add_reloads_durable_index_before_each_write(db_path: Path, tmp_path: Path) -> None:
    class FakeEmbedder:
        def encode(self, text):
            return np.asarray([[0.0, 1.0]], dtype="float32")

    path = tmp_path / "shared.faiss"
    first = SemanticMemory(db_path, index=VectorIndex(path=path, dim=2), embedder=FakeEmbedder())
    second = SemanticMemory(db_path, index=VectorIndex(path=path, dim=2), embedder=FakeEmbedder())

    first.add("first process")
    second.add("second process")

    durable = VectorIndex(path=path, dim=2)
    assert durable.size == 2
    assert {vector_id for vector_id, _ in durable.search(np.asarray([0.0, 1.0]), 2)} == {1, 2}


def test_long_lived_vector_reader_refreshes_after_external_persist(tmp_path: Path) -> None:
    path = tmp_path / "shared.faiss"
    reader = VectorIndex(path=path, dim=2)
    writer = VectorIndex(path=path, dim=2)

    writer.add(7, np.asarray([0.0, 1.0], dtype="float32"))
    writer.persist()

    assert reader.search(np.asarray([0.0, 1.0], dtype="float32"), 1)[0][0] == 7


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


def test_semantic_facts_redact_secrets_before_persistence(db_path: Path) -> None:
    secret = "sk-" + "a" * 40
    facts = SemanticFacts(db_path)
    result = facts.add_fact("service", "credential", secret)

    assert result.committed is True
    stored = facts.get(result.fact_id)
    assert secret not in stored["object"]
    assert "REDACTED" in stored["object"]


def test_contradiction_is_detected_and_not_committed(db_path: Path) -> None:
    facts = SemanticFacts(db_path)
    facts.add_fact("api", "listens_on_port", "8000")
    conflict = facts.add_fact("api", "listens_on_port", "9000")  # same subj+pred, diff obj
    assert conflict.committed is False
    assert conflict.reason == "contradiction"
    assert conflict.conflict_object == "8000"
    # The conflicting fact was NOT silently written; only the original stays active.
    assert [r["object"] for r in facts.facts_for("api", "listens_on_port")] == ["8000"]


def test_concurrent_fact_writers_cannot_commit_contradictions(db_path: Path) -> None:
    barrier = threading.Barrier(2)
    results = []

    def write(obj: str) -> None:
        barrier.wait()
        results.append(SemanticFacts(db_path).add_fact("api", "listens_on_port", obj))

    threads = [threading.Thread(target=write, args=(obj,)) for obj in ("8000", "9000")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(result.reason for result in results) == ["committed", "contradiction"]
    assert len(SemanticFacts(db_path).facts_for("api", "listens_on_port")) == 1


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


# --------------------------------------------------------------------------- #
# G1 — multi-hop fact-graph traversal (the reasoning single-hop facts_for can't do)
# --------------------------------------------------------------------------- #
def test_traverse_single_hop_returns_direct_facts(db_path: Path) -> None:
    facts = SemanticFacts(db_path)
    # Distinct predicates: same subject+predicate with a different object is a
    # contradiction (rejected), so two direct facts need different predicates.
    facts.add_fact("project", "uses", "FastAPI")
    facts.add_fact("project", "persists_with", "SQLite")
    rows = facts.traverse("project", max_depth=1)
    assert {r["object"] for r in rows} == {"FastAPI", "SQLite"}
    assert all(r["depth"] == 1 for r in rows)


def test_traverse_follows_multi_hop_chain(db_path: Path) -> None:
    facts = SemanticFacts(db_path)
    facts.add_fact("project", "uses", "FastAPI")
    facts.add_fact("FastAPI", "needs", "uvicorn")
    facts.add_fact("uvicorn", "needs", "asgi")
    rows = facts.traverse("project", max_depth=3)
    # The transitive reach facts_for (single-hop) cannot produce.
    assert {r["object"]: r["depth"] for r in rows} == {"FastAPI": 1, "uvicorn": 2, "asgi": 3}


def test_traverse_respects_max_depth(db_path: Path) -> None:
    facts = SemanticFacts(db_path)
    facts.add_fact("a", "to", "b")
    facts.add_fact("b", "to", "c")
    facts.add_fact("c", "to", "d")
    rows = facts.traverse("a", max_depth=2)
    assert {r["object"] for r in rows} == {"b", "c"}  # d is depth 3, beyond the limit


def test_traverse_terminates_on_cycle(db_path: Path) -> None:
    facts = SemanticFacts(db_path)
    facts.add_fact("a", "to", "b")
    facts.add_fact("b", "to", "a")  # cycle back to the start
    rows = facts.traverse("a", max_depth=4)
    # Terminates (no infinite loop) and never revisits an already-walked node.
    assert {(r["subject"], r["object"]) for r in rows} == {("a", "b")}


def test_traverse_ignores_superseded_facts(db_path: Path) -> None:
    facts = SemanticFacts(db_path)
    facts.add_fact("project", "uses", "FastAPI")
    facts.reconcile("project", "uses", "Flask")  # supersedes FastAPI; Flask is active
    rows = facts.traverse("project", max_depth=1)
    assert {r["object"] for r in rows} == {"Flask"}


def test_traverse_empty_or_unknown_start_returns_nothing(db_path: Path) -> None:
    facts = SemanticFacts(db_path)
    facts.add_fact("project", "uses", "FastAPI")
    assert facts.traverse("   ", max_depth=2) == []
    assert facts.traverse("nonexistent", max_depth=2) == []
