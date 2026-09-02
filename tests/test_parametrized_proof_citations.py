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


# --------------------------------------------------------------------------- #
# Vitest citations — quoted names, and describe-folded JUnit names
# --------------------------------------------------------------------------- #
# Organs 20, 48, 49 and 51 were unciteable by construction, not unproven. A
# vitest test IS its description -- `it('rejects malformed known events before
# read-model mutation or reaction')` -- so its name contains spaces, and the
# referent pattern admitted only [\w\[\]\-]+ after "::".
#
# The failure mode was worse than rejection: the path matched, the name group
# captured only `rejects`, and the citation PASSED the "a referent is named"
# check before failing execution-matching against a test nobody wrote. A
# citation that looks resolvable and points at nothing is exactly what this
# gate exists to prevent.

_citations = _MODULE._proof_citations
_unquote = _MODULE._unquote_proof_name

_VITEST_FILE = "frontend/src/superbrain/lib/livingMirrorRegistry.test.ts"
_VITEST_NAME = "rejects malformed known events before read-model mutation or reaction"
_VITEST_JUNIT = f"Living Mirror reaction registry > {_VITEST_NAME}"


def test_a_quoted_citation_captures_the_whole_name() -> None:
    """The fix: the space-bearing name survives intact.

    Before, this same text yielded ("...test.ts", "rejects").
    """
    text = f'PASS - proven by {_VITEST_FILE}::"{_VITEST_NAME}"'

    assert _citations(text) == [(_VITEST_FILE, _VITEST_NAME)]


def test_an_unquoted_spaced_citation_still_truncates_and_is_refused() -> None:
    """The old shape must not silently become valid.

    Widening the pattern must not make a badly-written citation work by
    accident: without quotes the name is still cut at the first space, and the
    truncated fragment must not match the real JUnit entry.
    """
    text = f"PASS - proven by {_VITEST_FILE}::{_VITEST_NAME}"

    assert _citations(text) == [(_VITEST_FILE, "rejects")]
    assert not _ran_and_passed(_outcome(passed=(_VITEST_JUNIT,)), "rejects")


def test_a_citation_matches_the_describe_folded_junit_name() -> None:
    """vitest folds describe() blocks into the reported name, joined by " > ".

    A citation names the leaf, because that is what a reader sees in the test
    file, so exact matching could never discharge a frontend proof.
    """
    assert _ran_and_passed(_outcome(passed=(_VITEST_JUNIT,)), _VITEST_NAME)


def test_a_failing_vitest_case_still_vetoes_its_citation() -> None:
    """The veto survives the new clause -- a red test cannot be cited."""
    outcome = _outcome(passed=(), failed=(_VITEST_JUNIT,))

    assert not _ran_and_passed(outcome, _VITEST_NAME)


@pytest.mark.parametrize(
    "sibling",
    [
        "Living Mirror reaction registry > rejects malformed known events before read-model mutation or reaction and more",
        "Living Mirror reaction registry > also rejects malformed known events before read-model mutation or reaction",
    ],
)
def test_a_vitest_sibling_never_discharges_the_citation(sibling: str) -> None:
    """Segment matching keeps the pytest sibling-safety guarantee.

    The cited name must equal the WHOLE segment after the last " > ". A longer
    sibling ("...and more") differs at the end; a differently-prefixed one
    ("also rejects...") is not preceded by " > " at the right offset. Neither
    may launder a citation.
    """
    assert not _ran_and_passed(_outcome(passed=(sibling,)), _VITEST_NAME)


def test_unquoting_leaves_bare_names_untouched() -> None:
    """Python citations keep working exactly as before."""
    assert _unquote("test_x") == "test_x"
    assert _unquote('"a b"') == "a b"
    assert _citations("tests/test_a.py::test_x") == [("tests/test_a.py", "test_x")]
