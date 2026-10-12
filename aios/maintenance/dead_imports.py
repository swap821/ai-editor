"""The one definition of a dead import -- standard library only.

Two callers, one rule: the vulture (`vulture_sanitation`) REPORTS dead
imports, and the executor's REMOVE_DEAD_IMPORTS_V1 (`repair_operations`)
REMOVES them. If the rule lived twice, the repair could delete what the scan
never called dead. This module imports only the standard library; through the
``aios.maintenance`` package it loads nothing third-party beyond what the
executor image (requirements-executor.txt) already installs.

An import is dead when its bound name is never read in its own file AND it is
not exported on purpose:

* a noqa directive covering F401 on the alias's line or the statement's first
  line (a deliberate re-export);
* listed in a literal ``__all__``;
* taken FROM this module by another file of the project -- ``from mod import
  name``, a ``"mod.name"`` monkeypatch target, or ``alias.name`` /
  ``setattr(alias, "name", ...)`` through ``import mod as alias`` or
  ``from pkg import mod`` (`ExternalImportIndex`).

Underscore names and ``from __future__`` directives are never reported.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Callable

_NOQA = re.compile(r"#\s*noqa(?::\s*(?P<codes>[A-Z0-9, ]+))?", re.IGNORECASE)
SKIP_DIRS = frozenset({"__pycache__", "node_modules", "venv", ".venv"})


def bound_name(node: ast.Import | ast.ImportFrom, alias: ast.alias) -> str:
    """The name an import alias binds in the importing module."""
    if isinstance(node, ast.Import):
        return alias.asname or alias.name.split(".", 1)[0]
    return alias.asname or alias.name


def noqa_f401(lines: list[str], lineno: int) -> bool:
    """True when line *lineno* (1-based) carries a bare noqa or one naming F401."""
    if not 1 <= lineno <= len(lines):
        return False
    match = _NOQA.search(lines[lineno - 1])
    if match is None:
        return False
    codes = match.group("codes")
    return codes is None or "F401" in codes.upper()


def dunder_all(tree: ast.Module) -> tuple[str, ...]:
    """Names a module lists in a literal ``__all__`` -- exported on purpose."""
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
            continue
        if isinstance(node.value, (ast.List, ast.Tuple)):
            names.extend(
                e.value
                for e in node.value.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            )
    return tuple(names)


def find_dead_imports(
    tree: ast.Module, lines: list[str], *, external_names: frozenset[str] = frozenset()
) -> dict[str, int]:
    """``{dead name: line of its import}`` for a parsed module."""
    imported: dict[str, int] = {}
    exported: set[str] = set(dunder_all(tree)) | set(external_names)
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module == "__future__":
                continue  # a compiler directive, not a binding to use
            for alias in node.names:
                if alias.name == "*":
                    continue
                name = bound_name(node, alias)
                imported.setdefault(name, node.lineno)
                alias_line = getattr(alias, "lineno", node.lineno)
                if noqa_f401(lines, alias_line) or noqa_f401(lines, node.lineno):
                    exported.add(name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
    return {
        name: line
        for name, line in imported.items()
        if name not in used and name not in exported and not name.startswith("_")
    }


def attribute_pairs(tree: ast.AST, aliases: set[str]) -> set[tuple[str, str]]:
    """``(alias, name)`` for ``alias.name`` reads and
    ``setattr/getattr/hasattr/delattr(alias, "name", ...)`` -- one walk."""
    found: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in aliases
        ):
            found.add((node.value.id, node.attr))
        elif isinstance(node, ast.Call) and len(node.args) >= 2:
            func = node.func
            fname = (
                func.attr
                if isinstance(func, ast.Attribute)
                else getattr(func, "id", "")
            )
            first, second = node.args[0], node.args[1]
            if (
                fname in ("setattr", "getattr", "hasattr", "delattr")
                and isinstance(first, ast.Name)
                and first.id in aliases
                and isinstance(second, ast.Constant)
                and isinstance(second.value, str)
            ):
                found.add((first.id, second.value))
    return found


def attributes_used_through(tree: ast.AST, aliases: set[str]) -> set[str]:
    """The names read through any of *aliases* (see `attribute_pairs`)."""
    return {name for _alias, name in attribute_pairs(tree, aliases)}


def python_files(root: Path) -> list[Path]:
    """The project's Python sources, sorted; dot-directories and caches skipped."""
    root = root.resolve()
    return [
        path
        for path in sorted(root.rglob("*.py"))
        if not any(
            part.startswith(".") or part in SKIP_DIRS
            for part in path.relative_to(root).parts
        )
    ]


_DOTTED = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+")


def _module_aliases(tree: ast.AST) -> dict[str, str]:
    """``{local alias: module}`` for ``import a.b as x`` and ``from a import b``.

    ``from a import b`` binds a module only when ``a.b`` is one; the index
    cannot tell, so it records the candidate and lets a lookup for a module
    that does not exist simply never match.
    """
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    aliases[a.asname] = a.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for a in node.names:
                if a.name != "*":
                    aliases[a.asname or a.name] = f"{node.module}.{a.name}"
    return aliases


class ExternalImportIndex:
    """Which names other files in a project take FROM a given module.

    Read-only, built in ONE pass over the project: each source is parsed once
    into ``{module: {name: files that take it}}``. (The first version re-read
    every file for every file scanned -- 457 s for GAGOS's 1,074 files on
    2026-10-12 -- too slow for a rescan with a deadline.) A name counts as
    taken when another file has ``from mod import name``, reaches it through a
    module alias (``alias.name``, ``setattr(alias, "name", ...)``), or spells
    ``mod.name`` anywhere in its text (a monkeypatch target string).
    """

    def __init__(
        self,
        root: Path,
        *,
        max_files: int | None = None,
        read: Callable[[Path], str] | None = None,
    ) -> None:
        self.root = root.resolve()
        self.max_files = max_files
        # A bounded scan passes its context's reader, so the contract's file,
        # byte and deadline limits hold for the index's reads too.
        self._read = read
        self._taken: dict[str, dict[str, set[Path]]] | None = None
        # module -> files that import or name it, in any form.
        self._importers: dict[str, set[Path]] = {}
        # modules whose namespace another file consumes in a way no static
        # rule can follow: a star import of it, or getattr/setattr/hasattr/
        # delattr on an alias of it with a COMPUTED name, vars(alias),
        # alias.__dict__. For these, no import can be called dead.
        self._opaque: set[str] = set()
        self.files_read = 0

    def _sources(self):
        for path in python_files(self.root):
            self.files_read += 1
            if self.max_files is not None and self.files_read > self.max_files:
                raise IndexBoundExceeded(
                    f"max_files exceeded: the project has more than {self.max_files}"
                    " Python files to index"
                )
            if self._read is not None:
                yield path, self._read(path)
                continue
            try:
                yield path, path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

    def _build(self) -> dict[str, dict[str, set[Path]]]:
        taken: dict[str, dict[str, set[Path]]] = {}

        def add(module: str, name: str, source: Path) -> None:
            taken.setdefault(module, {}).setdefault(name, set()).add(source)

        def imports(module: str, source: Path) -> None:
            self._importers.setdefault(module, set()).add(source)

        for source, text in self._sources():
            # Text: every contiguous run inside a dotted chain, so
            # "x.aios.api.main.sse" records ("aios.api.main", "sse") too.
            for chain in set(_DOTTED.findall(text)):
                parts = chain.split(".")
                for start in range(len(parts) - 1):
                    for end in range(start + 1, len(parts)):
                        add(".".join(parts[start:end]), parts[end], source)
                        imports(".".join(parts[start : end + 1]), source)
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            aliases = _module_aliases(tree)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    imports(node.module, source)
                    for a in node.names:
                        if a.name == "*":
                            self._opaque.add(node.module)
                        else:
                            add(node.module, a.name, source)
                            imports(f"{node.module}.{a.name}", source)
                elif isinstance(node, ast.Import):
                    for a in node.names:
                        imports(a.name, source)
                elif aliases:
                    module = _dynamic_namespace_use(node, aliases)
                    if module is not None:
                        self._opaque.add(module)
            if aliases:
                for alias, name in attribute_pairs(tree, set(aliases)):
                    add(aliases[alias], name, source)
        return taken

    def module_name(self, path: Path) -> str | None:
        try:
            rel = path.resolve().relative_to(self.root)
        except ValueError:
            return None
        parts = list(rel.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) or None

    def taken(self) -> dict[str, dict[str, set[Path]]]:
        """``{module: {name: files that take it}}`` for the project, built once."""
        if self._taken is None:
            self._taken = self._build()
        return self._taken

    def names_imported_from(self, path: Path) -> frozenset[str]:
        module = self.module_name(path)
        if module is None:
            return frozenset()
        own = path.resolve()
        return frozenset(
            name
            for name, sources in self.taken().get(module, {}).items()
            if any(s != own for s in sources)
        )

    def files_importing(self, path: Path) -> frozenset[Path]:
        """Other files that import or name the module at *path*, in any form."""
        module = self.module_name(path)
        if module is None:
            return frozenset()
        self.taken()
        own = path.resolve()
        return frozenset(s for s in self._importers.get(module, ()) if s != own)

    def is_opaque(self, path: Path) -> bool:
        """Another file consumes this module's namespace dynamically."""
        module = self.module_name(path)
        self.taken()
        return module is not None and module in self._opaque

    def dead_in(self, path: Path, text: str) -> dict[str, int]:
        """THE judgement, for every caller: ``{dead name: line}`` in *text*
        (the file at *path*), against the whole project. Raises SyntaxError."""
        tree = ast.parse(text)
        if self.is_opaque(path):
            return {}
        return find_dead_imports(
            tree, text.splitlines(), external_names=self.names_imported_from(path)
        )


def _dynamic_namespace_use(node: ast.AST, aliases: dict[str, str]) -> str | None:
    """The module whose namespace *node* consumes dynamically, if any."""
    if isinstance(node, ast.Call) and node.args:
        func = node.func
        fname = (
            func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        )
        first = node.args[0]
        if not (isinstance(first, ast.Name) and first.id in aliases):
            return None
        if fname == "vars":
            return aliases[first.id]
        if (
            fname in ("getattr", "setattr", "hasattr", "delattr")
            and len(node.args) >= 2
        ):
            second = node.args[1]
            if not (isinstance(second, ast.Constant) and isinstance(second.value, str)):
                return aliases[first.id]
    elif (
        isinstance(node, ast.Attribute)
        and node.attr == "__dict__"
        and isinstance(node.value, ast.Name)
        and node.value.id in aliases
    ):
        return aliases[node.value.id]
    return None


class IndexBoundExceeded(RuntimeError):
    """The project is larger than the scan's bounds allow; no partial answer."""


def dead_imports_in(
    content: str, *, path: Path, project_root: Path | None = None
) -> dict[str, int]:
    """Dead imports of the module *content* (the file at *path*). Raises SyntaxError."""
    if project_root is None:
        tree = ast.parse(content)
        return find_dead_imports(tree, content.splitlines())
    return ExternalImportIndex(project_root).dead_in(path, content)
