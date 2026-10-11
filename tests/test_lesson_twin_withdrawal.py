"""A withdrawn lesson's consolidated twin is withdrawn with it (RT-27, RT-28).

The live turn's confirm hook consolidates a promoted lesson AT ONCE into a
``VERIFIED LESSON`` semantic memory, and the operator's consolidation
re-indexes every verified lesson. Revocation (6e) and the quarantine (6d)
withdrew the lesson's provenance and never touched its twin -- which recall
admitted -- so both were bypassed on a live system. These hold now:

* a revocation and a quarantine withdraw the twin too: by the recorded
  lesson -> twin derivation, and by the twin's exact text for twins made
  before derivations were recorded -- for that principal only;
* consolidation follows recall's verdict: a lesson recall refuses is never
  indexed again;
* consolidation records lesson -> twin, once (the derivation graph's first
  live producer, plan Phase 3.3).
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)

from aios.memory import learning_freeze

ALICE, BOB = "principal:alice-twin", "principal:bob-twin"


def _seed() -> str:
    return (
        Ed25519PrivateKey.generate()
        .private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        .hex()
    )


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Bootstrap's shape: one signed provenance writer and one recall gate
    over lessons, semantic memory and facts; the authority; consolidation."""
    from aios.application.memory.adapters import (
        LegacySemanticMemoryAdapter,
        MemoryConsolidationAdapter,
        MistakeMemoryAdapter,
        SemanticFactsAdapter,
    )
    from aios.application.memory.authority import MemoryAuthority
    from aios.application.memory.provenance_policy import ProvenanceWriter, RecallGate
    from aios.infrastructure.memory.authority_store import MemoryAuthorityStore
    from aios.memory.consolidation import MemoryConsolidator
    from aios.memory.db import init_memory_db
    from aios.memory.facts import SemanticFacts
    from aios.memory.mistake import MistakeMemory
    from aios.memory.provenance import LearningSigner, LearningVerifier, ProvenanceStore
    from aios.memory.semantic import SemanticMemory

    monkeypatch.setattr(
        learning_freeze, "_latch_path", lambda: tmp_path / "emergency_stop.db"
    )
    monkeypatch.setattr(learning_freeze, "_controllers", {})
    db = tmp_path / "memory.sqlite"
    init_memory_db(db)
    signer = LearningSigner({"live": _seed()})
    verifier = LearningVerifier({"live": [signer.public_keys()["live"]]})
    store = ProvenanceStore(db)
    writer = ProvenanceWriter(store, signer, source_kind="live", verifier=verifier)
    gate = RecallGate(store, verifier, context="live")
    adapters = {
        "semantic": LegacySemanticMemoryAdapter(
            SemanticMemory(db), provenance=writer, gate=gate
        ),
        "facts": SemanticFactsAdapter(
            SemanticFacts(db_path=db), provenance=writer, gate=gate
        ),
        "lessons": MistakeMemoryAdapter(
            MistakeMemory(db_path=db), provenance=writer, gate=gate
        ),
    }
    authority = MemoryAuthority(
        store=MemoryAuthorityStore(tmp_path / "authority.db"), adapters=adapters
    )
    consolidation = MemoryConsolidationAdapter(
        MemoryConsolidator(
            semantic=adapters["semantic"].store,
            mistakes=adapters["lessons"].store,
            facts=adapters["facts"].store,
            memory_authority=authority,
            db_path=db,
        )
    )
    authority.register_adapter("consolidation", consolidation)
    consolidation.bind_authority(authority)
    return SimpleNamespace(
        root=tmp_path,
        db=db,
        store=store,
        signer=signer,
        gate=gate,
        authority=authority,
        lessons=adapters["lessons"],
    )


def _lesson(world, *, principal=ALICE, task="task-twin") -> int:
    from aios.core.verification_strength import VerificationStrength

    mistake_id, _ = world.lessons.record_or_increment(
        task,
        "release_build",
        "the warm-up step was skipped",
        "ran the warm-up step",
        "When preparing the release build, always run the warm-up step first.",
        -0.1,
        failed_command="make warmup",
        principal=principal,
    )
    world.lessons.promote(
        int(mistake_id), strength=VerificationStrength.STRONG, principal=principal
    )
    return int(mistake_id)


def _twin_admitted(world, twin: int, principal=ALICE) -> bool:
    from aios.application.memory.provenance_policy import semantic_digest

    with sqlite3.connect(world.db) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM semantic_memory WHERE id = ?", (twin,)
        ).fetchone()
    return world.gate.admits(
        "semantic_memory", twin, semantic_digest(row), principal=principal
    )


def _revoke(world, lesson: int) -> dict:
    from tools.revoke_learning import revoke

    return revoke(
        world.db,
        world.store,
        world.signer,
        table="mistake_pool",
        ids=[lesson],
        approver="operator:test",
        reason="twin test",
    )


def _newest(world, table: str, row_id: int) -> str:
    import json

    with sqlite3.connect(world.db) as conn:
        row = conn.execute(
            "SELECT provenance_json FROM learning_provenance WHERE row_table = ? "
            "AND row_id = ? ORDER BY id DESC LIMIT 1",
            (table, str(row_id)),
        ).fetchone()
    return json.loads(row[0])["transition"]


def test_consolidation_records_the_twin_once(world) -> None:
    lesson = _lesson(world)
    twin = world.authority.consolidate_lesson(lesson)
    assert twin is not None and _twin_admitted(world, twin)
    world.authority.consolidate_lesson(lesson)
    world.authority.consolidate()
    assert world.store.children_of("mistake_pool", str(lesson)) == [
        ("semantic_memory", str(twin), "consolidated")
    ]


def test_revoking_a_lesson_withdraws_its_twin(world) -> None:
    lesson = _lesson(world)
    twin = world.authority.consolidate_lesson(lesson)
    assert _twin_admitted(world, twin)

    done = _revoke(world, lesson)

    assert f"semantic_memory:{twin} (consolidated)" in done["withdrawn"]
    assert _newest(world, "semantic_memory", twin) == "withdrawn"
    assert not _twin_admitted(world, twin)


def test_a_twin_made_before_derivations_is_found_by_its_text(world) -> None:
    lesson = _lesson(world)
    twin = world.authority.consolidate_lesson(lesson)
    with sqlite3.connect(world.db) as conn:
        conn.execute("DELETE FROM learning_derivations")
    assert world.store.children_of("mistake_pool", str(lesson)) == []

    done = _revoke(world, lesson)

    assert f"semantic_memory:{twin} (consolidated twin)" in done["withdrawn"]
    assert not _twin_admitted(world, twin)


def test_another_principals_identical_twin_is_untouched(world) -> None:
    alices, bobs = _lesson(world, principal=ALICE), _lesson(world, principal=BOB)
    twin_a = world.authority.consolidate_lesson(alices)
    twin_b = world.authority.consolidate_lesson(bobs)
    assert twin_a != twin_b

    _revoke(world, alices)

    assert not _twin_admitted(world, twin_a, ALICE)
    assert _twin_admitted(world, twin_b, BOB)


def test_the_quarantine_withdraws_the_twin(world) -> None:
    lesson = _lesson(world)
    twin = world.authority.consolidate_lesson(lesson)
    quarantined: list[int] = []
    for _ in range(10):
        quarantined += world.authority.record_lesson_outcome(
            [lesson], success=False, principal=ALICE, baseline=lambda _t: 0.8
        )
    assert quarantined == [lesson]
    assert _newest(world, "semantic_memory", twin) == "withdrawn"
    assert not _twin_admitted(world, twin)


def test_consolidation_never_indexes_a_withdrawn_lesson(world) -> None:
    lesson = _lesson(world)
    _revoke(world, lesson)
    assert world.authority.lesson_admitted(lesson) is False

    assert world.authority.consolidate_lesson(lesson) is None
    world.authority.consolidate()
    with sqlite3.connect(world.db) as conn:
        twins = conn.execute(
            "SELECT COUNT(*) FROM semantic_memory WHERE memory_type = 'lesson'"
        ).fetchone()[0]
    assert twins == 0


def test_an_admitted_lesson_is_still_consolidated(world) -> None:
    """The control: the rule refuses what recall refuses, nothing more."""
    lesson = _lesson(world)
    assert world.authority.lesson_admitted(lesson) is True
    assert world.authority.consolidate_lesson(lesson) is not None


def test_an_ungated_consolidator_is_not_gated(tmp_path) -> None:
    """A legacy store with no authority has no recall gate to follow."""
    from aios.memory.consolidation import MemoryConsolidator
    from aios.memory.db import init_memory_db
    from aios.memory.facts import SemanticFacts
    from aios.memory.mistake import MistakeMemory
    from aios.memory.semantic import SemanticMemory

    db = tmp_path / "legacy.sqlite"
    init_memory_db(db)
    mistakes = MistakeMemory(db_path=db)
    mid = mistakes.record("t", "e", "r", "f", "lesson text", -0.1, principal_id=ALICE)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE mistake_pool SET verification_status = 'verified' WHERE id = ?",
            (mid,),
        )
    consolidator = MemoryConsolidator(
        semantic=SemanticMemory(db),
        mistakes=mistakes,
        facts=SemanticFacts(db_path=db),
        db_path=db,
    )
    assert consolidator.consolidate_lesson(mid) is not None


def test_an_authority_with_ungated_lessons_still_consolidates(
    world, monkeypatch
) -> None:
    """Recall over ungated lessons admits everything, so consolidation does too:
    the rule follows recall's verdict, it does not invent a stricter one."""
    lesson = _lesson(world)
    monkeypatch.setattr(world.lessons, "gate", None)
    assert world.authority.lesson_admitted(lesson) is True
    assert world.authority.consolidate_lesson(lesson) is not None
