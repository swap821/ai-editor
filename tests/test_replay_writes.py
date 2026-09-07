"""Stage 2 slice 1: the blob store and the exact-write-decision record.

The point of these tests is not that the happy path works. It is that the
narrow rule the operator chose -- *same bytes, same path* -- cannot be
satisfied by the much wider grant that already exists in `earned_autonomy`,
and that content carrying secrets never reaches disk.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from aios import config
from aios.core.autonomy import AutonomyLedger
from aios.core.replay_writes import (
    content_digest,
    decision_signature,
    is_approved_write,
    load_content,
    record_approval,
    store_content,
)
from aios.memory.db import get_connection, init_memory_db

_CONTENT = "def add(a, b):\n    return a + b\n"
_DIGEST = hashlib.sha256(_CONTENT.encode("utf-8")).hexdigest()


@pytest.fixture()
def db_path(tmp_path) -> Path:
    p = tmp_path / "replay.db"
    init_memory_db(p)
    return p


# --------------------------------------------------------------------------- #
# The bar: the glob grant must not satisfy the narrow decision
# --------------------------------------------------------------------------- #


def test_an_earned_glob_does_not_authorise_an_exact_write(db_path, monkeypatch) -> None:
    """THE BAR for this slice.

    `earned_autonomy` collapses a write target to `<dir>/*<.ext>`, so earning
    `src/*.py` grants ANY content to ANY .py under src/. If stage 2 read that
    ledger, the narrow rule the operator chose would silently become the wide
    one -- and it would look the same in the database.

    Earn the glob, then ask about a DIFFERENT file with DIFFERENT bytes.
    """
    ledger = AutonomyLedger(db_path=db_path, min_successes=1)
    for _ in range(3):
        ledger.record_outcome("create_file", "src/util.py", success=True)
    assert ledger.is_earned("create_file", "src/util.py", enabled=True), (
        "precondition: the glob grant must actually be earned"
    )

    # Same shape, so the glob covers it. Different file, different bytes.
    assert ledger.is_earned("create_file", "src/other.py", enabled=True), (
        "precondition: the glob is as wide as claimed"
    )

    approved = is_approved_write(
        "src/other.py",
        content_digest("something else entirely"),
        db_path=db_path,
        enabled=True,
    )

    assert approved is False, (
        "an earned <dir>/*<.ext> glob authorised an exact write it never approved"
    )


def test_the_two_keys_are_not_interchangeable() -> None:
    """A structural guard on the reason the above holds.

    `AutonomyLedger.signature` normalises the target; `decision_signature` must
    not. If a refactor ever routed one through the other, the test above would
    still pass for the wrong reason.
    """
    a = decision_signature("src/util.py", _DIGEST, workspace="ws")
    b = decision_signature("src/other.py", _DIGEST, workspace="ws")

    assert a != b, "two different paths produced the same decision key"

    c = decision_signature("src/util.py", content_digest("other bytes"), workspace="ws")
    assert a != c, "two different contents produced the same decision key"

    d = decision_signature("src/util.py", _DIGEST, workspace="another-workspace")
    assert a != d, "a decision leaked across workspaces"


# --------------------------------------------------------------------------- #
# The blob store never keeps secrets
# --------------------------------------------------------------------------- #


def test_content_carrying_a_secret_is_not_stored(db_path) -> None:
    """Refused, not redacted, and the caller stays on stage 1.

    Storing the SCRUBBED text would produce a blob whose digest no longer
    matches what the human approved, so a later replay would write the wrong
    bytes or fail its own check. Not storing is the correct answer.
    """
    secret = 'AWS_SECRET_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"\nkey = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"\n'

    result = store_content(secret, db_path=db_path)

    assert result.stored is False
    assert "secret" in result.reason
    assert load_content(result.digest, db_path=db_path) is None, "a secret reached disk"


def test_a_refused_blob_leaves_no_decision_behind(db_path) -> None:
    """A decision pointing at content nobody kept is not actionable.

    If the row survived the refused store, a later replay would find an
    approval with no bytes and would have to guess.
    """
    secret = 'password = "hunter2-not-a-real-one"\nAWS_SECRET_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"\n'

    result = record_approval("src/conf.py", secret, db_path=db_path)

    assert result.stored is False
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT COUNT(*) c FROM approved_write_decisions"
        ).fetchone()
    assert rows["c"] == 0


def test_clean_content_round_trips(db_path) -> None:
    result = store_content(_CONTENT, db_path=db_path)

    assert result.stored is True
    assert result.digest == _DIGEST
    assert load_content(_DIGEST, db_path=db_path) == _CONTENT.encode("utf-8")


# --------------------------------------------------------------------------- #
# Fail-closed on every axis
# --------------------------------------------------------------------------- #


def test_an_approved_write_is_recognised_when_enabled(db_path) -> None:
    """The positive case, so the negatives below cannot pass vacuously."""
    record_approval("src/util.py", _CONTENT, db_path=db_path)

    assert is_approved_write("src/util.py", _DIGEST, db_path=db_path, enabled=True)


def test_the_flag_is_off_by_default(db_path) -> None:
    """A deployment that never opts in behaves exactly like stage 1."""
    record_approval("src/util.py", _CONTENT, db_path=db_path)

    assert config.REPLAY_APPROVED_WRITES_ENABLED is False
    assert is_approved_write("src/util.py", _DIGEST, db_path=db_path) is False


def test_it_is_a_different_flag_from_earned_autonomy() -> None:
    """Different claims, different blast radii, independently disablable.

    Sharing EARNED_AUTONOMY_ENABLED would mean an operator could not turn off
    the glob-scoped content-blind grant without also losing this, or worse,
    could not turn this off while leaving that on.
    """
    assert (
        config.REPLAY_APPROVED_WRITES_ENABLED is not config.EARNED_AUTONOMY_ENABLED
        or (config.REPLAY_APPROVED_WRITES_ENABLED is False)
    )
    assert hasattr(config, "REPLAY_APPROVED_WRITES_ENABLED")
    assert hasattr(config, "EARNED_AUTONOMY_ENABLED")


def test_different_bytes_at_the_same_path_are_not_approved(db_path) -> None:
    """Drift in content misses. This is the rule, stated as a test."""
    record_approval("src/util.py", _CONTENT, db_path=db_path)

    assert not is_approved_write(
        "src/util.py",
        content_digest("def add(a, b):\n    return a - b\n"),
        db_path=db_path,
        enabled=True,
    )


def test_the_same_bytes_at_a_different_path_are_not_approved(db_path) -> None:
    """Drift in path misses too."""
    record_approval("src/util.py", _CONTENT, db_path=db_path)

    assert not is_approved_write(
        "src/elsewhere.py", _DIGEST, db_path=db_path, enabled=True
    )


def test_an_engaged_emergency_stop_denies(db_path) -> None:
    """ "The human said stop" must outrank "the human said yes earlier".

    The latch exists to halt work that was previously authorised. A prior
    approval is exactly that, so it must not survive the stop.
    """
    record_approval("src/util.py", _CONTENT, db_path=db_path)

    class _Engaged:
        def assert_operational(self):
            raise RuntimeError("emergency stop engaged")

    assert not is_approved_write(
        "src/util.py",
        _DIGEST,
        db_path=db_path,
        enabled=True,
        emergency_stop=_Engaged(),
    )


def test_an_unreadable_latch_also_denies(db_path) -> None:
    """Fail-closed: an unreadable stop control is not evidence it is clear."""
    record_approval("src/util.py", _CONTENT, db_path=db_path)

    class _Unreadable:
        def assert_operational(self):
            raise OSError("database is locked")

    assert not is_approved_write(
        "src/util.py",
        _DIGEST,
        db_path=db_path,
        enabled=True,
        emergency_stop=_Unreadable(),
    )


def test_a_decision_does_not_cross_workspaces(db_path, monkeypatch) -> None:
    """Approving a write in one project must grant nothing in another.

    The lesson `AutonomyLedger.signature` learned on 2026-08-31, applied here
    from the start rather than after the fact.
    """
    import aios.core.replay_writes as rw

    monkeypatch.setattr(rw, "workspace_id", lambda: "project-a")
    record_approval("src/util.py", _CONTENT, db_path=db_path)
    assert is_approved_write("src/util.py", _DIGEST, db_path=db_path, enabled=True)

    monkeypatch.setattr(rw, "workspace_id", lambda: "project-b")
    assert not is_approved_write("src/util.py", _DIGEST, db_path=db_path, enabled=True)
