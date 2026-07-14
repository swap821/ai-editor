"""Fail-closed application gateway to an isolated executor service."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Callable, Protocol

from aios.domain.executor import ExecutorJob, ExecutorResult


class IsolationUnavailable(RuntimeError):
    """Raised when the required isolation boundary cannot be used."""


class JobRunner(Protocol):
    def __call__(self, job: ExecutorJob) -> ExecutorResult:
        ...


class ExecutorService:
    """Dispatch structured jobs to one configured execution backend.

    The control plane owns this client boundary but never the container
    runtime socket. A missing or disallowed backend is a refusal, never a host
    fallback.
    """

    def __init__(
        self,
        *,
        profile: str,
        runner: JobRunner | None = None,
        backend_name: str = "container",
        require_isolation: bool = True,
    ) -> None:
        self.profile = profile
        self.runner = runner
        self.backend_name = backend_name
        self.require_isolation = require_isolation

    def execute(self, job: ExecutorJob) -> ExecutorResult:
        if self.profile == "production" and self.backend_name == "host":
            raise IsolationUnavailable("host execution is forbidden in production")
        if self.require_isolation and self.backend_name != "container":
            raise IsolationUnavailable(
                f"executor backend {self.backend_name!r} does not satisfy isolation"
            )
        if self.runner is None:
            raise IsolationUnavailable("isolated executor service is unavailable")
        result = self.runner(job)
        if result.job_id != job.job_id:
            raise IsolationUnavailable("executor returned a mismatched job id")
        if self.require_isolation and not result.isolation_verified:
            raise IsolationUnavailable("executor did not prove isolation")
        return result


def environment_digest(environment: dict[str, str]) -> str:
    canonical = json.dumps(environment, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


__all__ = ["ExecutorService", "IsolationUnavailable", "JobRunner", "environment_digest"]
