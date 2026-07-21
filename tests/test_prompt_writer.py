"""Tests for the composable prompt assembly module."""
from __future__ import annotations

import pytest

from aios.core.prompt_writer import PromptSection, PromptWriter, _estimate_tokens, _truncate_to_tokens


class TestEstimateTokens:
    def test_empty_string(self):
        assert _estimate_tokens("") == 1

    def test_single_word(self):
        assert _estimate_tokens("hello") == 1

    def test_multiple_words(self):
        assert _estimate_tokens("hello world foo bar") == 4


class TestTruncateToTokens:
    def test_short_text_unchanged(self):
        assert _truncate_to_tokens("hello world", 10) == "hello world"

    def test_long_text_truncated(self):
        text = " ".join(f"word{i}" for i in range(20))
        result = _truncate_to_tokens(text, 5)
        assert len(result.split()) == 5

    def test_exact_boundary(self):
        text = "a b c d e"
        assert _truncate_to_tokens(text, 5) == "a b c d e"


class TestPromptSection:
    def test_frozen_dataclass(self):
        section = PromptSection(name="test", priority=10, render=lambda: "hello")
        with pytest.raises(Exception):
            section.name = "changed"  # type: ignore[misc]


class TestPromptWriter:
    def test_persona_always_included(self):
        writer = PromptWriter("You are GAGOS.", [], total_budget=4000)
        result = writer.assemble("hello")
        assert "You are GAGOS." in result

    def test_sections_in_priority_order(self):
        order: list[str] = []
        writer = PromptWriter(
            "Persona.",
            [
                PromptSection(
                    name="low",
                    priority=10,
                    render=lambda: (order.append("low"), "Low priority")[1],
                ),
                PromptSection(
                    name="high",
                    priority=90,
                    render=lambda: (order.append("high"), "High priority")[1],
                ),
            ],
            total_budget=4000,
        )
        result = writer.assemble("query")
        assert order == ["high", "low"]
        high_pos = result.index("High priority")
        low_pos = result.index("Low priority")
        assert high_pos < low_pos

    def test_empty_section_skipped(self):
        writer = PromptWriter(
            "Persona.",
            [
                PromptSection(name="empty", priority=90, render=lambda: None),
                PromptSection(name="blank", priority=80, render=lambda: ""),
                PromptSection(name="real", priority=70, render=lambda: "Real content"),
            ],
            total_budget=4000,
        )
        result = writer.assemble("query")
        assert "Real content" in result
        parts = result.split("\n\n")
        assert len(parts) == 2

    def test_section_max_tokens_truncation(self):
        long_text = " ".join(f"word{i}" for i in range(100))
        writer = PromptWriter(
            "P.",
            [PromptSection(name="long", priority=50, render=lambda: long_text, max_tokens=10)],
            total_budget=4000,
        )
        result = writer.assemble("q")
        section_text = result.split("\n\n")[1]
        assert len(section_text.split()) <= 10

    def test_total_budget_respected(self):
        big_section = " ".join(f"w{i}" for i in range(500))
        writer = PromptWriter(
            "Short persona.",
            [
                PromptSection(name="big", priority=90, render=lambda: big_section),
                PromptSection(name="extra", priority=10, render=lambda: "Should be cut"),
            ],
            total_budget=20,
        )
        result = writer.assemble("q")
        total_words = len(result.split())
        assert total_words <= 25

    def test_backward_compat_same_output_shape(self):
        """The assembled prompt is a single string joining persona + sections."""
        writer = PromptWriter(
            "System prompt.",
            [PromptSection(name="facts", priority=90, render=lambda: "Fact block.")],
            total_budget=4000,
        )
        result = writer.assemble("hi")
        assert result == "System prompt.\n\nFact block."
