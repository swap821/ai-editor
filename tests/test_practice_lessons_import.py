"""Practice lessons reach live memory only by import, then by the operator's
re-admission; re-admission can sign with a key that lives only in the store."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aios.memory.db import init_memory_db
from aios.memory.mistake import MistakeMemory
from tools import import_practice_lessons as imp


def _store(path: Path) -> MistakeMemory:
    init_memory_db(path)
    return MistakeMemory(db_path=path)


def _lesson(store: MistakeMemory, text: str, *, verified: bool = True) -> int:
    lesson = store.record(
        "practice-run:aios/x.py::f", "AssertionError", "r", "f", text, -0.1
    )
    if verified:
        store.promote(lesson)
    return lesson


@pytest.fixture
def stores(tmp_path):
    practice = _store(tmp_path / "practice.db")
    live = _store(tmp_path / "live.db")
    return practice, live


def _rows(db: Path) -> list[tuple]:
    with sqlite3.connect(db) as conn:
        return conn.execute(
            "SELECT lesson_text, verification_status, principal_id FROM mistake_pool"
        ).fetchall()


def test_import_copies_only_the_named_verified_lessons(stores) -> None:
    practice, live = stores
    a = _lesson(practice, "`recalled_channels` splits on ':'")
    _lesson(practice, "`operator_text` returns the tag body")
    done = imp.import_lessons(practice.db_path, live.db_path, [a])
    assert list(done) == [a]
    assert _rows(live.db_path) == [
        ("`recalled_channels` splits on ':'", "verified", None)
    ]


def test_an_imported_lesson_is_unsigned_so_recall_refuses_it(stores) -> None:
    from aios.application.memory.provenance_policy import RecallGate, lesson_digest
    from aios.memory.provenance import LearningVerifier, ReadOnlyProvenanceStore

    practice, live = stores
    done = imp.import_lessons(
        practice.db_path, live.db_path, [_lesson(practice, "a fact")]
    )
    (new_id,) = done.values()
    gate = RecallGate(
        ReadOnlyProvenanceStore(live.db_path),
        LearningVerifier.from_pinned_file(),
        context="live",
    )
    row = live.get(new_id)
    assert not gate.admits(
        "mistake_pool", new_id, lesson_digest(row), principal="operator:x"
    )
    assert gate.refused, "refused, with a reason"


@pytest.mark.parametrize(
    "case", ["pending", "missing", "duplicate", "same_store", "no_ids"]
)
def test_a_refused_import_writes_nothing(stores, case) -> None:
    practice, live = stores
    verified = _lesson(practice, "a fact")
    pending = _lesson(practice, "a guess", verified=False)
    ids, destination = [verified], live.db_path
    if case == "pending":
        ids = [verified, pending]
    elif case == "missing":
        ids = [verified, 999]
    elif case == "duplicate":
        _lesson(live, "A  FACT")  # same text after normalisation
    elif case == "same_store":
        destination = practice.db_path
    elif case == "no_ids":
        ids = []
    before = _rows(live.db_path)
    with pytest.raises(imp.ImportError_):
        imp.import_lessons(practice.db_path, destination, ids)
    assert _rows(live.db_path) == before


def test_the_learning_freeze_refuses_an_import(stores, monkeypatch) -> None:
    practice, live = stores
    lesson = _lesson(practice, "a fact")

    def frozen(boundary: str) -> None:
        raise RuntimeError(f"learning frozen at {boundary}")

    monkeypatch.setattr(imp, "assert_learning_permitted", frozen)
    with pytest.raises(RuntimeError, match="lessons.import"):
        imp.import_lessons(practice.db_path, live.db_path, [lesson])
    assert _rows(live.db_path) == []


def test_the_dry_run_and_listing_write_nothing(stores, capsys) -> None:
    practice, live = stores
    lesson = _lesson(practice, "a fact")
    assert imp.main(["--from", str(practice.db_path), "--to", str(live.db_path)]) == 0
    assert '"lesson_text": "a fact"' in capsys.readouterr().out
    args = [
        "--from",
        str(practice.db_path),
        "--to",
        str(live.db_path),
        "--ids",
        str(lesson),
    ]
    assert imp.main(args) == 0
    assert _rows(live.db_path) == []


# --------------------------------------------------------------------------- #
# Re-admission signs with a key that lives only in the OS credential store
# --------------------------------------------------------------------------- #


def _seed() -> str:
    from aios.operations.keystore import GENERATORS

    return GENERATORS["AIOS_LEARNING_KEY_LIVE"]()


def test_the_signer_reads_the_store_when_the_environment_has_no_key() -> None:
    from aios.operations.keystore import MemoryKeystore
    from tools.readmit_learning import live_signer

    store = MemoryKeystore({"AIOS_LEARNING_KEY_LIVE": _seed()})
    assert "live" in live_signer({}, keystore=lambda: store).kinds
    assert "live" not in live_signer({}, keystore=lambda: MemoryKeystore()).kinds


def test_the_environment_key_wins_and_no_store_is_no_key() -> None:
    from aios.operations.keystore import KeystoreUnavailable, MemoryKeystore
    from aios.memory.provenance import LearningSigner
    from tools.readmit_learning import live_signer

    def unavailable():
        raise KeystoreUnavailable("not on this platform")

    env_seed, stored_seed = _seed(), _seed()
    store = MemoryKeystore({"AIOS_LEARNING_KEY_LIVE": stored_seed})
    signer = live_signer({"AIOS_LEARNING_KEY_LIVE": env_seed}, keystore=lambda: store)
    expected = LearningSigner({"live": env_seed}).public_keys()["live"]
    assert signer.public_keys()["live"] == expected, "the environment's key signs"
    assert "live" not in live_signer({}, keystore=unavailable).kinds
