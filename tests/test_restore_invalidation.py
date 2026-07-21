"""Slice 40: a restore must never silently resurrect stale authority.

`restore_backup` reinstates whatever the identity, capability and approval
databases looked like at snapshot time. Without invalidation, a restored old
session, an unconsumed capability, or a pending YELLOW approval from the
snapshot could all silently act as current the moment the restore completes.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from aios.core.approvals import ApprovalStore
from aios.domain.capabilities.contracts import Capability, CapabilityBinding
from aios.infrastructure.capabilities.sqlite_store import CapabilityStore
from aios.infrastructure.identity.sqlite_store import IdentityStore, credential_digest
from aios.operations.recovery import (
    RestoreInvalidationReport,
    create_backup,
    invalidate_stale_authority_after_restore,
    restore_backup,
)


def _seed_operator(identity_path: Path, *, operator_id: str = "op-1") -> int:
    store = IdentityStore(identity_path)
    store.create_operator(
        operator_id=operator_id,
        display_name="Operator",
        credential_digest_value=credential_digest("password"),
        recovery_digest_value=credential_digest("recovery"),
    )
    return store.bump_session_generation(operator_id)


def _seed_capability(capability_path: Path, *, capability_id: str = "cap-1") -> None:
    binding = CapabilityBinding(
        operator_id="op-1",
        device_id="device-1",
        authentication_event_id="event-1",
        session_id="session-1",
        action_type="command",
        route="/api/v1/actions/execute",
        http_method="POST",
        payload_digest="d" * 64,
        resource_digest="r" * 64,
        mission_id=None,
        contract_digest=None,
        policy_version="v1",
        scope="repo",
        verification_requirement="none",
    )
    capability = Capability(
        capability_id=capability_id,
        binding=binding,
        issued_at=time.time(),
        expires_at=time.time() + 3600,
        nonce="nonce-1",
    )
    CapabilityStore(capability_path).insert(capability, token_digest="t" * 64)


# --------------------------------------------------------------------------- #
# invalidate_stale_authority_after_restore -- direct unit coverage
# --------------------------------------------------------------------------- #


def test_invalidate_clears_pending_and_redeemed_approvals(tmp_path: Path) -> None:
    approval_path = tmp_path / "aios_approvals.db"
    store = ApprovalStore(db_path=approval_path)
    token = store.issue("command", {"cmd": "pytest"}, "session-1")

    report = invalidate_stale_authority_after_restore(data_dir=tmp_path)

    assert report.approvals_cleared is True
    with pytest.raises(Exception, match="unknown or already used"):
        store.consume(token, "session-1")


def test_invalidate_bumps_session_generation_past_the_restored_value(
    tmp_path: Path,
) -> None:
    identity_path = tmp_path / "aios_identity.db"
    generation_at_snapshot = _seed_operator(identity_path)

    report = invalidate_stale_authority_after_restore(data_dir=tmp_path)

    assert report.operator_id == "op-1"
    assert report.session_generation_bumped is True
    new_generation = IdentityStore(identity_path).current_session_generation("op-1")
    # A session cookie stamped with the snapshot's generation must no longer
    # match -- the exact invariant IdentityService.get_authenticated_principal
    # enforces via `stamped_generation != current_generation`.
    assert new_generation != generation_at_snapshot


def test_invalidate_revokes_unconsumed_capabilities(tmp_path: Path) -> None:
    capability_path = tmp_path / "aios_capabilities.db"
    _seed_capability(capability_path)

    report = invalidate_stale_authority_after_restore(data_dir=tmp_path)

    assert report.capabilities_revoked == 1
    store = CapabilityStore(capability_path)
    assert store.consume_if_available("cap-1", time.time()) is False


def test_invalidate_is_a_safe_noop_when_no_databases_exist(tmp_path: Path) -> None:
    """A fresh install / a backup predating these subsystems must not error."""
    report = invalidate_stale_authority_after_restore(data_dir=tmp_path)

    assert report == RestoreInvalidationReport(
        operator_id=None,
        session_generation_bumped=False,
        capabilities_revoked=0,
        approvals_cleared=False,
    )


# --------------------------------------------------------------------------- #
# restore_backup -- end-to-end: invalidation runs automatically, not opt-in
# --------------------------------------------------------------------------- #


def test_restore_backup_automatically_invalidates_stale_authority(
    tmp_path: Path,
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    identity_path = data / "aios_identity.db"
    approval_path = data / "aios_approvals.db"
    generation_at_snapshot = _seed_operator(identity_path)
    approval_store = ApprovalStore(db_path=approval_path)
    token = approval_store.issue("command", {"cmd": "pytest"}, "session-1")

    bundle = tmp_path / "backup.tar.gz"
    create_backup(data_dir=data, destination=bundle)

    # Simulate live drift after the snapshot was taken: a newer login bumps
    # the generation further, and the approval is still sitting there.
    IdentityStore(identity_path).bump_session_generation("op-1")

    restore_backup(
        bundle=bundle,
        data_dir=data,
        safety_backup=tmp_path / "safety.tar.gz",
    )

    restored_generation = IdentityStore(identity_path).current_session_generation(
        "op-1"
    )
    assert restored_generation != generation_at_snapshot
    with pytest.raises(Exception, match="unknown or already used"):
        ApprovalStore(db_path=approval_path).consume(token, "session-1")
