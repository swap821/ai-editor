from __future__ import annotations

from pathlib import Path

import pytest

from aios.application.workspaces import (
    BaselineChanged,
    StagedWorkspaceManager,
    WorkspaceCollision,
    WorkspacePathViolation,
)


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "src" / "main.py").write_text("print('baseline')\n", encoding="utf-8")
    return project


def test_worker_changes_stay_out_of_real_project_and_diff_is_reproducible(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    manager = StagedWorkspaceManager(tmp_path / "staged", enrolled_roots=(project,))
    lease = manager.stage("mission-1", project)

    staged_file = Path(lease.workspace_path) / "src" / "main.py"
    staged_file.write_text("print('changed')\n", encoding="utf-8")
    diff = manager.diff(lease)

    assert project.joinpath("src", "main.py").read_text() == "print('baseline')\n"
    assert diff["modified"] == ["src/main.py"]
    assert diff["diff_digest"] == manager.diff(lease)["diff_digest"]


def test_baseline_change_refuses_promotion_precondition(tmp_path: Path) -> None:
    project = _project(tmp_path)
    manager = StagedWorkspaceManager(tmp_path / "staged", enrolled_roots=(project,))
    lease = manager.stage("mission-1", project)
    project.joinpath("src", "main.py").write_text("outside change\n", encoding="utf-8")
    with pytest.raises(BaselineChanged):
        manager.verify_baseline(lease)


def test_one_mission_gets_one_workspace_and_cleanup_is_bounded(tmp_path: Path) -> None:
    project = _project(tmp_path)
    manager = StagedWorkspaceManager(tmp_path / "staged", enrolled_roots=(project,))
    lease = manager.stage("mission-1", project)
    with pytest.raises(WorkspaceCollision):
        manager.stage("mission-1", project)
    workspace = Path(lease.workspace_path)
    manager.cleanup(lease)
    assert not workspace.exists()


def test_unenrolled_and_symlinked_projects_are_rejected(tmp_path: Path) -> None:
    project = _project(tmp_path)
    manager = StagedWorkspaceManager(tmp_path / "staged", enrolled_roots=(project,))
    with pytest.raises(WorkspacePathViolation):
        manager.stage("mission-1", tmp_path)

    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = project / "link.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")
    with pytest.raises(WorkspacePathViolation):
        manager.stage("mission-2", project)


def test_enrollment_allows_a_descendant_without_widening_root(tmp_path: Path) -> None:
    project = _project(tmp_path)
    manager = StagedWorkspaceManager(tmp_path / "staged", enrolled_roots=(project,))

    lease = manager.stage("mission-nested", project / "src")

    assert Path(lease.project_root) == (project / "src").resolve()
    assert Path(lease.workspace_path).is_dir()


def test_failed_copy_releases_the_mission_lease(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path)
    manager = StagedWorkspaceManager(tmp_path / "staged", enrolled_roots=(project,))
    original_copy = manager._copy_tree

    def fail_once(source: Path, destination: Path) -> None:
        monkeypatch.setattr(manager, "_copy_tree", original_copy)
        raise OSError("copy failed")

    monkeypatch.setattr(manager, "_copy_tree", fail_once)
    with pytest.raises(OSError, match="copy failed"):
        manager.stage("mission-retry", project)

    lease = manager.stage("mission-retry", project)
    assert lease.mission_id == "mission-retry"


def test_cleanup_for_mission_removes_workspace_and_lease_marker(tmp_path: Path) -> None:
    project = _project(tmp_path)
    manager = StagedWorkspaceManager(tmp_path / "staged", enrolled_roots=(project,))
    lease = manager.stage("mission-cleanup", project)
    workspace = Path(lease.workspace_path)

    manager.cleanup_for_mission("mission-cleanup")

    assert not workspace.exists()
    assert manager.for_mission("mission-cleanup") is None
    replacement = manager.stage("mission-cleanup", project)
    assert replacement.mission_id == "mission-cleanup"
