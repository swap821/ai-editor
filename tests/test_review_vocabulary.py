"""One vocabulary for a review of a change (2026-11-10).

The consistency plan asked for the council's Critique queen and GAGOS's
workshop reviewer to share one verdict schema. Pinned here: the workshop reads
the one schema and parser, and a queen's verdict maps onto the same words in
one place, where an unknown word never reads as consent.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from aios.domain import reviews
from aios.maintenance import daily_work as dw


def test_the_workshop_reads_the_one_schema_and_parser() -> None:
    assert dw.REVIEW_SCHEMA is reviews.REVIEW_SCHEMA
    assert dw.parse_review is reviews.parse_review
    assert reviews.REVIEW_SCHEMA["properties"]["verdict"]["enum"] == list(
        reviews.REVIEW_VERDICTS
    )
    assert set(reviews.REVIEW_VERDICTS) < set(reviews.ADVISORY_VERDICTS)


def test_a_reviewers_answer_is_read_one_way() -> None:
    assert reviews.parse_review('{"verdict": "accept", "reason": " ok "}') == (
        "accept",
        "ok",
    )
    for bad in ('{"verdict": "defer", "reason": "x"}', "[]", '{"verdict": "accept"}'):
        with pytest.raises(ValueError):
            reviews.parse_review(bad)


def test_a_queens_verdict_maps_onto_the_same_words() -> None:
    def queen(word: str):
        return SimpleNamespace(verdict=word, reason=" because ")

    assert reviews.queen_review(queen("allow")) == ("accept", "because")
    assert reviews.queen_review(queen("deny")) == ("reject", "because")
    assert reviews.queen_review(queen("defer"))[0] == "defer"
    assert reviews.queen_review(queen("allow_with_approval"))[0] == "defer"
    assert reviews.queen_review(queen("something new"))[0] == "defer", (
        "an unknown word never reads as consent"
    )
