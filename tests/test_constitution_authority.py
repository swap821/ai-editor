"""Tests for ConstitutionAuthority (Organ 25)."""

import pytest
import threading
from pathlib import Path

from aios.application.governance.constitution_authority import ConstitutionAuthority
from aios.infrastructure.governance.constitution_snapshot_store import (
    ConstitutionSnapshotStore,
)
from aios.policy.kernel import PolicyKernel


def test_constitution_authority_initialization_and_durability(tmp_path: Path):
    db_path = tmp_path / "constitution_test.db"
    store = ConstitutionSnapshotStore(db_path)
    authority = ConstitutionAuthority(store)

    snapshot1 = authority.get_active_snapshot(ratified_by_operator_id="operator_1")
    assert snapshot1.version == 1
    assert snapshot1.constitution_id == "constitution:operator_1"
    assert snapshot1.snapshot_digest is not None

    # Verify durability across new store instance
    store2 = ConstitutionSnapshotStore(db_path)
    authority2 = ConstitutionAuthority(store2)
    snapshot2 = authority2.get_active_snapshot(ratified_by_operator_id="operator_1")

    assert snapshot2.snapshot_digest == snapshot1.snapshot_digest
    assert snapshot2.version == snapshot1.version



def test_constitution_authority_concurrent_access(tmp_path: Path):
    db_path = tmp_path / "constitution_concurrent.db"
    store = ConstitutionSnapshotStore(db_path)
    authority = ConstitutionAuthority(store)

    results = []

    def _worker():
        snap = authority.get_active_snapshot(ratified_by_operator_id="test_worker")
        results.append(snap.snapshot_digest)

    threads = [threading.Thread(target=_worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 5
    assert len(set(results)) == 1  # All threads received the identical active snapshot digest


def test_policy_kernel_consumes_constitution_authority(tmp_path: Path):
    db_path = tmp_path / "kernel_constitution.db"
    store = ConstitutionSnapshotStore(db_path)
    authority = ConstitutionAuthority(store)

    kernel = PolicyKernel(constitution_authority=authority)
    snap = kernel.constitution_snapshot()

    assert snap is not None
    assert hasattr(snap, "snapshot_digest")
    assert snap.snapshot_digest == authority.get_active_snapshot().snapshot_digest
