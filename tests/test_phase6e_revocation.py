"""Plan Phase 6e: revocation is enforced at retrieval and cascades (threat T6).

"Revoked but still authoritative" (2026): 0 of 5 memory systems enforced a
revocation at retrieval. Here the operator revokes a learned row with
``tools/revoke_learning.py`` and these hold:

* recall refuses it, and no MACHINE transition can build on the revocation --
  only the operator's re-admission signs it again;
* its content is tombstoned for its principal: learned again from another
  task, it is withdrawn at birth;
* it works while the emergency stop is engaged (a withdrawal);
* rows recorded as derived from it are withdrawn too;
* a self-model cached before it is rebuilt, never served stale.
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

ALICE, BOB = "principal:alice6e", "principal:bob6e"
TEXT = "when the parser build breaks, rerun the parser migration first"


def _seed() -> str:
    return (
        Ed25519PrivateKey.generate()
        .private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        .hex()
    )


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Lessons signing and gating like production, the operator's tools, and
    a latch of their own."""
    from aios.application.memory.adapters import MistakeMemoryAdapter
    from aios.application.memory.provenance_policy import ProvenanceWriter, RecallGate
    from aios.memory.db import init_memory_db
    from aios.memory.mistake import MistakeMemory
    from aios.memory.provenance import (
        LearningSigner,
        LearningVerifier,
        ProvenanceStore,
    )

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
    lessons = MistakeMemoryAdapter(
        MistakeMemory(db_path=db), provenance=writer, gate=gate
    )
    return SimpleNamespace(
        root=tmp_path, db=db, store=store, signer=signer, gate=gate, lessons=lessons
    )


def _lesson(world, *, task="task-a", principal=ALICE, text=TEXT) -> int:
    mistake_id = int(
        world.lessons.record(
            task,
            "migration_skipped",
            "skipped",
            "ran it",
            text,
            0.1,
            principal=principal,
        )
    )
    world.lessons.promote(mistake_id, principal=principal)
    return mistake_id


def _recalled(world, principal=ALICE) -> list[int]:
    return [
        int(r["mistake_id"])
        for r in world.lessons.relevant_verified(
            "parser migration", 10, principal=principal
        )
    ]


def _revoke(world, table, ids, **kw):
    from tools.revoke_learning import revoke

    return revoke(
        world.db,
        world.store,
        world.signer,
        table=table,
        ids=ids,
        approver=kw.pop("approver", "operator:test"),
        **kw,
    )


def _readmit(world, table, ids, principal=ALICE):
    from tools.readmit_learning import readmit

    return readmit(
        world.db,
        world.store,
        world.signer,
        table=table,
        ids=ids,
        approver="operator:test",
        principal=principal,
    )


# ------------------------------------------------- enforced at retrieval


class TestARevocationIsEnforcedAtRetrieval:
    def test_a_revoked_lesson_is_never_recalled(self, world) -> None:
        mistake_id = _lesson(world)
        assert _recalled(world) == [mistake_id]
        _revoke(world, "mistake_pool", [mistake_id], reason="wrong fix")
        assert _recalled(world) == []
        assert world.gate.refused.get("revoked")

    def test_positive_control_readmission_brings_it_back(self, world) -> None:
        mistake_id = _lesson(world)
        _revoke(world, "mistake_pool", [mistake_id])
        _readmit(world, "mistake_pool", [mistake_id])
        assert _recalled(world) == [mistake_id]

    def test_no_machine_transition_builds_on_a_revocation(self, world) -> None:
        """The same failure recurring onto the revoked lesson is a real event
        -- and still never signs it back into recall."""
        mistake_id = _lesson(world)
        _revoke(world, "mistake_pool", [mistake_id])
        again, recurred = world.lessons.record_or_increment(
            "task-a",
            "migration_skipped",
            "skipped",
            "ran it",
            TEXT,
            0.1,
            principal=ALICE,
        )
        assert recurred and int(again) == mistake_id
        assert _recalled(world) == []

    def test_a_revoked_memory_or_fact_is_refused_by_the_gate(self, world) -> None:
        from aios.application.memory.provenance_policy import (
            ProvenanceWriter,
            fact_digest,
            semantic_digest,
        )

        writer = ProvenanceWriter(
            world.store, world.signer, source_kind="live", verifier=world.gate.verifier
        )
        with sqlite3.connect(world.db) as conn:
            conn.execute(
                "INSERT INTO semantic_memory (id, text_content, memory_type, "
                "verification_status, principal_id) VALUES (41, 'a note', 'chat', "
                "'verified', ?)",
                (ALICE,),
            )
            conn.execute(
                "INSERT INTO semantic_facts (id, subject, predicate, object, "
                "approved_by, status, principal_id) VALUES (42, 'a', 'b', 'c', "
                "'operator:test', 'active', ?)",
                (ALICE,),
            )
        rows = {}
        with sqlite3.connect(world.db) as conn:
            conn.row_factory = sqlite3.Row
            rows["semantic_memory"] = conn.execute(
                "SELECT * FROM semantic_memory WHERE id = 41"
            ).fetchone()
            rows["semantic_facts"] = conn.execute(
                "SELECT * FROM semantic_facts WHERE id = 42"
            ).fetchone()
        digests = {
            "semantic_memory": semantic_digest(rows["semantic_memory"]),
            "semantic_facts": fact_digest(rows["semantic_facts"]),
        }
        for table, row_id in (("semantic_memory", 41), ("semantic_facts", 42)):
            writer.attest_new(table, row_id, digests[table], "created", principal=ALICE)
            assert world.gate.admits(table, row_id, digests[table], principal=ALICE)
            _revoke(world, table, [row_id])
            assert not world.gate.admits(table, row_id, digests[table], principal=ALICE)


# --------------------------------------------------------- the tombstone


class TestRevokedContentStaysRevoked:
    def test_the_same_lesson_learned_again_is_withdrawn_at_birth(self, world) -> None:
        first = _lesson(world)
        _revoke(world, "mistake_pool", [first])
        again = _lesson(world, task="task-b")
        assert again != first
        assert _recalled(world) == []
        assert world.store.latest("mistake_pool", str(again)) is None

    def test_a_tombstone_is_its_principals_own(self, world) -> None:
        _revoke(world, "mistake_pool", [_lesson(world)])
        theirs = _lesson(world, task="task-b", principal=BOB)
        assert _recalled(world, principal=BOB) == [theirs]

    def test_positive_control_different_content_is_learned(self, world) -> None:
        _revoke(world, "mistake_pool", [_lesson(world)])
        other = _lesson(
            world,
            task="task-b",
            text="rerun the parser migration after a schema change",
        )
        assert _recalled(world) == [other]

    def test_readmission_lifts_the_tombstone(self, world) -> None:
        first = _lesson(world)
        _revoke(world, "mistake_pool", [first])
        _readmit(world, "mistake_pool", [first])
        again = _lesson(world, task="task-b")
        assert set(_recalled(world)) == {first, again}

    def test_an_unreadable_tombstone_check_withdraws(self, world, monkeypatch) -> None:
        def unreadable(*_a, **_k):
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(world.store, "is_tombstoned", unreadable)
        mistake_id = _lesson(world)
        assert world.store.latest("mistake_pool", str(mistake_id)) is None
        assert _recalled(world) == []


# -------------------------------------------------------------- the stop


class TestRevocationUnderTheStop:
    def test_revocation_works_while_the_stop_is_engaged(self, world) -> None:
        mistake_id = _lesson(world)
        _engage(world)
        done = _revoke(world, "mistake_pool", [mistake_id])
        assert done["revoked"] == [f"mistake_pool:{mistake_id}"]
        assert _recalled(world) == []

    def test_positive_control_learning_itself_is_still_refused(self, world) -> None:
        from aios.application.governance.emergency_stop import EmergencyStopError

        _engage(world)
        with pytest.raises(EmergencyStopError):
            _lesson(world)


def _engage(world) -> None:
    from aios.application.governance.emergency_stop import (
        EmergencyStopController,
        EmergencyStopHooks,
    )
    from aios.domain.governance.contracts import EmergencyStopRequest

    def noop(*_a, **_k):
        return None

    EmergencyStopController(
        world.root / "emergency_stop.db",
        hooks=EmergencyStopHooks(
            revoke_capabilities=noop,
            cancel_queued_missions=noop,
            kill_active_workers=noop,
            disable_autonomy=noop,
            preserve_evidence=noop,
        ),
    ).engage(
        EmergencyStopRequest(
            operator_id="operator:test",
            authentication_event_id="event:engage",
            reason="revocation under the stop",
        )
    )
    learning_freeze._controllers.clear()


# ------------------------------------------------------------ the cascade


class TestARevocationCascades:
    def test_what_was_derived_from_it_is_withdrawn_all_the_way_down(
        self, world
    ) -> None:
        parent = _lesson(world)
        child = _lesson(
            world, task="task-b", text="the parser migration needs a warm cache"
        )
        grandchild = _lesson(
            world, task="task-c", text="warm the parser cache before migration"
        )
        world.store.append_derivation(
            child=("mistake_pool", str(child)),
            parent=("mistake_pool", str(parent)),
            relation="derived_from",
        )
        world.store.append_derivation(
            child=("mistake_pool", str(grandchild)),
            parent=("mistake_pool", str(child)),
            relation="derived_from",
        )
        assert set(_recalled(world)) == {parent, child, grandchild}
        done = _revoke(world, "mistake_pool", [parent])
        assert len(done["withdrawn"]) == 2
        assert _recalled(world) == []

    def test_positive_control_an_unrelated_lesson_is_untouched(self, world) -> None:
        parent = _lesson(world)
        other = _lesson(
            world, task="task-b", text="the parser migration needs a warm cache"
        )
        _revoke(world, "mistake_pool", [parent])
        assert _recalled(world) == [other]


# --------------------------------------------------------- the self-model


class _Authority:
    def __init__(self) -> None:
        self.calls = 0

    def self_model(self, *, principal):
        self.calls += 1
        return f"self-model #{self.calls} for {principal}"


def _handler(monkeypatch, mark):
    from aios.runtime import self_model_handler
    from aios.runtime.cortex_bus import BusEvent

    monkeypatch.setattr(self_model_handler, "last_withdrawal_id", lambda: mark[0])
    authority = _Authority()
    handler = self_model_handler.SelfModelHandler(memory_authority=authority)
    handler.remember("turn-1", ALICE)
    handler(BusEvent(1, "turn.completed", "turn-1", {"turnId": "turn-1"}))
    return handler, authority


class TestADerivedSelfModelIsNeverServedStale:
    def test_positive_control_unchanged_it_is_served_from_cache(
        self, monkeypatch
    ) -> None:
        mark = [7]
        handler, authority = _handler(monkeypatch, mark)
        assert handler.recall(ALICE) == f"self-model #1 for {ALICE}"
        assert authority.calls == 1

    def test_after_a_revocation_it_is_rebuilt(self, monkeypatch) -> None:
        mark = [7]
        handler, authority = _handler(monkeypatch, mark)
        mark[0] = 8  # a lesson was revoked (or quarantined) since
        assert handler.recall(ALICE) == f"self-model #2 for {ALICE}"
        assert handler.recall(ALICE) == f"self-model #2 for {ALICE}"
        assert authority.calls == 2

    def test_an_unreadable_journal_never_serves_the_cache(self, monkeypatch) -> None:
        mark = [7]
        handler, authority = _handler(monkeypatch, mark)
        mark[0] = None
        assert handler.recall(ALICE) == f"self-model #2 for {ALICE}"

    def test_without_an_authority_a_stale_one_is_withheld(self, monkeypatch) -> None:
        from aios.runtime import self_model_handler
        from aios.runtime.cortex_bus import BusEvent

        mark = [7]
        monkeypatch.setattr(self_model_handler, "last_withdrawal_id", lambda: mark[0])
        monkeypatch.setattr(
            self_model_handler, "synthesize_self_model", lambda *a, **k: object()
        )
        monkeypatch.setattr(self_model_handler, "render_self_model", lambda m: "legacy")
        handler = self_model_handler.SelfModelHandler(object(), object())
        handler.remember("turn-1", ALICE)
        handler(BusEvent(1, "turn.completed", "turn-1", {"turnId": "turn-1"}))
        assert handler.recall(ALICE) == "legacy"
        mark[0] = 8
        assert handler.recall(ALICE) is None

    def test_the_journal_mark_moves_on_every_kind_of_withdrawal(self, tmp_path) -> None:
        from aios.memory.db import init_memory_db
        from aios.memory.learning_journal import last_withdrawal_id, record

        db = tmp_path / "journal.sqlite"
        init_memory_db(db)
        assert last_withdrawal_id(db_path=db) == 0
        record("L4", "compiled", db_path=db)
        assert last_withdrawal_id(db_path=db) == 0
        marks = []
        for transition in ("revoked", "quarantined", "tombstoned", "withdrawn"):
            record("L2", transition, db_path=db)
            marks.append(last_withdrawal_id(db_path=db))
        assert marks == sorted(set(marks)) and marks[0] > 0
        assert last_withdrawal_id(db_path=tmp_path / "missing" / "no.sqlite") is None


# ---------------------------------------------------- the T6 lesson half


class TestASupersededLessonIsNeverRecalled:
    def test_superseded_is_out_of_every_lesson_channel(self, world) -> None:
        old = _lesson(world)
        new = _lesson(
            world, task="task-b", text="the parser migration needs a warm cache"
        )
        world.lessons.store.supersede(old, new, principal_id=ALICE)
        assert _recalled(world) == [new]
        assert old not in [
            int(r["id"])
            for r in world.lessons.store.recurring(limit=10, principal_id=ALICE)
        ]


# --------------------------------------------------------- the tool itself


class TestTheToolRefusesBeforeWriting:
    def test_refusals(self, world) -> None:
        from aios.memory.provenance import LearningSigner
        from tools.revoke_learning import RevokeError, revoke

        mistake_id = _lesson(world)
        for kwargs in (
            {"table": "nope", "ids": [mistake_id], "approver": "operator:test"},
            {"table": "mistake_pool", "ids": [mistake_id], "approver": "  "},
            {
                "table": "mistake_pool",
                "ids": [mistake_id, 99999],
                "approver": "operator:test",
            },
        ):
            with pytest.raises(RevokeError):
                revoke(world.db, world.store, world.signer, **kwargs)
        with pytest.raises(RevokeError, match="no live signing key"):
            revoke(
                world.db,
                world.store,
                LearningSigner({}),
                table="mistake_pool",
                ids=[mistake_id],
                approver="operator:test",
            )
        assert _recalled(world) == [mistake_id], "nothing was revoked"
