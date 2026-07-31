"""Bounded trace context shared by HTTP, mission and worker boundaries.

Trace values are correlation metadata only. They never authenticate a caller,
grant capabilities, or widen a mission scope.

Organ 52 (`ObservabilityAuthority`) owns the process context state; this
module keeps the historical import surface as thin aliases.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Mapping

from aios.application.observability.authority import (
    TraceContext,
    get_tracing_authority,
)


def new_trace_context(headers: Mapping[str, str] | None = None) -> TraceContext:
    """Build a safe context from headers, generating a request id when needed."""
    return get_tracing_authority().context_from_headers(headers or {})


def get_trace_context() -> TraceContext:
    return get_tracing_authority().current_context()


@contextmanager
def bind_trace_context(context: TraceContext) -> Iterator[TraceContext]:
    with get_tracing_authority().bind(context) as bound:
        yield bound


def set_trace_context(context: TraceContext) -> None:
    """Set context for code that owns the surrounding request lifecycle."""
    get_tracing_authority().set_context(context)


__all__ = [
    "TraceContext",
    "bind_trace_context",
    "get_trace_context",
    "new_trace_context",
    "set_trace_context",
]
