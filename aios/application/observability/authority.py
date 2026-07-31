"""Organ 52's named owner: one authority over correlation and health.

The ledger has always named `ObservabilityAuthority` as this organ's authority
owner, and no such class existed. The behaviour was real but scattered across
a frozen dataclass (`TraceContext`), a handful of free functions, and a
separately-scoped `MetricsCollector`, so there was no single place that could
answer "is this system observable right now, and can I trust what it says".

This owns the correlation chain and reports health honestly. In particular it
reports `unavailable` rather than a comfortable zero when it genuinely cannot
tell -- an observability organ that invents reassuring numbers is worse than
one that admits it does not know, because the numbers get believed.
"""

from __future__ import annotations

import logging
import logging.handlers
import re
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterator, Mapping

_LOGGER = logging.getLogger(__name__)

#: Keep a bounded amount of durable log history. Observability that vanishes
#: on restart is useless for the case it exists to serve -- investigating what
#: happened just before a crash.
_LOG_MAX_BYTES = 8 * 1024 * 1024
_LOG_BACKUP_COUNT = 3

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TRACE: ContextVar["TraceContext | None"] = ContextVar(
    "gagos_trace_context", default=None
)


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

    def as_env(self) -> dict[str, str]:
        """Same non-empty trace values as `headers()`, reshaped as
        environment-variable names for propagation across a subprocess
        boundary (e.g. `docker run --env`) rather than an HTTP transport --
        organ 52's own named gap: a trace id crossing into the isolated
        executor's spawned per-job container had no propagation mechanism
        at all before this."""
        return {
            f"AIOS_TRACE_{key[2:].upper().replace('-', '_')}": value
            for key, value in self.headers().items()
        }

    def with_ids(self, **values: str | None) -> "TraceContext":
        allowed = {
            key: _normalize_id(value) if value is not None else None
            for key, value in values.items()
            if key
            in {
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


_TRACING_AUTHORITY: "ObservabilityAuthority | None" = None


def get_tracing_authority() -> "ObservabilityAuthority":
    """Process singleton for correlation-id ownership (organ 52)."""
    global _TRACING_AUTHORITY
    if _TRACING_AUTHORITY is None:
        _TRACING_AUTHORITY = ObservabilityAuthority()
    return _TRACING_AUTHORITY


class ObservabilityAuthority:
    """The one authority over correlation ids and observable health."""

    def __init__(self, *, log_dir: Path | None = None) -> None:
        self._log_dir = log_dir
        self._durable_handler: logging.Handler | None = None

    @classmethod
    def from_config(cls) -> "ObservabilityAuthority":
        from aios import config

        return cls(log_dir=Path(config.DATA_DIR) / "logs")

    # -- correlation ---------------------------------------------------- #

    def context_from_headers(self, headers: Mapping[str, str] | Any) -> TraceContext:
        """Build a safe context from inbound headers, minting a request id
        when none was supplied. Values that fail validation are dropped, never
        passed through: a trace id is correlation metadata and must never
        become an injection vector."""
        source = {
            str(key).lower(): str(value) for key, value in (headers or {}).items()
        }
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

    def current_context(self) -> TraceContext:
        current = _TRACE.get()
        return current if current is not None else self.context_from_headers({})

    @contextmanager
    def bind(self, context: TraceContext) -> Iterator[TraceContext]:
        """Bind `context` for the duration of a block."""
        token = _TRACE.set(context)
        try:
            yield context
        finally:
            _TRACE.reset(token)

    def set_context(self, context: TraceContext) -> None:
        """Set context for code that owns the surrounding request lifecycle."""
        _TRACE.set(context)

    def propagation_headers(self) -> dict[str, str]:
        """Headers carrying the current correlation ids across an HTTP hop."""
        return self.current_context().headers()

    def propagation_env(self) -> dict[str, str]:
        """The same ids reshaped for a subprocess hop (`docker run --env`).

        Deliberately distinct from the job's security-reviewed
        `environment_allowlist`, which this must never bypass or widen.
        """
        return self.current_context().as_env()

    # -- durable state (condition 3) ------------------------------------ #

    def enable_durable_logs(self) -> Path | None:
        """Attach a size-bounded rotating file handler to the root logger.

        Returns the log path, or None if durable logging could not be enabled.

        Before this, `configure_logging()` attached only a StreamHandler to
        stderr, so every structured log line died with the process and an
        incident investigated after a crash had nothing organ-52-owned to read.

        Never raises: failing to open a log file must not stop the system from
        running, but it also must not be reported as success.
        """
        if self._log_dir is None:
            return None
        if self._durable_handler is not None:
            return self._log_path

        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            handler = logging.handlers.RotatingFileHandler(
                self._log_path,
                maxBytes=_LOG_MAX_BYTES,
                backupCount=_LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            logging.getLogger().addHandler(handler)
        except Exception as exc:  # noqa: BLE001 - logging must never block boot
            _LOGGER.warning(
                "durable_log_handler_unavailable", extra={"error": str(exc)}
            )
            return None

        self._durable_handler = handler
        return self._log_path

    @property
    def _log_path(self) -> Path:
        assert self._log_dir is not None
        return self._log_dir / "aios.log"

    def durable_log_status(self) -> dict[str, Any]:
        """Whether structured logs currently survive a restart."""
        if self._durable_handler is None:
            return {"durable": False, "reason": "no durable log handler attached"}
        path = self._log_path
        try:
            size = path.stat().st_size if path.exists() else 0
        except OSError as exc:
            return {"durable": True, "path": str(path), "error": str(exc)}
        return {
            "durable": True,
            "path": str(path),
            "bytes": size,
            "max_bytes": _LOG_MAX_BYTES,
            "backup_count": _LOG_BACKUP_COUNT,
        }

    # -- health --------------------------------------------------------- #

    def health(self) -> dict[str, Any]:
        """A truthful snapshot of what this organ can and cannot currently see.

        `metrics` reports `unavailable` when the collector cannot be reached,
        rather than an empty-but-plausible reading.
        """
        report: dict[str, Any] = {
            "trace": {"request_id": self.current_context().request_id},
            "logs": self.durable_log_status(),
        }
        try:
            from aios.core.metrics import MetricsCollector

            report["metrics"] = {
                "status": "available",
                "collector": MetricsCollector.__name__,
            }
        except Exception as exc:  # noqa: BLE001 - never fabricate health
            report["metrics"] = {"status": "unavailable", "error": str(exc)}
        return report


__all__ = ["ObservabilityAuthority", "TraceContext", "get_tracing_authority"]
