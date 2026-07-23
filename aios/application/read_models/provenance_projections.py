"""Organ 50 (half): a truthful projector for "why was this model chosen".

`DevelopmentTracker.recent_routing_decisions()` (`aios/memory/development.py`)
is a pure read of `development_events.metadata_json`, already durably written
by `generate_pipeline.py`'s `route_meta()` on every real `/api/generate` turn
-- nothing here invents a value. This deliberately does NOT answer "what was
sent / what was removed" (the `PrivacyFilter` audit): that data is computed
at multiple provider call sites (`FailoverChatClient` plus each cloud
client) and today is only logged, never durably captured -- a real,
separate, still-open gap this module does not paper over.
"""

from __future__ import annotations

from aios.domain.read_models.contracts import (
    MetricEnvelope,
    MetricStatus,
    RoutingDecisionProjection,
)
from aios.memory.development import DevelopmentTracker


def _measured(value: object, source: str) -> MetricEnvelope:
    return MetricEnvelope(value=value, status=MetricStatus.MEASURED, source=source, freshness=0)


def _unavailable(source: str) -> MetricEnvelope:
    return MetricEnvelope(value=None, status=MetricStatus.UNAVAILABLE, source=source, freshness=None)


def project_routing_decisions(
    tracker: DevelopmentTracker,
    *,
    limit: int = 10,
) -> tuple[RoutingDecisionProjection, ...]:
    """Project the most recent real turns' routing decisions, newest first.

    A field genuinely absent from a given event's metadata (e.g. an older
    event recorded before `turn_id` was added to `route_meta()`) stays
    `UNAVAILABLE` for that field alone, never guessed.
    """
    source = "development_tracker"
    projections = []
    for decision in tracker.recent_routing_decisions(limit=limit):
        projections.append(
            RoutingDecisionProjection(
                turn_id=(
                    _measured(decision["turn_id"], source)
                    if decision.get("turn_id")
                    else _unavailable(source)
                ),
                provider=_measured(decision["provider"], source),
                model=_measured(decision["model"], source),
                privacy=(
                    _measured(decision["privacy"], source)
                    if decision.get("privacy")
                    else _unavailable(source)
                ),
                task=(
                    _measured(decision["task"], source)
                    if decision.get("task")
                    else _unavailable(source)
                ),
                auto=(
                    _measured(decision["auto"], source)
                    if decision.get("auto") is not None
                    else _unavailable(source)
                ),
                recorded_at=_measured(decision["timestamp"], source),
            )
        )
    return tuple(projections)


__all__ = ["project_routing_decisions"]
