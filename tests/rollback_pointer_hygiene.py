"""A test session must not leave ``training_ground/.git`` pointing at its own
scratch, which pytest deletes when the session ends.

Found 2026-10-29 by a review. With no ``repo_dir``, ``RollbackEngine``'s
work-tree is the first scope root, the repository's own ``training_ground/``,
and its git database goes to ``config.ROLLBACK_DIR`` under the data directory,
which a test session puts in its own scratch. So ``Repo.init`` with
``separate_git_dir`` leaves a ``gitdir:`` pointer FILE in ``training_ground/``.
When the session ends, its scratch is deleted and the pointer dangles. Every
later session in that checkout that builds the default engine then fails, and
``scripts/learning_mutation_probe.py``, which runs one session per mutation,
scored every later mutation "killed", a do-nothing one included.

Only a pointer FILE into pytest's own scratch is ever removed. A real ``.git``
directory, or a pointer anywhere else, is never touched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def pointer_target(worktree: Path) -> Optional[Path]:
    """Where ``worktree/.git`` points, when it is a ``gitdir:`` pointer file."""
    pointer = worktree / ".git"
    if not pointer.is_file():
        return None
    try:
        text = pointer.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text.startswith("gitdir:"):
        return None
    return Path(text[len("gitdir:") :].strip())


def remove_pytest_pointer(
    worktree: Path, scratch_root: Path, *, only_if_dangling: bool
) -> bool:
    """Remove ``worktree/.git`` if it is a pointer into *scratch_root*; with
    *only_if_dangling*, only once its target is gone (another session running
    in this checkout may still be using a live one). True when removed."""
    target = pointer_target(worktree)
    if target is None:
        return False
    try:
        if not target.resolve().is_relative_to(scratch_root.resolve()):
            return False
        if only_if_dangling and target.exists():
            return False
        (worktree / ".git").unlink()
    except OSError:
        return False
    return True
