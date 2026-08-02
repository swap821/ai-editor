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

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "verify_organ_twelve_conditions.py"
)
_spec = importlib.util.spec_from_file_location(
    "verify_organ_twelve_conditions", _SCRIPT
)
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
    xml = (
        f"<testsuites><testsuite name='pytest'>{''.join(body)}</testsuite></testsuites>"
    )
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

    parsed = v12._parse_junit(report, root)[
        "tests/test_organ_condition_test_execution.py"
    ]

    assert parsed["passed"] == 1
    assert parsed["failed"] == 2, "an <error> must count as failed, not as passed"
    assert parsed["skipped"] == 1


def test_failure_names_are_reported_for_diagnosis(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    cls = "tests.test_organ_condition_test_execution"
    report = _junit(tmp_path, [(cls, "test_refuses_bad_input", "fail")])

    parsed = v12._parse_junit(report, root)[
        "tests/test_organ_condition_test_execution.py"
    ]

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

    assert (
        parsed["tests/test_organ_condition_test_execution.py"]["adversarial_total"] == 1
    )


def test_a_plain_happy_path_name_is_not_counted_as_adversarial(tmp_path: Path) -> None:
    """Otherwise every organ would satisfy C9 by accident and the condition
    would mean nothing again."""
    root = Path(__file__).resolve().parents[1]
    cls = "tests.test_organ_condition_test_execution"
    parsed = v12._parse_junit(
        _junit(tmp_path, [(cls, "test_creates_a_record", "pass")]), root
    )

    assert (
        parsed["tests/test_organ_condition_test_execution.py"]["adversarial_total"] == 0
    )


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


def test_a_suite_that_collects_nothing_at_all_fails() -> None:
    """A file that exists, runs, and yields no testcase whatsoever is exactly
    the hole the old on-disk check left open.

    Distinct from the all-SKIPPED case below: skipping is a deliberate
    "does not apply here" signal, while collecting nothing is an empty claim.
    """
    failures = v12._suite_outcome(
        ["tests/a.py"],
        {"tests/a.py": _outcome(passed=0, skipped=0)},
        "C6",
        "focused_tests",
        False,
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


def test_an_env_gated_suite_counts_when_its_real_run_is_merged(tmp_path: Path) -> None:
    """Organ 40's only integration suite gates on AIOS_EXECUTOR_INTEGRATION, so
    the gate's own pytest run skips all of it. The containerized run in CI now
    emits JUnit that is merged in via --extra-junit, which is what lets C7 be
    satisfied by the run that actually happened rather than by relaxing the
    all-skipped rule.
    """
    root = Path(__file__).resolve().parents[1]
    report = _junit(
        tmp_path,
        [
            ("tests.test_executor_integration", f"test_case_{i}", "pass")
            for i in range(4)
        ],
    )

    merged = v12._parse_junit(report, root)

    assert merged["tests/test_executor_integration.py"]["passed"] == 4
    assert (
        v12._suite_outcome(
            ["tests/test_executor_integration.py"],
            merged,
            "C7",
            "integration_tests",
            False,
        )
        == []
    )


def test_an_env_gated_suite_still_fails_when_no_real_run_is_merged() -> None:
    """The other half. Without the merged report the suite is all-skipped, and
    an organ whose ONLY integration suite is env-gated must still fail -- the
    fix must not become a blanket exemption for env-gated suites."""
    failures = v12._suite_outcome(
        ["tests/test_executor_integration.py"],
        {"tests/test_executor_integration.py": _outcome(passed=0, skipped=4)},
        "C7",
        "integration_tests",
        False,
    )

    assert [c for c, _ in failures] == ["C7"]
    assert "proved anything" in failures[0][1]


def test_a_frontend_suite_with_real_results_counts_as_proven() -> None:
    """The regression that made organs 48/49/51 fail their own gate.

    `--frontend-junit` supplied real vitest outcomes and the parser resolved
    them, but the extension check ran BEFORE the lookup, so every frontend
    result was discarded unread. A gate that ignores evidence it is already
    holding is no better than one that never asked for it.
    """
    failures = v12._suite_outcome(
        ["frontend/src/workbench/CouncilDashboard.sovereign.test.tsx"],
        {
            "frontend/src/workbench/CouncilDashboard.sovereign.test.tsx": _outcome(
                passed=8
            )
        },
        "C7",
        "integration_tests",
        True,
    )

    assert failures == []


def test_a_failing_frontend_suite_still_fails() -> None:
    """Consuming vitest results must not make them softer than pytest ones."""
    failures = v12._suite_outcome(
        ["frontend/src/x.test.tsx"],
        {"frontend/src/x.test.tsx": _outcome(passed=3, failed=1, failed_names=["a"])},
        "C7",
        "integration_tests",
        True,
    )

    assert [c for c, _ in failures] == ["C7"]
    assert "FAILED" in failures[0][1]


def test_frontend_suites_are_unverified_when_explicitly_allowed() -> None:
    """Allowed, but only alongside a suite that actually proved something --
    see the all-unverified case below."""
    failures = v12._suite_outcome(
        ["frontend/src/x.test.tsx", "tests/a.py"],
        {"tests/a.py": _outcome(passed=3)},
        "C6",
        "focused_tests",
        True,
    )
    assert failures == []


# --------------------------------------------------------------------------- #
# Env-gated suites: unverified, not failed -- and not a free pass either
# --------------------------------------------------------------------------- #


def test_an_all_skipped_suite_does_not_fail_when_a_sibling_proved_something() -> None:
    """`tests/test_executor_integration.py` gates itself on an env var and
    runs later in the same CI job inside the container. Failing organ 52 here
    would report a passing organ as broken -- and push whoever hits it toward
    weakening the gate."""
    failures = v12._suite_outcome(
        ["tests/real.py", "tests/gated.py"],
        {
            "tests/real.py": _outcome(passed=7),
            "tests/gated.py": _outcome(passed=0, skipped=4),
        },
        "C7",
        "integration_tests",
        False,
    )
    assert failures == []


def test_an_organ_whose_suites_all_skip_still_fails() -> None:
    """ "Nothing was proven" must never read as "verified". Without this, an
    organ could satisfy the condition entirely with env-gated suites that
    never run anywhere."""
    failures = v12._suite_outcome(
        ["tests/gated.py"],
        {"tests/gated.py": _outcome(passed=0, skipped=4)},
        "C7",
        "integration_tests",
        False,
    )
    assert [c for c, _ in failures] == ["C7"]
    assert "proved anything" in failures[0][1]


def test_a_real_failure_still_fails_even_beside_a_passing_sibling() -> None:
    """The skip allowance must never soften an actual red test."""
    failures = v12._suite_outcome(
        ["tests/real.py", "tests/broken.py"],
        {
            "tests/real.py": _outcome(passed=7),
            "tests/broken.py": _outcome(passed=1, failed=1, failed_names=["test_x"]),
        },
        "C7",
        "integration_tests",
        False,
    )
    assert [c for c, _ in failures] == ["C7"]
    assert "FAILED" in failures[0][1]


# --------------------------------------------------------------------------- #
# C9 vocabulary — widened after the first real run misjudged organ 11
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "name",
    [
        "test_no_handler_raises",
        "test_chat_without_transcript_emits_error",
        "test_unregistered_mode_falls_back_to_conversation",
        "test_chat_omits_facts_block_when_dormant",
    ],
)
def test_organ_11_style_names_are_recognised_as_failure_paths(
    tmp_path: Path, name: str
) -> None:
    """These are organ 11's real test names. The first CI run reported it as
    having no failure-path coverage at all, which was this vocabulary's gap,
    not the organ's -- `_not_` does not match `_no_`, and raise/error were
    missing entirely."""
    root = Path(__file__).resolve().parents[1]
    cls = "tests.test_organ_condition_test_execution"
    parsed = v12._parse_junit(_junit(tmp_path, [(cls, name, "pass")]), root)

    assert (
        parsed["tests/test_organ_condition_test_execution.py"]["adversarial_total"] == 1
    )


@pytest.mark.parametrize(
    "name",
    [
        "test_classify_mode",
        "test_register_and_coordinate_conversation",
        "test_turn_context_is_frozen_and_has_metadata",
    ],
)
def test_widening_did_not_make_every_name_adversarial(
    tmp_path: Path, name: str
) -> None:
    """The widened vocabulary matches 40.1% of the corpus, up from 31.3%. If it
    matched everything, C9 would silently stop meaning anything -- which is the
    failure mode this whole change exists to remove."""
    root = Path(__file__).resolve().parents[1]
    cls = "tests.test_organ_condition_test_execution"
    parsed = v12._parse_junit(_junit(tmp_path, [(cls, name, "pass")]), root)

    assert (
        parsed["tests/test_organ_condition_test_execution.py"]["adversarial_total"] == 0
    )
