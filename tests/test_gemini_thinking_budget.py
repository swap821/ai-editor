"""Gemini 2.5 thinks inside the output budget, and that budget was too small.

The defect
----------
`max_output_tokens` on Gemini 2.5 covers thinking tokens AND visible output,
and 2.5-pro cannot turn thinking off. At the old default of 1024, measured
against the live API with organ 44's own mission prompt, four trials in a row:

    finish_reason=MAX_TOKENS   thoughts=~980   visible output=~39 tokens

The model spent ~96% of its budget reasoning and was cut off with roughly 137
characters of usable text. Downstream that arrives as a turn that did nothing —
no tool call, no answer — which is exactly the failure organ 44's golden cohort
kept recording: 2 of 4 failures in the 2026-08-16 run were "the model produced
no output".

At 8192 the same prompt finishes cleanly: `finish_reason=STOP`, 2528 thinking
tokens, 1430 output tokens, ~5000 characters of real answer.

Why this file exists
--------------------
The number is the fix, so the number is what gets pinned. A future tidy-up that
"rounds 8192 back down to a sane 1024" would silently restore a defect that took
a day to find, and would look like a harmless config cleanup in review.

The other two cases here guard the defects found alongside it: a chunk carrying
both prose and a tool call used to drop the tool call, and truncation was
detected nowhere in the codebase at all.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

from aios import config
from aios.core import gemini


def test_the_output_budget_leaves_room_for_thinking() -> None:
    """1024 is not a safe default for a model that cannot stop thinking.

    Measured, not guessed: at 1024 the live API returned MAX_TOKENS with ~980
    thinking tokens and ~39 output tokens on four consecutive trials.
    """
    assert config.GEMINI_MAX_TOKENS >= 4096, (
        f"GEMINI_MAX_TOKENS is {config.GEMINI_MAX_TOKENS}; on Gemini 2.5 the "
        "output budget also pays for thinking, and 2.5-pro cannot disable it. "
        "At 1024 the model spends ~96% of the budget reasoning and returns a "
        "truncated fragment, which reaches the agent loop as a turn that did "
        "nothing"
    )


def test_thinking_budget_default_means_send_no_thinking_config() -> None:
    """0 is 'let the model decide', not 'no thinking'.

    Pinned because the name reads like an off switch. It is not one: the code
    only sends `thinking_config` when the value is > 0, so 0 leaves the model's
    own default in place -- dynamic thinking, which 2.5-pro cannot turn off.
    Reading it as 'thinking disabled' is what makes a 1024 budget look adequate.
    """
    assert config.GEMINI_THINKING_BUDGET == 0


def _chunk(*, text: str | None = None, fc_name: str | None = None) -> SimpleNamespace:
    """A streaming chunk shaped like google-genai's."""
    parts = []
    if text is not None:
        parts.append(SimpleNamespace(text=text, function_call=None))
    if fc_name is not None:
        parts.append(
            SimpleNamespace(
                text=None,
                function_call=SimpleNamespace(name=fc_name, args={"filepath": "x.py"}),
            )
        )
    return SimpleNamespace(
        text=text,  # what the SDK's convenience accessor returns
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=parts))],
    )


def test_a_chunk_with_both_text_and_a_tool_call_keeps_the_tool_call() -> None:
    """The dropped-tool-call bug.

    The stream parser short-circuited the moment `chunk.text` was truthy, so a
    tool call riding in the same chunk was discarded. The turn then looked like
    it answered while never calling the tool it had just asked for.
    """
    events = list(
        gemini._stream_from_gemini(
            [_chunk(text="writing it now", fc_name="create_file")]
        )
    )
    finished = events[-1]

    assert finished.tool_calls, (
        "the function_call in a mixed text+tool chunk was dropped -- the turn "
        "would appear to answer while never calling the tool"
    )
    assert finished.tool_calls[0]["function"]["name"] == "create_file"


def test_text_in_a_mixed_chunk_is_not_emitted_twice() -> None:
    """The over-correction guard.

    Removing the short-circuit means the parts loop re-reads the same text.
    Without the `seen_text` flag it would be yielded and accumulated twice, so
    the fix for a dropped tool call would corrupt every mixed chunk's prose.
    """
    events = list(
        gemini._stream_from_gemini([_chunk(text="hello", fc_name="create_file")])
    )
    finished = events[-1]
    streamed = [e for e in events[:-1]]

    assert streamed == ["hello"], f"text was emitted more than once: {streamed}"
    assert finished.content == "hello"


def test_a_tool_only_chunk_still_works() -> None:
    """The path that always worked must keep working."""
    events = list(gemini._stream_from_gemini([_chunk(fc_name="verify")]))
    assert events[-1].tool_calls[0]["function"]["name"] == "verify"
    assert events[-1].content == ""


def test_truncation_is_logged_instead_of_returning_silence(caplog) -> None:
    """`finish_reason` was checked nowhere, so being cut off looked like brevity.

    That silence is what made this expensive: four hypotheses were tested and
    rejected before the live API was asked directly and said MAX_TOKENS.
    """
    response = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[SimpleNamespace(text="par", function_call=None)]
                ),
                finish_reason="FinishReason.MAX_TOKENS",
            )
        ],
        usage_metadata=SimpleNamespace(
            thoughts_token_count=980, candidates_token_count=39
        ),
    )
    with caplog.at_level(logging.WARNING):
        gemini._parse_output(response)

    assert any("truncated" in r.message for r in caplog.records), (
        "a response cut off at max_output_tokens produced no warning; it "
        "reaches the agent loop indistinguishable from a genuinely short answer"
    )


def test_a_complete_response_logs_nothing(caplog) -> None:
    """The noise guard: STOP is the normal case and must stay quiet."""
    response = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[SimpleNamespace(text="done", function_call=None)]
                ),
                finish_reason="FinishReason.STOP",
            )
        ],
        usage_metadata=SimpleNamespace(
            thoughts_token_count=10, candidates_token_count=200
        ),
    )
    with caplog.at_level(logging.WARNING):
        gemini._parse_output(response)

    assert not [r for r in caplog.records if "truncated" in r.message]


def test_truncation_check_never_breaks_a_call() -> None:
    """A malformed response must not turn a diagnostic into an outage."""
    broken = SimpleNamespace(candidates=[SimpleNamespace(content=None)])
    assert gemini._parse_output(broken) == {"role": "assistant", "content": ""}
