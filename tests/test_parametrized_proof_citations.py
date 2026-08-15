"""A parametrized proof is still a proof — and a failing one still is not.

The defect
----------
`verify_organ_twelve_conditions.py` discharged a cited proof with an exact
membership test::

    test_name not in outcome["passed_names"]

pytest never records a parametrized test under its bare name. `test_x` with
three cases appears as `test_x[case0]`, `test_x[case1]`, `test_x[case2]`, so a
citation naming a parametrized test could NEVER be discharged, however
thoroughly it passed. The organ silently joined the C3/C4/C5 proof-gap set.

That took master's release-authority job down. Organ 46 went green in #213
citing `test_changes_swapped_after_ratification_are_refused` for C4 — three
parametrized cases, all green. The gate scored it unproven, the gap count went
46 -> 47, and the condition-proof ratchet refused the regression. The ratchet
was right; the measurement handed to it was wrong.

That distinction is the reason this fix is in the predicate and not in
`.aios/state/condition_proof_budget.json`, whose own note says the number "may
only go DOWN ... never raise it to make a failing gate pass".

What this file pins
-------------------
Both directions. The bar is if anything RAISED: a parametrized proof counts
only when NO case of it failed, and a citation is never discharged by a
same-prefix sibling test passing in its place.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "_twelve_conditions",
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "verify_organ_twelve_conditions.py",
)
_MODULE = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_MODULE)

_ran_and_passed = _MODULE._proof_ran_and_passed

_CITED = "test_changes_swapped_after_ratification_are_refused"


def _outcome(passed: tuple[str, ...] = (), failed: tuple[str, ...] = ()) -> dict:
    return {"passed_names": set(passed), "failed_names": list(failed)}


def test_a_parametrized_proof_that_passes_is_credited() -> None:
    """The exact shape that took master down.

    Three parametrized cases, all passing, cited by its bare name -- which is
    the only name a ledger verdict can reasonably carry.
    """
    outcome = _outcome(
        passed=(
            f"{_CITED}[swapped_to0]",
            f"{_CITED}[swapped_to1]",
            f"{_CITED}[swapped_to2]",
        )
    )
    assert _ran_and_passed(outcome, _CITED)


def test_an_unparametrized_proof_still_works() -> None:
    """The original behaviour is untouched for plain tests."""
    assert _ran_and_passed(_outcome(passed=("test_plain",)), "test_plain")


def test_a_proof_that_never_ran_is_refused() -> None:
    assert not _ran_and_passed(_outcome(passed=("test_something_else",)), _CITED)


def test_a_parametrized_proof_with_one_failing_case_is_refused() -> None:
    """The bar goes UP, not down.

    Two cases green and one red is not a discharged proof. Crediting it would
    be the fix quietly becoming a loophole -- the exact failure mode the
    condition-proof ratchet exists to catch.
    """
    outcome = _outcome(
        passed=(f"{_CITED}[swapped_to0]", f"{_CITED}[swapped_to1]"),
        failed=(f"{_CITED}[swapped_to2]",),
    )
    assert not _ran_and_passed(outcome, _CITED)


def test_a_failing_unparametrized_proof_is_refused() -> None:
    outcome = _outcome(passed=("test_other",), failed=("test_plain",))
    assert not _ran_and_passed(outcome, "test_plain")


@pytest.mark.parametrize(
    "sibling",
    (
        "test_plain_and_more",
        "test_plain_extra",
        "test_plainly",
    ),
)
def test_a_sibling_test_never_discharges_the_citation(sibling: str) -> None:
    """Matching is `name` or `name[...]` -- never a bare prefix.

    A loose `startswith` would let `test_plain_and_more` passing stand in for
    `test_plain`, silently discharging a proof that never ran. Parametrized
    here on purpose: this suite's own runner must handle the very shape the
    fix is about.
    """
    assert not _ran_and_passed(_outcome(passed=(sibling,)), "test_plain")


def test_the_real_organ46_citation_is_parametrized() -> None:
    """Guards the premise, not just the logic.

    If organ 46's C4 citation ever stops being parametrized, this file's
    motivating case is gone and the reader should be told that rather than
    left with a story that no longer matches the repo.
    """
    source = (
        Path(__file__).resolve().parents[1] / "tests" / "test_applicable_amendments.py"
    ).read_text(encoding="utf-8")
    head = source.split(f"def {_CITED}", 1)
    assert len(head) == 2, f"{_CITED} no longer exists in test_applicable_amendments.py"
    assert "parametrize" in head[0][-600:], (
        f"{_CITED} is no longer parametrized -- the regression this file "
        "guards can no longer occur through it; re-point the test at a "
        "parametrized proof rather than deleting the guard"
    )
