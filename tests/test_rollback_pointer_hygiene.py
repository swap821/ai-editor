"""A test session leaves no dangling ``training_ground/.git`` behind
(``tests/rollback_pointer_hygiene.py``; review, 2026-10-29)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.rollback_pointer_hygiene import pointer_target, remove_pytest_pointer

REPO = Path(__file__).resolve().parents[1]


def _pointer(worktree: Path, target: Path) -> None:
    worktree.mkdir(parents=True, exist_ok=True)
    (worktree / ".git").write_text(f"gitdir: {target.as_posix()}\n", encoding="utf-8")


def test_a_dangling_pointer_into_pytest_scratch_is_removed(tmp_path) -> None:
    scratch = tmp_path / "pytest-root"
    tree = tmp_path / "training_ground"
    _pointer(tree, scratch / "pytest-session-x" / "rollback")
    assert pointer_target(tree) is not None
    assert remove_pytest_pointer(tree, scratch, only_if_dangling=True)
    assert not (tree / ".git").exists()


def test_a_live_pointer_is_kept_until_its_own_session_ends(tmp_path) -> None:
    scratch = tmp_path / "pytest-root"
    live = scratch / "pytest-session-y" / "rollback"
    live.mkdir(parents=True)
    tree = tmp_path / "training_ground"
    _pointer(tree, live)
    assert not remove_pytest_pointer(tree, scratch, only_if_dangling=True)
    assert (tree / ".git").exists(), "another session may be using it"
    assert remove_pytest_pointer(tree, scratch, only_if_dangling=False)


def test_nothing_outside_pytest_scratch_is_touched(tmp_path) -> None:
    scratch = tmp_path / "pytest-root"
    tree = tmp_path / "training_ground"
    _pointer(tree, tmp_path / "elsewhere" / "rollback")
    assert not remove_pytest_pointer(tree, scratch, only_if_dangling=False)
    assert (tree / ".git").is_file()

    real = tmp_path / "real_repo"
    (real / ".git").mkdir(parents=True)
    assert not remove_pytest_pointer(real, scratch, only_if_dangling=False)
    assert (real / ".git").is_dir()


def test_a_session_that_builds_the_default_rollback_engine_leaves_no_dangling_pointer() -> (
    None
):
    """The real thing: a separate pytest session builds the default engine
    (its work-tree is this repository's training_ground) and exits. Afterwards
    any pointer there must still resolve."""
    node = (
        "tests/test_api_main_gaps.py::"
        "test_get_executor_and_rollback_engine_return_real_instances"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            node,
            "-q",
            "-p",
            "no:cacheprovider",
            "--no-cov",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-2000:]
    target = pointer_target(REPO / "training_ground")
    assert target is None or target.exists(), f"dangling pointer to {target}"
