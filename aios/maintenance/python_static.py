"""GAGOS's static checks for its own Python: its backend and itself (2026-11-02).

The operator, 2026-11-02: GAGOS's workshop must be "capable of improving its
both backend and frontend and itself". This is the Python half of what
:mod:`aios.maintenance.frontend_static` is for the frontend. It judges texts
that need not be on disk, with the project's own ruff and Python's parser, and
executes nothing a model wrote:

* :func:`editable_python_files` -- what GAGOS may change: tracked ``.py`` files
  under ``aios/`` and ``tools/`` (its backend, and its own worker), never the
  frozen security core (``aios/security/``: never agent-applied, and its bytes
  are the spine hash) and never an organ's production entrypoint (a change
  there makes that organ's evidence stale until it is gathered again);
* :func:`check_python_texts` -- ruff's messages, with ``# noqa`` honoured and
  ignored (so what a silencer hides can be compared), every comment, and
  whether the text parses;
* :func:`import_refusal` -- an import a proposal removes must not be one that
  other modules import from this one: ruff sees one file, not its importers.
"""

from __future__ import annotations

import ast
import io
import json
import re
import shutil
import subprocess
import sys
import tokenize
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from aios.maintenance.frontend_static import (
    Comment,
    LintMessage,
    StaticCheckUnavailable,
    StaticResult,
)

#: Where GAGOS's backend and its own worker live.
PYTHON_SCOPE = ("aios/", "tools/")
#: Never GAGOS's to change: the operator's rule for the security core.
FROZEN = ("aios/security/",)
#: Lint runs a few files at once; each is its own short ruff process.
_AT_ONCE = 8
_TIMEOUT_S = 60


def _run(argv: list[str], root: Path, text: str | None = None):
    """The one place this module runs a program: git or the project's ruff,
    by absolute path, never through a shell, on text it passes as input."""
    return subprocess.run(
        argv,
        cwd=str(root),
        input=text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_TIMEOUT_S,
    )


def _tracked(root: Path, *pathspec: str) -> list[str]:
    git = shutil.which("git")
    if git is None:
        raise StaticCheckUnavailable("git is not installed")
    proc = _run([git, "ls-files", "--", *pathspec], root)
    if proc.returncode != 0:
        raise StaticCheckUnavailable(
            f"git ls-files failed: {proc.stderr.strip()[:200]}"
        )
    return proc.stdout.splitlines()


def organ_entrypoints(project_root: Path) -> frozenset[str]:
    """Every organ's production entrypoints, from the organ ledger. Unknown is
    not empty: without the ledger GAGOS cannot tell evidence from code."""
    from aios.application.governance.organ_ledger import (
        _default_ledger_path,
        load_ledger,
    )

    try:
        records = load_ledger(_default_ledger_path(project_root))
    except Exception as exc:  # any failure to read it is a refusal, never "none"
        raise StaticCheckUnavailable(
            f"the organ ledger cannot be read, so its entrypoints are unknown: {exc}"
        ) from exc
    return frozenset(
        p.replace("\\", "/") for r in records for p in r.production_entrypoints
    )


def editable_python_files(project_root: Path) -> list[str]:
    """Tracked Python GAGOS may change, as POSIX paths, sorted."""
    tracked = _tracked(project_root, *PYTHON_SCOPE)
    evidence = organ_entrypoints(project_root)
    return sorted(
        rel
        for rel in tracked
        if rel.endswith(".py")
        and not rel.startswith(FROZEN)
        and rel not in evidence
        and (project_root / rel).is_file()
    )


def _ruff(project_root: Path, rel: str, text: str, *extra: str) -> list[dict]:
    try:
        proc = _run(
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--no-fix",
                "--force-exclude",
                "--output-format",
                "json",
                "--stdin-filename",
                rel,
                *extra,
                "-",
            ],
            project_root,
            text,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise StaticCheckUnavailable(f"ruff could not run: {exc}") from exc
    if proc.returncode not in (0, 1):
        raise StaticCheckUnavailable(
            f"ruff exited {proc.returncode}: {(proc.stderr or '').strip()[:300]}"
        )
    try:
        return json.loads(proc.stdout or "[]")
    except ValueError as exc:
        raise StaticCheckUnavailable(f"ruff's output is not JSON: {exc}") from exc


def _messages(raw: list[dict]) -> tuple[LintMessage, ...]:
    out = []
    for m in raw:
        code = m.get("code")
        syntax = code in (None, "invalid-syntax") or m.get("name") == "invalid-syntax"
        loc = m.get("location") or {}
        out.append(
            LintMessage(
                rule=None if syntax else code,
                severity=2 if syntax else 1,
                line=int(loc.get("row") or 0),
                column=int(loc.get("column") or 0),
                message=str(m.get("message", "")),
                fatal=syntax,
            )
        )
    return tuple(sorted(out, key=lambda x: (x.line, x.column, x.rule or "")))


def _comments(text: str) -> tuple[Comment, ...] | None:
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return None
    return tuple(
        Comment("Line", t.string[1:], t.start[0], t.end[0])
        for t in tokens
        if t.type == tokenize.COMMENT
    )


def _parse_errors(rel: str, text: str) -> tuple[str, ...]:
    try:
        ast.parse(text, filename=rel)
    except SyntaxError as exc:
        return (f"line {exc.lineno}: {exc.msg}",)
    return ()


def check_python_texts(
    project_root: Path, texts: Mapping[str, str], *, inline_off: bool = False
) -> dict[str, StaticResult]:
    """What ruff and the parser say about each text, keyed like *texts*.
    With *inline_off*, ruff runs again ignoring ``# noqa``, and every comment
    is returned, as :func:`silencing_refusal` needs."""
    root = Path(project_root)

    def one(item: tuple[str, str]) -> tuple[str, StaticResult]:
        rel, text = item
        messages = _messages(_ruff(root, rel, text))
        hidden = (
            _messages(_ruff(root, rel, text, "--ignore-noqa")) if inline_off else None
        )
        return rel, StaticResult(
            messages=messages,
            parse_errors=_parse_errors(rel, text),
            inline_off=hidden,
            comments=_comments(text) if inline_off else None,
        )

    with ThreadPoolExecutor(max_workers=_AT_ONCE) as pool:
        return dict(pool.map(one, texts.items()))


# --------------------------------------------------------------------- importers


def _bound_imports(text: str) -> set[str]:
    """The names a module's top-level and nested imports bind."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update(a.asname or a.name for a in node.names if a.name != "*")
    return names


def module_of(rel: str) -> str:
    """``aios/a/b.py`` -> ``aios.a.b``; a package's ``__init__.py`` is the package."""
    parts = rel[: -len(".py")].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def import_refusal(
    project_root: Path, rel: str, before_text: str, after_text: str
) -> str | None:
    """Why removing these imports may break another module, or None. A name a
    module imports may be imported from it elsewhere (a re-export); ruff,
    which sees one file, reports it unused all the same."""
    removed = _bound_imports(before_text) - _bound_imports(after_text)
    if not removed:
        return None
    module = module_of(rel)
    parent, _, last = module.rpartition(".")
    tracked = _tracked(project_root, "*.py")
    from_here = re.compile(
        rf"from\s+{re.escape(module)}\s+import\s+(\([^)]*\)|[^\n]*)", re.S
    )
    for other in tracked:
        if other == rel:
            continue
        try:
            source = (Path(project_root) / other).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if module not in source and not (parent and last in source):
            continue
        for name in sorted(removed):
            word = re.compile(rf"\b{re.escape(name)}\b")
            if any(word.search(m.group(1)) for m in from_here.finditer(source)) or (
                re.search(rf"\b{re.escape(module)}\.{re.escape(name)}\b", source)
                or (
                    parent
                    and re.search(
                        rf"from\s+{re.escape(parent)}\s+import\s+[^\n]*\b{re.escape(last)}\b",
                        source,
                    )
                    and re.search(rf"\b{re.escape(last)}\.{re.escape(name)}\b", source)
                )
            ):
                return (
                    f"the proposal removes the import of {name}, which another "
                    f"module ({Path(other).name}) takes from this one"
                )
    return None
