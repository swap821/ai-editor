"""Deterministic lexical relevance helpers for developmental memory.

These helpers deliberately avoid an LLM judge. They are used for lesson, skill,
and outcome retrieval where a transparent, stable score is preferable to a
probabilistic decision about whether past evidence should change behavior.
"""
from __future__ import annotations

import hashlib
import math
import re

_TOKEN = re.compile(r"[a-z0-9_./-]+")
_STOP = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "do", "for",
        "from", "how", "i", "in", "is", "it", "of", "on", "or", "the",
        "this", "to", "use", "with",
    }
)


def tokens(text: str) -> set[str]:
    """Return normalized, low-noise tokens from *text*."""
    return {token for token in _TOKEN.findall((text or "").lower()) if token not in _STOP}


def relevance(query: str, document: str) -> float:
    """Cosine-style set overlap in ``[0, 1]``; zero means no lexical evidence."""
    query_tokens = tokens(query)
    document_tokens = tokens(document)
    if not query_tokens or not document_tokens:
        return 0.0
    overlap = len(query_tokens & document_tokens)
    if not overlap:
        return 0.0
    return round(overlap / math.sqrt(len(query_tokens) * len(document_tokens)), 6)


def signature(text: str) -> str:
    """Stable non-secret signature for grouping similar normalized task text."""
    normalized = " ".join(sorted(tokens(text)))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def content_hash(text: str) -> str:
    """Hash text after whitespace/case normalization for exact consolidation."""
    normalized = " ".join((text or "").lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
