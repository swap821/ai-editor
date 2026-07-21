"""Council Runtime v0.1 package."""

from __future__ import annotations

import os
from pathlib import Path


def _safe_resolve(raw: str | Path) -> Path:
    """Resolve a filesystem path and reject traversal components.

    Guards against path-traversal attacks where an untrusted ``..`` segment
    could escape the expected directory hierarchy.  The resolved path must
    also fall under ``config.COUNCIL_RUNTIME_DIR`` (startswith containment).

    Uses ``os.path.realpath`` (string-native) so that CodeQL's taint analysis
    can track the sanitisation through the ``startswith`` guard.
    """
    if ".." in Path(raw).parts:
        raise ValueError(f"path traversal detected in: {raw}")
    resolved = os.path.realpath(str(raw))
    from aios import config

    base = os.path.realpath(str(config.COUNCIL_RUNTIME_DIR))
    if resolved != base and not resolved.startswith(base + os.sep):
        raise ValueError(
            f"path escapes runtime directory: {resolved} is not under {base}"
        )
    return Path(resolved)
