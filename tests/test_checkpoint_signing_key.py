"""Rollback checkpoints are signed with a real key, or not created at all.

Until 2026-10-19 a missing key fell back to a constant published in
checkpoint.py, so every manifest was signed with a key anyone could read. A
checkpoint failure is a promotion REFUSAL (PromotionAuthority), so refusing here
fails closed: no change is applied without a rollback point.
"""

from __future__ import annotations

import pytest

from aios.application.promotion.checkpoint import (
    CheckpointAuthority,
    CheckpointError,
)
from aios.operations import keystore as ks

REAL_KEY = "0123456789abcdef0123456789abcdef-checkpoint"


@pytest.fixture
def production(monkeypatch, tmp_path):
    """Production rules: no test escape, no key in the environment."""
    for name in (
        "AIOS_ENV",
        "AIOS_TEST_SIGNING_KEYS_ALLOWED",
        "AIOS_CHECKPOINT_AUTHORITY_KEY",
        "CHECKPOINT_AUTHORITY_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    project = tmp_path / "project"
    project.mkdir()
    return project, tmp_path / "rollback"


def _authority(project, rollback, key=None):
    return CheckpointAuthority(
        project_root=project, storage_root=rollback, authority_key=key
    )


def test_no_key_refuses_instead_of_signing_with_a_public_one(production) -> None:
    project, rollback = production
    with pytest.raises(CheckpointError, match="AIOS_CHECKPOINT_AUTHORITY_KEY"):
        _authority(project, rollback)


@pytest.mark.parametrize(
    "key", ["aios-checkpoint-key-default-32bytes!", "changeme", "short-key"]
)
def test_public_or_short_keys_are_refused(production, key) -> None:
    project, rollback = production
    with pytest.raises(CheckpointError):
        _authority(project, rollback, key)


def test_the_environment_key_signs(production, monkeypatch) -> None:
    project, rollback = production
    monkeypatch.setenv("AIOS_CHECKPOINT_AUTHORITY_KEY", REAL_KEY)
    assert _authority(project, rollback).authority_key == REAL_KEY


def test_a_manifest_signed_with_another_key_does_not_restore(production) -> None:
    project, rollback = production
    (project / "file.txt").write_text("original", encoding="utf-8")
    signer = _authority(project, rollback, REAL_KEY)
    manifest = signer.create_checkpoint(
        mission_id="m",
        action_id="a",
        worker_id="w",
        executor_job_id="j",
        contract_digest="c" * 64,
        workspace_digest="d" * 64,
        diff_digest="e" * 64,
        affected_paths=["file.txt"],
    )
    other = _authority(project, rollback, REAL_KEY[::-1])
    with pytest.raises(CheckpointError):
        other.restore_checkpoint(manifest.checkpoint_id)


def test_the_keystore_can_make_it() -> None:
    assert "AIOS_CHECKPOINT_AUTHORITY_KEY" in ks.REQUIRED
    store = ks.MemoryKeystore()
    ks.generate(store, "AIOS_CHECKPOINT_AUTHORITY_KEY")
    assert len(store.get("AIOS_CHECKPOINT_AUTHORITY_KEY")) >= 32
