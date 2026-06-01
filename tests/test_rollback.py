"""Rollback engine tests — snapshot/restore over an isolated temp git repo."""
from __future__ import annotations

import pytest

from aios import config
from aios.agents.rollback_engine import RollbackEngine, RollbackError


def test_refuses_to_manage_project_root() -> None:
    with pytest.raises(RollbackError):
        RollbackEngine(repo_dir=config.PROJECT_ROOT)


def test_snapshot_then_rollback_restores_state(tmp_path) -> None:
    engine = RollbackEngine(repo_dir=tmp_path)
    work = tmp_path / "work.txt"

    work.write_text("v1", encoding="utf-8")
    snap1 = engine.create_snapshot("v1 state")

    work.write_text("v2 BROKEN", encoding="utf-8")
    engine.create_snapshot("v2 state")
    assert work.read_text(encoding="utf-8") == "v2 BROKEN"

    result = engine.rollback(snap1.sha)
    assert result.restored is True
    assert work.read_text(encoding="utf-8") == "v1"


def test_rollback_without_sha_reverts_previous_snapshot(tmp_path) -> None:
    engine = RollbackEngine(repo_dir=tmp_path)
    work = tmp_path / "work.txt"

    work.write_text("good", encoding="utf-8")
    engine.create_snapshot("good state")
    work.write_text("bad", encoding="utf-8")
    engine.create_snapshot("bad state")

    engine.rollback()  # defaults to the previous snapshot
    assert work.read_text(encoding="utf-8") == "good"


def test_rollback_cleans_untracked_files(tmp_path) -> None:
    engine = RollbackEngine(repo_dir=tmp_path)
    (tmp_path / "keep.txt").write_text("keep", encoding="utf-8")
    snap = engine.create_snapshot("baseline with keep")

    # An untracked file created after the snapshot should be swept on rollback.
    (tmp_path / "garbage.txt").write_text("junk", encoding="utf-8")
    engine.rollback(snap.sha)
    assert not (tmp_path / "garbage.txt").exists()


def test_list_snapshots_newest_first(tmp_path) -> None:
    engine = RollbackEngine(repo_dir=tmp_path)
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    engine.create_snapshot("first")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    engine.create_snapshot("second")

    snaps = engine.list_snapshots(limit=5)
    assert len(snaps) >= 3  # baseline + first + second
    assert "second" in snaps[0].message
