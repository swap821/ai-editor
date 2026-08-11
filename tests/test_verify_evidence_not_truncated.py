"""A verify verdict must reach the record as whole as it reached the model.

The defect
----------
`ToolAgent` capped every streamed tool event at `_PREVIEW_LIMIT` (400 chars),
including the verifier's verdict. The model was never affected -- it reads
`_TOOL_RESULT_LIMIT` (4000) from its own conversation -- but the stream is the
ONLY thing an operator, and the golden-mission runner, ever sees.

So organ 44's audit trail recorded five identical failures that each died four
lines into pytest's FAILURES section:

    =============================== FAILURES ===============================
    _______________________ TestCalculator.test_add ________________________
    self = <training_ground.test_calculator.TestCalculator object at 0x...>
        def test_add(                                    <-- 400 chars, cut

One line short of the assertion. Every entry was exactly 400 bytes. The record
could say a test failed and never which assertion or why, so diagnosing a
cohort meant re-running the whole thing against a live cloud model.

Why this is a test and not a constant
-------------------------------------
The failure mode is silent: nothing errors, the log simply stops being useful
at a byte offset, and the loss is invisible unless you count characters. That
is exactly the kind of regression a reviewer waves through, so the boundary is
pinned here rather than trusted to a comment.

Narration stays at `_PREVIEW_LIMIT` -- this is a targeted exception for the one
event class that carries evidence, not a blanket raise.
"""

from __future__ import annotations

from aios.agents import tool_agent


def test_verify_verdicts_keep_the_models_budget() -> None:
    """Evidence is not narration, and must not be capped like it."""
    assert tool_agent._VERIFY_PREVIEW_LIMIT == tool_agent._TOOL_RESULT_LIMIT, (
        "a verify verdict must survive to the record as whole as it reached "
        "the model; anything smaller makes the audit trail lie by omission"
    )


def test_narration_is_still_capped_tightly() -> None:
    """The exception is targeted -- other tool output stays small.

    Guards the obvious over-correction: raising `_PREVIEW_LIMIT` itself would
    fix the evidence and bloat every unrelated event on the stream.
    """
    assert tool_agent._PREVIEW_LIMIT == 400
    assert tool_agent._VERIFY_PREVIEW_LIMIT > tool_agent._PREVIEW_LIMIT


def test_a_real_pytest_failure_survives_the_cap() -> None:
    """The end-to-end shape, at the length that actually got truncated.

    Uses the verdict text organ 44 recorded, padded to a realistic size: a
    two-failure pytest run with assertion diffs runs well past 400 chars and
    comfortably under 4000. The assertion must still be present after slicing.
    """
    verdict = (
        "[VERIFY FAIL] 0 passed, 5 failed (exit 1) (strength=NONE)\n"
        "FFFFF                                                    [100%]\n"
        "=========================== FAILURES ===========================\n"
        "______________________ TestCalculator.test_add _________________\n"
        "self = <training_ground.test_calculator.TestCalculator object>\n"
        "    def test_add(self):\n"
        "        calc = Calculator()\n"
        ">       assert calc.add(2, 3) == 5\n"
        "E       TypeError: add() missing 1 required positional argument\n"
    )
    assert len(verdict) > tool_agent._PREVIEW_LIMIT, (
        "this fixture must be long enough to have been truncated by the old "
        "cap, or it proves nothing"
    )

    kept = verdict[: tool_agent._VERIFY_PREVIEW_LIMIT]
    assert kept == verdict
    assert "TypeError" in kept, "the reader still cannot see why it failed"

    lost = verdict[: tool_agent._PREVIEW_LIMIT]
    assert "TypeError" not in lost, (
        "fixture no longer reproduces the original defect -- if the old cap "
        "would have kept the assertion, this test has stopped guarding it"
    )
