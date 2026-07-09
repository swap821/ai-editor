"""Local-only symbol RepoMap built over Project Passport evidence.

The map is intentionally advisory: it can suggest files and explain symbol
relationships, but it cannot promote memory, widen worker scope, call cloud
providers, or authorize writes.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import re
from typing import Any, Iterable, Optional

from aios.memory.project_passport import RepoScanLimits, harvest_project_passport
from aios.runtime.contracts import MissionContract
from aios.security.secret_scanner import scan_and_redact


_IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".next",
    "dist",
    "build",
    "coverage",
}
_SAFE_ENV_EXAMPLES = {".env.example", ".env.sample", ".env.template"}
_SECRET_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".npmrc",
    ".pypirc",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}
_SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".crt", ".cer"}
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")


@dataclass(frozen=True)
class SymbolRepoMapLimits:
    max_files: int = 500
    max_depth: int = 8
    max_file_bytes: int = 64_000
    max_symbols: int = 500


@dataclass(frozen=True)
class SymbolNode:
    symbol_id: str
    module: str
    name: str
    kind: str
    file: str
    line: int
    rank: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbolId": self.symbol_id,
            "module": self.module,
            "name": self.name,
            "kind": self.kind,
            "file": self.file,
            "line": self.line,
            "rank": round(self.rank, 6),
        }


@dataclass(frozen=True)
class ImportEdge:
    source: str
    target: str
    kind: str = "import"

    def as_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class ScopeHints:
    recommended_files: list[str]
    out_of_scope_matches: list[str]
    rationale: list[str]
    authority: str = "proposal/evidence"
    can_widen_scope: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "authority": self.authority,
            "canWidenScope": self.can_widen_scope,
            "recommendedFiles": self.recommended_files,
            "outOfScopeMatches": self.out_of_scope_matches,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class SymbolRepoMap:
    root: str
    generated_at: str
    project_passport: dict[str, Any]
    symbols: list[SymbolNode]
    edges: list[ImportEdge]
    evidence_files: list[str]
    skipped_files: list[str]
    activation: str = "proposal/evidence"
    trusted_memory_activated: bool = False
    local_only: bool = True
    cloud_calls: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "generatedAt": self.generated_at,
            "activation": self.activation,
            "trustedMemoryActivated": self.trusted_memory_activated,
            "localOnly": self.local_only,
            "cloudCalls": self.cloud_calls,
            "projectPassport": self.project_passport,
            "symbols": [symbol.as_dict() for symbol in self.symbols],
            "edges": [edge.as_dict() for edge in self.edges],
            "evidenceFiles": self.evidence_files,
            "skippedFiles": self.skipped_files,
        }


def scan_symbol_repo_map(
    root: Path | str,
    *,
    limits: Optional[SymbolRepoMapLimits] = None,
) -> SymbolRepoMap:
    """Scan Python symbols/imports under *root* as proposal/evidence only."""
    resolved = Path(root).resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise FileNotFoundError(f"project root does not exist or is not a directory: {resolved}")

    scan_limits = limits or SymbolRepoMapLimits()
    passport = harvest_project_passport(
        resolved,
        limits=RepoScanLimits(
            max_files=scan_limits.max_files,
            max_depth=scan_limits.max_depth,
            max_file_bytes=scan_limits.max_file_bytes,
        ),
    )
    files, skipped = _iter_python_files(resolved, scan_limits)
    parsed = [_parse_python_file(resolved, path, scan_limits) for path in files]
    symbols = _rank_symbols([symbol for item in parsed for symbol in item.symbols])
    edges = _dedupe_edges(edge for item in parsed for edge in item.edges)

    if len(symbols) > scan_limits.max_symbols:
        symbols = symbols[: scan_limits.max_symbols]

    return SymbolRepoMap(
        root=str(resolved),
        generated_at=datetime.now(timezone.utc).isoformat(),
        project_passport=passport.as_dict(),
        symbols=symbols,
        edges=edges,
        evidence_files=sorted(item.rel_path for item in parsed if item.readable),
        skipped_files=sorted(skipped + [item.rel_path for item in parsed if not item.readable]),
    )


def query_symbols(repo_map: SymbolRepoMap, query: str, *, limit: int = 10) -> list[SymbolNode]:
    """Return deterministic symbol matches for a human/worker query string."""
    terms = _query_terms(query)
    if not terms:
        return repo_map.symbols[:limit]

    scored: list[tuple[float, SymbolNode]] = []
    for symbol in repo_map.symbols:
        score = _symbol_match_score(symbol, terms)
        if score > 0:
            scored.append((score, symbol))

    scored.sort(key=lambda item: (-item[0], -item[1].rank, item[1].symbol_id))
    return [symbol for _, symbol in scored[:limit]]


def scope_hints_for_contract(
    repo_map: SymbolRepoMap,
    contract: MissionContract,
    *,
    limit: int = 10,
) -> ScopeHints:
    """Suggest in-scope files without expanding the worker contract."""
    allowed = {_normalize_contract_path(path) for path in contract.allowed_files}
    matches = query_symbols(repo_map, contract.goal, limit=limit)
    recommended: list[str] = []
    out_of_scope: list[str] = []

    for symbol in matches:
        rel = _normalize_contract_path(symbol.file)
        if rel in allowed:
            recommended.append(rel)
        else:
            out_of_scope.append(rel)

    recommended = _dedupe(recommended)
    out_of_scope = [path for path in _dedupe(out_of_scope) if path not in recommended]
    rationale = [
        "Symbol matches are advisory evidence only.",
        "Recommended files are restricted to MissionContract.allowed_files.",
    ]
    if out_of_scope:
        rationale.append("Out-of-scope matches require a separate human-approved scope change.")

    return ScopeHints(
        recommended_files=recommended,
        out_of_scope_matches=out_of_scope,
        rationale=rationale,
    )


@dataclass(frozen=True)
class _ParsedFile:
    rel_path: str
    readable: bool
    symbols: list[SymbolNode]
    edges: list[ImportEdge]


def _iter_python_files(root: Path, limits: SymbolRepoMapLimits) -> tuple[list[Path], list[str]]:
    found: list[Path] = []
    skipped: list[str] = []
    for current, dirs, files in os.walk(root, topdown=True):
        current_path = Path(current)
        rel_dir = current_path.relative_to(root)
        depth = 0 if rel_dir == Path(".") else len(rel_dir.parts)
        if depth >= limits.max_depth:
            skipped.extend((rel_dir / name).as_posix() for name in sorted(dirs))
            dirs[:] = []
        else:
            dirs[:] = [
                name
                for name in sorted(dirs)
                if name not in _IGNORED_DIRS and not _is_aios_private_dir(rel_dir / name)
            ]
        for name in sorted(files):
            path = current_path / name
            rel = path.relative_to(root)
            if _is_secret_path(rel) or _is_aios_private_dir(rel.parent):
                continue
            if path.suffix != ".py":
                continue
            found.append(path)
            if len(found) >= limits.max_files:
                return found, skipped
    return found, skipped


def _parse_python_file(root: Path, path: Path, limits: SymbolRepoMapLimits) -> _ParsedFile:
    rel = path.relative_to(root).as_posix()
    try:
        raw = path.read_bytes()
    except OSError:
        return _ParsedFile(rel_path=rel, readable=False, symbols=[], edges=[])
    if b"\x00" in raw:
        return _ParsedFile(rel_path=rel, readable=False, symbols=[], edges=[])
    if len(raw) > limits.max_file_bytes:
        raw = raw[: limits.max_file_bytes]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    text = scan_and_redact(text).scrubbed

    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError:
        return _ParsedFile(rel_path=rel, readable=False, symbols=[], edges=[])

    module = _module_name(rel)
    symbols: list[SymbolNode] = []
    edges: list[ImportEdge] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            symbols.append(_symbol(module, node.name, "class", rel, node.lineno))
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.append(
                        _symbol(
                            module,
                            f"{node.name}.{child.name}",
                            "method",
                            rel,
                            child.lineno,
                        )
                    )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(_symbol(module, node.name, "function", rel, node.lineno))
        elif isinstance(node, ast.Import):
            edges.extend(ImportEdge(source=module, target=alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            target = _import_from_target(module, node)
            if target:
                edges.append(ImportEdge(source=module, target=target))
    return _ParsedFile(rel_path=rel, readable=True, symbols=symbols, edges=edges)


def _symbol(module: str, name: str, kind: str, file: str, line: int) -> SymbolNode:
    return SymbolNode(
        symbol_id=f"{module}:{name}",
        module=module,
        name=name,
        kind=kind,
        file=file,
        line=line,
        rank=0.0,
    )


def _rank_symbols(symbols: list[SymbolNode]) -> list[SymbolNode]:
    module_counts: dict[str, int] = {}
    for symbol in symbols:
        module_counts[symbol.module] = module_counts.get(symbol.module, 0) + 1

    ranked: list[SymbolNode] = []
    for symbol in symbols:
        kind_bonus = {"class": 0.3, "function": 0.2, "method": 0.1}.get(symbol.kind, 0.0)
        rank = float(module_counts.get(symbol.module, 0)) + kind_bonus
        ranked.append(
            SymbolNode(
                symbol_id=symbol.symbol_id,
                module=symbol.module,
                name=symbol.name,
                kind=symbol.kind,
                file=symbol.file,
                line=symbol.line,
                rank=rank,
            )
        )
    ranked.sort(key=lambda symbol: (-symbol.rank, symbol.symbol_id))
    return ranked


def _dedupe_edges(edges: Iterable[ImportEdge]) -> list[ImportEdge]:
    unique: dict[tuple[str, str, str], ImportEdge] = {}
    for edge in edges:
        unique[(edge.source, edge.target, edge.kind)] = edge
    return [unique[key] for key in sorted(unique)]


def _module_name(rel_path: str) -> str:
    path = Path(rel_path)
    parts = list(path.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else "__init__"


def _import_from_target(module: str, node: ast.ImportFrom) -> str:
    if node.level <= 0:
        return node.module or ""
    package_parts = module.split(".")[:-1]
    if node.level > 1:
        package_parts = package_parts[: 1 - node.level]
    target_parts = package_parts[:]
    if node.module:
        target_parts.extend(node.module.split("."))
    elif node.names:
        target_parts.append(node.names[0].name)
    return ".".join(part for part in target_parts if part)


def _symbol_match_score(symbol: SymbolNode, terms: set[str]) -> float:
    searchable = {
        "symbol": symbol.symbol_id.lower(),
        "name": symbol.name.lower(),
        "name_words": symbol.name.replace("_", " ").replace(".", " ").lower(),
        "module": symbol.module.lower(),
        "file": symbol.file.lower(),
    }
    score = 0.0
    for term in terms:
        if term == searchable["name"]:
            score += 8.0
        if term in searchable["name"]:
            score += 5.0
        if term in searchable["name_words"]:
            score += 4.0
        if term in searchable["symbol"]:
            score += 2.0
        if term in searchable["module"] or term in searchable["file"]:
            score += 1.0
    return score


def _query_terms(query: str) -> set[str]:
    terms: set[str] = set()
    for match in _WORD_RE.finditer(query.lower()):
        value = match.group(0)
        terms.add(value)
        terms.update(part for part in value.split("_") if len(part) >= 3)
    return terms


def _normalize_contract_path(path: str) -> str:
    return Path(path).as_posix().lstrip("./")


def _is_aios_private_dir(rel: Path) -> bool:
    parts = rel.parts
    return len(parts) >= 2 and parts[0] == ".aios" and parts[1] in {"audit", "memory"}


def _is_secret_path(rel: Path) -> bool:
    name = rel.name
    lower = name.lower()
    if lower in _SAFE_ENV_EXAMPLES:
        return False
    return lower in _SECRET_FILENAMES or rel.suffix.lower() in _SECRET_SUFFIXES


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


__all__ = [
    "ImportEdge",
    "ScopeHints",
    "SymbolNode",
    "SymbolRepoMap",
    "SymbolRepoMapLimits",
    "query_symbols",
    "scan_symbol_repo_map",
    "scope_hints_for_contract",
]
