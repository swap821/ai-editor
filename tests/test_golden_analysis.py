"""Golden-regression harness for the Self-Analysis analyzer (freeze T1 findings).

Locks the analyzer's deterministic T1 findings against a COMMITTED, never-changing
fixture (``tests/golden/fixture/``), so any future change that alters diagnosis — a
refactor, a threshold tweak, a radon version bump — fails THIS test instead of
silently shifting the marquee feature's output (before T2 turns findings into
proposals).

Explicit thresholds (``long_function_threshold=15``, ``complexity_threshold=5``) are
baked into BOTH the fixture design and the golden, so the fixture stays small and
the golden is reproducible. ``uncovered`` is intentionally out of the golden (no
``coverage_data_path`` is passed, so the join stays dormant); a committed synthetic
``.coverage`` could freeze ``uncovered`` later.

Regenerate the golden deliberately, AFTER an intended change, with::

    AIOS_UPDATE_GOLDEN=1 .venv/Scripts/python -m pytest tests/test_golden_analysis.py -q
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from aios.agents.self_analysis_agent import SelfAnalysisAgent

_HERE = Path(__file__).resolve().parent
_FIXTURE = _HERE / "golden" / "fixture"
_GOLDEN = _HERE / "golden" / "expected_findings.json"

# Baked into the fixture design AND the committed golden — keep them in lockstep.
_LONG_FUNCTION_THRESHOLD = 15
_COMPLEXITY_THRESHOLD = 5


def _agent(tmp_path, *, complexity_threshold: int = _COMPLEXITY_THRESHOLD) -> SelfAnalysisAgent:
    return SelfAnalysisAgent(
        scope_root=_FIXTURE / "pkg",
        tests_root=_FIXTURE / "tests",
        path_root=_FIXTURE,
        db_path=tmp_path / "g.db",
        long_function_threshold=_LONG_FUNCTION_THRESHOLD,
        complexity_threshold=complexity_threshold,
        # No coverage_data_path -> 'uncovered' stays dormant and out of the golden.
    )


def _sorted_findings(agent: SelfAnalysisAgent) -> list[dict]:
    return sorted(
        (
            {
                "target_path": f.target_path,
                "finding_type": f.finding_type,
                "evidence": f.evidence,
                "symbol": f.symbol,
            }
            for f in agent.analyze().findings
        ),
        key=lambda d: (d["target_path"], d["finding_type"], d["symbol"], d["evidence"]),
    )


def test_golden_findings_match(tmp_path) -> None:
    pytest.importorskip("radon")  # the golden freezes radon's cyclomatic values
    actual = _sorted_findings(_agent(tmp_path))

    if os.environ.get("AIOS_UPDATE_GOLDEN") == "1":
        _GOLDEN.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"golden updated: wrote {len(actual)} findings to {_GOLDEN}")
        return

    expected = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    if actual != expected:
        actual_set = {tuple(sorted(d.items())) for d in actual}
        expected_set = {tuple(sorted(d.items())) for d in expected}
        added = [dict(t) for t in sorted(actual_set - expected_set)]
        removed = [dict(t) for t in sorted(expected_set - actual_set)]
        raise AssertionError(
            "Self-Analysis findings drifted from the golden:\n"
            f"  ADDED (in analysis, not golden): {added}\n"
            f"  REMOVED (in golden, not analysis): {removed}\n"
            "  Re-run with AIOS_UPDATE_GOLDEN=1 if this change is intended."
        )


def test_golden_t0_map_invariants(tmp_path) -> None:
    # A cheap drift signal on the T0 map: module count + a known intra-package edge.
    report = _agent(tmp_path).analyze()
    assert len(report.modules) == 5   # __init__, orphan, tidy, bloated, tangled
    assert "pkg.tidy" in report.import_map["pkg/orphan.py"]


def test_golden_comparison_is_load_bearing(tmp_path) -> None:
    # Prove the comparison actually catches drift: a much higher complexity
    # threshold drops tangled.py's 'complexity' finding, so the set MUST differ
    # from the frozen golden (otherwise the golden assertion would be vacuous).
    pytest.importorskip("radon")
    drifted = _sorted_findings(_agent(tmp_path, complexity_threshold=999))
    expected = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    assert drifted != expected
