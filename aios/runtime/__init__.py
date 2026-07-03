"""Council Runtime v0.1 package."""
from __future__ import annotations

from pathlib import Path


def _safe_resolve(raw: str | Path) -> Path:
    """Resolve a filesystem path and reject traversal components.

    Guards against path-traversal attacks where an untrusted ``..`` segment
    could escape the expected directory hierarchy.  Always returns an absolute,
    fully-resolved path with all symlinks dereferenced.
    """
    if ".." in Path(raw).parts:
        raise ValueError(f"path traversal detected in: {raw}")
    return Path(raw).resolve()
