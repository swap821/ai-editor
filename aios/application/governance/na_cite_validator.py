"""Validate N/A-BY-DESIGN code cites in the organ ledger.

Phase 3 absolute: every yellow ``N/A-BY-DESIGN`` blocker must carry a
resolvable ``path::symbol`` cite.  This module is the mechanical gate that
prevents silent regression to hand-wavy blockers or broken symbol paths.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from aios.application.governance.organ_ledger import _default_ledger_path, load_ledger
from aios.domain.governance.contracts import OrganRecord

_PY_CITE_RE = re.compile(r"([\w./\\-]+\.py)::([\w]+(?:\.[\w*]+)?)")
_FE_CITE_RE = re.compile(
    r"(frontend/[\w./\-]+\.(?:tsx?|jsx?))::([\w]+(?:\.[\w]+)?)"
)
_TS_CLASS_RE = re.compile(r"\b(?:export\s+)?class\s+(\w+)\b")
_TS_FN_RE = re.compile(r"\b(?:export\s+)?(?:async\s+)?function\s+(\w+)\b")
_TS_METHOD_RE = re.compile(r"\b(\w+)\s*\([^)]*\)\s*(?::\s*\w+)?\s*\{")


def _extract_cites_from_blocker(text: str) -> list[tuple[str, str]]:
    """Return (rel_path, symbol) pairs from one blocker string."""
    cites: list[tuple[str, str]] = []
    for match in _PY_CITE_RE.finditer(text):
        cites.append((match.group(1).replace("\\", "/"), match.group(2)))
    for match in _FE_CITE_RE.finditer(text):
        cites.append((match.group(1).replace("\\", "/"), match.group(2)))
    return cites


def _python_class_names(tree: ast.Module) -> set[str]:
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }


def _python_module_functions(tree: ast.Module) -> set[str]:
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _python_class_methods(tree: ast.Module, class_name: str) -> set[str]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                child.name
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    return set()


def _resolve_python_symbol(file_path: Path, symbol: str) -> str | None:
    """Return a violation message, or None when the symbol resolves."""
    try:
        source = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"cannot read {file_path}: {exc}"

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as exc:
        return f"cannot parse {file_path}: {exc}"

    if not isinstance(tree, ast.Module):
        return f"unexpected AST root in {file_path}"

    if symbol.endswith(".*"):
        class_name = symbol[:-2]
        if class_name in _python_class_names(tree):
            return None
        return f"class {class_name!r} not found in {file_path}"

    if "." in symbol:
        class_name, method_name = symbol.rsplit(".", 1)
        if class_name not in _python_class_names(tree):
            return f"class {class_name!r} not found in {file_path}"
        methods = _python_class_methods(tree, class_name)
        if method_name.endswith("*"):
            prefix = method_name[:-1]
            if not any(method.startswith(prefix) for method in methods):
                return (
                    f"no method matching {symbol!r} in {file_path} "
                    f"(expected prefix {prefix!r})"
                )
            return None
        if method_name not in methods:
            return f"method {symbol!r} not found in {file_path}"
        return None

    if symbol in _python_class_names(tree):
        return None
    if symbol in _python_module_functions(tree):
        return None
    return f"symbol {symbol!r} not found in {file_path}"


def _resolve_frontend_symbol(file_path: Path, symbol: str) -> str | None:
    """Return a violation message, or None when the symbol resolves."""
    try:
        source = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"cannot read {file_path}: {exc}"

    classes = set(_TS_CLASS_RE.findall(source))
    functions = set(_TS_FN_RE.findall(source))

    if "." in symbol:
        class_name, method_name = symbol.rsplit(".", 1)
        if class_name not in classes:
            return f"class {class_name!r} not found in {file_path}"
        if method_name not in _TS_METHOD_RE.findall(source):
            return f"method {symbol!r} not found in {file_path}"
        return None

    if symbol in classes or symbol in functions:
        return None
    return f"symbol {symbol!r} not found in {file_path}"


def validate_na_cites(
    records: tuple[OrganRecord, ...] | list[OrganRecord],
    *,
    repo_root: str | Path,
) -> tuple[str, ...]:
    """Return violation strings for unresolvable N/A-BY-DESIGN cites."""
    root = Path(repo_root).resolve()
    violations: list[str] = []

    for record in records:
        for blocker in record.known_blockers:
            if "N/A-BY-DESIGN" not in blocker:
                continue
            for rel_path, symbol in _extract_cites_from_blocker(blocker):
                file_path = root / rel_path
                if not file_path.exists():
                    violations.append(
                        f"organ_id {record.organ_id} ({record.name}) N/A-BY-DESIGN "
                        f"cite {rel_path}::{symbol} — file does not exist"
                    )
                    continue
                if rel_path.endswith(".py"):
                    issue = _resolve_python_symbol(file_path, symbol)
                else:
                    issue = _resolve_frontend_symbol(file_path, symbol)
                if issue is not None:
                    violations.append(
                        f"organ_id {record.organ_id} ({record.name}) N/A-BY-DESIGN "
                        f"cite {rel_path}::{symbol} — {issue}"
                    )

    return tuple(violations)


def validate_shipped_na_cites(repo_root: str | Path | None = None) -> tuple[str, ...]:
    """Validate N/A-BY-DESIGN cites in the shipped ledger."""
    root = Path(repo_root or Path(__file__).resolve().parents[3]).resolve()
    records = load_ledger(_default_ledger_path(root))
    return validate_na_cites(records, repo_root=root)


__all__ = [
    "validate_na_cites",
    "validate_shipped_na_cites",
    "_extract_cites_from_blocker",
]
