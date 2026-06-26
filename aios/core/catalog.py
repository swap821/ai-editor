"""Cloud model catalog — route across the MANY models a provider offers.

By default the cross-provider router routes among **one** model per cloud provider
(the configured ``BEDROCK_MODEL`` / ``GEMINI_MODEL``). The operator's point: AWS and
Vertex each offer many models — the library shouldn't be limited to one. This
expands the candidate set to the provider's **actual catalog**, discovered once per
process from the live client (the account's invocable Bedrock models / the project's
Gemini models), so ``auto`` + failover + evidence-calibration pick across the breadth.

Discovery is account-accurate (a model only appears if the client lists it as
invocable), so a frontier model is offered only where it can actually run — and the
failover cascade rides past any that still error. Capability here is a coarse
heuristic (refined by calibration); a small bonus keeps the operator's configured
default a strong, known-good cold-start option.
"""
from __future__ import annotations

from typing import Any

#: Capability-tier keywords (matched as substrings of the lowercased model id).
# NB: substring match — avoid keywords that appear inside other names (e.g. "mini"
# is INSIDE "gemini", so it is excluded; "-mini"/"haiku"/"lite" stand in for light tiers).
_FRONTIER = ("opus", "-pro", "gpt-4", "ultra", "sonnet", "command-r-plus", "405b", "70b", "72b")
_STRONG = ("flash", "large", "mixtral", "command-r")
_LIGHT = ("haiku", "lite", "-mini", "nano", "small", "8b", "1b", "3b")

#: Capability bump for the operator's configured default — a known-good model the
#: account can definitely invoke, so cold-start prefers it before evidence exists.
DEFAULT_BONUS = 20
#: Re-discover the cloud catalog every 5 minutes so newly enabled models appear and
#: recently removed models disappear without a process restart.
CATALOG_TTL_SECONDS = 300

_CACHE: dict[str, tuple[list[str], float]] = {}


def cloud_capability(model_id: str) -> int:
    """Coarse capability score for a cloud *model_id* (calibration refines it)."""
    s = model_id.lower()
    if "sonnet" in s or "opus" in s:
        return 360
    if any(k in s for k in _LIGHT):
        return 250
    if any(k in s for k in _FRONTIER):
        return 340
    if any(k in s for k in _STRONG):
        return 300
    return 290  # unknown cloud model — assume broadly capable


def catalog_models(client: Any, provider_name: str, default_model: str) -> list[str]:
    """The provider's invocable model ids (discovered once, cached per process).

    Always includes *default_model* (first). Falls back to ``[default_model]`` on any
    discovery error/empty — so a turn is never broken by discovery, and a working
    multi-model discovery is cached while a bare fallback is not (a later real
    discovery can still replace it). The cache expires after ``CATALOG_TTL_SECONDS``
    so model additions/removals are reflected without a restart.
    """
    import time

    now = time.time()
    cached = _CACHE.get(provider_name)
    if cached is not None:
        ids, cached_at = cached
        if now - cached_at < CATALOG_TTL_SECONDS:
            return ids
        _CACHE.pop(provider_name, None)
    ids: list[str] = []
    try:
        for m in client.list_models() or []:
            mid = m.get("id") if isinstance(m, dict) else None
            if mid:
                ids.append(str(mid))
    except Exception:  # noqa: BLE001 - discovery must never break a turn
        ids = []
    if default_model and default_model not in ids:
        ids.insert(0, default_model)
    if not ids:
        ids = [default_model] if default_model else []
    if len(ids) > 1:  # only cache a real multi-model discovery
        _CACHE[provider_name] = (ids, now)
    return ids


def clear_catalog_cache() -> None:
    """Drop the discovery cache (tests; or to force a re-discovery)."""
    _CACHE.clear()
