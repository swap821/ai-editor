from __future__ import annotations

import subprocess

import pytest

from aios.runtime.worktree_backend import (
    InvalidLaneIdError,
    LaneExistsError,
    WorktreeBackend,
)


def _git(args: list[str], cwd) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


@pytest.fixture
def base_repo(tmp_path):
    bare = tmp_path / "bare.git"
    base = tmp_path / "base"
    _git(["init", "--bare", str(bare)], tmp_path)
    _git(["clone", str(bare), str(base)], tmp_path)
    _git(["config", "user.email", "test@example.com"], base)
    _git(["config", "user.name", "Test User"], base)
    (base / "README.md").write_text("init\n")
    _git(["add", "README.md"], base)
    _git(["commit", "-m", "initial commit"], base)
    _git(["push", "origin", "HEAD:refs/heads/master"], base)
    return base


@pytest.fixture
def backend(tmp_path, base_repo):
    return WorktreeBackend(base_repo=base_repo, worktree_root=tmp_path / "worktrees")


def test_create_and_list_lanes(backend):
    path = backend.create_lane("alpha")
    assert path.exists()
    lanes = backend.list_lanes()
    lane_ids = {lane.lane_id for lane in lanes}
    assert "alpha" in lane_ids


def test_destroy_lane(backend):
    backend.create_lane("beta")
    assert backend.lane_exists("beta")
    backend.destroy_lane("beta")
    assert not backend.lane_exists("beta")
    lane_ids = {lane.lane_id for lane in backend.list_lanes()}
    assert "beta" not in lane_ids


def test_lane_exists(backend):
    assert not backend.lane_exists("gamma")
    backend.create_lane("gamma")
    assert backend.lane_exists("gamma")


def test_invalid_lane_id(backend):
    with pytest.raises(InvalidLaneIdError):
        backend.create_lane("../etc")
    with pytest.raises(InvalidLaneIdError):
        backend.create_lane("../../passwd")
    with pytest.raises(InvalidLaneIdError):
        backend.create_lane("lane/with/slash")
    with pytest.raises(InvalidLaneIdError):
        backend.create_lane("")


def test_create_duplicate_fails(backend):
    backend.create_lane("delta")
    with pytest.raises(LaneExistsError):
        backend.create_lane("delta")
