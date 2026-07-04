"""Composable prompt assembly with prioritized, budgeted sections.

Replaces hardcoded string concatenation with a declarative assembly pipeline:
each section has a priority, an optional token budget, and a render callable.
The writer assembles them in priority order, respecting the total budget.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


def _estimate_tokens(text: str) -> int:
    """Cheap whitespace-based token estimate (~1.3 words per token for English)."""
    return max(1, len(text.split()))


@dataclass(frozen=True)
class PromptSection:
    """A named, prioritized section of a system prompt.

    Higher priority sections are included first. If the rendered text exceeds
    max_tokens, it is truncated (word-boundary) to fit.
    """

    name: str
    priority: int
    render: Callable[[], Optional[str]]
    max_tokens: int = 0


class PromptWriter:
    """Assemble a system prompt from prioritized sections within a budget.

    Sections are rendered in priority order (highest first). Each section that
    returns non-empty text is included up to the total budget. A section whose
    rendered output exceeds its own max_tokens is truncated.
    """

    def __init__(
        self,
        persona: str,
        sections: list[PromptSection],
        *,
        total_budget: int = 4000,
    ) -> None:
        self._persona = persona
        self._sections = sorted(sections, key=lambda s: s.priority, reverse=True)
        self._total_budget = total_budget

    def assemble(self, query: str) -> str:  # noqa: ARG002
        """Build the final system prompt string within budget."""
        parts: list[str] = [self._persona]
        remaining = self._total_budget - _estimate_tokens(self._persona)

        for section in self._sections:
            if remaining <= 0:
                break
            text = section.render()
            if not text:
                continue
            tokens = _estimate_tokens(text)
            if section.max_tokens > 0 and tokens > section.max_tokens:
                text = _truncate_to_tokens(text, section.max_tokens)
                tokens = section.max_tokens
            if tokens > remaining:
                text = _truncate_to_tokens(text, remaining)
                tokens = remaining
            parts.append(text)
            remaining -= tokens

        return "\n\n".join(parts)


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to approximately max_tokens words."""
    words = text.split()
    if len(words) <= max_tokens:
        return text
    return " ".join(words[:max_tokens])
