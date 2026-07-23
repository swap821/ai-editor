"""Organ 50: truthful projectors for "why was this model chosen" and "what
was sent / what was removed".

`DevelopmentTracker.recent_routing_decisions()` (`aios/memory/development.py`)
is a pure read of `development_events.metadata_json`, already durably written
by `generate_pipeline.py`'s `route_meta()` on every real `/api/generate` turn.
`PrivacyAuditTracker.recent()` (`aios/application/models/privacy_audit.py`)
is a pure read of a process-local ring buffer fed by the real
`PrivacyFilter.filter()` audit dict at all 5 real call sites
(`FailoverChatClient` plus each of the 4 direct cloud clients). Nothing here
invents a value.
"""

from __future__ import annotations

from aios.application.models.privacy_audit import PrivacyAuditTracker
from aios.domain.read_models.contracts import (
    MetricEnvelope,
    MetricStatus,
    PrivacyAuditProjection,
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


def project_privacy_audits(
    tracker: PrivacyAuditTracker,
    *,
    limit: int = 10,
) -> tuple[PrivacyAuditProjection, ...]:
    """Project the most recent real `PrivacyFilter` audits, newest first.

    Every redaction-count field is always present in a real audit dict
    (`PrivacyFilter.filter()`'s own fixed shape), so no field here goes
    `UNAVAILABLE` -- a genuinely empty tracker just yields an empty tuple.
    """
    source = "privacy_audit_tracker"
    projections = []
    for record in tracker.recent(limit=limit):
        audit = record.audit
        projections.append(
            PrivacyAuditProjection(
                provider=_measured(record.provider, source),
                redacted_system=_measured(audit.get("redacted_system", 0), source),
                redacted_paths=_measured(audit.get("redacted_paths", 0), source),
                redacted_credentials=_measured(audit.get("redacted_credentials", 0), source),
                redacted_secrets=_measured(audit.get("redacted_secrets", 0), source),
                redacted_tool_files=_measured(audit.get("redacted_tool_files", 0), source),
                truncated_history=_measured(audit.get("truncated_history", 0), source),
                dropped_messages=_measured(audit.get("dropped_messages", 0), source),
                recorded_at=_measured(record.recorded_at, source),
            )
        )
    return tuple(projections)


__all__ = ["project_privacy_audits", "project_routing_decisions"]
