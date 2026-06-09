"""Rollback engine tests — snapshot/restore over an isolated temp git repo."""
from __future__ import annotations

import threading

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


def test_concurrent_snapshot_workers_share_repository_lock(tmp_path) -> None:
    first = RollbackEngine(repo_dir=tmp_path)
    second = RollbackEngine(repo_dir=tmp_path)
    barrier = threading.Barrier(2)
    errors = []

    def snapshot(engine: RollbackEngine, name: str) -> None:
        try:
            (tmp_path / name).write_text(name, encoding="utf-8")
            barrier.wait()
            engine.create_snapshot(name)
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    threads = [
        threading.Thread(target=snapshot, args=(first, "one.txt")),
        threading.Thread(target=snapshot, args=(second, "two.txt")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert first.list_snapshots()


# --------------------------------------------------------------------------- #
# FIX #3 — the rollback git DATABASE lives out of the tracked sandbox work-tree
# --------------------------------------------------------------------------- #
def test_default_engine_keeps_git_db_out_of_the_tracked_worktree(tmp_path, monkeypatch) -> None:
    # The default engine (no repo_dir) snapshots the sandbox work-tree but stores
    # its git DATABASE under the gitignored ROLLBACK_DIR — so no .git database
    # lands inside the main-repo-tracked training_ground/, only a gitdir pointer.
    work = tmp_path / "sandbox"
    gitdb = tmp_path / "data" / "rollback"
    monkeypatch.setattr(config, "SCOPE_ROOTS", (work,))
    monkeypatch.setattr(config, "ROLLBACK_DIR", gitdb)

    engine = RollbackEngine()  # uses the (patched) default sandbox + ROLLBACK_DIR

    pointer = work / ".git"
    assert pointer.is_file(), "the sandbox must hold a gitdir pointer, not a .git dir"
    assert "gitdir:" in pointer.read_text(encoding="utf-8")
    assert not (work / ".git").is_dir()
    # The actual git database (HEAD + objects) lives under ROLLBACK_DIR.
    assert (gitdb / "HEAD").exists() and (gitdb / "objects").is_dir()

    # Snapshot/rollback still works end-to-end through the external database.
    f = work / "work.txt"
    f.write_text("v1", encoding="utf-8")
    snap = engine.create_snapshot("v1 state")
    f.write_text("v2 BROKEN", encoding="utf-8")
    engine.create_snapshot("v2 state")
    assert engine.rollback(snap.sha).restored is True
    assert f.read_text(encoding="utf-8") == "v1"


def test_default_engine_reopens_existing_db_via_pointer(tmp_path, monkeypatch) -> None:
    # A second engine over the same sandbox reopens the external DB via the
    # pointer file (no re-init), so prior snapshot history is preserved.
    work = tmp_path / "sandbox"
    gitdb = tmp_path / "data" / "rollback"
    monkeypatch.setattr(config, "SCOPE_ROOTS", (work,))
    monkeypatch.setattr(config, "ROLLBACK_DIR", gitdb)

    first = RollbackEngine()
    (work / "a.txt").write_text("a", encoding="utf-8")
    snap = first.create_snapshot("first")

    second = RollbackEngine()
    assert any(s.sha == snap.sha for s in second.list_snapshots(limit=5)), (
        "a reopened engine must see snapshots from the external database"
    )


def test_injected_repo_dir_keeps_db_in_tree(tmp_path) -> None:
    # An explicitly injected repo_dir (a temp dir, already isolated) keeps its git
    # database in-tree — preserving the original behaviour the other tests rely on.
    engine = RollbackEngine(repo_dir=tmp_path)
    assert (tmp_path / ".git").is_dir(), "an injected repo_dir uses an in-tree .git database"
    assert engine.repo_dir == tmp_path.resolve()
