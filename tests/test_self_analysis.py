"""Tests for the Self-Analysis agent (T0/T1) and its read-only ``self_analyze`` tool.

The analyser runs over a small planted FIXTURE tree (never the real ``aios/``), so
its findings are deterministic and the "never writes source" guarantee is checked
by hashing every fixture file before and after a run. The tool test drives the
full :class:`ToolAgent` loop with a scripted fake chat client — no model, no shell.

DATA_DIR is isolated by tests/conftest.py; the analyser tests use their own temp
DB path so row-count assertions are exact and independent of other tests.
"""
from __future__ import annotations

import hashlib
import os

import pytest

from aios.agents import self_analysis_agent
from aios.agents.self_analysis_agent import SelfAnalysisAgent, finding_fingerprint
from aios.agents.tool_agent import ToolAgent
from aios.core.executor import Executor
from aios.memory.db import connect, get_connection, init_memory_db
from aios.security.gateway import RateLimiter


# --------------------------------------------------------------------------- #
# Fixture tree
# --------------------------------------------------------------------------- #
def _build_fixture(root) -> dict[str, int]:
    """Plant a tiny package + tests under *root*. Returns notable line numbers."""
    pkg = root / "pkg"
    tests = root / "tests"
    pkg.mkdir()
    tests.mkdir()

    (pkg / "__init__.py").write_text("", encoding="utf-8")

    # A module with a stdlib import, an intra-package import, a function + a class.
    (pkg / "covered.py").write_text(
        "import os\n"
        "import pkg.util\n"
        "\n"
        "\n"
        "def foo(x):\n"
        "    return x + 1\n"
        "\n"
        "\n"
        "class Bar:\n"
        "    def method(self):\n"
        "        return foo(2)\n",
        encoding="utf-8",
    )
    (tests / "test_covered.py").write_text("def test_foo():\n    assert True\n", encoding="utf-8")

    # The import target — short, tested, produces no findings.
    (pkg / "util.py").write_text("def helper():\n    return 7\n", encoding="utf-8")
    (tests / "test_util.py").write_text("def test_helper():\n    assert True\n", encoding="utf-8")

    # A testable module with NO corresponding test -> 'missing_test'.
    (pkg / "orphan.py").write_text("def lonely():\n    return 1\n", encoding="utf-8")

    # A big module that defines nothing (-> 'smell') and carries a TODO (-> 'todo').
    big_lines = [f"VALUE_{i} = {i}" for i in range(50)]
    todo_index = 10  # 0-based -> the TODO lands on 1-based line 11
    big_lines.insert(todo_index, "# TODO: split this giant config module up")
    (pkg / "bigconfig.py").write_text("\n".join(big_lines) + "\n", encoding="utf-8")

    return {"todo_line": todo_index + 1}


def _hash_tree(root) -> dict[str, str]:
    """SHA-256 of every .py file under *root* (to prove nothing was written)."""
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*.py"))
    }


# --------------------------------------------------------------------------- #
# T0 — index / architecture map
# --------------------------------------------------------------------------- #
def test_t0_builds_module_map_with_funcs_classes_loc_imports(tmp_path) -> None:
    _build_fixture(tmp_path)
    agent = SelfAnalysisAgent(
        scope_root=tmp_path / "pkg",
        tests_root=tmp_path / "tests",
        path_root=tmp_path,
        db_path=tmp_path / "report.db",
    )
    facts = agent.build_map()

    assert "pkg/covered.py" in facts
    covered = facts["pkg/covered.py"]
    # functions via ast.walk include the nested method (matches the §6.5 stub).
    assert "foo" in covered.functions and "method" in covered.functions
    assert covered.classes == ("Bar",)
    assert covered.loc > 5
    # imports: stdlib + intra-package; only the package import is an intra edge.
    assert "os" in covered.imports and "pkg.util" in covered.imports
    assert covered.intra_imports == ("pkg.util",)
    assert "os" not in covered.intra_imports

    # The dependency map exposes the same intra-package edge.
    report = agent.analyze()
    assert report.import_map["pkg/covered.py"] == ("pkg.util",)


# --------------------------------------------------------------------------- #
# T1 — deterministic diagnosis
# --------------------------------------------------------------------------- #
def test_t1_detects_todo_smell_and_missing_test(tmp_path) -> None:
    marks = _build_fixture(tmp_path)
    agent = SelfAnalysisAgent(
        scope_root=tmp_path / "pkg",
        tests_root=tmp_path / "tests",
        path_root=tmp_path,
        db_path=tmp_path / "report.db",
    )
    findings = agent.diagnose()
    by = {(f.finding_type, f.target_path) for f in findings}

    # missing_test: orphan has code but no test; covered/util are tested.
    assert ("missing_test", "pkg/orphan.py") in by
    assert ("missing_test", "pkg/covered.py") not in by
    assert ("missing_test", "pkg/util.py") not in by

    # smell: bigconfig is >40 LOC and defines nothing.
    assert ("smell", "pkg/bigconfig.py") in by

    # todo: the planted marker is reported with its exact line number.
    todo = [f for f in findings if f.finding_type == "todo"]
    assert len(todo) == 1
    assert todo[0].target_path == "pkg/bigconfig.py"
    assert f"line {marks['todo_line']}" in todo[0].evidence


def test_t1_flags_overlong_function_as_smell(tmp_path) -> None:
    # A single long function trips the long-function 'smell' rule (low threshold).
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (tmp_path / "tests").mkdir()
    body = "\n".join(f"    x = {i}" for i in range(20))
    (pkg / "huge.py").write_text(f"def big():\n{body}\n    return x\n", encoding="utf-8")
    (tmp_path / "tests" / "test_huge.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")

    agent = SelfAnalysisAgent(
        scope_root=pkg, tests_root=tmp_path / "tests", path_root=tmp_path,
        db_path=tmp_path / "report.db", long_function_threshold=10,
    )
    findings = agent.diagnose()
    smells = [f for f in findings if f.finding_type == "smell" and f.target_path == "pkg/huge.py"]
    assert smells and "big" in smells[0].evidence


# --------------------------------------------------------------------------- #
# Persistence — write to self_analysis_report, read it back
# --------------------------------------------------------------------------- #
def test_write_report_persists_open_findings(tmp_path) -> None:
    _build_fixture(tmp_path)
    db_path = tmp_path / "report.db"
    agent = SelfAnalysisAgent(
        scope_root=tmp_path / "pkg", tests_root=tmp_path / "tests",
        path_root=tmp_path, db_path=db_path,
    )
    report = agent.analyze()
    res = agent.write_report(list(report.findings))
    # On a fresh DB every finding is a new 'open' row; nothing updated/closed/skipped.
    assert res.inserted == len(report.findings) > 0
    assert res.open_total == len(report.findings)
    assert (res.updated, res.closed, res.skipped) == (0, 0, 0)

    rows = agent.read_findings()
    assert len(rows) == res.inserted
    # Deterministic columns are written; T2 columns stay NULL; status defaults open.
    types = {r["finding_type"] for r in rows}
    assert {"missing_test", "smell", "todo"} <= types
    for r in rows:
        assert r["status"] == "open"
        assert r["fingerprint"] is not None
        assert r["llm_commentary"] is None
        assert r["proposed_zone"] is None
        assert r["proposed_diff"] is None
        assert r["applied_audit_id"] is None

    # The status filter works (all rows are 'open').
    assert len(agent.read_findings(status="open")) == res.inserted
    assert agent.read_findings(status="applied") == []


def test_analyze_never_writes_to_any_source_file(tmp_path) -> None:
    _build_fixture(tmp_path)
    before = _hash_tree(tmp_path)
    agent = SelfAnalysisAgent(
        scope_root=tmp_path / "pkg", tests_root=tmp_path / "tests",
        path_root=tmp_path, db_path=tmp_path / "report.db",
    )
    report = agent.analyze()
    agent.write_report(list(report.findings))
    after = _hash_tree(tmp_path)
    assert before == after, "self-analysis must NEVER modify source files"


# --------------------------------------------------------------------------- #
# Static tooling — radon cyclomatic complexity + coverage 'uncovered' join
# --------------------------------------------------------------------------- #
def _tangled_module(tmp_path):
    """Plant a tested module with a genuinely high-cyclomatic-complexity function."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (tmp_path / "tests").mkdir()
    src = "def tangled(x):\n"
    for i in range(6):                      # 6 branches -> cyclomatic complexity ~7
        src += f"    if x == {i}:\n        return {i}\n"
    src += "    return -1\n"
    (pkg / "m.py").write_text(src, encoding="utf-8")
    (tmp_path / "tests" / "test_m.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    return SelfAnalysisAgent(
        scope_root=pkg, tests_root=tmp_path / "tests", path_root=tmp_path,
        db_path=tmp_path / "r.db", complexity_threshold=3,
    )


def test_radon_complexity_uses_real_metric(tmp_path) -> None:
    pytest.importorskip("radon")
    agent = _tangled_module(tmp_path)
    cx = [f for f in agent.diagnose()
          if f.finding_type == "complexity" and f.target_path == "pkg/m.py"]
    assert cx, "radon should flag the high-complexity function"
    assert "cyclomatic complexity" in cx[0].evidence
    assert cx[0].symbol == "tangled"        # bare name -> fingerprint-stable


def test_complexity_falls_back_to_proxy_without_radon(tmp_path, monkeypatch) -> None:
    # With radon unavailable, the SAME function is still flagged via the AST proxy.
    monkeypatch.setattr(self_analysis_agent, "_radon_cc_visit", None)
    agent = _tangled_module(tmp_path)
    cx = [f for f in agent.diagnose()
          if f.finding_type == "complexity" and f.target_path == "pkg/m.py"]
    assert cx, "the proxy fallback should still flag the function"
    assert "branch-count proxy" in cx[0].evidence
    assert cx[0].symbol == "tangled"        # same symbol as radon -> stable identity


def test_coverage_uncovered_flags_unmeasured_module(tmp_path) -> None:
    coverage = pytest.importorskip("coverage")
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (tmp_path / "tests").mkdir()
    (pkg / "seen.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (pkg / "unseen.py").write_text("def b():\n    return 2\n", encoding="utf-8")
    # Both are tested by convention, so only the coverage signal differs.
    (tmp_path / "tests" / "test_seen.py").write_text("def t():\n    assert True\n", encoding="utf-8")
    (tmp_path / "tests" / "test_unseen.py").write_text("def t():\n    assert True\n", encoding="utf-8")

    # Synthetic coverage DB: only seen.py was ever executed.
    cov_file = tmp_path / ".coverage"
    cd = coverage.CoverageData(basename=str(cov_file))
    cd.add_lines({os.path.realpath(str(pkg / "seen.py")): [1, 2]})
    cd.write()

    agent = SelfAnalysisAgent(
        scope_root=pkg, tests_root=tmp_path / "tests", path_root=tmp_path,
        db_path=tmp_path / "r.db", coverage_data_path=cov_file,
    )
    uncovered = {f.target_path for f in agent.diagnose() if f.finding_type == "uncovered"}
    assert "pkg/unseen.py" in uncovered      # never executed -> flagged
    assert "pkg/seen.py" not in uncovered    # executed -> not flagged


def test_coverage_join_dormant_without_data(tmp_path) -> None:
    # No .coverage and no coverage_data_path -> zero 'uncovered'; the rest stands.
    _build_fixture(tmp_path)
    agent = _agent(tmp_path)
    findings = agent.diagnose()
    assert not [f for f in findings if f.finding_type == "uncovered"]
    assert [f for f in findings if f.finding_type == "missing_test"]   # diagnosis unchanged


def test_diagnose_with_coverage_is_read_only(tmp_path) -> None:
    # The coverage join only READS an existing .coverage file — no source is written.
    coverage = pytest.importorskip("coverage")
    _build_fixture(tmp_path)
    cov_file = tmp_path / ".coverage"
    cd = coverage.CoverageData(basename=str(cov_file))
    cd.add_lines({os.path.realpath(str(tmp_path / "pkg" / "covered.py")): [1]})
    cd.write()

    before = _hash_tree(tmp_path)
    agent = SelfAnalysisAgent(
        scope_root=tmp_path / "pkg", tests_root=tmp_path / "tests", path_root=tmp_path,
        db_path=tmp_path / "r.db", coverage_data_path=cov_file,
    )
    agent.diagnose()
    after = _hash_tree(tmp_path)
    assert before == after, "the coverage join must NEVER modify source files"


# --------------------------------------------------------------------------- #
# Reconcile — fingerprint-based de-dup / lifecycle hygiene for re-runs
# --------------------------------------------------------------------------- #
def _agent(tmp_path):
    """A SelfAnalysisAgent over the fixture pkg with a per-test temp DB."""
    return SelfAnalysisAgent(
        scope_root=tmp_path / "pkg", tests_root=tmp_path / "tests",
        path_root=tmp_path, db_path=tmp_path / "report.db",
    )


def test_write_report_is_idempotent_on_rerun(tmp_path) -> None:
    _build_fixture(tmp_path)
    agent = _agent(tmp_path)
    first = agent.write_report(list(agent.analyze().findings))
    rows_after_first = agent.read_findings(limit=1000)

    second = agent.write_report(list(agent.analyze().findings))
    rows_after_second = agent.read_findings(limit=1000)

    # Re-running the same scan must not change the row set.
    assert len(rows_after_second) == len(rows_after_first)
    assert second.inserted == 0
    assert second.updated == first.inserted
    assert second.closed == 0
    # Exactly one row per fingerprint (no duplicate 'open' rows accumulate).
    fps = [r["fingerprint"] for r in rows_after_second]
    assert len(fps) == len(set(fps))


def test_reconcile_does_not_reopen_a_decided_finding(tmp_path) -> None:
    _build_fixture(tmp_path)
    agent = _agent(tmp_path)
    agent.write_report(list(agent.analyze().findings))

    # Promote one finding to a decided status, as T2 will.
    target_fp = agent.read_findings(limit=1000)[0]["fingerprint"]
    with get_connection(tmp_path / "report.db") as conn:
        conn.execute(
            "UPDATE self_analysis_report SET status = 'proposed' WHERE fingerprint = ?",
            (target_fp,),
        )

    res = agent.write_report(list(agent.analyze().findings))
    assert res.skipped >= 1
    rows = [r for r in agent.read_findings(limit=1000) if r["fingerprint"] == target_fp]
    # Still exactly one row for it, still 'proposed' — NOT re-opened or duplicated.
    assert len(rows) == 1
    assert rows[0]["status"] == "proposed"


def test_reconcile_closes_a_vanished_finding(tmp_path) -> None:
    _build_fixture(tmp_path)
    agent = _agent(tmp_path)
    agent.write_report(list(agent.analyze().findings))
    assert [r for r in agent.read_findings(limit=1000) if r["finding_type"] == "todo"]

    # Remove the TODO line so that finding disappears from the scan.
    big = tmp_path / "pkg" / "bigconfig.py"
    kept = [ln for ln in big.read_text(encoding="utf-8").splitlines() if "TODO" not in ln]
    big.write_text("\n".join(kept) + "\n", encoding="utf-8")

    res = agent.write_report(list(agent.analyze().findings))
    assert res.closed >= 1
    assert not [r for r in agent.read_findings(limit=1000) if r["finding_type"] == "todo"]
    # Unrelated findings survive.
    assert [r for r in agent.read_findings(limit=1000) if r["finding_type"] == "missing_test"]


def test_fingerprint_stable_when_todo_moves(tmp_path) -> None:
    _build_fixture(tmp_path)
    agent = _agent(tmp_path)
    agent.write_report(list(agent.analyze().findings))
    todo_before = [r for r in agent.read_findings(limit=1000) if r["finding_type"] == "todo"]
    assert len(todo_before) == 1
    fp_before, ev_before = todo_before[0]["fingerprint"], todo_before[0]["evidence"]

    # Same TODO TEXT, different line: prepend blank lines.
    big = tmp_path / "pkg" / "bigconfig.py"
    big.write_text("\n\n\n" + big.read_text(encoding="utf-8"), encoding="utf-8")

    res = agent.write_report(list(agent.analyze().findings))
    todo_after = [r for r in agent.read_findings(limit=1000) if r["finding_type"] == "todo"]
    assert len(todo_after) == 1                          # still ONE open row
    assert todo_after[0]["fingerprint"] == fp_before     # identity preserved
    assert todo_after[0]["evidence"] != ev_before        # line number refreshed
    assert res.inserted == 0 and res.updated >= 1        # an update, not a new insert


def test_reconcile_is_scope_confined(tmp_path) -> None:
    _build_fixture(tmp_path)
    db_path = tmp_path / "report.db"
    agent = _agent(tmp_path)

    # Seed an OPEN finding for a path OUTSIDE the analyzed 'pkg/' sub-tree.
    init_memory_db(db_path)
    outside_fp = finding_fingerprint("other/mod.py", "todo", "# TODO: external")
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO self_analysis_report (target_path, finding_type, evidence, fingerprint) "
            "VALUES ('other/mod.py', 'todo', 'TODO marker at line 1', ?)",
            (outside_fp,),
        )

    agent.write_report(list(agent.analyze().findings))  # analyzes 'pkg' only

    outside = [r for r in agent.read_findings(limit=1000) if r["target_path"] == "other/mod.py"]
    assert len(outside) == 1 and outside[0]["status"] == "open"  # untouched by an out-of-scope run


def test_migration_adds_fingerprint_to_legacy_db(tmp_path) -> None:
    db_path = tmp_path / "legacy.db"
    # Build a PR#4-shaped table WITHOUT the fingerprint column + a legacy open row
    # and a legacy decided row.
    conn = connect(db_path)
    conn.executescript(
        "CREATE TABLE self_analysis_report ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,"
        " target_path TEXT NOT NULL, finding_type TEXT NOT NULL, evidence TEXT NOT NULL,"
        " llm_commentary TEXT, proposed_zone TEXT, proposed_diff TEXT,"
        " status TEXT NOT NULL DEFAULT 'open', applied_audit_id INTEGER);"
        "INSERT INTO self_analysis_report (target_path, finding_type, evidence) "
        "VALUES ('legacy/x.py', 'todo', 'old open row');"
        "INSERT INTO self_analysis_report (target_path, finding_type, evidence, status) "
        "VALUES ('legacy/y.py', 'smell', 'kept decided row', 'proposed');"
    )
    conn.commit()
    conn.close()

    init_memory_db(db_path)  # runs the migration

    with get_connection(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(self_analysis_report)")}
        assert "fingerprint" in cols
        paths = {
            r["target_path"]: r["status"]
            for r in conn.execute("SELECT target_path, status FROM self_analysis_report")
        }
    # The legacy OPEN row (NULL fingerprint) is dropped; the DECIDED one is kept.
    assert "legacy/x.py" not in paths
    assert paths.get("legacy/y.py") == "proposed"

    # A subsequent write_report works against the MIGRATED DB (legacy.db).
    _build_fixture(tmp_path)
    agent = SelfAnalysisAgent(
        scope_root=tmp_path / "pkg", tests_root=tmp_path / "tests",
        path_root=tmp_path, db_path=db_path,
    )
    res = agent.write_report(list(agent.analyze().findings))
    assert res.inserted > 0


# --------------------------------------------------------------------------- #
# Tool wiring — self_analyze in the live ToolAgent loop (read-only)
# --------------------------------------------------------------------------- #
class ScriptedChat:
    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)

    def chat(self, messages, *, tools=None, model=None) -> dict:
        return self._responses.pop(0)


class _NoopRunner:
    def __call__(self, command, *, cwd, env, timeout_s):
        return "", "", 0


def _executor() -> Executor:
    return Executor(runner=_NoopRunner(), rate_limiter=RateLimiter(), audit_log=lambda *a, **k: None)


def _tool_call(name: str, arguments: dict) -> dict:
    return {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": name, "arguments": arguments}}
    ]}


def test_self_analyze_tool_returns_summary(tmp_path) -> None:
    _build_fixture(tmp_path)
    chat = ScriptedChat([
        _tool_call("self_analyze", {"path": "pkg"}),
        {"role": "assistant", "content": "Analysis complete."},
    ])
    agent = ToolAgent(chat, _executor(), max_iters=3, read_root=tmp_path)
    events = list(agent.run([{"role": "user", "content": "audit your own code"}]))

    results = [e for e in events if e["type"] == "tool_result" and e.get("tool") == "self_analyze"]
    assert results, "self_analyze must surface a tool_result"
    out = results[0]["output"]
    assert "Self-analysis of 'pkg'" in out
    assert "finding(s)" in out
    assert events[-1]["type"] == "done"


def test_self_analyze_tool_refuses_path_escape(tmp_path) -> None:
    _build_fixture(tmp_path)
    chat = ScriptedChat([
        _tool_call("self_analyze", {"path": "../../etc"}),
        {"role": "assistant", "content": "Blocked, as expected."},
    ])
    agent = ToolAgent(chat, _executor(), max_iters=3, read_root=tmp_path)
    events = list(agent.run([{"role": "user", "content": "analyze outside"}]))

    blocked = [e for e in events if e["type"] == "tool_blocked" and e.get("tool") == "self_analyze"]
    assert blocked, "a path escaping the project root must be blocked"
    assert "escapes the project root" in blocked[0]["reason"]
