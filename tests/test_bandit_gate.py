"""The security lint runs, and its ratchet keeps its teeth.

Inventory item 87 / Ultra-plan Phase 8. `pip-audit` covers third-party CVEs and
CodeQL covers semantic queries; neither catches bandit's class -- a new
`subprocess(..., shell=True)`, a hardcoded credential, weak crypto, an insecure
temp file.

The gate is ratcheted rather than clean-slate because the first run found **141
findings, 0 of them HIGH**, and demanding zero would have meant either a week of
triage before anything landed or blanket `# nosec`, which is how a security lint
becomes decoration.

These tests drive the real script against a real budget file. They do NOT assert
the finding count, which would turn every unrelated refactor into a failing test
-- they assert the gate's *behaviour*: that HIGH always fails, that a new finding
fails, and that an overstated budget fails.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_bandit.py"
BUDGET = REPO_ROOT / ".aios" / "state" / "bandit_budget.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("_bandit_gate", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_gate_runs_in_ci() -> None:
    """A gate nobody invokes is a claim.

    This repo has shipped several checks that existed and never ran; the rule
    lives here so removing the invocation fails review rather than silently
    dropping security lint.
    """
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert "python scripts/check_bandit.py" in workflow, (
        "the bandit gate is no longer invoked by ci.yml"
    )
    assert "bandit==" in workflow, (
        "bandit is not installed in CI with a pinned version; an unpinned "
        "security linter changes its findings under you and the ratchet becomes "
        "noise"
    )


def test_the_budget_exists_and_is_shaped_as_a_ratchet() -> None:
    payload = json.loads(BUDGET.read_text(encoding="utf-8"))
    assert "budget" in payload
    assert all(isinstance(v, int) and v > 0 for v in payload["budget"].values()), (
        "budget entries must be positive counts"
    )
    assert "_comment" in payload, (
        "the budget must explain itself; a bare number file invites someone to "
        "raise it without thinking"
    )


def test_a_high_severity_finding_is_never_budgeted() -> None:
    """The half of the gate that has teeth from day one.

    There are zero HIGH findings today, so a budget-only gate would be purely
    historical. HIGH must fail regardless of what the budget says -- asserted by
    reading the decision logic, since manufacturing a real HIGH finding inside
    the package would mean committing one.
    """
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'issue_severity"] == "HIGH"' in source
    # The HIGH list must feed `failures` without consulting `budget`.
    high_block = source.split("# 1. HIGH severity is never budgeted.")[1].split("# 2/3.")[0]
    assert "budget" not in high_block, (
        "HIGH-severity findings are being checked against the budget; they must "
        "fail unconditionally"
    )


def test_the_fingerprint_ignores_line_numbers() -> None:
    """Keyed on (test, file) so unrelated edits do not churn the budget.

    A line-keyed ratchet forces a budget rewrite on every insertion above a
    finding, and a budget that churns is a budget nobody reads.
    """
    module = _load_module()
    a = module.fingerprint(
        {"test_id": "B608", "filename": str(REPO_ROOT / "aios" / "x.py"), "line_number": 10}
    )
    b = module.fingerprint(
        {"test_id": "B608", "filename": str(REPO_ROOT / "aios" / "x.py"), "line_number": 99}
    )
    assert a == b
    assert a == "B608:aios/x.py"


def _run_gate(cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_gate_passes_on_the_current_tree() -> None:
    """The budget must actually match reality right now.

    If this fails, either a finding was introduced or one was removed without
    lowering the budget -- both are things the gate exists to surface.
    """
    result = _run_gate(REPO_ROOT)
    assert result.returncode == 0, (
        "the bandit gate does not pass on the current tree:\n"
        + (result.stdout + result.stderr)[-1500:]
    )


def test_an_overstated_budget_fails(tmp_path: Path) -> None:
    """The half that keeps the ratchet honest.

    Without it, findings get fixed, the budget stays high, and the file becomes
    a standing permission slip for re-introducing them. Exercised by adding an
    entry that cannot correspond to any real finding.
    """
    original = BUDGET.read_text(encoding="utf-8")
    payload = json.loads(original)
    payload["budget"]["B999:aios/definitely_not_a_real_file.py"] = 3
    try:
        BUDGET.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        result = _run_gate(REPO_ROOT)
        assert result.returncode == 1
        assert "STALE" in result.stderr, result.stderr[-600:]
    finally:
        BUDGET.write_text(original, encoding="utf-8")

    # And the tree is left exactly as found.
    assert _run_gate(REPO_ROOT).returncode == 0


def test_a_missing_budget_fails_closed(tmp_path: Path) -> None:
    """No budget must not mean no findings.

    Asserted against a scratch repo so the real budget is never at risk.
    """
    scratch = tmp_path / "repo"
    (scratch / "scripts").mkdir(parents=True)
    (scratch / "aios").mkdir()
    (scratch / "aios" / "m.py").write_text("x = 1\n", encoding="utf-8")
    (scratch / "scripts" / "check_bandit.py").write_text(
        SCRIPT.read_text(encoding="utf-8"), encoding="utf-8"
    )

    result = subprocess.run(
        [sys.executable, "scripts/check_bandit.py"],
        cwd=scratch,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "missing" in (result.stdout + result.stderr).lower()
