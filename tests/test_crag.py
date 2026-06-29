"""CRAG Slice 1 — decompose-then-recompose context refinement.

The single biggest accuracy driver in the CRAG ablation (-5.1% when removed):
shatter retrieved context into sentence strips, drop the noise (sub-min_chars
fragments + strips with no query relevance), recompose only the golden strips.
Pure + deterministic by default (uses aios.memory.relevance); an optional `keep`
callback can override the filter. See
docs/superpowers/specs/2026-06-29-crag-for-gagos-design.md.
"""
from __future__ import annotations

from aios.memory.crag import refine_context


def test_refine_keeps_golden_sentence_and_drops_filler() -> None:
    query = "capital of France"
    doc = (
        "This document was written long ago by many authors. "
        "The capital of France is Paris, a major European city. "
        "We hope you enjoyed reading this introductory paragraph."
    )
    refined = refine_context(query, [doc])
    assert "Paris" in refined  # the golden strip survived
    assert "capital of France" in refined
    assert "enjoyed reading" not in refined  # pure filler dropped
    assert len(refined) < len(doc)  # denser than the original


def test_refine_drops_short_fragments() -> None:
    query = "alpha beta"
    doc = "OK. The alpha and beta parameters control the model behavior precisely."
    refined = refine_context(query, [doc])
    assert "OK." not in refined  # sub-20-char fragment dropped
    assert "alpha" in refined and "beta" in refined


def test_refine_recompose_preserves_order() -> None:
    query = "sky ocean"
    doc = "The sky is blue and vast above us. The ocean is deep and wide below us."
    refined = refine_context(query, [doc])
    assert refined.index("sky") < refined.index("ocean")


def test_refine_empty_input_is_empty() -> None:
    assert refine_context("q", []) == ""
    assert refine_context("q", ["   ", ""]) == ""
    assert refine_context("q", ["short"]) == ""  # all fragments below min_chars


def test_refine_never_blanks_when_no_lexical_overlap() -> None:
    # A long sentence with zero query-term overlap still yields its best strip,
    # never an empty block — the never-blank contract for the default path.
    query = "quantum entanglement"
    doc = "The garden was full of blooming roses and tall green trees in summer."
    refined = refine_context(query, [doc])
    assert refined != ""
    assert "garden" in refined


def test_refine_custom_keep_callback_controls_filtering() -> None:
    query = "anything"
    doc = "First candidate sentence here now. Second candidate sentence here now."
    refined = refine_context(query, [doc], keep=lambda _q, s: "Second" in s)
    assert "Second" in refined
    assert "First" not in refined


def test_refine_keep_callback_error_keeps_strip() -> None:
    # A model-backed strip filter that throws must NOT drop real context (fail-open
    # at the strip level — recall is an enhancement, never a gate).
    def boom(_q: str, _s: str) -> bool:
        raise RuntimeError("strip judge unreachable")

    doc = "This is a sufficiently long sentence to survive decomposition cleanly."
    refined = refine_context("q", [doc], keep=boom)
    assert "sufficiently long sentence" in refined


def test_refine_spans_multiple_documents_in_order() -> None:
    query = "tea coffee"
    refined = refine_context(
        query,
        [
            "The morning tea was warm and comforting on a cold day.",
            "Some unrelated filler about distant mountains and rivers.",
            "The afternoon coffee was strong and bitter as usual today.",
        ],
    )
    assert "tea" in refined and "coffee" in refined
    assert "mountains" not in refined  # the irrelevant middle document dropped
    assert refined.index("tea") < refined.index("coffee")
