"""Unused imports in GAGOS's own frontend: found, and removed, conservatively.

The frontend twin of the dead-import repair (``dead_imports.py``,
``repair_operations.REMOVE_DEAD_IMPORTS_V1``), added 2026-10-30 for GAGOS's
daily frontend worker (the operator's ask: "a permanent daily small worker of
frontend of GAGOS by GAGOS"). One rule serves both the scanner and the repair
operation, so a repair can never remove what the scanner did not report, and
the scanner reports only what the repair can remove.

**The rule is deliberately conservative.** An imported binding is unused only
when its name appears NOWHERE else in the file -- not in code, not in a string,
not in a comment, not in a template literal. A name mentioned only in a comment
is therefore kept: this rule may miss an unused import, but it never calls a
used one unused. ``React`` is never reported (a default ``React`` import is
kept by convention in this codebase).

**What removal preserves.** The frontend compiles with ``isolatedModules`` and
without ``verbatimModuleSyntax`` (``frontend/tsconfig.json``), so in ``.ts`` /
``.tsx`` an import whose bindings are all unused is already dropped by the
compiler: removing it changes nothing at runtime. In ``.js`` / ``.jsx`` /
``.mjs`` an import is kept for its side effects, so an import emptied by the
repair becomes ``import 'module';`` and the module still loads (a CSS file
still styles). ``import type`` statements have no runtime effect at all.

**What it refuses.** Anything it cannot rewrite safely is left alone and
reported as skipped: an import inside a comment or template literal, a clause
it cannot parse (a comment inside the braces, say), a multi-line import whose
unused name shares a line with other code, or a file whose syntax the light
lexer cannot follow. The rewrite must re-parse to exactly the kept bindings, and
nothing outside the rewritten imports may change, or the operation refuses.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

#: Source files the frontend worker reads.
FRONTEND_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs")
#: In these, an import with no used binding is dropped by the compiler already.
TYPESCRIPT_SUFFIXES = (".ts", ".tsx")
#: Where GAGOS's frontend sources live, relative to the project root.
FRONTEND_SOURCE_ROOT = Path("frontend") / "src"
#: Never reported: kept by convention.
KEPT_NAMES = frozenset({"React"})

_IDENT = r"[A-Za-z_$][\w$]*"
_IMPORT = re.compile(
    r"^import(?P<type>[ \t]+type)?[ \t]+(?P<clause>[^;'\"`]*?)[ \t\r\n]+from[ \t]+"
    r"(?P<q>['\"])(?P<module>[^'\"\r\n]+)(?P=q)(?P<semi>[ \t]*;)?",
    re.MULTILINE,
)
_NAMED_ITEM = re.compile(
    rf"^(?P<type>type\s+)?(?P<imported>{_IDENT}|'[^']*'|\"[^\"]*\")"
    rf"(?:\s+as\s+(?P<local>{_IDENT}))?$"
)


class FrontendImportError(ValueError):
    """The file or statement could not be followed safely."""


@dataclass(frozen=True)
class NamedSpecifier:
    text: str  # the specifier as written, e.g. "type Foo as Bar"
    local: str
    type_only: bool


@dataclass(frozen=True)
class ImportStatement:
    start: int
    end: int  # exclusive; the statement's text is source[start:end]
    type_only: bool
    default: Optional[str]
    namespace: Optional[str]
    named: tuple[NamedSpecifier, ...]
    has_braces: bool
    module: str
    quote: str
    semicolon: bool

    @property
    def locals(self) -> tuple[str, ...]:
        names = [n for n in (self.default, self.namespace) if n]
        names.extend(spec.local for spec in self.named)
        return tuple(names)


@dataclass(frozen=True)
class FrontendImportRepair:
    """What the operation decided for one file."""

    content: str
    removed: tuple[str, ...]
    skipped: tuple[str, ...] = field(default=())

    @property
    def changed(self) -> bool:
        return bool(self.removed)


# --------------------------------------------------------------------------- #
# Lexing: where code is, as opposed to comments and template literals
# --------------------------------------------------------------------------- #
def _non_code_spans(text: str) -> list[tuple[int, int]]:
    """Spans of comments and template literals. Strings are followed only so a
    quote or slash inside one is not mistaken for anything else. Regex literals
    are not modelled: a file the lexer cannot close is refused."""
    spans: list[tuple[int, int]] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            j = text.find("\n", i)
            j = n if j < 0 else j
            spans.append((i, j))
            i = j
        elif c == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            if j < 0:
                raise FrontendImportError("unterminated block comment")
            spans.append((i, j + 2))
            i = j + 2
        elif c in ("'", '"'):
            j = i + 1
            while j < n and text[j] != c:
                if text[j] == "\\":
                    j += 1
                elif text[j] == "\n":
                    break  # a quote in a regex literal or JSX text; not a string
                j += 1
            i = j + 1
        elif c == "`":
            j, depth = i + 1, 0
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text.startswith("${", j):
                    depth += 1
                    j += 2
                    continue
                if text[j] == "}" and depth:
                    depth -= 1
                elif text[j] == "`" and not depth:
                    break
                j += 1
            if j >= n:
                raise FrontendImportError("unterminated template literal")
            spans.append((i, j + 1))
            i = j + 1
        else:
            i += 1
    return spans


def _inside(spans: list[tuple[int, int]], offset: int) -> bool:
    return any(a <= offset < b for a, b in spans)


# --------------------------------------------------------------------------- #
# Parsing import statements
# --------------------------------------------------------------------------- #
def _parse_clause(
    clause: str,
) -> tuple[Optional[str], Optional[str], tuple[NamedSpecifier, ...], bool]:
    clause = clause.strip()
    if not clause or "/" in clause:
        raise FrontendImportError(f"unparseable import clause: {clause[:60]!r}")
    default: Optional[str] = None
    namespace: Optional[str] = None
    named: list[NamedSpecifier] = []
    has_braces = False
    rest = clause
    if not rest.startswith(("{", "*")):
        m = re.match(rf"({_IDENT})\s*(?:,\s*(.*))?$", rest, re.DOTALL)
        if not m:
            raise FrontendImportError(f"unparseable default import: {clause[:60]!r}")
        default, rest = m.group(1), (m.group(2) or "").strip()
    if rest.startswith("*"):
        m = re.match(rf"\*\s*as\s+({_IDENT})$", rest)
        if not m:
            raise FrontendImportError(f"unparseable namespace import: {clause[:60]!r}")
        namespace = m.group(1)
    elif rest.startswith("{"):
        if not rest.endswith("}") or rest.count("{") != 1 or rest.count("}") != 1:
            raise FrontendImportError(f"unparseable named imports: {clause[:60]!r}")
        has_braces = True
        for raw in rest[1:-1].split(","):
            item = raw.strip()
            if not item:
                continue
            m = _NAMED_ITEM.match(re.sub(r"\s+", " ", item))
            if not m or (
                m.group("imported").startswith(("'", '"')) and not m.group("local")
            ):
                raise FrontendImportError(f"unparseable named import: {item!r}")
            named.append(
                NamedSpecifier(
                    text=re.sub(r"\s+", " ", item),
                    local=m.group("local") or m.group("imported"),
                    type_only=bool(m.group("type")),
                )
            )
    elif rest:
        raise FrontendImportError(f"unparseable import clause: {clause[:60]!r}")
    return default, namespace, tuple(named), has_braces


def parse_imports(text: str) -> tuple[list[ImportStatement], list[str]]:
    """The file's top-level import statements, and the ones refused (by their
    first line). Raises :class:`FrontendImportError` when the file cannot be
    lexed at all."""
    spans = _non_code_spans(text)
    statements: list[ImportStatement] = []
    refused: list[str] = []
    for m in _IMPORT.finditer(text):
        if _inside(spans, m.start()):
            continue  # an "import" inside a comment or template literal
        line_end = text.find("\n", m.start())
        first_line = text[m.start() : len(text) if line_end < 0 else line_end]
        # Comments inside the statement: a "// ..." on a line of a multi-line
        # import is blanked before parsing (names keep their own comments);
        # a block comment, or one before the clause, refuses the statement.
        a, b = m.start("clause"), m.end("clause")
        inner = [(s, e) for s, e in spans if s < m.end() and e > m.start()]
        clause = list(m.group("clause"))
        refuse = False
        for s, e in inner:
            if text.startswith("/*", s) or s < a or e > b:
                refuse = True
                break
            for k in range(s, e):
                clause[k - a] = " "
        try:
            if refuse:
                raise FrontendImportError("a comment the rewrite cannot keep")
            default, namespace, named, has_braces = _parse_clause("".join(clause))
        except FrontendImportError:
            refused.append(first_line.strip()[:120])
            continue
        statements.append(
            ImportStatement(
                start=m.start(),
                end=m.end(),
                type_only=bool(m.group("type")),
                default=default,
                namespace=namespace,
                named=named,
                has_braces=has_braces,
                module=m.group("module"),
                quote=m.group("q"),
                semicolon=bool(m.group("semi")),
            )
        )
    return statements, refused


def _mentions(text: str, name: str) -> int:
    return len(re.findall(rf"(?<![\w$]){re.escape(name)}(?![\w$])", text))


def unused_bindings(text: str) -> dict[int, tuple[str, ...]]:
    """Unused bindings by the start offset of their import statement: a name
    appearing nowhere in the file outside its own import statement."""
    statements, _refused = parse_imports(text)
    result: dict[int, tuple[str, ...]] = {}
    for stmt in statements:
        outside = text[: stmt.start] + text[stmt.end :]
        dead = tuple(
            name
            for name in stmt.locals
            if name not in KEPT_NAMES and _mentions(outside, name) == 0
        )
        if dead:
            result[stmt.start] = dead
    return result


# --------------------------------------------------------------------------- #
# The rewrite
# --------------------------------------------------------------------------- #
def _render(stmt: ImportStatement, keep: set[str]) -> str:
    """A single-line import with only *keep*'s bindings."""
    default = stmt.default if stmt.default in keep else None
    namespace = stmt.namespace if stmt.namespace in keep else None
    named = [spec.text for spec in stmt.named if spec.local in keep]
    parts: list[str] = []
    if default:
        parts.append(default)
    if namespace:
        parts.append(f"* as {namespace}")
    if named:
        parts.append("{ " + ", ".join(named) + " }")
    head = "import type " if stmt.type_only else "import "
    semi = ";" if stmt.semicolon else ""
    return f"{head}{', '.join(parts)} from {stmt.quote}{stmt.module}{stmt.quote}{semi}"


def _emptied(stmt: ImportStatement, suffix: str) -> Optional[str]:
    """What an import with no surviving binding becomes: nothing where the
    compiler would drop it anyway, a side-effect import where it would not."""
    all_type = stmt.type_only or (
        stmt.named
        and not stmt.default
        and not stmt.namespace
        and all(spec.type_only for spec in stmt.named)
    )
    if all_type or suffix in TYPESCRIPT_SUFFIXES:
        return None
    semi = ";" if stmt.semicolon else ""
    return f"import {stmt.quote}{stmt.module}{stmt.quote}{semi}"


def remove_unused_frontend_imports(text: str, *, suffix: str) -> FrontendImportRepair:
    """Remove the unused imports :func:`unused_bindings` reports; refuse the
    rest. The result must re-parse to exactly the kept bindings."""
    if suffix not in FRONTEND_SUFFIXES:
        raise FrontendImportError(f"not a frontend source file: {suffix}")
    statements, _refused = parse_imports(text)
    dead_by_start = unused_bindings(text)
    pieces: list[str] = []
    cursor = 0
    removed: list[str] = []
    skipped: list[str] = []
    for stmt in statements:
        dead = set(dead_by_start.get(stmt.start, ()))
        if not dead:
            continue
        original = text[stmt.start : stmt.end]
        keep = [name for name in stmt.locals if name not in dead]
        if "\n" not in original:
            replacement: Optional[str] = (
                _render(stmt, set(keep)) if keep else _emptied(stmt, suffix)
            )
            end = stmt.end
            if replacement is None:
                # Drop the statement and its line break.
                if text.startswith("\r\n", end):
                    end += 2
                elif text.startswith("\n", end):
                    end += 1
                replacement = ""
            pieces.append(text[cursor : stmt.start])
            pieces.append(replacement)
            cursor = end
            removed.extend(sorted(dead))
            continue
        # Multi-line: remove only lines holding exactly one dead named specifier.
        lines = original.split("\n")
        kept_lines: list[str] = []
        took: list[str] = []
        for line in lines:
            m = re.match(
                rf"^\s*(?:type\s+)?(?:{_IDENT}|'[^']*'|\"[^\"]*\")(?:\s+as\s+({_IDENT}))?\s*,?\s*\r?$",
                line,
            )
            name = None
            if m:
                bare = re.sub(r",?\s*\r?$", "", line.strip())
                name = re.split(r"\s+as\s+", bare)[-1].replace("type ", "").strip()
            if name and name in dead:
                took.append(name)
                continue
            kept_lines.append(line)
        refused_here = dead - set(took)
        skipped.extend(sorted(refused_here))
        if not took:
            continue
        if not keep:
            replacement = _emptied(stmt, suffix)
            end = stmt.end
            if replacement is None:
                if text.startswith("\r\n", end):
                    end += 2
                elif text.startswith("\n", end):
                    end += 1
                replacement = ""
            pieces.append(text[cursor : stmt.start])
            pieces.append(replacement)
            cursor = end
        else:
            pieces.append(text[cursor : stmt.start])
            pieces.append("\n".join(kept_lines))
            cursor = stmt.end
        removed.extend(sorted(took))
    pieces.append(text[cursor:])
    result = "".join(pieces)
    if removed:
        _verify(text, result, removed=set(removed))
    return FrontendImportRepair(
        content=result,
        removed=tuple(sorted(set(removed))),
        skipped=tuple(sorted(set(skipped))),
    )


def _verify(before: str, after: str, *, removed: set[str]) -> None:
    """Exactly the removed bindings are gone, every other binding survives,
    and the code outside the import statements is unchanged."""
    old, _ = parse_imports(before)
    new, _ = parse_imports(after)
    old_names = {name for stmt in old for name in stmt.locals}
    new_names = {name for stmt in new for name in stmt.locals}
    if old_names - new_names != removed or new_names - old_names:
        raise FrontendImportError(
            "the rewrite did not remove exactly the unused bindings; nothing written"
        )

    def body(text: str, stmts: list[ImportStatement]) -> str:
        out, cursor = [], 0
        for stmt in stmts:
            out.append(text[cursor : stmt.start])
            cursor = stmt.end
        out.append(text[cursor:])
        return re.sub(
            r"^import\s+['\"][^'\"\r\n]+['\"];?\s*$", "", "".join(out), flags=re.M
        ).strip()

    if body(before, old).split() != body(after, new).split():
        raise FrontendImportError(
            "the rewrite changed code outside its import statements; nothing written"
        )


# --------------------------------------------------------------------------- #
# Which files
# --------------------------------------------------------------------------- #
def frontend_files(project_root: Path) -> list[Path]:
    """The frontend source files under ``frontend/src``, never generated or
    vendored code, never declaration files."""
    root = project_root / FRONTEND_SOURCE_ROOT
    if not root.is_dir():
        return []
    found: list[Path] = []
    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(
            d
            for d in directories
            if d not in {"node_modules", "dist", "build", "coverage"}
            and not d.startswith(".")
        )
        for name in sorted(files):
            if name.endswith(".d.ts") or not name.endswith(FRONTEND_SUFFIXES):
                continue
            found.append(Path(current) / name)
    return found


__all__ = [
    "FRONTEND_SOURCE_ROOT",
    "FRONTEND_SUFFIXES",
    "FrontendImportError",
    "FrontendImportRepair",
    "frontend_files",
    "parse_imports",
    "remove_unused_frontend_imports",
    "unused_bindings",
]
