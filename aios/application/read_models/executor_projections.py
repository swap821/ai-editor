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


class IsolatedExecutorLiveAuthority:
    """Own the truthful executor reachability projection used by the mirror.

    The owner never substitutes configuration for a health result: an
    unconfigured client is unavailable, and a configured client must complete
    its authenticated ``/health`` call before reachability is measured.
    """

    def project(self, client: StructuredExecutorClient | None) -> ExecutorStatusProjection:
        """Return measured executor state or an explicit unavailable envelope."""
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


_ISOLATED_EXECUTOR_LIVE_AUTHORITY = IsolatedExecutorLiveAuthority()


def get_isolated_executor_live_authority() -> IsolatedExecutorLiveAuthority:
    return _ISOLATED_EXECUTOR_LIVE_AUTHORITY


def project_executor_status(client: StructuredExecutorClient | None) -> ExecutorStatusProjection:
    """Compatibility function for existing projection callers and tests."""
    return _ISOLATED_EXECUTOR_LIVE_AUTHORITY.project(client)


__all__ = [
    "IsolatedExecutorLiveAuthority",
    "get_isolated_executor_live_authority",
    "project_executor_status",
]
