"""Organ 45: durable, content-addressed history for ConstitutionSnapshotV1."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from aios.domain.governance.constitution import build_constitution_snapshot
from aios.infrastructure.governance.constitution_snapshot_store import (
    ConcurrentActivationError,
    ConstitutionSnapshotStore,
    RecordTamperedError,
)


def test_save_and_get_current_round_trips(tmp_path: Path) -> None:
    store = ConstitutionSnapshotStore(tmp_path / "constitution.db")
    snapshot = build_constitution_snapshot(ratified_by_operator_id="op-1")

    store.save(snapshot)

    current = store.get_current(snapshot.constitution_id)
    assert current == snapshot


def test_get_current_missing_constitution_returns_none(tmp_path: Path) -> None:
    store = ConstitutionSnapshotStore(tmp_path / "constitution.db")
    assert store.get_current("constitution:no-such-operator") is None


def test_activation_chain_advances_current_and_preserves_history(
    tmp_path: Path,
) -> None:
    store = ConstitutionSnapshotStore(tmp_path / "constitution.db")
    v1 = build_constitution_snapshot(ratified_by_operator_id="op-1")
    store.save(v1)

    v2 = build_constitution_snapshot(ratified_by_operator_id="op-1", previous_snapshot=v1)
    store.save(v2)

    assert store.get_current(v1.constitution_id) == v2
    history = store.get_history(v1.constitution_id)
    assert [s.version for s in history] == [1, 2]
    assert history[0] == v1
    assert history[1] == v2


def test_rollback_repoints_current_without_duplicating_history(
    tmp_path: Path,
) -> None:
    """Rollback re-saves the exact predecessor object -- the store must not
    create a second row for a digest it already has."""
    store = ConstitutionSnapshotStore(tmp_path / "constitution.db")
    v1 = build_constitution_snapshot(ratified_by_operator_id="op-1")
    store.save(v1)
    v2 = build_constitution_snapshot(ratified_by_operator_id="op-1", previous_snapshot=v1)
    store.save(v2)

    store.save(v1)  # rollback: re-point current back to v1

    assert store.get_current(v1.constitution_id) == v1
    history = store.get_history(v1.constitution_id)
    assert [s.version for s in history] == [1, 2]  # no duplicate v1 row


def test_get_by_digest(tmp_path: Path) -> None:
    store = ConstitutionSnapshotStore(tmp_path / "constitution.db")
    snapshot = build_constitution_snapshot(ratified_by_operator_id="op-1")
    store.save(snapshot)

    assert store.get_by_digest(snapshot.snapshot_digest) == snapshot
    assert store.get_by_digest("no-such-digest") is None


def test_tampered_row_is_detected_at_read_time(tmp_path: Path) -> None:
    db_path = tmp_path / "constitution.db"
    store = ConstitutionSnapshotStore(db_path)
    snapshot = build_constitution_snapshot(ratified_by_operator_id="op-1")
    store.save(snapshot)

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT snapshot_json FROM constitution_snapshots WHERE snapshot_digest = ?",
        (snapshot.snapshot_digest,),
    ).fetchone()
    payload = json.loads(row[0])
    payload["scope_roots"] = ["/something/nobody/approved"]
    conn.execute(
        "UPDATE constitution_snapshots SET snapshot_json = ? WHERE snapshot_digest = ?",
        (json.dumps(payload), snapshot.snapshot_digest),
    )
    conn.commit()
    conn.close()

    with pytest.raises(RecordTamperedError):
        store.get_current(snapshot.constitution_id)


# --------------------------------------------------------------------------- #
# Compare-and-swap activation (organ 25)
#
# Without this, two activations that both read the same "current" snapshot
# would both write, and the second silently clobbers the first: one of the two
# amendments vanishes with no error, leaving a chain that skips a version.
# --------------------------------------------------------------------------- #


def test_cas_bootstrap_rejects_a_second_first_activation(tmp_path: Path) -> None:
    """``expected_previous_digest=None`` asserts no pointer exists yet."""
    store = ConstitutionSnapshotStore(tmp_path / "constitution.db")
    v1 = build_constitution_snapshot(ratified_by_operator_id="op-1")
    store.save(v1, expected_previous_digest=None)

    rival = build_constitution_snapshot(ratified_by_operator_id="op-1")
    with pytest.raises(ConcurrentActivationError):
        store.save(rival, expected_previous_digest=None)

    assert store.get_current(v1.constitution_id) == v1


def test_cas_rejects_an_activation_whose_predecessor_moved(tmp_path: Path) -> None:
    store = ConstitutionSnapshotStore(tmp_path / "constitution.db")
    v1 = build_constitution_snapshot(ratified_by_operator_id="op-1")
    store.save(v1)
    v2 = build_constitution_snapshot(
        ratified_by_operator_id="op-1", previous_snapshot=v1
    )
    store.save(v2, expected_previous_digest=v1.snapshot_digest)

    # A writer that still believes v1 is current is working from a stale read.
    v2_rival = build_constitution_snapshot(
        ratified_by_operator_id="op-1", previous_snapshot=v1
    )
    with pytest.raises(ConcurrentActivationError):
        store.save(v2_rival, expected_previous_digest=v1.snapshot_digest)

    assert store.get_current(v1.constitution_id) == v2
    assert [s.version for s in store.get_history(v1.constitution_id)] == [1, 2]


def test_cas_failure_writes_nothing_at_all(tmp_path: Path) -> None:
    """A losing activation must not leave its snapshot row behind either --
    a half-applied activation would let a later reader resolve a version that
    was never actually made current."""
    store = ConstitutionSnapshotStore(tmp_path / "constitution.db")
    v1 = build_constitution_snapshot(ratified_by_operator_id="op-1")
    store.save(v1)

    orphan = build_constitution_snapshot(
        ratified_by_operator_id="op-1", previous_snapshot=v1
    )
    with pytest.raises(ConcurrentActivationError):
        store.save(orphan, expected_previous_digest="0" * 64)

    assert store.get_by_digest(orphan.snapshot_digest) is None
    assert [s.version for s in store.get_history(v1.constitution_id)] == [1]


def test_omitting_expected_previous_digest_stays_unconditional(
    tmp_path: Path,
) -> None:
    """Non-activation callers (and the rollback re-point) must be unaffected."""
    store = ConstitutionSnapshotStore(tmp_path / "constitution.db")
    v1 = build_constitution_snapshot(ratified_by_operator_id="op-1")
    store.save(v1)
    v2 = build_constitution_snapshot(
        ratified_by_operator_id="op-1", previous_snapshot=v1
    )
    store.save(v2)

    store.save(v1)  # rollback re-point, no CAS requested

    assert store.get_current(v1.constitution_id) == v1


def test_concurrent_activations_produce_one_ordered_chain(tmp_path: Path) -> None:
    """Two threads race to activate from the same predecessor. Exactly one
    wins; the loser is refused, never silently dropped."""
    import threading

    store = ConstitutionSnapshotStore(tmp_path / "constitution.db")
    v1 = build_constitution_snapshot(ratified_by_operator_id="op-1")
    store.save(v1)

    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def activate(_tag: str) -> None:
        # Both threads build the real successor. `build_constitution_snapshot`
        # is deterministic over (live config, previous snapshot, operator), so
        # these are byte-identical -- the point being proved is that the CAS
        # serialises the *pointer move*, not that the payloads differ. A forged
        # digest could not be used here: the store's own tamper check would
        # reject it at read time.
        successor = build_constitution_snapshot(
            ratified_by_operator_id="op-1", previous_snapshot=v1
        )
        barrier.wait(timeout=10)
        try:
            store.save(successor, expected_previous_digest=v1.snapshot_digest)
            result = "won"
        except ConcurrentActivationError:
            result = "lost"
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=activate, args=(t,)) for t in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(outcomes) == ["lost", "won"], outcomes
    # Exactly one successor became current, and history has no phantom row.
    current = store.get_current(v1.constitution_id)
    assert current is not None and current.snapshot_digest != v1.snapshot_digest
    assert len(store.get_history(v1.constitution_id)) == 2
