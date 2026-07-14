"""Bounded trace context shared by HTTP, mission and worker boundaries.

Trace values are correlation metadata only. They never authenticate a caller,
grant capabilities, or widen a mission scope.
"""
from __future__ import annotations

import re
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import Iterator, Mapping


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TRACE: ContextVar["TraceContext | None"] = ContextVar("gagos_trace_context", default=None)


@dataclass(frozen=True, slots=True)
class TraceContext:
    request_id: str
    turn_id: str | None = None
    mission_id: str | None = None
    action_id: str | None = None
    worker_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None

    def headers(self) -> dict[str, str]:
        """Return only non-empty trace headers for downstream propagation."""
        values = {
            "x-request-id": self.request_id,
            "x-turn-id": self.turn_id,
            "x-mission-id": self.mission_id,
            "x-action-id": self.action_id,
            "x-worker-id": self.worker_id,
            "x-correlation-id": self.correlation_id,
            "x-causation-id": self.causation_id,
        }
        return {key: value for key, value in values.items() if value}

    def with_ids(self, **values: str | None) -> "TraceContext":
        allowed = {
            key: _normalize_id(value) if value is not None else None
            for key, value in values.items()
            if key in {
                "turn_id",
                "mission_id",
                "action_id",
                "worker_id",
                "correlation_id",
                "causation_id",
            }
        }
        return replace(self, **allowed)


def _normalize_id(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized or not _SAFE_ID.fullmatch(normalized):
        return None
    return normalized


def new_trace_context(headers: Mapping[str, str] | None = None) -> TraceContext:
    """Build a safe context from headers, generating a request id when needed."""
    source = {str(key).lower(): str(value) for key, value in (headers or {}).items()}
    request_id = _normalize_id(source.get("x-request-id")) or str(uuid.uuid4())
    return TraceContext(
        request_id=request_id,
        turn_id=_normalize_id(source.get("x-turn-id")),
        mission_id=_normalize_id(source.get("x-mission-id")),
        action_id=_normalize_id(source.get("x-action-id")),
        worker_id=_normalize_id(source.get("x-worker-id")),
        correlation_id=_normalize_id(source.get("x-correlation-id")),
        causation_id=_normalize_id(source.get("x-causation-id")),
    )


def get_trace_context() -> TraceContext:
    current = _TRACE.get()
    return current if current is not None else new_trace_context()


@contextmanager
def bind_trace_context(context: TraceContext) -> Iterator[TraceContext]:
    token = _TRACE.set(context)
    try:
        yield context
    finally:
        _TRACE.reset(token)


def set_trace_context(context: TraceContext) -> None:
    """Set context for code that owns the surrounding request lifecycle."""
    _TRACE.set(context)


__all__ = [
    "TraceContext",
    "bind_trace_context",
    "get_trace_context",
    "new_trace_context",
    "set_trace_context",
]
