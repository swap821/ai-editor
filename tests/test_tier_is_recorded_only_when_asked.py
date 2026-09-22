"""A model that was never reached earns neither a success nor a failure.

The ladder offers each target to a tier, retries with feedback, then records
one outcome for that tier. `_attempt_one` can fail three ways, and only two of
them are the model's fault:

* ``model_error`` — the provider was unreachable. A timeout, a 401, a throttle.
  The tier was never put the question.
* ``no_code_block`` — reached, answered, output unusable. The model's fault
  (though when it is a tier's ONLY outcome it usually indicts the extractor:
  `nemotron-nano-9b` scored 0/8 that way on an unclosed fence).
* ``rejected`` / ``vacuous`` — reached, graded, failed the grader.

The recording read only `.earned`, from the tier's LAST attempt. So a tier
whose retries all timed out was charged a FAILURE for a question it never saw,
and that failure is permanent: it sits in the denominator of the 80% promotion
rate forever. Near-miss on 2026-09-21 — a 300s Ollama timeout on try 1, with
try 2 landing a real answer by luck.

This is the same shape as scoring a hollow pytest run (see
`test_self_corpus_grading.py::TestAHollowRunIsNotAVerdict`): a measurement that
never happened, published as a result. Both directions are pinned here, because
the obvious risk in fixing it is that real failures start vanishing too.
"""

from __future__ import annotations

from tools.reverse_engineer_gagos import Attempt, tier_verdict


def _attempt(outcome: str, *, earned: bool = False) -> Attempt:
    """An attempt whose `reached_model` is derived the way the runner does."""
    return Attempt(
        target="calc.py::add",
        outcome=outcome,
        model="ollama.qwen2.5-coder:7b",
        earned=earned,
        # `_attempt_one` sets this immediately after `complete_via` returns, so
        # it is true for everything except a transport failure.
        reached_model=outcome != "model_error",
    )


class TestAnUnreachedTierIsNotRecorded:
    def test_every_attempt_timed_out_records_nothing(self) -> None:
        should_record, earned, why = tier_verdict(
            [_attempt("model_error"), _attempt("model_error")]
        )
        assert should_record is False
        assert earned is False
        assert "model_error" in why, "the run must say WHY it declined to score"

    def test_no_attempts_at_all_records_nothing(self) -> None:
        should_record, _earned, why = tier_verdict([])
        assert should_record is False
        assert why, "silence needs a reason too"

    def test_one_real_answer_among_outages_is_still_measured(self) -> None:
        """A flaky provider must not erase a verdict it eventually delivered."""
        should_record, earned, _ = tier_verdict(
            [_attempt("model_error"), _attempt("rejected")]
        )
        assert (should_record, earned) == (True, False)

        should_record, earned, _ = tier_verdict(
            [_attempt("model_error"), _attempt("earned", earned=True)]
        )
        assert (should_record, earned) == (True, True)


class TestWhatMustStillCountAsFailure:
    """The risk in fixing this is that real failures start disappearing."""

    def test_a_graded_rejection_is_recorded(self) -> None:
        assert tier_verdict([_attempt("rejected")])[:2] == (True, False)

    def test_a_vacuous_test_is_recorded_as_failure(self) -> None:
        """A test that cannot fail passed pytest; the grader still says no."""
        assert tier_verdict([_attempt("vacuous")])[:2] == (True, False)

    def test_unusable_output_is_the_models_fault(self) -> None:
        """Reached and answered, just not with anything parseable."""
        assert tier_verdict([_attempt("no_code_block")])[:2] == (True, False)

    def test_an_earned_attempt_is_recorded(self) -> None:
        assert tier_verdict([_attempt("earned", earned=True)])[:2] == (True, True)


class TestTheVerdictDoesNotDependOnOrder:
    """Taking the LAST attempt made the record depend on retry ordering.

    A tier that earned and then hit an outage on a later re-ask is the same
    tier as one that earned on its final try. If the order can change the
    verdict, the number is about the schedule, not the model.
    """

    def test_earned_first_then_outage(self) -> None:
        assert tier_verdict([_attempt("earned", earned=True), _attempt("model_error")])[
            :2
        ] == (True, True)

    def test_outage_first_then_earned(self) -> None:
        assert tier_verdict([_attempt("model_error"), _attempt("earned", earned=True)])[
            :2
        ] == (True, True)

    def test_earned_first_then_rejected(self) -> None:
        """One clean earn is an earn; a later miss does not retract it."""
        assert tier_verdict([_attempt("earned", earned=True), _attempt("rejected")])[
            :2
        ] == (True, True)
