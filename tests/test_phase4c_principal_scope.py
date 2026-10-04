"""Plan Phase 4 remainder, slice 4c-1: learned memory belongs to a principal.

Operator decisions, 2026-09-29 and 2026-10-04: principal scoping covers
everything; a row learned before scoping (no principal) is withheld from
everyone until re-earned or readmitted.

* Every learned write records its principal -- as row identity (a column) and
  under the signature (its provenance).
* Recall admits a row only for the principal its SIGNED provenance names; a
  recall that names no one recalls nothing.
* Identity is per principal: one principal's write never increments,
  promotes, supersedes or contradicts another's row.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)

from aios.application.memory.adapters import (
    LegacySemanticMemoryAdapter,
    MistakeMemoryAdapter,
    SemanticFactsAdapter,
)
from aios.application.memory.provenance_policy import ProvenanceWriter, RecallGate
from aios.core.verification_strength import VerificationStrength
from aios.domain.memory import MemoryRecallContext
from aios.memory import learning_freeze
from aios.memory.db import init_memory_db
from aios.memory.facts import SemanticFacts
from aios.memory.mistake import MistakeMemory
from aios.memory.provenance import LearningSigner, LearningVerifier, ProvenanceStore
from aios.memory.semantic import SemanticMemory
from aios.runtime.self_model_handler import SelfModelHandler

ALICE = "principal:alice"
BOB = "principal:bob"
GOAL = "prepare the release build"


def _seed() -> str:
    return (
        Ed25519PrivateKey.generate()
        .private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        .hex()
    )


def _lesson(**overrides):
    return {
        "task_id": "session-1",
        "error_type": "ReleaseError",
        "root_cause": "the build needs a warm-up",
        "fix_applied": "warm up first",
        "lesson_text": "prepare the release build with a warm-up step",
        "confidence_delta": -0.1,
        "failed_command": "make release",
        **overrides,
    }


class _Embedder:
    def encode(self, text: str):
        return [[0.0, 1.0]]


class _Index:
    def __init__(self, path: Path) -> None:
        self.path = path

    def reload(self) -> None:
        pass

    def add(self, vector_id: int, vector) -> None:
        pass

    def persist(self) -> None:
        pass


@pytest.fixture()
def world(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        learning_freeze, "_latch_path", lambda: tmp_path / "emergency_stop.db"
    )
    monkeypatch.setattr(learning_freeze, "_controllers", {})
    db = tmp_path / "memory.db"
    init_memory_db(db)
    signer = LearningSigner({"live": _seed()})
    verifier = LearningVerifier({"live": [signer.public_keys()["live"]]})
    store = ProvenanceStore(db)
    writer = ProvenanceWriter(store, signer, source_kind="live", verifier=verifier)
    gate = RecallGate(store, verifier, context="live")
    return SimpleNamespace(
        db=db,
        gate=gate,
        store=store,
        lessons=MistakeMemoryAdapter(
            MistakeMemory(db_path=db), provenance=writer, gate=gate
        ),
        semantic=LegacySemanticMemoryAdapter(
            SemanticMemory(
                db, index=_Index(tmp_path / "i.faiss"), embedder=_Embedder()
            ),
            provenance=writer,
            gate=gate,
        ),
        facts=SemanticFactsAdapter(SemanticFacts(db), provenance=writer, gate=gate),
    )


def _learn(world, principal, **overrides) -> int:
    lid, _ = world.lessons.record_or_increment(
        **_lesson(**overrides), principal=principal
    )
    world.lessons.promote(
        lid, strength=VerificationStrength.STRONG, principal=principal
    )
    return lid


def _recalled(world, principal) -> set[int]:
    return {
        int(item["mistake_id"])
        for item in world.lessons.relevant_verified(GOAL, 5, principal=principal)
    }


# ------------------------------------------------------------ the gate


class TestRecallIsPerPrincipal:
    def test_a_principals_lesson_is_recalled_for_them_only(self, world) -> None:
        lid = _learn(world, ALICE)
        assert _recalled(world, ALICE) == {lid}, "positive control"
        assert _recalled(world, BOB) == set()

    def test_another_principals_row_is_refused_by_name(self, world) -> None:
        """Bob's recall reaches Alice's row -- forced here by moving the
        column -- and the gate refuses it on the SIGNED principal."""
        lid = _learn(world, ALICE)
        with sqlite3.connect(world.db) as conn:
            conn.execute(
                "UPDATE mistake_pool SET principal_id = ? WHERE id = ?", (BOB, lid)
            )
        assert _recalled(world, BOB) == set()
        assert world.gate.refused.get("another principal", 0) >= 1

    def test_a_recall_that_names_no_one_recalls_nothing(self, world) -> None:
        _learn(world, ALICE)
        _learn(world, None, error_type="Unattributed")
        assert _recalled(world, None) == set()
        assert world.gate.refused.get("no principal", 0) >= 1

    def test_a_row_learned_before_scoping_is_withheld_from_everyone(
        self, world
    ) -> None:
        """Operator decision 2026-10-04: no principal, no recall -- until
        re-earned or readmitted. Signed, so only the missing name refuses it."""
        lid = _learn(world, None)
        assert world.lessons.relevant_verified(GOAL, 5, principal=None) == []
        rows = world.lessons.store.relevant_verified(GOAL, 5, principal_id=None)
        assert [int(r["mistake_id"]) for r in rows] == [lid]
        assert (
            world.gate.admits("mistake_pool", lid, _digest(world, lid), principal=ALICE)
            is False
        )
        assert world.gate.refused.get("unattributed", 0) >= 1

    def test_a_pending_lesson_is_recalled_for_its_principal(self, world) -> None:
        """Never promoted, so its only record is the creation one: that record
        must name the principal too, not just a later promotion."""
        lid, _ = world.lessons.record_or_increment(**_lesson(), principal=ALICE)
        recalled = world.lessons.recall_relevant(GOAL, "session-1", 5, principal=ALICE)
        assert lid in {int(r["mistake_id"]) for r in recalled}
        assert world.store.latest("mistake_pool", str(lid)).provenance.principal == (
            ALICE
        )

    def test_the_signed_principal_is_part_of_the_provenance(self, world) -> None:
        lid = _learn(world, ALICE)
        assert (
            world.store.latest("mistake_pool", str(lid)).provenance.principal == ALICE
        )

    def test_semantic_memory_is_per_principal(self, world) -> None:
        mem = world.semantic.add(
            "release notes live in docs",
            memory_type="fact",
            verification_status="verified",
            principal=ALICE,
        )
        world.semantic.promote(mem, principal=ALICE)
        hits = world.semantic.recall(
            "release notes",
            MemoryRecallContext(limit=5, principal_id=BOB),
            retrieval_fn=lambda q, top_k: [SimpleNamespace(id=mem, text="x")],
        )
        assert hits == ()
        own = world.semantic.recall(
            "release notes",
            MemoryRecallContext(limit=5, principal_id=ALICE),
            retrieval_fn=lambda q, top_k: [SimpleNamespace(id=mem, text="x")],
        )
        assert [h.external_id for h in own] == [mem]


def test_a_turn_indexed_through_the_live_indexer_is_its_principals(world) -> None:
    """In production the turn indexer IS the semantic adapter
    (``deps.get_semantic_indexer``, pinned in ``test_memory_architecture``), so
    ``record_chat`` writes through it. The learning red-team reel found every
    live turn failing to index here: the adapter takes ``principal``, not the
    store's ``principal_id``."""
    mem = world.semantic.record_chat(
        "User: hi\nAssistant: hello", indexer=world.semantic, principal=ALICE
    )
    with sqlite3.connect(world.db) as conn:
        row = conn.execute(
            "SELECT memory_type, verification_status, principal_id "
            "FROM semantic_memory WHERE id = ?",
            (mem,),
        ).fetchone()
    assert row == ("chat", "unverified", ALICE)
    assert world.store.latest("semantic_memory", str(mem)).provenance.principal == (
        ALICE
    )


def _digest(world, lid: int) -> str:
    from aios.application.memory.provenance_policy import lesson_digest

    return lesson_digest(world.lessons.store.get(lid))


# ------------------------------------------------------------ identity


class TestOnePrincipalCannotTouchAnothersRow:
    def test_the_same_lesson_from_two_principals_is_two_rows(self, world) -> None:
        a, a_recur = world.lessons.record_or_increment(**_lesson(), principal=ALICE)
        b, b_recur = world.lessons.record_or_increment(**_lesson(), principal=BOB)
        assert a != b and not a_recur and not b_recur
        again, recur = world.lessons.record_or_increment(**_lesson(), principal=BOB)
        assert again == b and recur
        assert int(world.lessons.store.get(a)["occurrence_count"]) == 1

    def test_one_principal_cannot_promote_anothers_lesson(self, world) -> None:
        """Nor sign anything onto it: a transition record naming Bob on Alice's
        row would make the gate refuse it to Alice -- a silent denial."""
        lid, _ = world.lessons.record_or_increment(**_lesson(), principal=ALICE)
        world.lessons.promote(
            lid, strength=VerificationStrength.STRONG, principal=ALICE
        )
        world.lessons.promote(lid, strength=VerificationStrength.STRONG, principal=BOB)
        assert world.store.latest("mistake_pool", str(lid)).provenance.principal == (
            ALICE
        )
        assert _recalled(world, ALICE) == {lid}
        pending, _ = world.lessons.record_or_increment(
            **_lesson(error_type="Other"), principal=ALICE
        )
        world.lessons.promote(
            pending, strength=VerificationStrength.STRONG, principal=BOB
        )
        assert world.lessons.store.get(pending)["verification_status"] == "pending"

    def test_the_same_memory_from_two_principals_is_two_rows(self, world) -> None:
        a = world.semantic.add("the same words", principal=ALICE)
        b = world.semantic.add("the same words", principal=BOB)
        assert a != b
        assert world.semantic.supersede_text("the same words", principal=BOB) == 1
        assert world.semantic.store.get(a)["verification_status"] != "superseded"

    def test_another_principals_fact_is_never_a_contradiction(self, world) -> None:
        a = world.facts.add_fact(
            "project", "uses", "FastAPI", approved_by="alice", principal=ALICE
        )
        b = world.facts.add_fact(
            "project", "uses", "Flask", approved_by="bob", principal=BOB
        )
        assert a.committed and b.committed
        world.facts.reconcile(
            "project", "uses", "Django", approved_by="bob", principal=BOB
        )
        alice_rows = world.facts.facts_for("project", principal=ALICE)
        assert [r["object"] for r in alice_rows] == ["FastAPI"]
        assert [
            r["object"] for r in world.facts.facts_for("project", principal=BOB)
        ] == ["Django"]

    def test_a_principal_approves_only_its_own_proposals(self, world) -> None:
        proposal = world.facts.store.propose(
            "operator", "prefers", "tea", principal_id=ALICE
        )
        assert world.facts.pending_proposals(principal=BOB) == []
        refused = world.facts.approve_proposal(
            proposal.proposal_id, approved_by="bob", principal=BOB
        )
        assert (
            not refused.committed and refused.reason == "another principal's proposal"
        )
        approved = world.facts.approve_proposal(
            proposal.proposal_id, approved_by="alice", principal=ALICE
        )
        assert approved.committed
        assert [
            r["object"] for r in world.facts.facts_for("operator", principal=ALICE)
        ] == ["tea"]

    def test_a_graph_walk_never_crosses_principals(self, world) -> None:
        world.facts.add_fact("a", "to", "b", approved_by="alice", principal=ALICE)
        world.facts.add_fact("b", "to", "c", approved_by="bob", principal=BOB)
        reached = {
            r["object"]
            for r in world.facts.store.traverse("a", max_depth=3, principal_id=ALICE)
        }
        assert reached == {"b"}
        weighted = world.facts.traverse_weighted("a", max_depth=3, principal=ALICE)
        assert {e.object for e in weighted} == {"b"}


# ------------------------------------------------------------ migration


def test_an_old_database_gains_the_column_and_its_rows_stay_unattributed(
    tmp_path,
) -> None:
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE mistake_pool (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, task_id TEXT NOT NULL, "
            "error_type TEXT NOT NULL, root_cause TEXT NOT NULL, "
            "fix_applied TEXT NOT NULL, lesson_text TEXT NOT NULL, "
            "confidence_delta REAL NOT NULL, verification_status TEXT NOT NULL "
            "DEFAULT 'pending', superseded_by INTEGER, occurrence_count INTEGER "
            "NOT NULL DEFAULT 1, failed_command TEXT NOT NULL DEFAULT '')"
        )
        conn.execute(
            "INSERT INTO mistake_pool (task_id, error_type, root_cause, fix_applied, "
            "lesson_text, confidence_delta) VALUES ('t', 'e', 'r', 'f', 'l', -0.1)"
        )
    init_memory_db(db)
    init_memory_db(db)
    with sqlite3.connect(db) as conn:
        assert [
            r[0] for r in conn.execute("SELECT principal_id FROM mistake_pool")
        ] == [None]


# ------------------------------------------------------------ the self-model


class _Authority:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def self_model(self, *, principal):
        self.calls.append(principal)
        return f"self of {principal}"


def _completed(tmp_path: Path, turn_id: str):
    """A ``turn.completed`` exactly as the SSE layer appends it
    (``aios/api/main.py``: session_id and turn_id both the turn id), read back
    from a real bus -- the stored payload is ``CanonicalEvent.to_dict()``."""
    from aios.core.events import CanonicalEvent, EventPhase, TrustLevel
    from aios.runtime.cortex_bus import CortexBus

    bus = CortexBus(db_path=tmp_path / "bus.db")
    bus.append(
        CanonicalEvent(
            event_type="turn.completed",
            phase=EventPhase.NARRATIVE.value,
            status="completed",
            trust=TrustLevel.ADVISORY.value,
            source="aios.api.main.sse",
            session_id=turn_id,
            turn_id=turn_id,
            payload={},
        )
    )
    (event,) = bus.fetch_since(0, limit=10)
    return event


def test_the_self_model_cache_is_per_principal(tmp_path) -> None:
    authority = _Authority()
    handler = SelfModelHandler(memory_authority=authority)
    handler.remember("turn-1", ALICE)
    handler(_completed(tmp_path, "turn-1"))
    assert handler.recall(ALICE) == f"self of {ALICE}"
    assert handler.recall(BOB) is None
    assert handler.recall(None) is None


def test_a_turn_nobody_named_refreshes_nothing(tmp_path) -> None:
    authority = _Authority()
    handler = SelfModelHandler(memory_authority=authority)
    handler(_completed(tmp_path, "turn-unknown"))
    assert authority.calls == []


def test_startup_never_merges_two_principals_memories(world) -> None:
    """``init_memory_db`` merges duplicate memories on every start. Within one
    principal that is housekeeping; across two it would hand one principal's
    row to the other."""
    a = world.semantic.add("the same words", principal=ALICE)
    b = world.semantic.add("the same words", principal=BOB)
    init_memory_db(world.db)
    assert world.semantic.store.get(a) is not None
    assert world.semantic.store.get(b) is not None
    with sqlite3.connect(world.db) as conn:
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' "
                "AND tbl_name = 'semantic_memory'"
            )
        }
    assert "idx_semantic_active_hash" not in names
    assert "idx_semantic_active_hash_principal" in names
