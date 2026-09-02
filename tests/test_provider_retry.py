"""A throttle is not an outage — inventory item 38.

Every cloud client raised `LLMError` on the first transport failure, so a
momentary 429 was indistinguishable from a permanent one: it burned a
`FailoverChatClient` slot and could silently downgrade the turn to a weaker
local model.

Measured, not theorised: on 2026-09-02 a golden-mission cohort lost the
`multi-module` mission mid-run to a single

    429 RESOURCE_EXHAUSTED ... Resource exhausted. Please try again later.

with nothing else wrong. The ledger would have recorded a quota blip as a
capability failure.

Both directions are pinned. Retrying everything would be as wrong as retrying
nothing: a 404 for a model that does not exist must fail immediately, not after
three backoffs, because the delay hides the real error behind a wait.
"""

from __future__ import annotations

import pytest

from aios.core.provider_retry import call_with_backoff, is_transient

_THROTTLE = RuntimeError(
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': "
    "'Resource exhausted. Please try again later.', 'status': 'RESOURCE_EXHAUSTED'}}"
)
_NOT_FOUND = RuntimeError(
    "404 NOT_FOUND. Publisher model `gemini-3.7-flash` was not found or your "
    "project does not have access to it."
)


class _Recorder:
    """A sleep that records instead of sleeping, so the delay path is real."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def test_a_throttle_is_retried_and_then_succeeds() -> None:
    """The exact shape that cost the cohort a mission."""
    calls = {"n": 0}
    sleep = _Recorder()

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _THROTTLE
        return "ok"

    result = call_with_backoff(flaky, sleep=sleep, jitter=lambda: 1.0)

    assert result == "ok"
    assert calls["n"] == 3
    assert len(sleep.delays) == 2, "the backoff path did not actually run"


def test_backoff_grows_and_is_capped() -> None:
    """Exponential, jittered, bounded — not a tight loop hammering the throttle."""
    sleep = _Recorder()

    with pytest.raises(RuntimeError):
        call_with_backoff(
            lambda: (_ for _ in ()).throw(_THROTTLE),
            attempts=4,
            base_delay_s=1.0,
            sleep=sleep,
            jitter=lambda: 1.0,
        )

    assert len(sleep.delays) == 3, "should sleep between attempts, not after the last"
    assert sleep.delays == sorted(sleep.delays), "delay must not shrink"
    assert all(d <= 8.0 for d in sleep.delays), "delay must stay capped"


def test_a_permanent_error_fails_immediately() -> None:
    """A 404 must not sit through three backoffs before surfacing.

    This is the half that keeps the fix honest: retrying everything would turn
    every real error into a slow one.
    """
    calls = {"n": 0}
    sleep = _Recorder()

    def always_404() -> str:
        calls["n"] += 1
        raise _NOT_FOUND

    with pytest.raises(RuntimeError, match="404"):
        call_with_backoff(always_404, sleep=sleep)

    assert calls["n"] == 1, "a permanent error was retried"
    assert sleep.delays == [], "a permanent error slept before failing"


def test_the_last_provider_error_is_what_surfaces() -> None:
    """Exhausting the retries must not hide the provider's own message."""
    with pytest.raises(RuntimeError, match="RESOURCE_EXHAUSTED"):
        call_with_backoff(
            lambda: (_ for _ in ()).throw(_THROTTLE),
            attempts=2,
            sleep=_Recorder(),
            jitter=lambda: 0.0,
        )


@pytest.mark.parametrize(
    "message",
    [
        "429 Too Many Requests",
        "ThrottlingException: Rate exceeded",
        "503 Service Unavailable",
        "504 DEADLINE_EXCEEDED",
        "connection reset by peer",
        "request timed out",
    ],
)
def test_transient_shapes_are_recognised(message: str) -> None:
    assert is_transient(RuntimeError(message)) is True


@pytest.mark.parametrize(
    "message",
    [
        "404 NOT_FOUND. Publisher model was not found",
        "403 PERMISSION_DENIED",
        "401 unauthenticated",
        "400 INVALID_ARGUMENT: contents must not be empty",
    ],
)
def test_permanent_shapes_are_not_retried(message: str) -> None:
    assert is_transient(RuntimeError(message)) is False


def test_a_permanent_marker_wins_over_an_incidental_transient_word() -> None:
    """'model unavailable in your region' is a 404, not a blip.

    Matching 'unavailable' alone would make a permanent error take the slow
    path, so the permanent check runs first and vetoes.
    """
    exc = RuntimeError("404 NOT_FOUND: model unavailable in your region")

    assert is_transient(exc) is False


# --------------------------------------------------------------------------- #
# Streaming: retry is bounded by EMISSION, not by call position
# --------------------------------------------------------------------------- #
# The first version of this module wrapped only the call that CREATES a stream.
# The Gemini SDK returns a lazy iterator that issues no request until consumed,
# so the wrapper guarded a line that cannot fail. A real 429 sailed past it and
# cost a golden-mission run on 2026-09-02, with zero retries logged.
#
# These pin the corrected invariant: a stream that has emitted nothing can be
# re-issued safely; once a chunk has escaped it cannot.

from aios.core.provider_retry import stream_with_backoff  # noqa: E402


def _lazy_stream(fail_times: int, chunks: tuple[str, ...] = ("a", "b")):
    """A factory whose failure happens during ITERATION, like the real SDK."""
    state = {"calls": 0}

    def make():
        state["calls"] += 1
        n = state["calls"]

        def gen():
            if n <= fail_times:
                raise _THROTTLE  # raised on first next(), not at call time
            yield from chunks

        return gen()

    return make, state


def test_a_lazy_stream_that_throttles_before_emitting_is_retried() -> None:
    """The exact bug: the failure occurs on consumption, not creation."""
    make, state = _lazy_stream(fail_times=2)
    sleep = _Recorder()

    out = list(stream_with_backoff(make, sleep=sleep, jitter=lambda: 1.0))

    assert out == ["a", "b"]
    assert state["calls"] == 3
    assert len(sleep.delays) == 2, "the lazy-stream failure never reached the backoff"


def test_a_stream_that_fails_after_emitting_is_not_retried() -> None:
    """Once a chunk has escaped downstream, re-issuing would duplicate output.

    This is the safety half. Without it, a mid-stream throttle would replay the
    beginning of the response into the caller's transcript.
    """
    state = {"calls": 0}

    def make():
        state["calls"] += 1

        def gen():
            yield "partial"
            raise _THROTTLE

        return gen()

    sleep = _Recorder()
    got = []
    with pytest.raises(RuntimeError, match="RESOURCE_EXHAUSTED"):
        for chunk in stream_with_backoff(make, sleep=sleep):
            got.append(chunk)

    assert got == ["partial"]
    assert state["calls"] == 1, "a partially-emitted stream was re-issued"
    assert sleep.delays == []


def test_a_permanent_stream_error_is_not_retried() -> None:
    state = {"calls": 0}

    def make():
        state["calls"] += 1

        def gen():
            raise _NOT_FOUND
            yield  # pragma: no cover

        return gen()

    with pytest.raises(RuntimeError, match="404"):
        list(stream_with_backoff(make, sleep=_Recorder()))

    assert state["calls"] == 1


def test_the_happy_path_costs_exactly_one_call_and_no_delay() -> None:
    """A wrapper that re-issues or sleeps when nothing failed would be worse
    than no wrapper at all: every turn would pay for a fault that never
    happened. Pins both entry points on the common path.
    """
    unary = {"n": 0}

    def once() -> str:
        unary["n"] += 1
        return "ok"

    sleep_a = _Recorder()
    assert call_with_backoff(once, sleep=sleep_a) == "ok"
    assert unary["n"] == 1
    assert sleep_a.delays == []

    streamed = {"n": 0}

    def make():
        streamed["n"] += 1
        return iter(("x", "y", "z"))

    sleep_b = _Recorder()
    assert list(stream_with_backoff(make, sleep=sleep_b)) == ["x", "y", "z"]
    assert streamed["n"] == 1, "a healthy stream was re-issued"
    assert sleep_b.delays == []
