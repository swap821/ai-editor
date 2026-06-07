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

import pytest

from aios.agents.self_analysis_agent import SelfAnalysisAgent
from aios.agents.tool_agent import ToolAgent
from aios.core.executor import Executor
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
    written = agent.write_report(list(report.findings))
    assert written == len(report.findings) > 0

    rows = agent.read_findings()
    assert len(rows) == written
    # Deterministic columns are written; T2 columns stay NULL; status defaults open.
    types = {r["finding_type"] for r in rows}
    assert {"missing_test", "smell", "todo"} <= types
    for r in rows:
        assert r["status"] == "open"
        assert r["llm_commentary"] is None
        assert r["proposed_zone"] is None
        assert r["proposed_diff"] is None
        assert r["applied_audit_id"] is None

    # The status filter works (all rows are 'open').
    assert len(agent.read_findings(status="open")) == written
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
