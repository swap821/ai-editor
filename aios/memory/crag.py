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

import enum
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from aios.memory.relevance import relevance

__all__ = [
    "CalibrationResult",
    "CragAction",
    "RetrievalVerdict",
    "calibrate_thresholds",
    "evaluate_retrieval",
    "external_retrieve",
    "refine_context",
]


class CragAction(enum.Enum):
    """The tripartite corrective routing decision for one retrieval event."""

    CORRECT = "correct"      # local retrieval is good → refine & use it
    AMBIGUOUS = "ambiguous"  # partial → refine local AND (Slice 3) seek external
    INCORRECT = "incorrect"  # local is junk → drop it (Slice 3) and go external


class _Hit(Protocol):
    """Structural view of a retrieved hit (duck-types ``RetrievalResult``)."""

    text: str
    faiss: float


@dataclass(frozen=True)
class RetrievalVerdict:
    """The evaluator's decision plus explainable per-hit confidence scores."""

    action: CragAction
    score: float            # the max per-hit confidence in [0, 1]
    per_hit: list[float]    # one confidence per hit, in retrieval order


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def evaluate_retrieval(
    query: str,
    hits: Sequence[_Hit],
    *,
    upper: float,
    lower: float,
    judge: Callable[[str, str], float] | None = None,
) -> RetrievalVerdict:
    """Score retrieved *hits* for actual relevance and route them tripartite.

    Per-hit confidence is ``max(semantic cosine, lexical relevance)`` — reusing the
    already-computed FAISS sub-score and the deterministic lexical scorer, both on
    ``[0, 1]``; a hit strong on *either* axis survives. ``CORRECT`` if any hit's
    confidence ``>= upper``; ``INCORRECT`` if every hit is ``< lower`` (or there are
    no hits); ``AMBIGUOUS`` otherwise.

    The optional ``judge`` is a caution-only clamp (strengthen-only, like the
    Reasoning King): it may only *lower* a hit's deterministic confidence, never
    raise it — so a hallucinated "this is relevant!" can never rescue junk. A judge
    error is ignored (the deterministic score stands).
    """
    per_hit: list[float] = []
    for hit in hits:
        score = max(_clamp01(getattr(hit, "faiss", 0.0)), relevance(query, hit.text))
        if judge is not None:
            try:
                score = min(score, _clamp01(judge(query, hit.text)))
            except Exception:  # noqa: BLE001 - a flaky judge must not break routing
                pass
        per_hit.append(score)

    best = max(per_hit, default=0.0)
    if best >= upper:
        action = CragAction.CORRECT
    elif best < lower:
        action = CragAction.INCORRECT
    else:
        action = CragAction.AMBIGUOUS
    return RetrievalVerdict(action=action, score=best, per_hit=per_hit)


def external_retrieve(
    query: str,
    sources: Sequence[Callable[[str], Sequence[str]]],
    *,
    per_source_limit: int = 3,
) -> list[str]:
    """Gather candidate external documents from each pluggable *source*, fail-soft.

    Each source is a callable ``query -> texts`` (e.g. a cloud-LLM knowledge call or
    a web-search fetch); the caller decides which sources are enabled (all default
    off, privacy-gated). A source that raises or returns nothing is simply skipped —
    one provider's outage never sinks the others. Up to ``per_source_limit`` texts
    are taken per source, blanks are dropped, and results are de-duplicated
    (case/whitespace-insensitive, order-preserving). The returned texts are raw — the
    caller refines them through :func:`refine_context` and labels them unverified
    before they reach a prompt.
    """
    aggregated: list[str] = []
    seen: set[str] = set()
    for source in sources:
        try:
            texts = source(query) or []
        except Exception:  # noqa: BLE001 - one external source must not break recall
            continue
        for text in list(texts)[:per_source_limit]:
            if not text or not text.strip():
                continue
            key = " ".join(text.lower().split())
            if key in seen:
                continue
            seen.add(key)
            aggregated.append(text)
    return aggregated


@dataclass(frozen=True)
class CalibrationResult:
    """Tuned thresholds plus the two error rates they incur on the labeled data."""

    lower: float
    upper: float
    false_drop_rate: float    # relevant recalls wrongly routed INCORRECT (score < lower)
    false_accept_rate: float  # irrelevant recalls wrongly routed CORRECT (score >= upper)


_DEFAULT_GRID: tuple[float, ...] = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


def calibrate_thresholds(
    labeled: Sequence[tuple[float, bool]],
    *,
    grid: Sequence[float] = _DEFAULT_GRID,
    drop_weight: float = 1.0,
    accept_weight: float = 1.0,
) -> CalibrationResult:
    """Tune ``(lower, upper)`` for the CRAG gate from labeled recalls.

    *labeled* is a list of ``(score, is_relevant)`` — the combined confidence score
    (``max(faiss, lexical)``) a real recall received, paired with whether that recall
    was actually useful. The harness sweeps ``lower <= upper`` over *grid* and
    maximizes a utility that REWARDS correct decisions and penalizes wrong ones, so
    pure hedging (routing everything to AMBIGUOUS) never wins:

        +1 per relevant recall routed CORRECT (score >= upper)
        +1 per irrelevant recall routed INCORRECT (score < lower)
        -drop_weight   per relevant recall wrongly dropped (score < lower)
        -accept_weight per irrelevant recall wrongly trusted (score >= upper)

    Raise ``drop_weight`` to protect recall, ``accept_weight`` to suppress
    hallucination risk. Ties prefer a NARROWER ambiguous band (more decisive).

    Empty input raises — calibrating on no data would be meaningless theater.
    """
    if not labeled:
        raise ValueError("calibrate_thresholds needs at least one labeled example")
    relevant = [score for score, is_rel in labeled if is_rel]
    irrelevant = [score for score, is_rel in labeled if not is_rel]

    best_key: tuple[float, float] | None = None
    best: CalibrationResult | None = None
    for lower in grid:
        for upper in grid:
            if upper < lower:
                continue
            false_drops = sum(s < lower for s in relevant)
            true_accepts = sum(s >= upper for s in relevant)
            false_accepts = sum(s >= upper for s in irrelevant)
            true_drops = sum(s < lower for s in irrelevant)
            # Utility REWARDS correct decisions so pure hedging (all-AMBIGUOUS,
            # which trivially has zero hard errors) never wins.
            utility = (
                true_accepts + true_drops
                - drop_weight * false_drops
                - accept_weight * false_accepts
            )
            fdr = (false_drops / len(relevant)) if relevant else 0.0
            far = (false_accepts / len(irrelevant)) if irrelevant else 0.0
            # Maximize utility; tie-break toward a NARROWER band (more decisive).
            key = (-utility, upper - lower)
            if best_key is None or key < best_key:
                best_key = key
                best = CalibrationResult(lower, upper, fdr, far)
    assert best is not None  # grid is non-empty, so at least lower==upper qualifies
    return best

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
