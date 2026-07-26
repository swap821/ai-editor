"""Tests for ConstitutionAuthority (Organ 25).

The point of this organ is that there is exactly ONE answer to "what is the
current constitution?". These tests pin the fail-closed contract that makes
that true -- in particular that enrollment is checked on every call, including
the calls that pass an explicit operator id, which are the only ones that
actually run in production.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

import pytest

from aios.application.governance.constitution_authority import (
    ConstitutionAuthority,
    ConstitutionDegraded,
    NoEnrolledSovereignError,
    OperatorIdentityChangedError,
)
from aios.domain.governance.constitution import build_constitution_snapshot
from aios.infrastructure.governance.constitution_snapshot_store import (
    UNCHECKED,
    ConstitutionSnapshotStore,
)
from aios.policy.kernel import PolicyKernel

OPERATOR = "operator_1"


class FakeIdentityStore:
    """The `operator()` slice of IdentityStore, per the OperatorLookup Protocol."""

    def __init__(self, operator_id: str | None = OPERATOR) -> None:
        self.operator_id = operator_id
        self.raises: Exception | None = None

    def operator(self) -> dict[str, Any] | None:
        if self.raises is not None:
            raise self.raises
        if self.operator_id is None:
            return None
        return {"operator_id": self.operator_id, "display_name": "Sovereign"}


def _authority(
    db_path: Path, identity: FakeIdentityStore | None = None
) -> ConstitutionAuthority:
    return ConstitutionAuthority(
        ConstitutionSnapshotStore(db_path),
        identity_store=identity or FakeIdentityStore(),
    )


# --------------------------------------------------------------------------- #
# Durability
# --------------------------------------------------------------------------- #


def test_baseline_is_minted_once_and_survives_a_new_process(tmp_path: Path) -> None:
    db_path = tmp_path / "constitution_test.db"
    authority = _authority(db_path)

    first = authority.get_active_snapshot()
    assert first.version == 1
    assert first.constitution_id == f"constitution:{OPERATOR}"

    # A brand-new store + authority pair stands in for a process restart.
    second = _authority(db_path).get_active_snapshot()
    assert second.snapshot_digest == first.snapshot_digest
    assert second.version == first.version


def test_an_activated_amendment_is_what_later_reads_return(tmp_path: Path) -> None:
    """The whole point: the durable chain, not a rebuild from live config."""
    db_path = tmp_path / "constitution_chain.db"
    authority = _authority(db_path)
    v1 = authority.get_active_snapshot()

    v2 = build_constitution_snapshot(
        ratified_by_operator_id=OPERATOR, previous_snapshot=v1
    )
    authority.activate_snapshot(v2, expected_previous_digest=v1.snapshot_digest)

    assert authority.get_active_snapshot().snapshot_digest == v2.snapshot_digest
    # And across a restart.
    assert _authority(db_path).get_active_snapshot().snapshot_digest == (
        v2.snapshot_digest
    )


def test_concurrent_readers_all_see_one_identical_snapshot(tmp_path: Path) -> None:
    authority = _authority(tmp_path / "constitution_concurrent.db")
    results: list[str] = []
    lock = threading.Lock()

    def _worker() -> None:
        snap = authority.get_active_snapshot()
        with lock:
            results.append(snap.snapshot_digest)

    threads = [threading.Thread(target=_worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 5
    assert len(set(results)) == 1


# --------------------------------------------------------------------------- #
# Fail-closed contract
# --------------------------------------------------------------------------- #


def test_no_enrolled_sovereign_fails_closed(tmp_path: Path) -> None:
    authority = _authority(
        tmp_path / "constitution.db", FakeIdentityStore(operator_id=None)
    )
    with pytest.raises(NoEnrolledSovereignError):
        authority.get_active_snapshot()


def test_no_enrolled_sovereign_fails_closed_for_explicit_id_callers_too(
    tmp_path: Path,
) -> None:
    """The regression this organ exists to prevent.

    `IdentityService` and `CapabilityAuthority.consume` both pass an explicit
    operator id. If the enrollment check only guarded the argument-free call,
    it would guard nothing that actually runs in production.
    """
    authority = _authority(
        tmp_path / "constitution.db", FakeIdentityStore(operator_id=None)
    )
    with pytest.raises(NoEnrolledSovereignError):
        authority.get_active_snapshot(ratified_by_operator_id=OPERATOR)


def test_an_unknown_operator_id_cannot_mint_a_shadow_chain(tmp_path: Path) -> None:
    """Previously, any novel id silently auto-bootstrapped its own v1 and
    returned it as authoritative -- a second, never-amended constitution that
    no amendment would ever reach."""
    db_path = tmp_path / "constitution.db"
    authority = _authority(db_path)
    authority.get_active_snapshot()  # real chain exists

    with pytest.raises(OperatorIdentityChangedError):
        authority.get_active_snapshot(ratified_by_operator_id="someone-else")

    # Nothing was written for the impostor id.
    store = ConstitutionSnapshotStore(db_path)
    assert store.get_current("constitution:someone-else") is None


def test_a_capability_from_a_replaced_sovereign_is_refused(tmp_path: Path) -> None:
    """A capability minted for operator A, consumed after the sovereign was
    re-enrolled as B, must not resolve A's old chain."""
    db_path = tmp_path / "constitution.db"
    identity = FakeIdentityStore(operator_id="operator_a")
    authority = _authority(db_path, identity)
    authority.get_active_snapshot()

    identity.operator_id = "operator_b"  # re-enrollment
    with pytest.raises(OperatorIdentityChangedError):
        authority.get_active_snapshot(ratified_by_operator_id="operator_a")


def test_identity_store_failure_is_degraded_not_permissive(tmp_path: Path) -> None:
    identity = FakeIdentityStore()
    identity.raises = sqlite3.OperationalError("unable to open database file")
    authority = _authority(tmp_path / "constitution.db", identity)

    with pytest.raises(ConstitutionDegraded):
        authority.get_active_snapshot()


def test_a_tampered_snapshot_row_fails_closed(tmp_path: Path) -> None:
    db_path = tmp_path / "constitution.db"
    authority = _authority(db_path)
    snapshot = authority.get_active_snapshot()

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE constitution_snapshots SET snapshot_json = "
        "replace(snapshot_json, '\"version\": 1', '\"version\": 99') "
        "WHERE snapshot_digest = ?",
        (snapshot.snapshot_digest,),
    )
    conn.commit()
    conn.close()

    with pytest.raises(ConstitutionDegraded):
        _authority(db_path).get_active_snapshot()


def test_an_empty_operator_id_row_is_degraded(tmp_path: Path) -> None:
    authority = _authority(tmp_path / "constitution.db", FakeIdentityStore(""))
    with pytest.raises(ConstitutionDegraded):
        authority.get_active_snapshot()


# --------------------------------------------------------------------------- #
# PolicyKernel consumption
# --------------------------------------------------------------------------- #


def test_policy_kernel_consumes_constitution_authority(tmp_path: Path) -> None:
    authority = _authority(tmp_path / "kernel_constitution.db")
    kernel = PolicyKernel(constitution_authority=authority)

    snap = kernel.constitution_snapshot()

    assert snap.snapshot_digest == authority.get_active_snapshot().snapshot_digest
    # It must be the enrolled sovereign, never the old hardcoded "operator".
    assert snap.ratified_by_operator_id == OPERATOR


def test_policy_kernel_without_an_authority_fails_closed(tmp_path: Path) -> None:
    """Previously this fabricated a snapshot ratified by a hardcoded
    "operator" string that matched no real authenticated identity."""
    kernel = PolicyKernel()
    with pytest.raises(RuntimeError):
        kernel.constitution_snapshot()


def test_kernel_reflects_an_activation_without_being_rebuilt(tmp_path: Path) -> None:
    db_path = tmp_path / "kernel_chain.db"
    authority = _authority(db_path)
    kernel = PolicyKernel(constitution_authority=authority)
    v1 = kernel.constitution_snapshot()

    v2 = build_constitution_snapshot(
        ratified_by_operator_id=OPERATOR, previous_snapshot=v1
    )
    authority.activate_snapshot(v2, expected_previous_digest=v1.snapshot_digest)

    assert kernel.constitution_snapshot().snapshot_digest == v2.snapshot_digest


def test_fixture_seeded_chain_is_read_not_rebuilt(tmp_path: Path) -> None:
    """A chain seeded directly into the store (bypassing the authority) is
    still what the authority serves -- proving it reads durable state rather
    than recomputing from live config."""
    db_path = tmp_path / "seeded.db"
    store = ConstitutionSnapshotStore(db_path)
    v1 = build_constitution_snapshot(ratified_by_operator_id=OPERATOR)
    v2 = build_constitution_snapshot(
        ratified_by_operator_id=OPERATOR, previous_snapshot=v1
    )
    store.save(v1, expected_previous_digest=UNCHECKED)
    store.save(v2, expected_previous_digest=UNCHECKED)

    authority = _authority(db_path)
    assert authority.get_active_snapshot().version == 2
