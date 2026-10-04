"""Plan Phase 4c-3: what the learning hardening may cost a turn.

Wall-clock depends on the machine, so it is measured, not asserted here:
``tools/learning_latency_bench.py`` times a whole turn with a populated, signed
store on one machine across trees (docs/learning/PHASE4_DESIGN.md, 4c-3). What
this file pins is the cost that does NOT depend on the machine: the work the
recall gate does per check.

The bench found the largest single cost a learned store added to a turn: the
fact gate re-ran the whole schema script and every migration
(``init_memory_db``) on EVERY recalled triple it verified -- about 23 times a
turn at 50 facts, some 20 ms each on the reference laptop.
"""

from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)

from aios.application.memory import adapters as adapters_module
from aios.application.memory.adapters import SemanticFactsAdapter
from aios.application.memory.provenance_policy import ProvenanceWriter, RecallGate
from aios.memory import learning_freeze
from aios.memory.db import init_memory_db
from aios.memory.facts import SemanticFacts
from aios.memory.provenance import LearningSigner, LearningVerifier, ProvenanceStore

PRINCIPAL = "principal:latency"


def _seed() -> str:
    return (
        Ed25519PrivateKey.generate()
        .private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        .hex()
    )


def test_the_fact_gate_ensures_the_schema_once(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        learning_freeze, "_latch_path", lambda: tmp_path / "emergency_stop.db"
    )
    monkeypatch.setattr(learning_freeze, "_controllers", {})
    db = tmp_path / "memory.db"
    init_memory_db(db)
    signer = LearningSigner({"live": _seed()})
    verifier = LearningVerifier({"live": [signer.public_keys()["live"]]})
    store = ProvenanceStore(db)
    facts = SemanticFactsAdapter(
        SemanticFacts(db),
        provenance=ProvenanceWriter(
            store, signer, source_kind="live", verifier=verifier
        ),
        gate=RecallGate(store, verifier, context="live"),
    )
    for i in range(5):
        facts.add_fact(
            "router",
            f"needs_step_{i}",
            f"step {i}",
            approved_by="op",
            principal=PRINCIPAL,
        )

    calls: list[Path] = []
    real = adapters_module.init_memory_db

    def counting(path):
        calls.append(path)
        return real(path)

    monkeypatch.setattr(adapters_module, "init_memory_db", counting)
    admitted = [
        facts._admits_triple("router", f"needs_step_{i}", f"step {i}", PRINCIPAL)
        for i in range(5)
        for _ in range(4)
    ]
    assert all(admitted), "positive control: every signed triple is admitted"
    assert len(calls) <= 1, f"the schema was ensured {len(calls)} times for 20 checks"


def _facts(tmp_path: Path, monkeypatch) -> tuple[SemanticFactsAdapter, Path]:
    monkeypatch.setattr(
        learning_freeze, "_latch_path", lambda: tmp_path / "emergency_stop.db"
    )
    monkeypatch.setattr(learning_freeze, "_controllers", {})
    db = tmp_path / "memory.db"
    init_memory_db(db)
    signer = LearningSigner({"live": _seed()})
    verifier = LearningVerifier({"live": [signer.public_keys()["live"]]})
    store = ProvenanceStore(db)
    adapter = SemanticFactsAdapter(
        SemanticFacts(db),
        provenance=ProvenanceWriter(
            store, signer, source_kind="live", verifier=verifier
        ),
        gate=RecallGate(store, verifier, context="live"),
    )
    return adapter, db


def test_the_batched_gate_admits_exactly_what_each_row_proves(
    tmp_path: Path, monkeypatch
) -> None:
    """One query for a walk's triples; still every row verified on its own."""
    import sqlite3

    facts, db = _facts(tmp_path, monkeypatch)
    facts.add_fact("router", "uses", "FastAPI", approved_by="op", principal=PRINCIPAL)
    facts.add_fact("router", "serves", "api", approved_by="op", principal=PRINCIPAL)
    # No approver: recorded unsigned (3b), never admitted.
    facts.add_fact("router", "runs_on", "uvicorn", principal=PRINCIPAL)
    # Tampered after signing: content changed since it was signed.
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE semantic_facts SET approved_by = 'forged' WHERE predicate = 'serves'"
        )
    triples = [
        ("router", "uses", "FastAPI"),
        ("router", "serves", "api"),
        ("router", "runs_on", "uvicorn"),
        ("router", "absent", "nothing"),
    ]
    assert facts._admitted_triples(triples, PRINCIPAL) == {
        ("router", "uses", "FastAPI")
    }
    assert [facts._admits_triple(*t, PRINCIPAL) for t in triples] == [
        True,
        False,
        False,
        False,
    ]
    assert facts._admitted_triples(triples, None) == set()


def test_the_same_triple_of_two_principals_is_each_ones_own(
    tmp_path: Path, monkeypatch
) -> None:
    """Bob's NEWER row of the same triple never shadows Alice's own."""
    facts, _ = _facts(tmp_path, monkeypatch)
    other = "principal:other"
    facts.add_fact("router", "uses", "FastAPI", approved_by="op", principal=PRINCIPAL)
    facts.add_fact("router", "uses", "FastAPI", approved_by="op", principal=other)
    triple = [("router", "uses", "FastAPI")]
    assert facts._admitted_triples(triple, PRINCIPAL) == set(triple)
    assert facts._admitted_triples(triple, other) == set(triple)
    assert [r["object"] for r in facts.neighbors("router", principal=PRINCIPAL)] == [
        "FastAPI"
    ]


def test_a_walk_looks_its_triples_up_in_one_query(tmp_path: Path, monkeypatch) -> None:
    facts, _ = _facts(tmp_path, monkeypatch)
    for i in range(12):
        facts.add_fact(
            "router", f"needs_{i}", f"step {i}", approved_by="op", principal=PRINCIPAL
        )
    facts._admitted_triples([("router", "needs_0", "step 0")], PRINCIPAL)  # schema
    opened: list[object] = []
    real = adapters_module.get_connection

    def counting(path):
        opened.append(path)
        return real(path)

    monkeypatch.setattr(adapters_module, "get_connection", counting)
    admitted = facts._admitted_triples(
        [("router", f"needs_{i}", f"step {i}") for i in range(12)], PRINCIPAL
    )
    assert len(admitted) == 12, "positive control"
    assert len(opened) == 1
