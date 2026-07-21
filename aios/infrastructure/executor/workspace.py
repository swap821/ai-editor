"""Fail-closed validation for executor staging workspaces."""

from __future__ import annotations

import os
import posixpath
import re
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


def daemon_workspace_path(
    path: str | Path,
    *,
    staged_root: str | Path,
    daemon_root: str | Path,
) -> str:
    """Map a validated executor path into the Docker daemon's host view.

    The private executor receives the staging bind mount at one path, while
    the Docker daemon reached through the mounted socket resolves bind sources
    in the host filesystem namespace.  Passing the executor-container path to
    ``docker run`` therefore fails on Docker Desktop and is unsafe to paper
    over with a project-root fallback.  Keep the containment check in the
    executor namespace, then append only the validated relative suffix to the
    explicitly configured daemon-visible root.
    """
    if not str(daemon_root).strip():
        raise ValueError("Docker daemon workspace root is not configured")
    validated = resolve_staged_workspace(path, staged_root)
    root = Path(os.path.realpath(str(staged_root)))
    relative = validated.relative_to(root)
    daemon_text = str(daemon_root).rstrip("/\\")
    if re.match(r"^[A-Za-z]:[\\/]", daemon_text):
        return daemon_text + "\\" + "\\".join(relative.parts)
    return posixpath.join(daemon_text, *relative.parts)


__all__ = ["daemon_workspace_path", "resolve_staged_workspace"]
