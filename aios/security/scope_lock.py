"""Path canonicalization and scope-root enforcement (fail-closed).

Every candidate path is resolved to an absolute, symlink-resolved real path
before being compared against the session's declared scope roots. This defeats
directory-escape attacks — relative traversal (``../../etc/passwd``), absolute
paths (``C:\\Windows\\System32``), and symlinks that point outside the allowed
tree — because :meth:`pathlib.Path.resolve` follows symlinks on the existing
prefix and normalises the rest. Anything that cannot be *proven* in-scope is
treated as out-of-scope.

Scope roots default to :data:`aios.config.SCOPE_ROOTS` (the ``training_ground``
"playground") and can be re-declared per session via :func:`set_scope_roots`.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from aios import config

#: Tokens inside a shell command that look like filesystem paths: a drive
#: prefix (``C:\``), a relative marker (``./`` / ``../``), or a leading slash.
_PATH_TOKEN = re.compile(r"(?:[A-Za-z]:[\\/]|\.{1,2}[\\/]|[\\/])[^\s\"';|&]*")

_lock = threading.RLock()
_scope_roots: list[Path] = [Path(p).resolve() for p in config.SCOPE_ROOTS]


@dataclass(frozen=True)
class ScopeResult:
    """Outcome of a single path scope check."""

    in_scope: bool
    resolved: str
    reason: str


@dataclass(frozen=True)
class CommandScopeResult:
    """Outcome of scanning a whole command for out-of-scope path tokens."""

    in_scope: bool
    reason: str
    offending: Optional[str] = None


def set_scope_roots(roots: Iterable[str | Path]) -> tuple[Path, ...]:
    """Replace the declared scope roots (session init). Returns the new roots."""
    resolved = [Path(r).resolve() for r in roots]
    if not resolved:
        raise ValueError("At least one scope root is required.")
    with _lock:
        _scope_roots.clear()
        _scope_roots.extend(resolved)
        return tuple(_scope_roots)


def get_scope_roots() -> tuple[Path, ...]:
    """Return the currently declared scope roots."""
    with _lock:
        return tuple(_scope_roots)


def _is_within(resolved: Path, root: Path) -> bool:
    """Return True if *resolved* is *root* itself or nested beneath it."""
    if resolved == root:
        return True
    try:
        resolved.relative_to(root)
        return True
    except ValueError:
        return False


def is_path_in_scope(candidate: str) -> ScopeResult:
    """Resolve *candidate* and check it against every declared scope root.

    Relative paths are resolved against the primary (first) scope root.
    Fail-closed: any resolution error yields ``in_scope=False``.
    """
    try:
        if not candidate or not isinstance(candidate, str):
            return ScopeResult(False, "", "Empty or invalid path (fail-closed).")

        roots = get_scope_roots()
        base = roots[0] if roots else Path.cwd()
        raw = Path(candidate)
        # Join relative paths onto the primary root; absolute/drive-rooted paths
        # override the base per pathlib semantics (which is what we want — they
        # then fail the scope check below).
        resolved = (base / raw).resolve()

        for root in roots:
            if _is_within(resolved, root):
                return ScopeResult(True, str(resolved), "Path within declared scope.")
        return ScopeResult(
            False,
            str(resolved),
            f"Path '{resolved}' escapes all declared scope roots.",
        )
    except Exception as exc:  # noqa: BLE001 - fail-closed on any error
        return ScopeResult(False, "", f"Path resolution failed (fail-closed): {exc}")


def command_stays_in_scope(command: str) -> CommandScopeResult:
    """Extract path-like tokens from *command* and verify each stays in scope.

    Returns at the first offending token. Pure flags (``-rf``, ``/s``) are
    skipped via a minimum-length guard so they are not mistaken for paths.
    """
    if not command or not isinstance(command, str):
        return CommandScopeResult(False, "Empty command (fail-closed).")

    for token in _PATH_TOKEN.findall(command):
        if len(token) < 3:  # e.g. "/s", "-r" — a flag, not a path
            continue
        check = is_path_in_scope(token)
        if not check.in_scope:
            return CommandScopeResult(False, check.reason, offending=token)
    return CommandScopeResult(True, "All path tokens within scope.")
