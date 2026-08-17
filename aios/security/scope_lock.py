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
#: A scheme-bearing token (``https://``, ``git@``-style ``ssh://``, ``file://``).
#: Deliberately NOT a filesystem path -- see :func:`_looks_like_path`. Requires
#: ``//`` so a Windows drive (``C:\\x``) is still treated as the path it is.
_URL_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://")

#: Commands exempt from the sandbox scope check by EXACT string identity.
#:
#: Exactly one entry, and it must stay that way: the §VIII self-apply verify
#: suite, which by design runs the project's own tests against a proposed change
#: to `aios/`. Its boundary is identity-pinning plus container-only execution
#: (`aios/api/deps.py` raises on any other command), not the training_ground
#: sandbox. Duplicated as a literal rather than imported to keep this frozen
#: module free of an application-layer dependency; a test asserts the two never
#: drift.
#:
#: Do not add patterns here. A pattern is a hole; an exact string is a fact.
_SCOPE_EXEMPT_COMMANDS = frozenset({".venv/Scripts/python -m pytest tests/ -q"})


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


def _is_within(resolved: Path, root: Path) -> bool:
    """Return True if *resolved* is *root* itself or nested beneath it."""
    import os

    res_str = os.path.realpath(str(resolved))
    root_str = os.path.realpath(str(root))
    if res_str == root_str or res_str.startswith(root_str + os.sep):
        return True
    return False


def _looks_like_path(token: str) -> bool:
    """Whether a shell word is worth scope-checking as a filesystem path.

    True when it contains a path separator, starts with a parent ref (``..``), or
    has a drive prefix (``C:``). Bare words (``pip``, ``flask``) are not paths and
    are skipped, so a command argument can't be mistaken for one.
    """
    # A URL is not a filesystem path, and scope-checking it produces a
    # meaningless answer that depends on the resolution base rather than on
    # anything about the request. `https://github.com/x/y.git` used to resolve
    # under the scope root and pass; once command tokens began resolving against
    # the executor's real cwd it resolved outside and failed. Both verdicts were
    # accidents of arithmetic, and the second silently turned `git clone` from
    # CAUTION into RED as a side effect of a containment fix.
    #
    # Network reach is a POLICY question (see the network patterns in
    # `gateway.py`), not a containment one. Skipping schemes here keeps the two
    # decisions separate, so tightening one cannot quietly move the other.
    if _URL_SCHEME.match(token):
        return False
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
_WRITE_VERBS = frozenset(
    {
        "mkdir",
        "md",
        "rmdir",
        "rd",
        "touch",
        "rm",
        "del",
        "erase",
        "cp",
        "copy",
        "mv",
        "move",
        "ren",
        "rename",
    }
)


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


class ScopeLockAuthority:
    """Own path canonicalization and scope-root enforcement (Decision A / organ 2).

    Module-level :func:`set_scope_roots`, :func:`get_scope_roots`,
    :func:`is_path_in_scope`, and :func:`command_stays_in_scope` remain the
    production call sites; they delegate to the process singleton
    :data:`_SCOPE_LOCK`.
    """

    def __init__(self, roots: Iterable[str | Path] | None = None) -> None:
        self._lock = threading.RLock()
        initial = roots if roots is not None else config.SCOPE_ROOTS
        self._scope_roots: list[Path] = [Path(p).resolve() for p in initial]

    def set_scope_roots(self, roots: Iterable[str | Path]) -> tuple[Path, ...]:
        """Replace the declared scope roots (session init). Returns the new roots."""
        resolved = [Path(r).resolve() for r in roots]
        if not resolved:
            raise ValueError("At least one scope root is required.")
        with self._lock:
            self._scope_roots.clear()
            self._scope_roots.extend(resolved)
            return tuple(self._scope_roots)

    def get_scope_roots(self) -> tuple[Path, ...]:
        """Return the currently declared scope roots."""
        with self._lock:
            return tuple(self._scope_roots)

    def command_cwd(self) -> Path:
        """The directory a sandboxed command actually runs in.

        This is the SINGLE source for that directory: ``Executor._scope_cwd()``
        calls it rather than deriving the same thing a second time. The executor
        runs with cwd = the scope root's PARENT so ``training_ground`` is
        importable as a package, and a relative path token in a command is
        therefore resolved by the shell against that parent -- not against the
        scope root.

        Resolving the CHECK against a different base than the EXECUTION is a
        containment escape, not a cosmetic mismatch. See
        :meth:`is_path_in_scope`.

        It is a single function because two copies kept in sync by comment did
        drift, and the drift was an escape. The executor previously derived this
        from :data:`aios.config.SCOPE_ROOTS` (the process-start default) while
        the check derived it from ``get_scope_roots()`` (the live, re-declarable
        authority). Under any session that called :func:`set_scope_roots`, the
        two disagreed and ``touch training_ground/PROOF.txt`` was ALLOWED while
        landing outside every declared root. Read the roots from one place.
        """
        roots = self.get_scope_roots()
        return roots[0].resolve().parent if roots else Path.cwd()

    def is_path_in_scope(
        self, candidate: str, *, base: Optional[Path] = None
    ) -> ScopeResult:
        """Resolve *candidate* and check it against every declared scope root.

        Relative paths resolve against *base*, defaulting to the primary scope
        root. Fail-closed: any resolution error yields ``in_scope=False``.

        ``base`` exists because the default is WRONG for command tokens, and was
        a real escape. The executor runs commands with cwd = the scope root's
        parent (the repo root), so a token like ``training_ground/../X`` was:

            CHECKED  as (training_ground / "training_ground/../X")
                     -> <repo>/training_ground/X        -- in scope, allowed
            EXECUTED as (<repo> / "training_ground/../X")
                     -> <repo>/X                        -- outside every root

        Measured before the fix: ``touch training_ground/../PROOF_ESCAPE.txt``
        classified YELLOW -- one operator approval away from writing outside the
        sandbox, including over ``aios/security/gateway.py`` and the audit DB.

        Callers passing an ABSOLUTE path (the file tools do) are unaffected:
        pathlib lets an absolute right-hand side override the base entirely.
        """
        try:
            if not candidate or not isinstance(candidate, str):
                return ScopeResult(False, "", "Empty or invalid path (fail-closed).")

            roots = self.get_scope_roots()
            if base is None:
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

    def command_stays_in_scope(self, command: str) -> CommandScopeResult:
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
        # The §VIII self-apply verify suite is exempt, by EXACT string identity.
        #
        # It is the one command that legitimately runs repo-wide: it executes the
        # project's own test suite against a proposed change to `aios/`. The
        # sandbox is not its boundary, and never was -- `aios/api/deps.py` refuses
        # ANY other command outright (`if command != DEFAULT_VERIFY_COMMAND:
        # raise`), it is container-only, and self_apply adds no-self-approval,
        # RED-target refusal, single-file diff confinement and auto-rollback.
        # Exact-match identity on one fixed string is a stronger control than
        # path scoping, and it cannot be widened or parameterised.
        #
        # It passed the scope check before only by accident: `.venv/Scripts/...`
        # resolved under the scope ROOT, which is the same arithmetic that let
        # `training_ground/../X` escape. Fixing the base correctly turned this
        # RED and would have blocked §VIII self-modification entirely.
        if command.strip() in _SCOPE_EXEMPT_COMMANDS:
            return CommandScopeResult(
                True, "Exempt fixed command (self-apply verify suite)."
            )
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
            # Resolve against the cwd the command will ACTUALLY run in, not the
            # scope root. Anything else checks a path the executor never opens.
            check = self.is_path_in_scope(token, base=self.command_cwd())
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


_SCOPE_LOCK = ScopeLockAuthority()


def set_scope_roots(roots: Iterable[str | Path]) -> tuple[Path, ...]:
    """Replace the declared scope roots (session init). Returns the new roots."""
    return _SCOPE_LOCK.set_scope_roots(roots)


def get_scope_roots() -> tuple[Path, ...]:
    """Return the currently declared scope roots."""
    return _SCOPE_LOCK.get_scope_roots()


def command_cwd() -> Path:
    """The directory a sandboxed command actually runs in.

    The single source for the command-resolution base, shared by the scope CHECK
    and by ``Executor._scope_cwd()`` which ACTS. See
    :meth:`ScopeLockAuthority.command_cwd`.
    """
    return _SCOPE_LOCK.command_cwd()


def is_path_in_scope(candidate: str) -> ScopeResult:
    """Resolve *candidate* and check it against every declared scope root.

    Relative paths are resolved against the primary (first) scope root.
    Fail-closed: any resolution error yields ``in_scope=False``.
    """
    return _SCOPE_LOCK.is_path_in_scope(candidate)


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
    return _SCOPE_LOCK.command_stays_in_scope(command)
