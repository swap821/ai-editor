"""Fail-closed validation for executor staging workspaces."""
from __future__ import annotations

import os
from pathlib import Path


def resolve_staged_workspace(path: str, root: str | Path) -> Path:
    """Return *path* only when its real path is a directory under *root*.

    Both values are canonicalized before the containment check so traversal and
    symlink escapes cannot reach the Docker mount builder.  This function is
    the trust boundary for the authenticated executor service; callers should
    pass its result onward rather than re-resolving the request value.
    """
    safe_root = os.path.normcase(os.path.realpath(str(root)))
    candidate = os.path.normcase(os.path.realpath(str(path)))
    if candidate != safe_root and not candidate.startswith(safe_root + os.sep):
        raise ValueError("workspace is outside executor staging root")
    if not os.path.isdir(candidate):
        raise ValueError("workspace is not a directory")
    return Path(candidate)


__all__ = ["resolve_staged_workspace"]
