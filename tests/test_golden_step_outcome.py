"""A step is scored by the evidence it earned, not by how its turn ended.

`run_prompt` had two classification paths. The clean-finish path applied
"last terminal verdict wins". The `error` path returned `outcome="error"` and
discarded the evidence entirely. So identical verifier output scored differently
depending on whether the turn ended cleanly or was stopped -- the same
validator/actor divergence this repo has now been bitten by three times, here
between two branches of one function.

It mattered. Raising the step budget (`AIOS_AGENT_MAX_ITERS`) gave the agent
room to keep going after finishing, and it dithers: it re-reads a file it has
already read, the loop detector correctly stops the turn, and organ 44's
`iterative-refinement` step 2 was scored a FAILURE while carrying
`[VERIFY PASS] 6 passed, 0 failed (exit 0) (strength=STRONG)`.

The bar is unchanged. These cases are the real evidence strings from the
2026-08-18 cohort run, kept verbatim so a future "improvement" that converts a
skip or a trailing failure into a pass fails here.
"""
from __future__ import annotations

import pytest

from tools.golden_mission_runner import outcome_from_evidence


#: (label, evidence, expected outcome) -- verbatim from the run that exposed this.
_REAL_CASES = [
    (
        "iterative-refinement s2: work finished and verified, then the agent dithered",
        ["[VERIFY PASS] 6 passed, 0 failed (exit 0) (strength=STRONG)"],
        "verified_success",
    ),
    (
        "tdd-workflow s2: a real test failure is still a failure",
        ["[VERIFY FAIL] 3 passed, 1 failed (exit 1) (strength=NONE)"],
        "verified_failure",
    ),
    (
        "multi-module s2: a skipped verify is not evidence",
        [
            "[VERIFY SKIPPED] no sibling test for training_ground/user_registry.py"
        ],
        "unverified",
    ),
]


@pytest.mark.parametrize(
    "label,evidence,expected", _REAL_CASES, ids=[c[0][:34] for c in _REAL_CASES]
)
def test_the_outcome_follows_the_evidence(label, evidence, expected) -> None:
    assert outcome_from_evidence(evidence) == expected, label


def test_no_evidence_is_unverified_not_success() -> None:
    """Fail-closed: a turn that produced nothing has proven nothing."""
    assert outcome_from_evidence([]) == "unverified"


def test_a_later_failure_supersedes_an_earlier_pass() -> None:
    """Last terminal verdict wins -- a fix that breaks it is not a success."""
    assert (
        outcome_from_evidence(
            [
                "[VERIFY PASS] 6 passed, 0 failed (exit 0) (strength=STRONG)",
                "[VERIFY FAIL] 5 passed, 1 failed (exit 1) (strength=NONE)",
            ]
        )
        == "verified_failure"
    )


def test_a_skip_after_a_pass_does_not_erase_the_pass() -> None:
    """A skip is silence, not a verdict; it must not overwrite a real one."""
    assert (
        outcome_from_evidence(
            [
                "[VERIFY PASS] 6 passed, 0 failed (exit 0) (strength=STRONG)",
                "[VERIFY SKIPPED] no sibling test for training_ground/x.py",
            ]
        )
        == "verified_success"
    )


def test_both_classification_paths_call_one_function() -> None:
    """Structural: the error path and the clean path must not re-derive this.

    Asserted against the source because behavioural agreement is exactly what
    drifted -- the two branches agreed on nothing-earned and disagreed on
    everything else.
    """
    import inspect

    from tools import golden_mission_runner

    src = inspect.getsource(golden_mission_runner.run_prompt)
    assert src.count("outcome_from_evidence(evidence)") == 2, (
        "run_prompt must classify through the shared helper on BOTH the error "
        "path and the clean-finish path; a second inline rule is the drift."
    )
    assert '"outcome": "error"' not in src, (
        "the error path must not discard earned evidence by returning a bare "
        "'error' outcome"
    )
