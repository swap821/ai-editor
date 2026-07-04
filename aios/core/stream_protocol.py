"""Streaming protocol types for tool-aware cloud token streaming (C4)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StreamFinished:
    """Sentinel yielded as the last item from a streaming-with-tools iterator.

    Text chunks are yielded as plain ``str``; this final value carries the
    accumulated content and any tool_calls the model produced.
    """

    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    content: str = ""
