"""What metered cloud calls used and cost, and the ceiling over all of them.

Codex's design conditions for GAGOS (2026-11-02): "Respect operator spend
ceiling and record actual usage; AWS Budgets notifications are delayed, not a
synchronous hard cap." Until 2026-11-10 the gateway discarded the token counts
the providers return, and only GAGOS's workshop held a ceiling, over its own
calls, on a character-count estimate. Here (2026-11-10):

* every metered provider adapter (``aios/core/{bedrock,gemini,anthropic_direct,
  openai_compat}.py``) records the tokens the provider reports for each call
  (:func:`record_usage`); a stream that reports none is recorded from its
  characters and marked ``estimated``;
* :func:`model_calls.observe`, which every adapter calls before a request
  leaves, refuses a metered call once this UTC month's recorded spend has
  reached :data:`aios.config.CLOUD_MONTHLY_USD` (the operator, 2026-11-02:
  "$100 a month for AWS"), whatever entrance or caller it came from. The
  refusal is an :class:`~aios.core.llm.LLMError`, so a turn's failover moves
  on to the next brain, the local one last.

What a token costs is not read from any bill: :data:`PRICE_PER_MTOK` is one
deliberately high price for every metered model, so the recorded spend
over-states the bill. A ceiling checked before each call, against calls
already settled, can be passed by the calls in flight when it is reached --
a few cents at the sizes GAGOS sends; that bound is the honest one, not a
hard cap. Free brains (the local one and the operator's subscription plans)
are never metered.

The record is ``<data>/cloud_spend/<UTC month>.jsonl``, one line per call:
provider, model, tokens in and out, USD, whether estimated. No prompt, no
output, no key. It is kept whole for the month; the model-call ledger's
thirty-day pruning does not touch it.
"""

from __future__ import annotations

import functools
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Optional, TypeVar

from aios.core.llm import LLMError

_T = TypeVar("_T")

#: USD per million tokens (input, output) for every metered model: a
#: deliberately high price, the one GAGOS's workshop has used since 2026-11-02.
PRICE_PER_MTOK = (1.00, 4.00)
#: When a provider reports no tokens, characters are counted as tokens at this
#: rate (over-counting them).
CHARS_PER_TOKEN = 3

_LOCK = threading.Lock()
_LAST = threading.local()
_CACHE: dict[str, tuple[int, float, float]] = {}


class CloudSpendCeilingReached(LLMError):
    """A metered call refused before it left: the month's ceiling is reached."""


@functools.lru_cache(maxsize=1)
def free_call_providers() -> frozenset[str]:
    """The model-call ledger's names for brains that cost nothing per call: the
    registry's local brains and the operator's plans. Every other provider is
    metered, so a provider added later counts until it is named here."""
    from aios.core.router import PROVIDER_PLAN, PROVIDERS

    return frozenset({p.name for p in PROVIDERS if not p.is_cloud} | {PROVIDER_PLAN})


def is_metered(provider: str) -> bool:
    return provider not in free_call_providers()


def ceiling_usd() -> float:
    """This month's ceiling over every metered call, USD."""
    from aios import config

    return float(config.CLOUD_MONTHLY_USD)


def usd(tokens_in: int, tokens_out: int) -> float:
    price_in, price_out = PRICE_PER_MTOK
    return (max(0, tokens_in) * price_in + max(0, tokens_out) * price_out) / 1e6


def _month(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m")


def _path(month: str) -> Path:
    from aios import config

    return Path(config.DATA_DIR) / "cloud_spend" / f"{month}.jsonl"


def record_usage(
    provider: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    *,
    estimated: bool = False,
) -> dict[str, Any]:
    """Record one metered call's usage; also kept as this thread's last usage.
    A free provider's call is not recorded (it costs nothing)."""
    now = datetime.now(timezone.utc)
    record = {
        "ts": now.isoformat(),
        "provider": provider,
        "model": model,
        "tokens_in": int(tokens_in),
        "tokens_out": int(tokens_out),
        "usd": round(usd(int(tokens_in), int(tokens_out)), 6),
        "estimated": bool(estimated),
        "pid": os.getpid(),
    }
    _LAST.usage = record
    if not is_metered(provider):
        return record
    path = _path(_month(now))
    with _LOCK:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
        except OSError:
            # Under-counting is the risk of a lost line; the call has happened.
            pass
    return record


def record_estimated(provider: str, model: str, chars_in: int, chars_out: int) -> dict:
    """A call whose provider reported no tokens, recorded from its characters."""
    return record_usage(
        provider,
        model,
        -(-int(chars_in) // CHARS_PER_TOKEN),
        -(-int(chars_out) // CHARS_PER_TOKEN),
        estimated=True,
    )


def last_usage() -> Optional[dict[str, Any]]:
    """The usage this thread's most recent call recorded, or None."""
    return getattr(_LAST, "usage", None)


def forget_last_usage() -> None:
    _LAST.usage = None


def month_spend(month: Optional[str] = None) -> float:
    """What this UTC month's metered calls are recorded to have cost, USD."""
    path = _path(month or _month())
    try:
        stat = path.stat()
    except OSError:
        return 0.0
    key = str(path)
    with _LOCK:
        cached = _CACHE.get(key)
        if cached and cached[0] == stat.st_size and cached[1] == stat.st_mtime:
            return cached[2]
        total = 0.0
        try:
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    try:
                        total += float(json.loads(line).get("usd") or 0.0)
                    except (ValueError, AttributeError):
                        continue
        except OSError:
            return 0.0
        _CACHE[key] = (stat.st_size, stat.st_mtime, total)
        return total


def month_records(month: Optional[str] = None) -> list[dict[str, Any]]:
    """This month's recorded calls, oldest first."""
    path = _path(month or _month())
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def ensure_under_ceiling(provider: str, model: str) -> None:
    """Refuse a metered call once the month's recorded spend reached the
    ceiling (:class:`CloudSpendCeilingReached`)."""
    if not is_metered(provider):
        return
    spent, ceiling = month_spend(), ceiling_usd()
    if spent >= ceiling:
        raise CloudSpendCeilingReached(
            f"{provider} {model}: this month's cloud spend is recorded at "
            f"${spent:.2f}, at the operator's ceiling of ${ceiling:.2f} "
            "(AIOS_CLOUD_MONTHLY_USD); no metered call leaves until next month"
        )


def counted_stream(
    chunks: Iterable[_T],
    provider: str,
    model: str,
    usage_of: Callable[[_T], Optional[tuple[int, int]]],
    *,
    chars_in: int = 0,
    text_of: Optional[Callable[[_T], str]] = None,
) -> Iterator[_T]:
    """Pass a provider's stream through, recording its usage when it ends: the
    last tokens it reported, or, when it reported none and *text_of* is given,
    its characters (estimated)."""
    seen: Optional[tuple[int, int]] = None
    chars_out = 0
    try:
        for chunk in chunks:
            found = usage_of(chunk)
            if found is not None:
                seen = (
                    max(found[0], seen[0] if seen else 0),
                    max(found[1], seen[1] if seen else 0),
                )
            if text_of is not None:
                chars_out += len(text_of(chunk) or "")
            yield chunk
    finally:
        if seen is not None:
            record_usage(provider, model, seen[0], seen[1])
        elif text_of is not None and (chars_in or chars_out):
            record_estimated(provider, model, chars_in, chars_out)


__all__ = [
    "CHARS_PER_TOKEN",
    "CloudSpendCeilingReached",
    "PRICE_PER_MTOK",
    "ceiling_usd",
    "counted_stream",
    "ensure_under_ceiling",
    "forget_last_usage",
    "free_call_providers",
    "is_metered",
    "last_usage",
    "month_records",
    "month_spend",
    "record_estimated",
    "record_usage",
    "usd",
]
