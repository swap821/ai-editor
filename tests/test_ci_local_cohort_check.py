"""The CI cohort gate must fail on a broken harness and never on a weak model.

Blocker 2 says every organ-44 number comes from one laptop. A cohort in CI on a
local model fixes the reproducibility half with no cloud credentials -- but only
if the gate asserts the right thing.

Nine infrastructure defects on 2026-08-18 each produced a low cohort score that
looked exactly like model quality: a region default, a missing protocol field,
an inherited 1024-token budget, a privacy filter emitting invalid JSON, a stub
conftest. A gate on SCORE goes red for all nine and tells you nothing about
which. A gate on HARNESS INTEGRITY goes red for exactly those nine and stays
green when the model is merely small.

`local-clerk-live` already states the rule this follows: demanding a pass "would
create pressure to pick a model that flatters the suite or to loosen the suite
until something passes".
"""
from __future__ import annotations

import pytest

from scripts.ci_local_cohort_check import check

_STEPS = "step 1/2: first\nstep 2/2: second\n"


# -- a weak model is not a broken harness ------------------------------------

@pytest.mark.parametrize("score", ["0/5", "1/5", "3/5", "5/5"])
def test_any_score_passes_when_the_harness_ran(score: str) -> None:
    ok, notes = check(_STEPS + f"[golden] FINAL: {score} mission runs passed\n")

    assert ok, f"score {score} was gated: {notes}"
    assert any("NOT gated" in n for n in notes)


def test_allowlist_refusals_do_not_fail_the_gate() -> None:
    """A refusal is the approval gate working, not the harness breaking."""
    ok, notes = check(
        _STEPS
        + "command outside allowlist: ['pytest -k sel training_ground/x.py']\n"
        + "[golden] FINAL: 3/5 mission runs passed\n"
    )

    assert ok
    assert any("refused by ALLOWED_CMD_RE" in n for n in notes)


# -- the nine shapes that must fail ------------------------------------------

HARNESS_FAULTS = [
    ("auth", "aios.probe_session.ProbeAuthError: no credential"),
    ("provider", "Local inference error: 400 INVALID_ARGUMENT"),
    ("traceback", "Traceback (most recent call last):\n  File x"),
    ("backend died", "requests.exceptions.ConnectionError: Connection aborted"),
    ("reset", "ConnectionResetError(10054)"),
    ("wrong host", "Host header is not configured for this API"),
    ("stale instance", "an operator is already enrolled and no credential"),
]


@pytest.mark.parametrize("label,line", HARNESS_FAULTS, ids=[c[0] for c in HARNESS_FAULTS])
def test_a_harness_fault_fails_the_gate(label: str, line: str) -> None:
    ok, notes = check(_STEPS + line + "\n[golden] FINAL: 4/5 mission runs passed\n")

    assert not ok, f"{label} passed the gate: {notes}"
    assert any("HARNESS FAILURE" in n for n in notes)


def test_a_run_that_never_finished_fails() -> None:
    """No FINAL line means it died rather than scored badly."""
    ok, _ = check(_STEPS)

    assert not ok


def test_a_run_that_never_reached_a_model_fails() -> None:
    """A FINAL line with no steps is a harness that did nothing."""
    ok, _ = check("[golden] FINAL: 0/5 mission runs passed\n")

    assert not ok


def test_the_score_is_reported_even_when_the_harness_failed() -> None:
    """A reader needs both facts, not just the verdict."""
    ok, notes = check(
        _STEPS + "Local inference error: boom\n[golden] FINAL: 2/5 mission runs passed\n"
    )

    assert not ok
    assert any("score 2/5" in n for n in notes)
