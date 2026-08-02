"""C6/C7/C9 must be decided by test OUTCOMES, not by files existing.

Before this, three of the twelve green-contract conditions were satisfiable
without executing anything:

* C6 ("focused tests pass")      -> passed if the file existed on disk.
* C7 ("integration tests pass")  -> passed if the file existed on disk.
* C9 ("adversarial tests pass")  -> passed if ``known_blockers`` was empty,
  which is the contract's own explicitly forbidden anti-pattern.

So an organ could cite a suite that failed, contained no tests at all, or
tested something unrelated, and still be certified green.

These tests pin the replacement. They deliberately drive the parsing and
verdict logic with synthetic JUnit reports rather than by running the real
94-file suite: the point under test is "does a failing test actually fail the
condition", and that must be provable in milliseconds or nobody will run it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_organ_twelve_conditions.py"
_spec = importlib.util.spec_from_file_location("verify_organ_twelve_conditions", _SCRIPT)
v12 = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(v12)


def _junit(tmp_path: Path, cases: list[tuple[str, str, str]]) -> Path:
    """Write a JUnit report. Each case is (classname, name, outcome)."""
    body = []
    for classname, name, outcome in cases:
        inner = {
            "pass": "",
            "fail": "<failure message='boom'>boom</failure>",
            "error": "<error message='collect'>collect</error>",
            "skip": "<skipped message='skipped'/>",
        }[outcome]
        body.append(
            f"<testcase classname='{classname}' name='{name}' time='0.01'>{inner}</testcase>"
        )
    xml = f"<testsuites><testsuite name='pytest'>{''.join(body)}</testsuite></testsuites>"
    path = tmp_path / "junit.xml"
    path.write_text(xml, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# classname -> file resolution
# --------------------------------------------------------------------------- #


def test_a_module_classname_resolves_to_its_file() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (
        v12._classname_to_path("tests.test_organ_condition_test_execution", root)
        == "tests/test_organ_condition_test_execution.py"
    )


def test_a_test_inside_a_class_still_resolves_to_the_file() -> None:
    """pytest appends the class name, so the dotted path is not a module.
    Walking the prefix is what makes `tests.test_x.TestY` resolve to
    `tests/test_x.py` without guessing which segments are classes."""
    root = Path(__file__).resolve().parents[1]
    assert (
        v12._classname_to_path(
            "tests.test_organ_condition_test_execution.TestSomething", root
        )
        == "tests/test_organ_condition_test_execution.py"
    )


def test_an_unresolvable_classname_is_dropped_not_guessed() -> None:
    root = Path(__file__).resolve().parents[1]
    assert v12._classname_to_path("nowhere.no_such_module", root) is None


# --------------------------------------------------------------------------- #
# JUnit parsing
# --------------------------------------------------------------------------- #


def test_failures_and_errors_both_count_as_failed(tmp_path: Path) -> None:
    """A collection error is not a pass. Counting only <failure> would let an
    import-time explosion read as a clean suite."""
    root = Path(__file__).resolve().parents[1]
    cls = "tests.test_organ_condition_test_execution"
    report = _junit(
        tmp_path,
        [
            (cls, "test_ok", "pass"),
            (cls, "test_broken", "fail"),
            (cls, "test_uncollectable", "error"),
            (cls, "test_ignored", "skip"),
        ],
    )

    parsed = v12._parse_junit(report, root)["tests/test_organ_condition_test_execution.py"]

    assert parsed["passed"] == 1
    assert parsed["failed"] == 2, "an <error> must count as failed, not as passed"
    assert parsed["skipped"] == 1


def test_failure_names_are_reported_for_diagnosis(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    cls = "tests.test_organ_condition_test_execution"
    report = _junit(tmp_path, [(cls, "test_refuses_bad_input", "fail")])

    parsed = v12._parse_junit(report, root)["tests/test_organ_condition_test_execution.py"]

    assert "test_refuses_bad_input" in parsed["failed_names"]


# --------------------------------------------------------------------------- #
# C9 — adversarial / failure-path detection
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "name",
    [
        "test_refuses_an_unknown_token",
        "test_rejects_replay",
        "test_tampered_row_is_detected",
        "test_never_reports_unknown_as_healthy",
        "test_cannot_escape_the_workspace",
        "test_returns_403_for_bad_origin",
    ],
)
def test_failure_path_names_are_recognised(tmp_path: Path, name: str) -> None:
    root = Path(__file__).resolve().parents[1]
    cls = "tests.test_organ_condition_test_execution"
    parsed = v12._parse_junit(_junit(tmp_path, [(cls, name, "pass")]), root)

    assert parsed["tests/test_organ_condition_test_execution.py"]["adversarial_total"] == 1


def test_a_plain_happy_path_name_is_not_counted_as_adversarial(tmp_path: Path) -> None:
    """Otherwise every organ would satisfy C9 by accident and the condition
    would mean nothing again."""
    root = Path(__file__).resolve().parents[1]
    cls = "tests.test_organ_condition_test_execution"
    parsed = v12._parse_junit(_junit(tmp_path, [(cls, "test_creates_a_record", "pass")]), root)

    assert parsed["tests/test_organ_condition_test_execution.py"]["adversarial_total"] == 0


# --------------------------------------------------------------------------- #
# The condition verdicts themselves
# --------------------------------------------------------------------------- #


def _outcome(**kw):
    base = {
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "adversarial_total": 0,
        "adversarial_failed": 0,
        "failed_names": [],
    }
    base.update(kw)
    return base


def test_a_passing_suite_satisfies_the_condition() -> None:
    failures = v12._suite_outcome(
        ["tests/a.py"], {"tests/a.py": _outcome(passed=5)}, "C6", "focused_tests", False
    )
    assert failures == []


def test_a_failing_suite_fails_the_condition() -> None:
    """The whole point. Under the old existence check this passed."""
    failures = v12._suite_outcome(
        ["tests/a.py"],
        {"tests/a.py": _outcome(passed=4, failed=1, failed_names=["test_x"])},
        "C6",
        "focused_tests",
        False,
    )
    assert [c for c, _ in failures] == ["C6"]
    assert "FAILED" in failures[0][1]


def test_a_suite_that_never_ran_fails_rather_than_passing_silently() -> None:
    failures = v12._suite_outcome(["tests/a.py"], {}, "C7", "integration_tests", False)
    assert [c for c, _ in failures] == ["C7"]
    assert "did not run" in failures[0][1]


def test_a_suite_with_no_passing_tests_fails() -> None:
    """A file that exists and collects nothing is exactly the hole the old
    on-disk check left open."""
    failures = v12._suite_outcome(
        ["tests/a.py"], {"tests/a.py": _outcome(passed=0, skipped=3)}, "C6", "focused_tests", False
    )
    assert [c for c, _ in failures] == ["C6"]
    assert "collected no passing tests" in failures[0][1]


def test_an_empty_suite_list_fails() -> None:
    assert v12._suite_outcome([], {}, "C6", "focused_tests", False) == [
        ("C6", "no focused_tests listed")
    ]


def test_an_unrunnable_frontend_suite_is_unverified_not_passed() -> None:
    """This job is Python-only. Reporting a vitest suite as passing because we
    could not run it is precisely the fabrication the ledger exists to stop."""
    failures = v12._suite_outcome(
        ["frontend/src/x.test.tsx"], {}, "C6", "focused_tests", False
    )
    assert [c for c, _ in failures] == ["C6"]
    assert "not executed here" in failures[0][1]


def test_frontend_suites_pass_only_when_explicitly_allowed_or_supplied() -> None:
    assert (
        v12._suite_outcome(["frontend/src/x.test.tsx"], {}, "C6", "focused_tests", True)
        == []
    )
