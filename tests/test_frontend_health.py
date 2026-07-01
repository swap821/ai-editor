"""Unit tests for the CRW Phase-0 detector's pure roll-up logic.

Only the subprocess-free aggregation is tested here; the checks themselves shell out
to npm/canon tools and are exercised by running the script, not in the suite.
"""
from tools.frontend_health import (
    FAIL,
    OK,
    UNAVAILABLE,
    WARN,
    CheckResult,
    summarize,
)


def test_all_ok_rolls_up_to_ok() -> None:
    checks = [
        CheckResult("eslint", "correctness", OK, "clean"),
        CheckResult("typecheck", "types", OK, "clean"),
    ]
    s = summarize(checks)
    assert s["overall"] == OK
    assert s["counts"][OK] == 2
    assert s["actionable_findings"] == []


def test_worst_status_wins_and_findings_flatten() -> None:
    checks = [
        CheckResult("eslint", "correctness", OK, "clean"),
        CheckResult("css-canon", "canon", FAIL, "violations", findings=["css-canon: off-canon hex"]),
        CheckResult("bundle-size", "build", WARN, "large"),
        CheckResult("a11y-static", "a11y", UNAVAILABLE, "not wired"),
    ]
    s = summarize(checks)
    assert s["overall"] == FAIL  # fail outranks warn/unavailable/ok
    assert s["counts"] == {OK: 1, WARN: 1, UNAVAILABLE: 1, FAIL: 1}
    assert s["actionable_findings"] == ["css-canon: off-canon hex"]
    assert s["n_checks"] == 4


def test_unavailable_does_not_mask_ok_but_outranks_it() -> None:
    # An unavailable check should surface (worse than ok) but never read as a failure.
    checks = [
        CheckResult("eslint", "correctness", OK, "clean"),
        CheckResult("a11y-static", "a11y", UNAVAILABLE, "not wired"),
    ]
    s = summarize(checks)
    assert s["overall"] == UNAVAILABLE
    assert s["counts"][FAIL] == 0
