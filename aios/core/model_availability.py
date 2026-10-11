"""Which (provider, model) pairs this account can actually call.

Found 2026-10-11 hardening for "best cloud+local intelligence": Bedrock's
model discovery lists models the operator's account cannot invoke (every
Claude, GPT-5.x/6 and Grok answer "not available for this account"), and the
router ranked several of them near the top. Worse, the failover client counted
each such refusal as a Bedrock OUTAGE: after one transient failure of the top
model, two denied Claude candidates made three consecutive "provider failures"
and the circuit breaker switched off every Bedrock model -- quietly turning
"best cloud" into "local only" for the cooldown.

A refusal that is about ONE model is now a fact about that model:

* it is remembered for ``UNAVAILABLE_TTL_S`` and the router stops offering it;
* it never counts against the provider's circuit breaker.

Anything provider-wide -- a bad or revoked key, an organization denying API
keys outright, throttling, a timeout -- is NOT model-specific and still trips
the breaker exactly as before.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Optional

#: How long a model stays out of routing after its refusal. A day: model access
#: changes when the operator changes it, not from one turn to the next.
UNAVAILABLE_TTL_S = 24 * 60 * 60

#: Refusals that name one model, not the account or the provider. Matched
#: case-insensitively against the provider's (already scrubbed) error text.
_MODEL_SPECIFIC = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"is not available for this account",
        r"provided model identifier is invalid",
        r"don't have access to the model",
        r"do not have access to the model",
        r"model .{0,80} has reached its end",
        r"\bHTTP 410\b",
        r"model[^\n]{0,80}not found",
        r"model_not_found",
    )
)
#: Text that marks a refusal as account- or provider-wide even when it also
#: mentions a model: these must keep counting toward the breaker.
_PROVIDER_WIDE = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"CallWithBearerToken",
        r"service control policy",
        r"security token included in the request is invalid",
        r"UnrecognizedClientException",
        r"ExpiredToken",
        r"Throttling",
        r"timed out",
        r"used all available credits|spending limit",
    )
)

_unavailable: dict[tuple[str, str], float] = {}
_lock = threading.Lock()


def is_model_unavailable_error(error: BaseException | str) -> bool:
    """Is *error* a refusal of ONE model (rather than of the provider)?"""
    text = str(error)
    if any(p.search(text) for p in _PROVIDER_WIDE):
        return False
    return any(p.search(text) for p in _MODEL_SPECIFIC)


def mark_unavailable(provider: str, model: str, *, now: Optional[float] = None) -> None:
    with _lock:
        _unavailable[(provider, model)] = time.time() if now is None else now


def is_unavailable(provider: str, model: str, *, now: Optional[float] = None) -> bool:
    current = time.time() if now is None else now
    with _lock:
        marked = _unavailable.get((provider, model))
        if marked is None:
            return False
        if current - marked >= UNAVAILABLE_TTL_S:
            del _unavailable[(provider, model)]
            return False
        return True


def unavailable_models() -> dict[tuple[str, str], float]:
    """A snapshot, for observability."""
    with _lock:
        return dict(_unavailable)


def clear() -> None:
    with _lock:
        _unavailable.clear()


__all__ = [
    "UNAVAILABLE_TTL_S",
    "clear",
    "is_model_unavailable_error",
    "is_unavailable",
    "mark_unavailable",
    "unavailable_models",
]
