"""Organ 45: durable, content-addressed history for ConstitutionSnapshotV1."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from aios.domain.governance.constitution import build_constitution_snapshot
from aios.infrastructure.governance.constitution_snapshot_store import (
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
