"""Immutable context for a single human directive."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class TurnMode(str, Enum):
    """Canonical mode a turn resolves into.

    Modes are mutually exclusive and determine which runtime path serves the
    directive. They are decided deterministically from the request surface,
    not inferred by an LLM.
    """

    CONVERSATION = "conversation"
    ADVISORY = "advisory"
    MISSION = "mission"
    GOVERNANCE = "governance"


@dataclass(frozen=True)
class TurnContext:
    """Everything the coordinator needs to route and execute one turn.

    A ``turn_id`` is distinct from ``session_id``. A session may contain many
    turns; events, memory and missions all reference the same ``turn_id`` for
    one human directive.
    """

    turn_id: str
    session_id: str
    operator_id: Optional[str]
    project_id: Optional[str]
    directive: str
    mode: TurnMode
    model_id: Optional[str]
    approval_tokens: tuple[str, ...]
    data_classification: str = "PROJECT_INTERNAL"
    correlation_id: Optional[str] = None
    created_at: datetime = datetime.now(timezone.utc)
    status: str = "active"
    metadata: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})
