"""Organ 40: a truthful projector for the isolated private executor service.

`ExecutorService` (`aios/application/executor/service.py`) and its production
DI accessor `get_private_executor_service` (`aios/api/deps.py`) already exist;
nothing here invents a value. `configured` is read from the client's own
settings (no network call). `reachable`/`runtime` come from a real
authenticated call to the service's `/health` endpoint
(`aios/executor_service.py::health`) and stay `MetricStatus.UNAVAILABLE` when
unconfigured or unreachable -- never guessed as healthy.
"""

from __future__ import annotations

from typing import Any

from aios.application.executor.service import IsolationUnavailable, StructuredExecutorClient
from aios.domain.read_models.contracts import (
    ExecutorStatusProjection,
    MetricEnvelope,
    MetricStatus,
)


def _measured(value: Any, source: str) -> MetricEnvelope:
    return MetricEnvelope(value=value, status=MetricStatus.MEASURED, source=source, freshness=0)


def _unavailable(source: str) -> MetricEnvelope:
    return MetricEnvelope(value=None, status=MetricStatus.UNAVAILABLE, source=source, freshness=None)


def project_executor_status(client: StructuredExecutorClient | None) -> ExecutorStatusProjection:
    """Project the private executor's real, current reachability.

    `client` is the real `ExecutorService.client` -- `None` only in a test
    double that never configured one. A configured client with no base_url
    or token fails `.health()` instantly (no network call); a configured,
    unreachable one fails after a real bounded HTTP attempt. Both are
    reported as an honest `reason`, never silently swallowed.
    """
    source = "executor_service_health"
    if client is None or not client.base_url or not client.token:
        return ExecutorStatusProjection(
            configured=_measured(False, source),
            reachable=_unavailable(source),
            runtime=_unavailable(source),
            reason=_measured("private executor service is not configured", source),
        )
    try:
        payload = client.health()
    except IsolationUnavailable as exc:
        return ExecutorStatusProjection(
            configured=_measured(True, source),
            reachable=_measured(False, source),
            runtime=_unavailable(source),
            reason=_measured(str(exc), source),
        )
    return ExecutorStatusProjection(
        configured=_measured(True, source),
        reachable=_measured(True, source),
        runtime=_measured(payload.get("runtime"), source),
        reason=_unavailable(source),
    )


__all__ = ["project_executor_status"]
