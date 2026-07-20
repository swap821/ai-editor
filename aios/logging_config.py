"""Centralised structured logging configuration for GAGOS.

The backend uses ``structlog`` bound to the standard-library logging sink so that
existing tooling (``caplog`` in tests, journald, etc.) works out of the box while
still getting per-request context variables (request_id, session_id) and
optional JSON output.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
from typing import Final

import structlog

_CONFIGURED: bool = False

#: Default log level. Override with ``AIOS_LOG_LEVEL``.
DEFAULT_LEVEL: Final[str] = "INFO"


def configure_logging(
    *, json_format: bool | None = None, level: str | None = None
) -> None:
    """Configure structlog + stdlib logging. Idempotent.

    Parameters
    ----------
    json_format:
        When ``True`` emit JSON; when ``False`` emit a coloured console format.
        Defaults to the ``AIOS_LOG_JSON`` environment variable (``true/1/yes/on``).
    level:
        Root log level. Defaults to ``AIOS_LOG_LEVEL`` or ``INFO``.
    """
    global _CONFIGURED  # noqa: PLW0603
    if _CONFIGURED:
        return

    if json_format is None:
        raw_json = os.getenv("AIOS_LOG_JSON", "").strip().lower()
        json_format = raw_json in ("1", "true", "yes", "on")

    level = (level or os.getenv("AIOS_LOG_LEVEL", DEFAULT_LEVEL)).upper()

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.stdlib.ExtraAdder(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    renderer: structlog.types.Processor
    if json_format:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )

    root = logging.getLogger()
    root.setLevel(getattr(logging, level, logging.INFO))
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(handler)

    _CONFIGURED = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to the standard-library sink."""
    return structlog.get_logger(name)


def session_log_key(session_id: str) -> str:
    """Return a non-reversible key for caller-supplied session ids in logs."""
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()
