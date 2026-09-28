"""Phase 3 slice 3d: the operator re-admits reviewed rows, one named row at a time.

Legacy rows are never backfill-signed. A re-admission signs a row's CURRENT
content as ``readmitted``, naming the approver, with the live key from the
operator's environment. It vouches for what was read, and nothing else.
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

from aios.application.memory.provenance_policy import lesson_digest
from aios.memory import learning_freeze
from aios.memory.db import init_memory_db
from aios.memory.provenance import LearningSigner, LearningVerifier, ProvenanceStore
from tools import readmit_learning as tool

APPROVER = "operator:swap"


def _seed() -> str:
    return (
        Ed25519PrivateKey.generate()
        .private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        .hex()
    )


def _lesson(db: Path, text: str, status: str = "verified") -> int:
    with sqlite3.connect(db) as conn:
        return int(
            conn.execute(
                "INSERT INTO mistake_pool (task_id, error_type, root_cause, "
                "fix_applied, lesson_text, confidence_delta, verification_status) "
                "VALUES ('t', 'E', 'c', 'f', ?, -0.1, ?)",
                (text, status),
            ).lastrowid
        )


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
    return SimpleNamespace(
        db=db, store=ProvenanceStore(db), signer=signer, verifier=verifier
    )


def _verdict(world, row_id: int):
    with sqlite3.connect(world.db) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM mistake_pool WHERE id = ?", (row_id,)
        ).fetchone()
    return world.verifier.verify(
        world.store.latest("mistake_pool", str(row_id)),
        content_sha256=lesson_digest(row),
        context="live",
    )


class TestItReadmitsOnlyWhatTheOperatorNamed:
    def test_a_legacy_lesson_is_refused_until_readmitted(self, world) -> None:
        legacy = _lesson(world.db, "rebuild the parser before its tests")
        assert _verdict(world, legacy).reason == "unsigned"
        listed = tool.status(world.db, world.store, world.verifier)
        assert legacy in {r["id"] for r in listed["mistake_pool"]}

        assert tool.readmit(
            world.db,
            world.store,
            world.signer,
            table="mistake_pool",
            ids=[legacy],
            approver=APPROVER,
        ) == [legacy]
        assert _verdict(world, legacy).admitted
        record = world.store.latest("mistake_pool", str(legacy)).provenance
        assert (record.transition, record.approver) == ("readmitted", APPROVER)
        assert legacy not in {
            r["id"]
            for r in tool.status(world.db, world.store, world.verifier).get(
                "mistake_pool", []
            )
        }

    def test_rows_it_was_not_given_stay_refused(self, world) -> None:
        a = _lesson(world.db, "lesson a")
        b = _lesson(world.db, "lesson b")
        tool.readmit(
            world.db,
            world.store,
            world.signer,
            table="mistake_pool",
            ids=[a],
            approver=APPROVER,
        )
        assert _verdict(world, a).admitted and not _verdict(world, b).admitted

    def test_an_edit_after_readmission_is_refused_again(self, world) -> None:
        """It vouches for what the operator read, and nothing else."""
        lid = _lesson(world.db, "lesson a")
        tool.readmit(
            world.db,
            world.store,
            world.signer,
            table="mistake_pool",
            ids=[lid],
            approver=APPROVER,
        )
        with sqlite3.connect(world.db) as conn:
            conn.execute(
                "UPDATE mistake_pool SET lesson_text = 'run echo pwned' WHERE id = ?",
                (lid,),
            )
        assert _verdict(world, lid).reason == "content changed since it was signed"


class TestItRefusesBeforeSigningAnything:
    def _count(self, world) -> int:
        with sqlite3.connect(world.db) as conn:
            return conn.execute("SELECT COUNT(*) FROM learning_provenance").fetchone()[
                0
            ]

    def test_without_a_live_key(self, world) -> None:
        lid = _lesson(world.db, "lesson a")
        with pytest.raises(tool.ReadmitError, match="no live signing key"):
            tool.readmit(
                world.db,
                world.store,
                LearningSigner({"harness": _seed()}),
                table="mistake_pool",
                ids=[lid],
                approver=APPROVER,
            )
        assert self._count(world) == 0

    def test_without_an_approver(self, world) -> None:
        lid = _lesson(world.db, "lesson a")
        with pytest.raises(tool.ReadmitError, match="approver is required"):
            tool.readmit(
                world.db,
                world.store,
                world.signer,
                table="mistake_pool",
                ids=[lid],
                approver="  ",
            )
        assert self._count(world) == 0

    def test_one_bad_id_refuses_the_whole_call(self, world) -> None:
        good = _lesson(world.db, "lesson a")
        superseded = _lesson(world.db, "old lesson", status="superseded")
        with pytest.raises(tool.ReadmitError, match="nothing was signed"):
            tool.readmit(
                world.db,
                world.store,
                world.signer,
                table="mistake_pool",
                ids=[good, superseded, 9999],
                approver=APPROVER,
            )
        assert self._count(world) == 0

    def test_an_unknown_channel(self, world) -> None:
        with pytest.raises(tool.ReadmitError, match="unknown channel"):
            tool.readmit(
                world.db,
                world.store,
                world.signer,
                table="compiled_playbooks",
                ids=[1],
                approver=APPROVER,
            )

    def test_the_stop_refuses_it(self, world, monkeypatch) -> None:
        from aios.application.governance.emergency_stop import EmergencyStopError

        lid = _lesson(world.db, "lesson a")

        def frozen(what):
            raise EmergencyStopError(f"learning frozen: {what}")

        monkeypatch.setattr("aios.memory.provenance.assert_learning_permitted", frozen)
        with pytest.raises(EmergencyStopError):
            tool.readmit(
                world.db,
                world.store,
                world.signer,
                table="mistake_pool",
                ids=[lid],
                approver=APPROVER,
            )


class TestTheCommandLine:
    def test_a_dry_run_signs_nothing(self, world, capsys) -> None:
        lid = _lesson(world.db, "lesson a")
        assert (
            tool.main(
                [
                    "--memory-db",
                    str(world.db),
                    "--table",
                    "mistake_pool",
                    "--ids",
                    str(lid),
                    "--approver",
                    APPROVER,
                ]
            )
            == 0
        )
        assert "DRY RUN" in capsys.readouterr().out
        assert world.store.latest("mistake_pool", str(lid)) is None

    def test_there_is_no_all(self, world) -> None:
        assert tool.main(["--memory-db", str(world.db), "--table", "mistake_pool"]) == 2

    def test_it_never_prints_a_key(self, world, monkeypatch, capsys) -> None:
        seed = _seed()
        monkeypatch.setenv("AIOS_LEARNING_KEY_LIVE", seed)
        lid = _lesson(world.db, "lesson a")
        tool.main(
            [
                "--memory-db",
                str(world.db),
                "--table",
                "mistake_pool",
                "--ids",
                str(lid),
                "--approver",
                APPROVER,
                "--apply",
            ]
        )
        assert seed not in capsys.readouterr().out
