"""Corrective-RAG (CRAG) layer — Slice 1: decompose-then-recompose refinement.

The CRAG ablation makes this the single biggest accuracy driver (-5.1% when
removed, more than any routing pathway): retrieved context is shattered into
sentence-level "knowledge strips", the noise is dropped (sub-min_chars fragments
and strips with no query relevance), and only the surviving golden strips are
recomposed into a dense context block.

This module is pure and deterministic by default — it uses the transparent lexical
:func:`aios.memory.relevance.relevance` scorer, no model, no I/O — so it is cheap,
explainable, and privacy-safe. An optional ``keep`` callback lets a model-backed
strip filter drop in behind the same interface later.

Design: docs/superpowers/specs/2026-06-29-crag-for-gagos-design.md
"""
from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from aios.memory.relevance import relevance

__all__ = ["refine_context"]

#: Excerption-mode split: break on whitespace that FOLLOWS terminal punctuation, so
#: each strip keeps its punctuation and a document with no terminal stays whole.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
#: Collapse irregular whitespace / line breaks before segmentation.
_WHITESPACE = re.compile(r"\s+")


def _decompose(documents: Sequence[str], *, min_chars: int) -> list[str]:
    """Shatter *documents* into normalized sentence strips.

    Sub-``min_chars`` fragments (abrupt transitions, citation brackets) carry no
    standalone factual signal and only consume token budget, so they are dropped.
    """
    strips: list[str] = []
    for document in documents:
        normalized = _WHITESPACE.sub(" ", document or "").strip()
        if not normalized:
            continue
        for sentence in _SENTENCE_SPLIT.split(normalized):
            stripped = sentence.strip()
            if len(stripped) >= min_chars:
                strips.append(stripped)
    return strips


def _safe_keep(keep: Callable[[str, str], bool], query: str, strip: str) -> bool:
    """A model-backed strip filter must never break refinement; on error keep the
    strip (fail-open at the strip level — recall is an enhancement, not a gate)."""
    try:
        return bool(keep(query, strip))
    except Exception:  # noqa: BLE001 - a flaky strip judge must not drop real context
        return True


def refine_context(
    query: str,
    documents: Sequence[str],
    *,
    keep: Callable[[str, str], bool] | None = None,
    min_chars: int = 20,
) -> str:
    """Decompose *documents* into strips, keep only the query-relevant ones, recompose.

    Returns a dense context string of the surviving strips in their original order
    (empty when there is no real content). Deterministic by default — a strip
    survives iff it shares lexical evidence with *query*
    (:func:`aios.memory.relevance.relevance`). Pass ``keep(query, strip) -> bool`` to
    override with a model-backed filter (whose verdict is then authoritative,
    including an intentional empty result).

    Never-blank contract (default path only): if the deterministic filter would drop
    every strip, the single most-relevant strip is retained, so genuinely present
    input is never silently blanked.
    """
    strips = _decompose(documents, min_chars=min_chars)
    if not strips:
        return ""
    if keep is not None:
        kept = [strip for strip in strips if _safe_keep(keep, query, strip)]
        return " ".join(kept)
    kept = [strip for strip in strips if relevance(query, strip) > 0.0]
    if not kept:
        # Never blank present input — fall back to the single most-relevant strip.
        kept = [max(strips, key=lambda strip: relevance(query, strip))]
    return " ".join(kept)
