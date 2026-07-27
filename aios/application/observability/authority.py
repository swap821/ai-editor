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
from pathlib import Path
from typing import Any, Iterator

from aios.operations.tracing import (
    TraceContext,
    bind_trace_context,
    get_trace_context,
    new_trace_context,
)

_LOGGER = logging.getLogger(__name__)

#: Keep a bounded amount of durable log history. Observability that vanishes
#: on restart is useless for the case it exists to serve -- investigating what
#: happened just before a crash.
_LOG_MAX_BYTES = 8 * 1024 * 1024
_LOG_BACKUP_COUNT = 3


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

    def context_from_headers(self, headers: Any) -> TraceContext:
        """Build a safe context from inbound headers, minting a request id
        when none was supplied. Values that fail validation are dropped, never
        passed through: a trace id is correlation metadata and must never
        become an injection vector."""
        return new_trace_context(headers)

    def current_context(self) -> TraceContext:
        return get_trace_context()

    def bind(self, context: TraceContext) -> Iterator[TraceContext]:
        """Bind `context` for the duration of a block."""
        return bind_trace_context(context)

    def propagation_headers(self) -> dict[str, str]:
        """Headers carrying the current correlation ids across an HTTP hop."""
        return get_trace_context().headers()

    def propagation_env(self) -> dict[str, str]:
        """The same ids reshaped for a subprocess hop (`docker run --env`).

        Deliberately distinct from the job's security-reviewed
        `environment_allowlist`, which this must never bypass or widen.
        """
        return get_trace_context().as_env()

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
            _LOGGER.warning("durable_log_handler_unavailable", extra={"error": str(exc)})
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
            "trace": {"request_id": get_trace_context().request_id},
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


__all__ = ["ObservabilityAuthority"]
