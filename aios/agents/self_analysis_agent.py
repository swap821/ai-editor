"""Self-Analysis agent — Tiers T0/T1: read + diagnose the system's OWN code.

This is the first, zero-risk slice of the marquee Self-Analysis & Self-Improvement
module (Assessment §6). It is **strictly read-only and GREEN**:

  * **T0 — index/map.** Parse every ``*.py`` module under a scope root with the
    stdlib :mod:`ast` and record deterministic facts — path, lines of code,
    function names, class names, imported modules — and build a simple
    intra-package import/dependency map.
  * **T1 — diagnose.** Emit deterministic findings, each a
    ``{target_path, finding_type, evidence}`` triple: modules with no
    corresponding test (``missing_test``), structural smells (``smell``),
    ``TODO``/``FIXME``/``XXX``/``HACK`` markers (``todo``), cyclomatic
    ``complexity`` over a threshold (radon when installed, else an AST branch-count
    proxy), and modules the test suite never executed (``uncovered``, from a join
    against an existing ``.coverage`` data file).

**It NEVER edits source, NEVER executes anything, loads NO model, and opens no
network connection.** Findings are *deterministic facts*, not model guesses —
the whole point of doing this statically (Assessment §7: "so T1 findings are
deterministic facts, not model guesses"). Any LLM commentary is a later
enhancement and, when added, is stored separately and labelled explicitly
non-authoritative ("trust the evidence, not the model"); this increment omits it
entirely so there is no model dependency.

Proposing a fix (T2, writes ``proposed_diff`` + routes to the gate) and applying
one (T3/T4, approval → snapshot → verify → audit → auto-rollback) are SEPARATE,
later increments — deliberately not built here.

Mostly stdlib (``ast``, ``pathlib``, ``hashlib``, ``re``). Two *optional* analysis
deps sharpen the diagnosis when present and fail soft when absent: ``radon`` for a
real cyclomatic metric (else the AST branch-count proxy) and ``coverage`` for the
``uncovered`` join (else dormant). Both are read-only — radon only parses source,
the coverage join only *reads* an existing ``.coverage`` file; neither runs tests.
A ``dead_code`` finding is deferred (it would need a third dep, ``vulture``).
"""
from __future__ import annotations

import ast
import hashlib
import io
import os
import re
import sqlite3
import tokenize
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from aios import config
from aios.core.llm import LLMClient, LLMError
from aios.memory.db import get_connection, init_memory_db
from aios.security.secret_scanner import scan_and_redact

# --- Optional static-analysis deps (fail-soft, like the rest of the project) --- #
try:  # radon gives a real cyclomatic-complexity metric (read-only AST analysis).
    from radon.complexity import cc_visit as _radon_cc_visit
except Exception:  # noqa: BLE001 - radon optional: degrade to the AST branch-count proxy
    _radon_cc_visit = None  # type: ignore[assignment]
try:  # coverage lets us flag modules the suite never executed (read of an existing DB).
    import coverage as _coverage
except Exception:  # noqa: BLE001 - coverage optional: skip the coverage join entirely
    _coverage = None  # type: ignore[assignment]

#: Markers that flag deferred work, surfaced as ``todo`` findings (file + line).
_TODO_MARKER = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")

#: AST node types that introduce a decision point, for the branch-count proxy —
#: the FALLBACK cyclomatic estimate used only when ``radon`` is not installed.
_BRANCH_NODES: tuple[type[ast.AST], ...] = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.With,
    ast.AsyncWith,
    ast.BoolOp,
    ast.IfExp,
    ast.comprehension,
)

_FUNC_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


@dataclass(frozen=True)
class ModuleFacts:
    """Deterministic T0 facts for a single Python module."""

    path: str  #: project-relative path (POSIX separators) — stable target_path
    loc: int
    functions: tuple[str, ...]
    classes: tuple[str, ...]
    imports: tuple[str, ...]  #: every imported module (dotted; relative as ``.mod``)
    intra_imports: tuple[str, ...]  #: subset that targets this package (the dep edges)
    sha256: str  #: content hash — supports the later two-snapshot integrity check


@dataclass(frozen=True)
class Finding:
    """One deterministic T1 finding. Mirrors the report table's core columns.

    ``symbol`` is a line-number-free discriminator *within the file* — a function
    name, the trimmed text of a TODO line, or ``""`` for one-per-module findings.
    It exists so a finding has a STABLE :func:`finding_fingerprint` identity across
    runs: ``evidence`` refreshes (line numbers move) but the fingerprint does not,
    which lets reconcile preserve a finding's lifecycle status across unrelated
    edits (see :meth:`SelfAnalysisAgent.write_report`).
    """

    target_path: str
    finding_type: str  #: 'missing_test' | 'smell' | 'todo' | 'complexity' | 'uncovered'
    evidence: str
    symbol: str = ""


def finding_fingerprint(target_path: str, finding_type: str, symbol: str) -> str:
    """Stable logical identity of a finding: ``sha256(path \\x1f type \\x1f symbol)``.

    Deliberately excludes ``evidence`` (which carries volatile line numbers) so the
    same logical issue keeps one identity across runs even as the file shifts.
    """
    return hashlib.sha256(
        f"{target_path}\x1f{finding_type}\x1f{symbol}".encode("utf-8")
    ).hexdigest()


def classify_target(
    rel_path: str,
    *,
    package: str = "aios",
    frozen_subdirs: tuple[str, ...] = ("security",),
) -> str:
    """Deterministic would-be-apply zone for a project-relative path.

    A file under a frozen subdir of *package* (e.g. ``aios/security/…``, the frozen
    core in CLAUDE.md §XI) is **RED** — editing the gate that guards the agent is the
    highest-risk action. Every other path is **YELLOW**. This is the single source of
    truth shared by T2 (records ``proposed_zone``) and T3 (the apply zone gate), so
    the two can never diverge.
    """
    for sub in frozen_subdirs:
        base = f"{package}/{sub}"
        if rel_path == base or rel_path.startswith(base + "/"):
            return "RED"
    return "YELLOW"


@dataclass(frozen=True)
class SelfAnalysisReport:
    """The structured result of an analysis run (T0 map + T1 findings)."""

    modules: tuple[ModuleFacts, ...]
    #: intra-package dependency map: module rel-path -> imported package modules.
    import_map: dict[str, tuple[str, ...]] = field(default_factory=dict)
    findings: tuple[Finding, ...] = ()


@dataclass(frozen=True)
class ReconcileResult:
    """Outcome of reconciling a fresh scan into ``self_analysis_report``."""

    inserted: int  #: genuinely new findings written at status 'open'
    updated: int   #: existing open findings whose evidence was refreshed
    closed: int    #: open rows whose finding vanished from the scan (deleted)
    skipped: int   #: fresh findings already in a decided/in-flight status
    open_total: int  #: open rows under the analyzed scope after reconcile


class SelfAnalysisAgent:
    """Read-only T0/T1 analyser over the system's own ``aios/`` package.

    All paths are reported relative to *path_root* (default
    :data:`config.PROJECT_ROOT`) so a finding's ``target_path`` is a stable,
    project-relative string like ``aios/memory/facts.py``. The analysed tree
    (*scope_root*), the tests location (*tests_root*), and *path_root* are all
    injectable so tests can point the agent at a small fixture tree.
    """

    def __init__(
        self,
        scope_root: Optional[Path] = None,
        *,
        tests_root: Optional[Path] = None,
        path_root: Optional[Path] = None,
        db_path: Path = config.MEMORY_DB_PATH,
        coverage_data_path: Optional[Path] = None,
        llm: Optional[LLMClient] = None,
        frozen_subdirs: tuple[str, ...] = ("security",),
        loc_smell_threshold: int = 40,
        long_function_threshold: int = 80,
        complexity_threshold: int = 12,
    ) -> None:
        #: What to analyse. Default: the ``aios/`` package under the project root.
        self.scope_root = (scope_root or (config.PROJECT_ROOT / "aios")).resolve()
        #: Where test modules live (``test_<stem>.py`` convention).
        self.tests_root = (tests_root or (config.PROJECT_ROOT / "tests")).resolve()
        #: Findings' ``target_path`` is relative to this.
        self.path_root = (path_root or config.PROJECT_ROOT).resolve()
        self.db_path = db_path
        #: Optional coverage data file for the ``uncovered`` join; defaults to a
        #: ``.coverage`` at the path root. Read-only — never written or generated.
        self.coverage_data_path = coverage_data_path
        #: Optional COMPLETION client (``.complete()``) for T2 propose-diff — the
        #: same kind the Planner/Reflection use, NOT a chat client. ``None`` ->
        #: ``propose_*`` is a no-op (fail-soft). It NEVER writes source — only the
        #: report's ``proposed_diff``.
        self.llm = llm
        #: Package subdirs whose files map to a RED would-be-apply zone (the frozen
        #: core, CLAUDE.md §XI). A proposal against them may be drafted, but applying
        #: is T4/RED — recorded here only as ``proposed_zone`` groundwork.
        self.frozen_subdirs = frozen_subdirs
        self.loc_smell_threshold = loc_smell_threshold
        self.long_function_threshold = long_function_threshold
        self.complexity_threshold = complexity_threshold
        #: The package name drives intra-package import detection.
        self._package = self.scope_root.name

    # ----------------------------------------------------------------- helpers
    def _rel(self, path: Path) -> str:
        """Path relative to *path_root* (POSIX), falling back to the absolute path."""
        try:
            return path.resolve().relative_to(self.path_root).as_posix()
        except ValueError:
            return path.resolve().as_posix()

    def _iter_modules(self) -> list[Path]:
        """Every ``*.py`` file under the scope root, in deterministic order."""
        if not self.scope_root.is_dir():
            return []
        return sorted(self.scope_root.rglob("*.py"))

    # ------------------------------------------------------------------ T0 map
    def scan_module(self, path: Path) -> Optional[ModuleFacts]:
        """Parse one module into :class:`ModuleFacts`; ``None`` if unreadable.

        Fail-soft: a file that cannot be read or parsed (e.g. a syntax error) is
        skipped rather than aborting the whole scan — read-only diagnosis must
        never crash on a single bad file.
        """
        try:
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except (OSError, SyntaxError, ValueError):
            return None

        functions = tuple(
            n.name for n in ast.walk(tree) if isinstance(n, _FUNC_NODES)
        )
        classes = tuple(n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
        imports, intra = self._collect_imports(tree)
        return ModuleFacts(
            path=self._rel(path),
            loc=src.count("\n") + 1,
            functions=functions,
            classes=classes,
            imports=imports,
            intra_imports=intra,
            sha256=hashlib.sha256(src.encode("utf-8")).hexdigest(),
        )

    def _collect_imports(self, tree: ast.AST) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Return ``(all_imports, intra_package_imports)`` as sorted dotted names.

        An import counts as intra-package when it names this package
        (``aios`` / ``aios.*``) or is a relative import (``from . import x``),
        which by definition targets the same package.
        """
        all_imports: set[str] = set()
        intra: set[str] = set()
        pkg = self._package
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    all_imports.add(alias.name)
                    if alias.name == pkg or alias.name.startswith(pkg + "."):
                        intra.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:  # relative import -> intra-package
                    name = "." * node.level + (node.module or "")
                    all_imports.add(name)
                    intra.add(name)
                elif node.module:
                    all_imports.add(node.module)
                    if node.module == pkg or node.module.startswith(pkg + "."):
                        intra.add(node.module)
        return tuple(sorted(all_imports)), tuple(sorted(intra))

    def build_map(self) -> dict[str, ModuleFacts]:
        """T0: scan every module into a ``{rel_path: ModuleFacts}`` map."""
        facts: dict[str, ModuleFacts] = {}
        for path in self._iter_modules():
            m = self.scan_module(path)
            if m is not None:
                facts[m.path] = m
        return facts

    # ---------------------------------------------------------------- T1 diagnose
    def diagnose(self, facts: Optional[dict[str, ModuleFacts]] = None) -> list[Finding]:
        """T1: deterministic findings over the T0 map.

        Findings (all deterministic facts, never model opinion):
          * ``missing_test`` — a testable module (defines a function/class, not an
            ``__init__``) with neither a conventional ``tests/test_<stem>.py`` nor
            a test module that imports it.
          * ``smell`` — a substantial module (> ``loc_smell_threshold`` LOC) that
            defines nothing, or a function longer than ``long_function_threshold``.
          * ``todo`` — a TODO/FIXME/XXX/HACK marker (file + line).
          * ``complexity`` — cyclomatic complexity over ``complexity_threshold``
            (radon when installed; otherwise the AST branch-count proxy).
          * ``uncovered`` — a testable module with no executed lines in an existing
            ``.coverage`` data file. Binary "never executed" only — partial-coverage
            percentages are a later refinement; dormant when coverage is absent.

        Deferred: ``dead_code`` (unreferenced functions) — needs a third dep
        (``vulture``); not implemented here.
        """
        facts = self.build_map() if facts is None else facts
        findings: list[Finding] = []
        #: Realpaths the coverage data recorded as executed, or ``None`` when the
        #: join is dormant (no coverage installed / no ``.coverage`` file).
        measured = self._measured_files()
        test_imports = self._test_imports()
        for rel_path, m in facts.items():
            path = (self.path_root / rel_path)
            stem = Path(rel_path).stem
            testable = stem != "__init__" and bool(m.functions or m.classes)

            if testable and not self._has_test(rel_path, test_imports):
                findings.append(
                    Finding(rel_path, "missing_test",
                            f"no conventional or import-linked test for a module defining "
                            f"{len(m.functions)} function(s)/{len(m.classes)} class(es)")
                )

            if testable and measured is not None and os.path.realpath(str(path)) not in measured:
                findings.append(
                    Finding(rel_path, "uncovered",
                            "module has no executed lines in the coverage data")
                )

            if m.loc > self.loc_smell_threshold and not m.functions and not m.classes:
                findings.append(
                    Finding(rel_path, "smell",
                            f"{m.loc} LOC but defines no functions or classes")
                )

            findings.extend(self._scan_source_findings(path, rel_path))
        return findings

    def _measured_files(self) -> Optional[set[str]]:
        """Realpaths the coverage data recorded as executed, or ``None``.

        **Read-only**: opens an EXISTING ``.coverage`` data file and reads the list
        of measured files; it never runs tests or generates coverage. Returns
        ``None`` (the join is dormant) when ``coverage`` is not installed, no data
        file exists, or the file can't be read — so diagnosis degrades gracefully.
        """
        if _coverage is None:
            return None
        cov_path = self.coverage_data_path or (self.path_root / ".coverage")
        if not cov_path.exists():
            return None
        try:
            data = _coverage.CoverageData(basename=str(cov_path))
            data.read()
            return {os.path.realpath(f) for f in data.measured_files()}
        except Exception:  # noqa: BLE001 - fail-soft: a corrupt/locked DB -> no coverage findings
            return None

    def _test_imports(self) -> set[str]:
        """Return dotted modules imported by test files, ignoring unreadable tests."""
        imports: set[str] = set()
        if not self.tests_root.is_dir():
            return imports
        for test_path in self.tests_root.rglob("test_*.py"):
            try:
                tree = ast.parse(test_path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError, ValueError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module)
                    imports.update(f"{node.module}.{alias.name}" for alias in node.names)
        return imports

    def _has_test(self, rel_path: str, test_imports: set[str]) -> bool:
        """True when a conventional or import-linked test covers *rel_path*."""
        stem = Path(rel_path).stem
        if any(self.tests_root.rglob(f"test_{stem}.py")):
            return True
        module_parts = Path(rel_path).with_suffix("").parts
        if module_parts and module_parts[-1] == "__init__":
            module_parts = module_parts[:-1]
        module_name = ".".join(module_parts)
        return bool(module_name and module_name in test_imports)

    def _scan_source_findings(self, path: Path, rel_path: str) -> list[Finding]:
        """Per-module findings that need the source/AST: TODOs, long funcs, complexity."""
        out: list[Finding] = []
        try:
            src = path.read_text(encoding="utf-8")
        except OSError:
            return out

        try:
            tokens = tokenize.generate_tokens(io.StringIO(src).readline)
            for token in tokens:
                if token.type != tokenize.COMMENT:
                    continue
                marker = _TODO_MARKER.search(token.string)
                if marker is not None:
                    out.append(
                        Finding(rel_path, "todo",
                                f"{marker.group(1)} marker at line {token.start[0]}",
                                symbol=token.string.strip())
                    )
        except (IndentationError, tokenize.TokenError):
            return out

        try:
            tree = ast.parse(src)
        except (SyntaxError, ValueError):
            return out

        for node in ast.walk(tree):
            if not isinstance(node, _FUNC_NODES):
                continue
            span = self._func_span(node)
            if span > self.long_function_threshold:
                out.append(
                    Finding(rel_path, "smell",
                            f"function '{node.name}' is {span} lines long "
                            f"(> {self.long_function_threshold})",
                            symbol=node.name)
                )

        out.extend(self._complexity_findings(src, tree, rel_path))
        return out

    def _complexity_findings(self, src: str, tree: ast.AST, rel_path: str) -> list[Finding]:
        """Cyclomatic-complexity findings for *rel_path*.

        Prefers radon's :func:`cc_visit` — a real cyclomatic metric (read-only AST
        analysis) — and falls back to the AST branch-count proxy when radon is
        absent or raises on exotic source. The ``symbol`` is always the BARE
        function/method name (radon ``block.name``) so switching proxy->radon
        UPDATES existing open rows (evidence refreshed) rather than duplicating them.
        """
        if _radon_cc_visit is not None:
            try:
                blocks = _radon_cc_visit(src)
            except Exception:  # noqa: BLE001 - radon can choke on exotic source -> fall back
                blocks = None
            if blocks is not None:
                out: list[Finding] = []
                for block in blocks:
                    # cc_visit returns a flat list; functions are 'F', methods 'M'
                    # (classes 'C' are skipped — their methods appear individually).
                    if getattr(block, "letter", "") not in ("F", "M"):
                        continue
                    if block.complexity > self.complexity_threshold:
                        out.append(
                            Finding(rel_path, "complexity",
                                    f"cyclomatic complexity {block.complexity} "
                                    f"(> {self.complexity_threshold})",
                                    symbol=block.name)
                        )
                return out
        return self._complexity_proxy_findings(tree, rel_path)

    def _complexity_proxy_findings(self, tree: ast.AST, rel_path: str) -> list[Finding]:
        """Fallback cyclomatic estimate: 1 + decision-point count per function.

        Used only when radon is unavailable. Same ``symbol`` (bare function name)
        as the radon path, so a finding's identity is stable across the two.
        """
        out: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, _FUNC_NODES):
                continue
            branches = sum(1 for n in ast.walk(node) if isinstance(n, _BRANCH_NODES))
            complexity = branches + 1  # 1 base path + one per decision point
            if complexity > self.complexity_threshold:
                out.append(
                    Finding(rel_path, "complexity",
                            f"function '{node.name}' branch-count proxy {complexity} "
                            f"(> {self.complexity_threshold})",
                            symbol=node.name)
                )
        return out

    @staticmethod
    def _func_span(node: ast.AST) -> int:
        """Line span of a function definition (1 if line numbers are unavailable)."""
        start = getattr(node, "lineno", None)
        end = getattr(node, "end_lineno", None)
        if isinstance(start, int) and isinstance(end, int):
            return end - start + 1
        return 1

    # ------------------------------------------------------------------- analyse
    def analyze(self) -> SelfAnalysisReport:
        """Run T0 + T1 and return a structured report. **Pure / read-only** — no DB
        write, no source edit. Persisting is the caller's explicit choice via
        :meth:`write_report`."""
        facts = self.build_map()
        findings = self.diagnose(facts)
        import_map = {rel: m.intra_imports for rel, m in facts.items()}
        return SelfAnalysisReport(
            modules=tuple(facts.values()),
            import_map=import_map,
            findings=tuple(findings),
        )

    # ----------------------------------------------------------------- persistence
    def write_report(self, findings: list[Finding]) -> ReconcileResult:
        """Reconcile *findings* into ``self_analysis_report`` by stable fingerprint.

        A plain re-INSERT would pile up duplicate ``open`` rows every run, which
        would make T2 (propose-diff) propose the same fix N times and muddy the
        status lifecycle. Instead, each finding has a stable
        :func:`finding_fingerprint` (path + type + line-number-free ``symbol``), and
        reconcile keeps the ``open`` set a clean, de-duplicated mirror of the current
        scan **within the analyzed scope**, while never disturbing a finding that
        already has a human/agent decision:

          * fresh finding already in a *decided* status (proposed/approved/applied/
            rejected/rolled_back)  -> **skipped** (never re-opened or duplicated);
          * fresh finding matching an existing *open* row -> **updated** (evidence
            refreshed, e.g. new line numbers) — identity and status preserved;
          * genuinely new finding  -> **inserted** at status 'open';
          * existing *open* row whose finding vanished from the scan -> **closed**
            (deleted): an open row is undecided and deterministically regenerable,
            so the open set tracks reality. A non-``open`` row is NEVER deleted —
            that lineage is the decision/audit trail.

        Scope-confined: only rows whose ``target_path`` is the analyzed sub-tree
        (derived from ``scope_root``) are reconciled; other sub-trees are untouched.
        Ensures the schema + migration first (idempotent), so it is self-contained
        on a fresh or legacy DB.

        Known v1 limitation (acceptable, refine later): two identically named
        functions in one module, or two identical TODO lines in one file, collapse
        to a single fingerprint.
        """
        init_memory_db(self.db_path)
        prefix = self._rel(self.scope_root)
        # `_rel` yields "." (not "") when scope_root == path_root; treat both as the
        # defensive "reconcile the whole table" case. In practice the tool always
        # passes a non-empty sub-path, so the scoped branch is the live one.
        whole_table = prefix in ("", ".")
        # NOTE (v1 caveat): the LIKE pattern is unescaped, so a scope path containing
        # '_' or '%' would treat them as wildcards. Real scopes here ('aios', test
        # 'pkg') contain neither; refine with ESCAPE if that ever changes.
        like = prefix + "/%"

        fresh: dict[str, Finding] = {
            finding_fingerprint(f.target_path, f.finding_type, f.symbol): f
            for f in findings
        }

        inserted = updated = closed = skipped = 0
        with get_connection(self.db_path) as conn:
            if whole_table:
                existing = conn.execute(
                    "SELECT id, fingerprint, status FROM self_analysis_report"
                ).fetchall()
            else:
                existing = conn.execute(
                    "SELECT id, fingerprint, status FROM self_analysis_report "
                    "WHERE target_path = ? OR target_path LIKE ?",
                    (prefix, like),
                ).fetchall()

            open_by_fp: dict[str, int] = {}
            decided_fps: set[str] = set()
            for row in existing:
                fp = row["fingerprint"]
                if fp is None:
                    continue  # legacy/unfingerprinted; migration drops open ones
                if row["status"] == "open":
                    open_by_fp[fp] = int(row["id"])
                else:
                    decided_fps.add(fp)

            for fp, f in fresh.items():
                if fp in decided_fps:
                    skipped += 1  # already decided — never re-open or duplicate
                elif fp in open_by_fp:
                    conn.execute(
                        "UPDATE self_analysis_report SET evidence = ? WHERE id = ?",
                        (scan_and_redact(f.evidence).scrubbed, open_by_fp[fp]),
                    )
                    updated += 1
                else:
                    conn.execute(
                        "INSERT INTO self_analysis_report "
                        "(target_path, finding_type, evidence, fingerprint) "
                        "VALUES (?, ?, ?, ?)",
                        (
                            f.target_path,
                            f.finding_type,
                            scan_and_redact(f.evidence).scrubbed,
                            fp,
                        ),
                    )
                    inserted += 1

            for fp, row_id in open_by_fp.items():
                if fp not in fresh:
                    conn.execute(
                        "DELETE FROM self_analysis_report WHERE id = ?", (row_id,)
                    )
                    closed += 1

            if whole_table:
                open_total = conn.execute(
                    "SELECT COUNT(*) FROM self_analysis_report WHERE status = 'open'"
                ).fetchone()[0]
            else:
                open_total = conn.execute(
                    "SELECT COUNT(*) FROM self_analysis_report "
                    "WHERE status = 'open' AND (target_path = ? OR target_path LIKE ?)",
                    (prefix, like),
                ).fetchone()[0]

        return ReconcileResult(
            inserted=inserted, updated=updated, closed=closed,
            skipped=skipped, open_total=int(open_total),
        )

    def read_findings(
        self,
        *,
        status: Optional[str] = None,
        target_path: Optional[str] = None,
        limit: int = 100,
    ) -> list[sqlite3.Row]:
        """Read back persisted findings, newest first; optional status/path filters."""
        init_memory_db(self.db_path)
        sql = "SELECT * FROM self_analysis_report"
        clauses: list[str] = []
        params: list[object] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if target_path is not None:
            clauses.append("target_path = ?")
            params.append(target_path)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with get_connection(self.db_path) as conn:
            return conn.execute(sql, params).fetchall()

    # ----------------------------------------------------------- T2 propose-diff
    #: Stable proposer identity stamped on every T2 proposal, so T3's
    #: no-self-approval guard (§6.3) can require a human approver != the proposer.
    PROPOSER_ID = "self_analysis_agent"

    #: System prompt for :meth:`propose_fix` — demand a bare unified diff.
    _PROPOSE_SYSTEM = (
        "You produce a MINIMAL unified diff that fixes the described issue. "
        "Output ONLY a unified diff (---/+++/@@ ...), no prose, no code fences."
    )

    def _classify_target(self, rel_path: str) -> str:
        """Deterministic would-be-apply zone for *rel_path* (T2 records; T3 enforces).

        Delegates to the shared :func:`classify_target` so T2's recorded
        ``proposed_zone`` and T3's apply-time zone gate use IDENTICAL logic.
        """
        return classify_target(
            rel_path, package=self._package, frozen_subdirs=self.frozen_subdirs
        )

    def propose_fix(
        self,
        *,
        target_path: str,
        finding_type: str,
        evidence: str,
        llm: Optional[LLMClient] = None,
    ) -> Optional[str]:
        """Draft a unified-diff fix for one finding via the completion LLM; READ-ONLY.

        Reads ``path_root/target_path`` for context, asks the model for a bare
        unified diff, and returns it **scrubbed of secrets** (a fix must never
        surface a credential read from the file). Fail-soft → ``None`` (caller
        leaves the finding ``open``) when: no client, the file is unreadable, the
        model raises :class:`LLMError`/anything, or the output is empty. NEVER writes
        a source file and NEVER applies the diff.
        """
        client = llm or self.llm
        if client is None:
            return None
        try:
            source = (self.path_root / target_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        prompt = (
            f"File (path: {target_path}):\n```\n{source}\n```\n\n"
            f"Finding type: {finding_type}\nEvidence: {evidence}\n\n"
            "Produce a minimal unified diff that fixes this finding."
        )
        try:
            diff = client.complete(prompt, system=self._PROPOSE_SYSTEM)
        except LLMError:
            return None
        except Exception:  # noqa: BLE001 - advisory: any model failure leaves the finding open
            return None
        if not diff or not diff.strip():
            return None
        return scan_and_redact(diff).scrubbed

    def propose_open(self, *, limit: int = 25, llm: Optional[LLMClient] = None) -> int:
        """T2: draft + store fix proposals for up to *limit* ``open`` findings.

        For each open row, :meth:`propose_fix` drafts a diff; on success the row is
        flipped ``open -> proposed`` with ``proposed_diff`` / ``proposed_zone``
        (:meth:`_classify_target`) / ``proposed_by`` (:data:`PROPOSER_ID`) set. A
        finding whose proposal fails stays ``open``. **Only the report DB is
        written — never source, never an apply.** No client → ``0`` (no-op). Returns
        the number of findings proposed.
        """
        init_memory_db(self.db_path)
        client = llm or self.llm
        if client is None:
            return 0
        rows = self.read_findings(status="open", limit=limit)
        proposed = 0
        for row in rows:
            target_path = row["target_path"]
            diff = self.propose_fix(
                target_path=target_path,
                finding_type=row["finding_type"],
                evidence=row["evidence"],
                llm=client,
            )
            if not diff:
                continue  # fail-soft: this finding stays 'open'
            with get_connection(self.db_path) as conn:
                conn.execute(
                    "UPDATE self_analysis_report "
                    "SET proposed_diff = ?, proposed_zone = ?, proposed_by = ?, status = 'proposed' "
                    "WHERE id = ?",
                    (diff, self._classify_target(target_path), self.PROPOSER_ID, int(row["id"])),
                )
            proposed += 1
        return proposed
