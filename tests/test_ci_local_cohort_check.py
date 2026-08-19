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


# -- the gate once passed the very run it existed to fail ---------------------

_REAL_MISSING_IMAGE = (
    "step 1/2: write the tests" + chr(10)
    + "      evidence: [VERIFY FAIL] 0 passed, 0 failed (exit 125) (strength=NONE)" + chr(10)
    + "Unable to find image 'aios-worker:local' locally" + chr(10)
    + "docker: Error response from daemon: pull access denied for aios-worker, "
    "repository does not exist" + chr(10)
    + "[golden] FINAL: 0/1 mission runs passed (0%)" + chr(10)
)


def test_a_missing_workload_image_is_a_harness_failure_not_a_low_score() -> None:
    """Verbatim from run 32201154129, the job's first real execution.

    AIOS_APPROVED_EXECUTION_BACKEND defaults to "container" and the cohort job
    did not build aios-worker:local, so every verify step died in the docker
    daemon. The mission scored 0/1 and this gate said "harness integrity: OK".

    That is the precise confusion this file exists to prevent -- infrastructure
    reported as model quality -- occurring inside the guard against it. The
    string is kept verbatim so a reworded docker error does not silently reopen
    the hole.
    """
    ok, notes = check(_REAL_MISSING_IMAGE)

    assert ok is False, "a cohort that could not start a container proved nothing"
    joined = " ".join(notes)
    assert "image was never built" in joined
    assert "score 0/1 (reported, NOT gated)" in joined, (
        "the score must still be REPORTED -- the gate stops enforcing it, it "
        "does not stop showing it"
    )


@pytest.mark.parametrize("code", ["125", "126", "127"])
def test_docker_reserved_exit_codes_fail_the_gate(code: str) -> None:
    """125/126/127 mean the container never ran. pytest returns 0-5, never these."""
    log = (
        _STEPS
        + "      evidence: [VERIFY FAIL] 0 passed, 0 failed (exit " + code + ") (strength=NONE)" + chr(10)
        + "FINAL: 0/5 mission runs passed" + chr(10)
    )
    ok, notes = check(log)

    assert ok is False
    assert "sandbox never started" in " ".join(notes)


def test_a_real_pytest_failure_still_passes_the_gate() -> None:
    """The counterpart that must NOT regress: exit 1 is a model failing a test.

    If this ever starts failing the gate, the gate has become a score gate and
    the whole distinction is gone.
    """
    log = (
        _STEPS
        + "      evidence: [VERIFY FAIL] 3 passed, 1 failed (exit 1) (strength=NONE)" + chr(10)
        + "FINAL: 0/5 mission runs passed" + chr(10)
    )
    ok, _ = check(log)

    assert ok is True, "a genuinely failing test is model performance, not a fault"
