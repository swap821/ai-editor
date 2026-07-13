"""Fail-closed validation for executor staging workspaces."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_staged_workspace(path: str, root: str | Path) -> Path:
    """Return *path* only when its real path is contained under *root*.

    Both values are canonicalized before the containment check so traversal and
    symlink escapes cannot reach the Docker mount builder.  This function is
    the trust boundary for the authenticated executor service; callers should
    pass its result onward rather than re-resolving the request value.
    """
    raw_root = str(root).rstrip("/\\")
    raw_path = str(path)
    if raw_path != raw_root and not raw_path.startswith(raw_root + os.sep):
        raise ValueError("workspace is outside executor staging root")
    safe_root = os.path.realpath(raw_root)
    candidate = os.path.realpath(raw_path)
    if candidate != safe_root and not candidate.startswith(safe_root + os.sep):
        raise ValueError("workspace is outside executor staging root")
    return Path(candidate)


__all__ = ["resolve_staged_workspace"]
