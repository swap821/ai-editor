"""A ledger verdict may not name a mission count the runner contradicts.

Organ 55's C9 read "All EIGHT missions are runnable" while the runner defined
nine. The existing contradiction rule could not see it: "eight" asserts nothing
about a field being *empty*, which is all that rule checks.

This is the same class as every other finding in this file's neighbourhood --
the record and the mechanism resolving one fact differently -- sitting in the
artifact a reader trusts first.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

_spec = importlib.util.spec_from_file_location(
    "_verify_twelve", REPO_ROOT / "scripts" / "verify_organ_twelve_conditions.py"
)
_verify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_verify)


def _record(**verdicts):
    return SimpleNamespace(organ_id=55, name="probe", condition_verdicts=verdicts)


def test_the_real_mission_count_is_derived_not_configured() -> None:
    """A hand-maintained number falls behind the thing it describes.

    That is the defect this rule exists to catch, so the rule must not
    reproduce it. Counted from the runner's own adjudicators.
    """
    assert _verify._actual_mission_count(REPO_ROOT) == 9


def test_a_stale_count_is_caught() -> None:
    """THE BAR. This is the exact text that sat in the ledger."""
    failures = _verify._mission_count_failures(
        _record(C9="NOT MET - All EIGHT missions are runnable (M1-M5 ...)"),
        REPO_ROOT,
    )

    assert failures, "a verdict naming the wrong mission count passed"
    assert "EIGHT" in failures[0][1] and "9" in failures[0][1]


def test_the_correct_count_passes() -> None:
    """A rule that fires on the truth is worse than no rule."""
    assert not _verify._mission_count_failures(
        _record(C9="NOT MET - All NINE missions are runnable (M1-M5 ...)"),
        REPO_ROOT,
    )


def test_a_verdict_naming_no_count_is_ignored() -> None:
    """Most verdicts say nothing about missions; they must not be touched."""
    assert not _verify._mission_count_failures(
        _record(C1="MET - production entrypoints resolve", C2="MET - tests run"),
        REPO_ROOT,
    )


def test_the_shipped_ledger_satisfies_the_rule() -> None:
    """The rule and the artifact must agree in the repository as shipped."""
    from aios.application.governance.organ_ledger import load_ledger

    records = load_ledger(REPO_ROOT / ".aios/state/ORGAN_GREEN_LEDGER.json")
    offenders = [
        (r.organ_id, cond, why)
        for r in records
        for cond, why in _verify._mission_count_failures(r, REPO_ROOT)
    ]

    assert not offenders, f"ledger contradicts the mission set: {offenders}"
