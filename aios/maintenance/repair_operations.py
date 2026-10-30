"""Deterministic repair operations the executor may run inside a staged workspace.

A maintenance repair never lets a model write code. The worker PROPOSES an
operation by id; the executor runs only an operation registered here, on the
staged copy, and the result is verified by a rescan before anything is
promoted. Each operation decides what to change from the workspace itself, so
a forged or confused proposal cannot widen it.

``REMOVE_DEAD_IMPORTS_V1`` (added 2026-10-12 for GAGOS's first self-maintenance
mission, the vulture as scavenger) removes the imports the vulture's own rule
calls dead -- unused, not a noqa/``__all__`` re-export, not imported or patched
from this module anywhere in the project -- and nothing else. It rewrites only
what it can rewrite safely and refuses the rest:

* a single-line import is rebuilt from its surviving names, trailing comment
  kept;
* in a multi-line import, only lines holding exactly one dead name are
  deleted, so the surviving names keep their own comments;
* a statement sharing its lines with other code, or a multi-line import whose
  dead name shares a line with a live one, is left untouched and reported.

The result must parse, and exactly the removed names -- no others -- must be
gone, or the operation refuses and writes nothing.

``REMOVE_UNUSED_FRONTEND_IMPORTS_V1`` (added 2026-10-30 for GAGOS's daily
frontend worker) is its frontend twin: the rule and the rewrite are
``aios/maintenance/frontend_imports.py``. An imported binding goes only when its
name appears nowhere else in the file; an import emptied in ``.js``/``.jsx``
becomes a side-effect import, so its module still loads.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from aios.maintenance.dead_imports import bound_name, dead_imports_in

REMOVE_MAINTENANCE_MARKER_V1 = "REMOVE_MAINTENANCE_MARKER_V1"
REMOVE_DEAD_IMPORTS_V1 = "REMOVE_DEAD_IMPORTS_V1"
REMOVE_UNUSED_FRONTEND_IMPORTS_V1 = "REMOVE_UNUSED_FRONTEND_IMPORTS_V1"

#: The operations an executor may run. Anything else is refused.
REGISTERED_REPAIR_OPERATIONS = frozenset(
    {
        REMOVE_MAINTENANCE_MARKER_V1,
        REMOVE_DEAD_IMPORTS_V1,
        REMOVE_UNUSED_FRONTEND_IMPORTS_V1,
    }
)


class RepairRefused(ValueError):
    """The operation would not be safe or did not verify; nothing was written."""


def remove_unused_frontend_imports_in(content: str, *, path: Path) -> str:
    """REMOVE_UNUSED_FRONTEND_IMPORTS_V1 on one file's text: the new text, or
    :class:`RepairRefused` when there is nothing it may remove."""
    from aios.maintenance.frontend_imports import (
        FrontendImportError,
        remove_unused_frontend_imports,
    )

    try:
        result = remove_unused_frontend_imports(content, suffix=path.suffix)
    except FrontendImportError as exc:
        raise RepairRefused(str(exc)) from exc
    if not result.changed:
        raise RepairRefused("no unused frontend import the rule may remove")
    return result.content


@dataclass(frozen=True)
class DeadImportRepair:
    """What REMOVE_DEAD_IMPORTS_V1 decided for one file."""

    content: str
    removed: tuple[str, ...]
    skipped: tuple[str, ...] = field(default=())

    @property
    def changed(self) -> bool:
        return bool(self.removed)


def dead_import_names(
    content: str, *, path: Path, project_root: Path
) -> frozenset[str]:
    """The names the vulture calls dead in *content*, judged against the project.

    The same rule the vulture reports with (aios/maintenance/dead_imports.py),
    not a second copy of it.
    """
    return frozenset(dead_imports_in(content, path=path, project_root=project_root))


_bound = bound_name


def _render(node: ast.Import | ast.ImportFrom, keep: list[ast.alias]) -> str:
    names = ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in keep)
    if isinstance(node, ast.Import):
        return f"import {names}"
    return f"from {'.' * node.level}{node.module or ''} import {names}"


_ONE_ALIAS_LINE = re.compile(r"^\s*([\w.]+)(\s+as\s+(\w+))?\s*,?\s*(#.*)?$")


def _imported_names(tree: ast.AST) -> list[str]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module == "__future__":
                continue
            out.extend(_bound(node, a) for a in node.names if a.name != "*")
    return out


def remove_dead_imports(
    content: str, *, path: Path, project_root: Path
) -> DeadImportRepair:
    """Apply REMOVE_DEAD_IMPORTS_V1 to *content* (the file at *path*)."""
    try:
        tree = ast.parse(content)
    except SyntaxError as exc:
        raise RepairRefused(f"target does not parse: {exc}") from exc
    dead = dead_import_names(content, path=path, project_root=project_root)
    if not dead:
        return DeadImportRepair(content=content, removed=())

    lines = content.splitlines(keepends=True)
    edits: list[tuple[int, int, list[str]]] = []
    removed: list[str] = []
    skipped: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            continue
        pairs = [(a, _bound(node, a)) for a in node.names if a.name != "*"]
        dead_here = [n for _a, n in pairs if n in dead]
        if not dead_here:
            continue
        keep = [a for a, n in pairs if n not in dead]
        start, end = node.lineno - 1, node.end_lineno or node.lineno
        first, last = lines[start], lines[end - 1]
        tail = last[node.end_col_offset :] if node.end_col_offset is not None else ""
        code_only = "".join(lines[start:end]).split("#", 1)[0]
        if (
            first[: node.col_offset].strip()
            or (tail.strip() and not tail.strip().startswith("#"))
            or ";" in code_only
        ):
            skipped.extend(dead_here)
            continue
        if not keep:
            edits.append((start, end, []))
            removed.extend(dead_here)
            continue
        if node.lineno == node.end_lineno:
            newline = first[len(first.rstrip("\r\n")) :] or "\n"
            indent = first[: node.col_offset]
            edits.append(
                (
                    start,
                    end,
                    [indent + _render(node, keep) + tail.rstrip("\r\n") + newline],
                )
            )
            removed.extend(dead_here)
            continue
        # Multi-line: delete only lines that hold exactly one dead name.
        alias_lines: dict[int, list[ast.alias]] = {}
        for alias in node.names:
            alias_lines.setdefault(alias.lineno, []).append(alias)
        deletable = []
        safe = True
        for alias, name in pairs:
            if name not in dead:
                continue
            on_line = alias_lines.get(alias.lineno, [])
            text = lines[alias.lineno - 1]
            if (
                len(on_line) != 1
                or alias.lineno in (node.lineno, node.end_lineno)
                or not _ONE_ALIAS_LINE.match(text.rstrip("\r\n"))
            ):
                safe = False
                break
            deletable.append(alias.lineno - 1)
        if not safe:
            skipped.extend(dead_here)
            continue
        for idx in deletable:
            edits.append((idx, idx + 1, []))
        removed.extend(dead_here)

    if not edits:
        return DeadImportRepair(
            content=content, removed=(), skipped=tuple(sorted(skipped))
        )
    for start, end, replacement in sorted(edits, key=lambda e: e[0], reverse=True):
        lines[start:end] = replacement
    new_content = "".join(lines)

    # Verify: it parses, and exactly the removed names are gone.
    try:
        new_tree = ast.parse(new_content)
    except SyntaxError as exc:
        raise RepairRefused(f"the edited file would not parse: {exc}") from exc
    before = sorted(_imported_names(tree))
    after = sorted(_imported_names(new_tree))
    expected = list(before)
    for name in removed:
        expected.remove(name)
    if after != expected:
        raise RepairRefused(
            "the edit did not remove exactly the dead imports: "
            f"expected to keep {len(expected)} bindings, kept {len(after)}"
        )
    return DeadImportRepair(
        content=new_content,
        removed=tuple(sorted(removed)),
        skipped=tuple(sorted(skipped)),
    )
