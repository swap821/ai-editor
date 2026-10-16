"""Read-only immune/vulture evidence scanner.

This module is deliberately outside ``aios.security``. It can detect and report
dangerous lessons, prompt-injection phrases, unsafe autonomy claims, and secret
material, but every result is proposal/evidence only. It performs no writes,
cloud calls, memory compaction, pheromone decay, policy mutation, or deletion.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Mapping, Pattern

from aios.security import gateway
from aios.security.secret_scanner import scan_and_redact

VultureKind = Literal[
    "security_bypass",
    "approval_bypass",
    "trusted_memory_activation",
    "unsafe_self_modification",
    "secret_material",
    "cognitive_parasite",
    "dead_import",
    "read_error",
]
VultureSeverity = Literal["low", "medium", "high", "critical"]


@dataclass(frozen=True)
class VultureRule:
    kind: VultureKind
    severity: VultureSeverity
    pattern: Pattern[str]
    evidence: str


@dataclass(frozen=True)
class VultureFinding:
    target_id: str
    kind: VultureKind
    severity: VultureSeverity
    excerpt: str
    evidence: tuple[str, ...]
    recommendation: str
    recommended_action: str = "quarantine_proposal"
    authority: str = "proposal/evidence"

    def to_dict(self) -> dict[str, object]:
        return {
            "target_id": self.target_id,
            "kind": self.kind,
            "severity": self.severity,
            "excerpt": self.excerpt,
            "evidence": list(self.evidence),
            "recommendation": self.recommendation,
            "recommended_action": self.recommended_action,
            "authority": self.authority,
        }


@dataclass(frozen=True)
class VultureReport:
    findings: tuple[VultureFinding, ...]
    local_only: bool = True
    writes_performed: bool = False
    cloud_calls: int = 0
    activation: str = "proposal/evidence"

    def to_dict(self) -> dict[str, object]:
        return {
            "activation": self.activation,
            "local_only": self.local_only,
            "writes_performed": self.writes_performed,
            "cloud_calls": self.cloud_calls,
            "findings": [finding.to_dict() for finding in self.findings],
        }


_RULES: tuple[VultureRule, ...] = (
    VultureRule(
        kind="security_bypass",
        severity="critical",
        pattern=re.compile(
            r"\b(ignore\s+all\s+previous\s+instructions|bypass\s+(?:the\s+)?(?:security|gateway|guardrail)|approve\s+red\s+actions?|red\s+actions?\s+(?:can|should|must)\s+auto)",
            re.IGNORECASE,
        ),
        evidence="security bypass or RED auto-approval language",
    ),
    VultureRule(
        kind="approval_bypass",
        severity="high",
        pattern=re.compile(
            r"\b(?:never\s+ask\s+approval|skip\s+human\s+approval|yellow\s+actions?.*(?:auto-run|auto\s+approve|without\s+approval)|auto-run\s+them)\b",
            re.IGNORECASE,
        ),
        evidence="human approval bypass language",
    ),
    VultureRule(
        kind="trusted_memory_activation",
        severity="high",
        pattern=re.compile(
            r"\b(?:trusted\s+memory|activate\s+(?:as\s+)?memory|store\s+.*(?:as|into)\s+trusted)\b",
            re.IGNORECASE,
        ),
        evidence="unreviewed evidence promoted to trusted memory",
    ),
    VultureRule(
        kind="unsafe_self_modification",
        severity="critical",
        pattern=re.compile(
            r"\b(?:self-modif(?:y|ication)|modify\s+the\s+frozen\s+core|frozen\s+core\s+without\s+human\s+review|without\s+human\s+review)\b",
            re.IGNORECASE,
        ),
        evidence="self-modification without the approval chain",
    ),
    VultureRule(
        kind="cognitive_parasite",
        severity="high",
        pattern=re.compile(
            r"\b(?:disable\s+(?:the\s+)?vulture|remove\s+(?:the\s+)?immune\s+system|immune\s+system\s+is\s+(?:waste|unnecessary|expensive)|vulture\s+is\s+(?:waste|unnecessary|expensive)|disable\s+(?:the\s+)?security\s+ganglion)\b",
            re.IGNORECASE,
        ),
        evidence="anti-immune-system language that should not be trusted automatically",
    ),
)

_RECOMMENDATIONS: Mapping[VultureKind, str] = {
    "security_bypass": "Quarantine the lesson/proposal for human review; security gateway remains authoritative.",
    "approval_bypass": "Quarantine and require explicit operator review before reuse.",
    "trusted_memory_activation": "Keep as evidence only until an existing memory authority accepts it.",
    "unsafe_self_modification": "Convert to a proposal and route through controlled self-modification review.",
    "secret_material": "Redact before persistence and review the source for credential exposure.",
    "cognitive_parasite": "Keep as cautionary evidence and require human review before reuse.",
    "dead_import": "Treat as a cleanup proposal; do not remove code without verifier-backed review.",
    "read_error": "Treat unreadable target as incomplete evidence, not as a clean scan.",
}


class VultureScanner:
    """Local-only scanner that emits proposal findings without side effects."""

    def scan_targets(self, targets: Mapping[str, str]) -> VultureReport:
        findings: list[VultureFinding] = []
        for target_id in sorted(targets):
            findings.extend(self._scan_text(target_id, targets[target_id]))
        return VultureReport(findings=tuple(findings))

    def scan_files(
        self,
        paths: Iterable[Path | str],
        *,
        memory_store: object = None,
        pheromone_store: object = None,
        policy_engine: object = None,
    ) -> VultureReport:
        """Read files and scan them without touching supplied mutable systems.

        The subsystem parameters are intentional guardrails for callers: this
        method accepts them so tests and integrations can prove they are not
        invoked by the read-only phase.
        """

        del memory_store, pheromone_store, policy_engine
        targets: dict[str, str] = {}
        findings: list[VultureFinding] = []
        for raw_path in sorted((Path(p) for p in paths), key=lambda p: p.as_posix()):
            try:
                targets[raw_path.as_posix()] = raw_path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
            except OSError as exc:
                findings.append(
                    VultureFinding(
                        target_id=raw_path.as_posix(),
                        kind="read_error",
                        severity="medium",
                        excerpt=_clip(str(exc)),
                        evidence=("local file read failed",),
                        recommendation=_RECOMMENDATIONS["read_error"],
                    )
                )
        findings.extend(self.scan_targets(targets).findings)
        return VultureReport(findings=tuple(findings))

    def scan_code_paths(
        self, paths: Iterable[Path | str], *, importers_root: Path | str | None = None
    ) -> VultureReport:
        """Read Python files and propose local code hygiene findings only.

        This intentionally stops at evidence. It does not edit files, run tests,
        invoke formatters, or quarantine anything.

        *importers_root*: the project the scanned files belong to. When given,
        a name another file takes FROM the scanned module (``from mod import
        name``, or ``"mod.name"`` as a monkeypatch target) is a live re-export,
        not dead -- read-only, by AST and text over that root.
        """

        root = Path(importers_root).resolve() if importers_root is not None else None
        index = _ExternalImportIndex(root) if root is not None else None
        findings: list[VultureFinding] = []
        for raw_path in sorted((Path(p) for p in paths), key=lambda p: p.as_posix()):
            target_id = raw_path.as_posix()
            try:
                payload = raw_path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                findings.append(
                    VultureFinding(
                        target_id=target_id,
                        kind="read_error",
                        severity="medium",
                        excerpt=_clip(str(exc)),
                        evidence=("local file read failed",),
                        recommendation=_RECOMMENDATIONS["read_error"],
                    )
                )
                continue

            findings.extend(self._scan_text(target_id, payload))
            if raw_path.suffix == ".py":
                external = (
                    index.names_imported_from(raw_path)
                    if index is not None
                    else frozenset()
                )
                findings.extend(
                    self._scan_python_ast(target_id, payload, external_names=external)
                )

        return VultureReport(findings=tuple(findings))

    def _scan_text(self, target_id: str, payload: str) -> tuple[VultureFinding, ...]:
        if not payload:
            return ()

        redaction = scan_and_redact(payload)
        scrubbed = redaction.scrubbed
        findings: list[VultureFinding] = []
        if redaction.detected:
            findings.append(
                VultureFinding(
                    target_id=target_id,
                    kind="secret_material",
                    severity="critical",
                    excerpt=_clip(scrubbed),
                    evidence=redaction.findings,
                    recommendation=_RECOMMENDATIONS["secret_material"],
                )
            )

        for rule in _RULES:
            match = rule.pattern.search(scrubbed)
            if match is None:
                continue
            findings.append(
                VultureFinding(
                    target_id=target_id,
                    kind=rule.kind,
                    severity=rule.severity,
                    excerpt=_excerpt(scrubbed, match.start(), match.end()),
                    evidence=(rule.evidence,),
                    recommendation=_RECOMMENDATIONS[rule.kind],
                )
            )

        classification = gateway.classify(scrubbed)
        if (
            classification.zone is gateway.Zone.RED
            and "Prompt-injection pattern" in classification.reason
            and not any(f.kind == "security_bypass" for f in findings)
        ):
            findings.append(
                VultureFinding(
                    target_id=target_id,
                    kind="security_bypass",
                    severity="critical",
                    excerpt=_clip(scrubbed),
                    evidence=(classification.reason,),
                    recommendation=_RECOMMENDATIONS["security_bypass"],
                )
            )

        return tuple(findings)

    def _scan_python_ast(
        self,
        target_id: str,
        payload: str,
        *,
        external_names: frozenset[str] = frozenset(),
    ) -> tuple[VultureFinding, ...]:
        try:
            tree = ast.parse(payload)
        except SyntaxError as exc:
            return (
                VultureFinding(
                    target_id=target_id,
                    kind="read_error",
                    severity="low",
                    excerpt=_clip(str(exc)),
                    evidence=("local Python AST parse failed",),
                    recommendation=_RECOMMENDATIONS["read_error"],
                ),
            )

        lines = payload.splitlines()
        imported: dict[str, int] = {}
        exported: set[str] = set(_dunder_all(tree)) | set(external_names)
        used_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if alias.name == "*" or (
                        isinstance(node, ast.ImportFrom) and node.module == "__future__"
                    ):
                        continue  # a compiler directive, not a binding to use
                    if isinstance(node, ast.Import):
                        name = alias.asname or alias.name.split(".", 1)[0]
                    else:
                        name = alias.asname or alias.name
                    imported.setdefault(name, node.lineno)
                    # A deliberate re-export: a noqa directive covering F401
                    # on the alias's own line or on the statement's first line.
                    alias_line = getattr(alias, "lineno", node.lineno)
                    if _noqa_f401(lines, alias_line) or _noqa_f401(lines, node.lineno):
                        exported.add(name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                used_names.add(node.id)

        findings: list[VultureFinding] = []
        for name in sorted(imported):
            if name in used_names or name in exported or name.startswith("_"):
                continue
            line_no = imported[name]
            findings.append(
                VultureFinding(
                    target_id=f"{target_id}:import:{name}",
                    kind="dead_import",
                    severity="low",
                    excerpt=f"line {line_no}: unused import {name}",
                    evidence=(name, "unused import from local AST name scan"),
                    recommendation=_RECOMMENDATIONS["dead_import"],
                )
            )
        return tuple(findings)


_NOQA = re.compile(r"#\s*noqa(?::\s*(?P<codes>[A-Z0-9, ]+))?", re.IGNORECASE)


def _noqa_f401(lines: list[str], lineno: int) -> bool:
    """True when line *lineno* (1-based) carries a bare noqa or one naming F401."""
    if not 1 <= lineno <= len(lines):
        return False
    match = _NOQA.search(lines[lineno - 1])
    if match is None:
        return False
    codes = match.group("codes")
    return codes is None or "F401" in codes.upper()


def _dunder_all(tree: ast.Module) -> tuple[str, ...]:
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


_SKIP_DIRS = frozenset({"__pycache__", "node_modules", "venv", ".venv"})


class _ExternalImportIndex:
    """Which names other files in a project take FROM a given module.

    Read-only: AST for ``from mod import name``, text for ``mod.name`` (the
    shape a ``monkeypatch.setattr("mod.name", ...)`` target takes). The
    project's sources are read once per index.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self._sources: list[tuple[Path, str]] | None = None

    def _all_sources(self) -> list[tuple[Path, str]]:
        if self._sources is None:
            out = []
            for path in sorted(self.root.rglob("*.py")):
                parts = path.relative_to(self.root).parts
                if any(p.startswith(".") or p in _SKIP_DIRS for p in parts):
                    continue
                try:
                    out.append(
                        (path, path.read_text(encoding="utf-8", errors="replace"))
                    )
                except OSError:
                    continue
            self._sources = out
        return self._sources

    def _module_name(self, path: Path) -> str | None:
        try:
            rel = path.resolve().relative_to(self.root)
        except ValueError:
            return None
        parts = list(rel.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) or None

    def names_imported_from(self, path: Path) -> frozenset[str]:
        module = self._module_name(path)
        if module is None:
            return frozenset()
        target = path.resolve()
        dotted = re.compile(re.escape(module) + r"\.([A-Za-z_]\w*)")
        names: set[str] = set()
        for source_path, text in self._all_sources():
            if source_path.resolve() == target or module not in text:
                continue
            names.update(dotted.findall(text))
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            parent, _, leaf = module.rpartition(".")
            aliases: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == module:
                    names.update(a.name for a in node.names if a.name != "*")
                elif isinstance(node, ast.ImportFrom) and node.module == parent:
                    # `from aios.api import main [as api_main]`
                    aliases.update(
                        a.asname or a.name for a in node.names if a.name == leaf
                    )
                elif isinstance(node, ast.Import):
                    # `import aios.api.main as api_main`
                    aliases.update(
                        a.asname for a in node.names if a.name == module and a.asname
                    )
            if aliases:
                names.update(_attributes_used_through(tree, aliases))
        return frozenset(names)


def _attributes_used_through(tree: ast.AST, aliases: set[str]) -> set[str]:
    """``alias.name`` reads, and ``setattr/getattr/hasattr(alias, "name", ...)``."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in aliases
        ):
            found.add(node.attr)
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
                found.add(second.value)
    return found


def scan_vulture_targets(targets: Mapping[str, str]) -> VultureReport:
    return VultureScanner().scan_targets(targets)


def scan_vulture_code_paths(
    paths: Iterable[Path | str], *, importers_root: Path | str | None = None
) -> VultureReport:
    return VultureScanner().scan_code_paths(paths, importers_root=importers_root)


def _clip(text: str, limit: int = 180) -> str:
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return f"{clean[: limit - 3]}..."


def _excerpt(text: str, start: int, end: int, radius: int = 70) -> str:
    lo = max(0, start - radius)
    hi = min(len(text), end + radius)
    return _clip(text[lo:hi])


__all__ = [
    "VultureFinding",
    "VultureReport",
    "VultureScanner",
    "scan_vulture_code_paths",
    "scan_vulture_targets",
]
