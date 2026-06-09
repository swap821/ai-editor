"""Tests for deterministic developmental-memory relevance helpers."""
from __future__ import annotations

from aios.memory.relevance import content_hash, relevance, signature, tokens


def test_tokens_normalize_and_remove_low_signal_words() -> None:
    assert tokens("Use THE API/path.py with Parser_One") == {
        "api/path.py",
        "parser_one",
    }


def test_relevance_is_zero_without_overlap_and_bounded_with_overlap() -> None:
    assert relevance("deploy api", "write frontend css") == 0.0
    score = relevance("deploy api safely", "verify api deploy")
    assert 0.0 < score <= 1.0


def test_signature_is_order_independent_after_normalization() -> None:
    assert signature("deploy the api") == signature("API deploy")


def test_content_hash_normalizes_case_and_whitespace_only() -> None:
    assert content_hash(" Same   Knowledge\n") == content_hash("same knowledge")
    assert content_hash("same knowledge") != content_hash("different knowledge")
