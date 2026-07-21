"""SelfModelHandler — the cortex-bus consumer that rebuilds the self-model (W2).

Subscribes to "turn.completed" events on the CortexBus and performs the
synthesize_self_model + render call OFF the hot path. The result is cached
in-process; the cheap READ path (_recall_self_model) can optionally check this
cache instead of re-running synthesis on every turn.

Design constraints (Fable's supervisory decisions):
- The handler is ADVISORY: synthesis errors degrade to a silent no-op.
- The self-model is NEVER authority: it is recalled context only.
- Idempotent: replaying the same event must not raise.
- Thread-safe cache access (a threading.Lock guards the cached string).
- Ignores event types other than "turn.completed" — forward-compatible.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

from aios.memory.self_model import render as render_self_model, synthesize_self_model
from aios.runtime.cortex_bus import BusEvent

logger = logging.getLogger(__name__)

_HANDLED_EVENT_TYPE = "turn.completed"


class SelfModelHandler:
    """A CortexBus subscriber that synthesizes the self-model off the hot path.

    Usage::

        handler = SelfModelHandler(development_tracker, mistake_memory)
        bus.subscribe(handler)
        # Later, from the per-turn recall path:
        cached = handler.recall()  # None until the first event is processed
    """

    def __init__(
        self,
        development: Any | None = None,
        mistakes: Any | None = None,
        *,
        memory_authority: Any | None = None,
    ) -> None:
        self._development = development
        self._mistakes = mistakes
        self._memory_authority = memory_authority
        self._cache: Optional[str] = None
        self._lock = threading.Lock()

    def __call__(self, event: BusEvent) -> None:
        """Handle a bus event (idempotent; errors are advisory, never raised)."""
        if event.event_type != _HANDLED_EVENT_TYPE:
            return
        try:
            if self._memory_authority is not None:
                text = self._memory_authority.self_model() or None
            else:
                model = synthesize_self_model(self._development, self._mistakes)
                text = render_self_model(model) or None
        except Exception:  # noqa: BLE001 — self-model is advisory; never block the bus
            logger.warning(
                "self_model_handler_synthesis_failed",
                exc_info=True,
            )
            return
        with self._lock:
            self._cache = text
        logger.debug("self_model_handler_refreshed")

    def recall(self) -> Optional[str]:
        """Return the most recently synthesized self-model text, or None."""
        with self._lock:
            return self._cache


__all__ = ["SelfModelHandler"]
