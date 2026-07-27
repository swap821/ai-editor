"""Organ 38: the clerk provenance chain must actually be a chain.

Four defects this pins, each of which the code had and none of which the
existing tests caught:

  * the link never matched -- the store digested with
    `json.dumps(..., sort_keys=True, separators=(",",":"))` while the caller
    computed `previous_record_digest` with `model_dump_json()`, so every link
    was wrong from the first record;
  * nothing verified the chain, only each row's own digest, so a deleted or
    reordered record was undetectable;
  * a repeated job raised an uncaught IntegrityError instead of being
    idempotent, turning a retry into a crash;
  * the caller chose its own predecessor, so it could fork the chain.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aios.domain.local_workforce.contracts import LocalClerkProvenanceRecord
from aios.infrastructure.local_workforce.sqlite_store import (
    LocalWorkforceProvenanceStore,
    ProvenanceChainBrokenError,
    RecordTamperedError,
)


def _store(tmp_path: Path) -> LocalWorkforceProvenanceStore:
    return LocalWorkforceProvenanceStore(tmp_path / "provenance.db")


def _record(job_id: str, **overrides) -> LocalClerkProvenanceRecord:
    fields = dict(
        job_id=job_id,
        job_contract_digest="a" * 64,
        dispatcher_decision="local_clerk",
    )
    fields.update(overrides)
    return LocalClerkProvenanceRecord(**fields)


def test_the_chain_actually_links_up(tmp_path: Path) -> None:
    store = _store(tmp_path)

    first = store.save_provenance_record(_record("job-1"))
    second = store.save_provenance_record(_record("job-2"))

    assert first.previous_record_digest is None, "the head has no predecessor"
    assert second.previous_record_digest is not None
    assert store.verify_provenance_chain() == 2


def test_a_caller_cannot_choose_its_own_predecessor(tmp_path: Path) -> None:
    """A caller-supplied link is ignored, so the chain cannot be forked."""
    store = _store(tmp_path)
    store.save_provenance_record(_record("job-1"))

    forked = store.save_provenance_record(
        _record("job-2", previous_record_digest="f" * 64)
    )

    assert forked.previous_record_digest != "f" * 64
    assert store.verify_provenance_chain() == 2


def test_a_repeated_job_is_idempotent_not_a_crash(tmp_path: Path) -> None:
    store = _store(tmp_path)
    original = store.save_provenance_record(_record("job-1"))

    repeated = store.save_provenance_record(_record("job-1"))

    assert repeated == original
    assert store.verify_provenance_chain() == 1, "a retry must not append"


def test_a_deleted_record_breaks_the_chain_detectably(tmp_path: Path) -> None:
    """Per-row digests alone cannot catch this: every surviving row still
    matches its own content. Only the link check does."""
    store = _store(tmp_path)
    for job_id in ("job-1", "job-2", "job-3"):
        store.save_provenance_record(_record(job_id))
    assert store.verify_provenance_chain() == 3

    conn = sqlite3.connect(str(tmp_path / "provenance.db"))
    conn.execute("DELETE FROM local_clerk_provenance_chain WHERE job_id = 'job-2'")
    conn.commit()
    conn.close()

    with pytest.raises(ProvenanceChainBrokenError, match="deleted, reordered"):
        store.verify_provenance_chain()


def test_a_tampered_record_is_detected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save_provenance_record(_record("job-1"))

    conn = sqlite3.connect(str(tmp_path / "provenance.db"))
    conn.execute(
        "UPDATE local_clerk_provenance_chain SET dispatcher_decision = 'deterministic' "
        "WHERE job_id = 'job-1'"
    )
    conn.commit()
    conn.close()

    with pytest.raises(RecordTamperedError):
        store.verify_provenance_chain()


def test_an_empty_chain_verifies(tmp_path: Path) -> None:
    assert _store(tmp_path).verify_provenance_chain() == 0
