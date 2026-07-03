"""Council Runtime v0.1 package."""
from __future__ import annotations

from pathlib import Path


def _safe_resolve(raw: str | Path) -> Path:
    """Resolve a filesystem path and reject traversal components.

    Guards against path-traversal attacks where an untrusted ``..`` segment
    could escape the expected directory hierarchy.  The resolved path must
    also fall under ``config.COUNCIL_RUNTIME_DIR`` (startswith containment).
    """
    if ".." in Path(raw).parts:
        raise ValueError(f"path traversal detected in: {raw}")
    resolved = Path(raw).resolve()
    from aios import config
    base = str(config.COUNCIL_RUNTIME_DIR.resolve())
    if not str(resolved).startswith(base):
        raise ValueError(
            f"path escapes runtime directory: {resolved} is not under {base}"
        )
    return resolved
