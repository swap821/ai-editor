"""Bounded backoff-retry for transient cloud-provider failures.

Inventory item 38. Every cloud client raised `LLMError` immediately on any
transport failure, so a momentary throttle was indistinguishable from a
permanent outage: it burned a `FailoverChatClient` slot and could silently
downgrade a turn to a weaker local model.

That is not theoretical. On 2026-09-02 a golden-mission cohort lost the
`multi-module` mission to a single `429 RESOURCE_EXHAUSTED` from Gemini,
mid-mission, with nothing else wrong -- the ledger recorded it as a capability
failure when it was a quota blip. That is exactly the risk item 38 predicted:
"under any real cloud rate-limit (likely on the free/low-cost tiers this
project targets), turns degrade to worse models more often than necessary".

Deliberately narrow
-------------------
Only *transient* statuses retry. A 404 (wrong model), 403 (no access) or 400
(bad request) is permanent: retrying it wastes the caller's time and hides the
real error behind a delay. The classifier below is an allowlist of things that
are known to be worth retrying, not a denylist of things that are not.

Two entry points, because streaming needs a different invariant
---------------------------------------------------------------
`call_with_backoff` retries a unary call. `stream_with_backoff` retries a
stream only while nothing has been emitted, which is the safe boundary: output
already yielded downstream cannot be un-yielded, so re-issuing would duplicate
it.

Wrapping stream *creation* is not enough and was the first version's bug — the
Gemini SDK returns a lazy iterator that issues no request until consumed, so
the wrapper guarded a line that cannot fail. See `stream_with_backoff`.
"""

from __future__ import annotations

import random
import time
from typing import Callable, Iterator, TypeVar

T = TypeVar("T")

#: Substrings that mark a provider failure as worth retrying. Matched against
#: the stringified exception because the SDKs raise a wide range of types and
#: none of them expose a stable status attribute across providers.
_TRANSIENT_MARKERS = (
    "429",
    "resource_exhausted",
    "resource exhausted",
    "rate limit",
    "ratelimit",
    "too many requests",
    "throttl",  # Bedrock ThrottlingException / throttled
    "503",
    "unavailable",
    "504",
    "deadline_exceeded",
    "deadline exceeded",
    "timed out",
    "timeout",
    "connection reset",
    "connection aborted",
    "temporarily",
)

#: Never retried, even when a transient marker also appears. A permanent error
#: whose message happens to contain "unavailable" (e.g. "model unavailable in
#: your region") must fail fast rather than sit through the whole backoff.
_PERMANENT_MARKERS = (
    "not_found",
    "not found",
    "permission_denied",
    "permission denied",
    "unauthenticated",
    "invalid_argument",
    "invalid argument",
    "401",
    "403",
    "404",
    "400",
)

DEFAULT_ATTEMPTS = 3
DEFAULT_BASE_DELAY_S = 1.0
MAX_DELAY_S = 8.0


def is_transient(exc: BaseException) -> bool:
    """Whether *exc* looks like a throttle or blip worth one more attempt."""
    text = f"{type(exc).__name__}: {exc}".lower()
    if any(marker in text for marker in _PERMANENT_MARKERS):
        return False
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def call_with_backoff(
    operation: Callable[[], T],
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    base_delay_s: float = DEFAULT_BASE_DELAY_S,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = random.random,
    on_retry: Callable[[int, BaseException, float], None] | None = None,
) -> T:
    """Run *operation*, retrying only transient failures.

    `sleep` and `jitter` are injected so tests exercise the real control flow
    without spending real seconds -- a retry helper whose tests skip the delay
    path is not testing the thing that matters.

    Raises the LAST exception when every attempt fails, so the caller still
    sees a real provider error rather than a wrapper hiding it.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    last: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            last = exc
            if attempt >= attempts or not is_transient(exc):
                raise
            # Exponential with full jitter, capped: a synchronised retry storm
            # across concurrent turns would reproduce the throttle it is
            # backing off from.
            delay = min(base_delay_s * (2 ** (attempt - 1)), MAX_DELAY_S)
            delay = delay * (0.5 + 0.5 * jitter())
            if on_retry is not None:
                on_retry(attempt, exc, delay)
            sleep(delay)
    # Unreachable: the final attempt either returns or re-raises above. Written
    # as a raise rather than `assert last is not None` because `python -O`
    # strips asserts, so the assert would vanish in exactly the deployment that
    # most needs the invariant to hold (bandit B101).
    raise last if last is not None else RuntimeError("retry loop exited without result")


def stream_with_backoff(
    make_stream: Callable[[], Iterator[T]],
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    base_delay_s: float = DEFAULT_BASE_DELAY_S,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = random.random,
    on_retry: Callable[[int, BaseException, float], None] | None = None,
) -> Iterator[T]:
    """Yield from a provider stream, retrying only while nothing has been emitted.

    Why this exists separately from `call_with_backoff`
    ---------------------------------------------------
    The first version of this module wrapped only the *call* that creates the
    stream, reasoning that re-issuing a partially consumed stream would
    duplicate output. The reasoning was right; the placement was wrong. The
    Gemini SDK's `generate_content_stream()` is LAZY -- it returns an iterator
    and issues no HTTP request until iteration begins -- so the wrapper guarded
    a line that cannot fail, and a real `429 RESOURCE_EXHAUSTED` sailed straight
    past it. Measured, not guessed: a golden-mission cohort on 2026-09-02 lost a
    mission to a 429 *with the wrapper already in place* and logged zero
    retries.

    The correct invariant is about emission, not about call position: a stream
    that has yielded nothing downstream can be re-issued safely, because there
    is no output to duplicate. Once a single chunk has escaped, the attempt is
    committed and any failure propagates.
    """
    last: BaseException | None = None
    for attempt in range(1, attempts + 1):
        emitted = False
        try:
            for chunk in make_stream():
                emitted = True
                yield chunk
            return
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            last = exc
            if emitted or attempt >= attempts or not is_transient(exc):
                raise
            delay = min(base_delay_s * (2 ** (attempt - 1)), MAX_DELAY_S)
            delay = delay * (0.5 + 0.5 * jitter())
            if on_retry is not None:
                on_retry(attempt, exc, delay)
            sleep(delay)
    raise (
        last if last is not None else RuntimeError("stream retry exited without result")
    )


__all__ = [
    "call_with_backoff",
    "stream_with_backoff",
    "is_transient",
    "DEFAULT_ATTEMPTS",
]
