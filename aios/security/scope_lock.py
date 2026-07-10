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
import shlex
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from aios import config

#: Shell operators that separate commands/redirections. We split on these BEFORE
#: tokenising so an absolute path glued to a prior word (``x>/etc/p``,
#: ``foo;/etc/passwd``) becomes its own word and is scope-checked as the escape
#: it is. Newlines are already handled by shlex's whitespace split.
_SHELL_OPS = re.compile(r"[;|&<>`]+")

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
    import os
    res_str = os.path.realpath(str(resolved))
    root_str = os.path.realpath(str(root))
    if res_str == root_str or res_str.startswith(root_str + os.sep):
        return True
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


def _looks_like_path(token: str) -> bool:
    """Whether a shell word is worth scope-checking as a filesystem path.

    True when it contains a path separator, starts with a parent ref (``..``), or
    has a drive prefix (``C:``). Bare words (``pip``, ``flask``) are not paths and
    are skipped, so a command argument can't be mistaken for one.
    """
    if "/" in token or "\\" in token:
        return True
    if token.startswith(".."):
        return True
    return len(token) >= 2 and token[1] == ":" and token[0].isalpha()


#: Verbs whose bare (no-separator) argument is a file/directory TARGET, not
#: free text -- e.g. ``mkdir probe_dir``. These need scope-checking even
#: though ``probe_dir`` alone fails ``_looks_like_path`` (no separator), since
#: the executor's real process cwd is the repo root the primary scope root
#: lives under, not the scope root itself (see ``Executor._scope_cwd``) — a
#: bare relative target therefore lands next to the sandbox, not inside it.
#: Confirmed via a live repro: an approved ``mkdir probe_dir`` created
#: ``probe_dir`` as a sibling of ``training_ground/`` instead of nested under
#: it. Rather than try to resolve a bare word (which is ambiguous about which
#: directory it's relative to), we require an explicit sandbox-relative path
#: for these verbs — matching the prefix already mandated for autonomous
#: writes (see ``aios/probe_common.py``'s ``ALLOWED_FILE_RE``). Limited to
#: simple verbs with plain positional path arguments; PowerShell cmdlets
#: (``New-Item``, ``Copy-Item``, ...) commonly pass paths via ``-Path``/
#: ``-Destination`` flag/value pairs and are intentionally out of scope here
#: to avoid false-blocking legitimate flag values.
_WRITE_VERBS = frozenset({
    "mkdir", "md", "rmdir", "rd", "touch",
    "rm", "del", "erase", "cp", "copy", "mv", "move", "ren", "rename",
})


def _bare_write_target_is_out_of_scope(words: list[str]) -> Optional[str]:
    """First bare (unprefixed) path argument to a write verb, if any.

    Returns the offending word, or ``None`` if the command doesn't open with
    a write verb or every argument already carries an explicit path.
    """
    if not words:
        return None
    verb = words[0].strip("\"'").lower()
    if verb not in _WRITE_VERBS:
        return None
    for raw in words[1:]:
        token = raw.strip("\"'")
        if not token or token.startswith("-"):
            continue  # unix-style flag, not a path argument
        if _looks_like_path(token):
            continue  # already carries an explicit path; the normal check covers it
        return token
    return None


def command_stays_in_scope(command: str) -> CommandScopeResult:
    """Verify every path-like *word* in *command* resolves inside a scope root.

    The command is split into shell **words** and each path-like word is resolved
    as a *single* path. This is deliberately different from scanning for path
    *fragments*: a relative tool path like ``.venv\\Scripts\\python.exe`` is checked
    intact, instead of a mid-word separator being mis-read as the rooted
    ``\\Scripts\\python.exe`` (which used to falsely resolve to ``C:\\Scripts\\…``
    and block legitimate commands). Real escapes are still caught — an absolute
    path, a drive path, or relative traversal (``..\\..``) resolves outside the
    root and is blocked. The line is first split on shell operators (so an
    absolute path glued to a word by ``>`` ``;`` ``|`` ``&`` is isolated), and a
    ``~`` home reference is refused outright. Returns at the first offending word;
    fail-closed (unbalanced quotes fall back to a whitespace split).
    """
    if not command or not isinstance(command, str):
        return CommandScopeResult(False, "Empty command (fail-closed).")

    # Split on shell operators first so a glued absolute path (``x>/etc/p``,
    # ``a;/etc/passwd``) becomes its own word, then shlex-tokenise each segment
    # (posix=False keeps Windows backslashes literal). Unbalanced quotes fall
    # back to a whitespace split. Over-splitting a quoted literal can only block,
    # never silently allow — the right bias for a fail-closed scope gate.
    words: list[str] = []
    for segment in _SHELL_OPS.split(command):
        if not segment.strip():
            continue
        try:
            words.extend(shlex.split(segment, posix=False))
        except ValueError:
            words.extend(segment.split())

    for raw in words:
        token = raw.strip("\"'")
        if not token:
            continue
        # Home reference: Path never expands ``~``, so a literal join would
        # resolve in-scope. Refuse it — home is never inside the sandbox.
        if token.startswith("~"):
            return CommandScopeResult(
                False,
                f"Home-directory reference '{token}' escapes the sandbox scope.",
                offending=token,
            )
        if not _looks_like_path(token):
            continue
        # Skip tiny pure flags (``/s``, ``-r``) — but never a parent ref (``..``).
        if len(token) < 3 and not token.startswith(".."):
            continue
        check = is_path_in_scope(token)
        if not check.in_scope:
            return CommandScopeResult(False, check.reason, offending=token)

    bare_target = _bare_write_target_is_out_of_scope(words)
    if bare_target is not None:
        return CommandScopeResult(
            False,
            f"'{bare_target}' has no explicit sandbox-relative path (e.g. "
            f"'training_ground/{bare_target}') — a bare argument to a "
            "file-mutating command is ambiguous about which directory it "
            "targets and is refused rather than guessed.",
            offending=bare_target,
        )
    return CommandScopeResult(True, "All path tokens within scope.")
