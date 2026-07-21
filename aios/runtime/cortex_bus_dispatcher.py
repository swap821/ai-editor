"""CortexBusDispatcher — the daemon drainer for the cortex bus (W2).

Starts a single background thread that loops:
  1. Sleeps up to ``poll_interval`` seconds (the heartbeat).
  2. Wakes *early* if the bus's wake-hint file exists (set by the producer).
  3. Calls ``bus.poll_once()`` unconditionally.

The hint-wake lets the thread respond in ~hint-check-interval (default 50 ms)
without burning CPU on the 250 ms heartbeat path, while the heartbeat guarantees
a lost hint never strands an observation.

Design constraints (Fable's supervisory decisions):
- Daemon thread: never blocks clean process exit.
- ``threading.Event`` stop flag: ``stop()`` is O(1) and idempotent.
- Isolated + testable WITHOUT the full FastAPI app.
- No thread starts on construction; call ``start()`` explicitly.
- ONLY wired when ``config.CORTEX_BUS`` is True (enforced in the lifespan, not here).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from aios.runtime.cortex_bus import CortexBus

logger = logging.getLogger(__name__)

# How often to check for the hint file within each heartbeat sleep.
_HINT_CHECK_INTERVAL = 0.05  # 50 ms


class CortexBusDispatcher:
    """A start/stop-able daemon thread that drains the cortex bus."""

    def __init__(
        self,
        bus: CortexBus,
        *,
        poll_interval: float = 0.25,
    ) -> None:
        self._bus = bus
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the background drainer thread (idempotent if already running)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="cortex-bus-dispatcher",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "cortex_bus_dispatcher_started",
            extra={"poll_interval": self._poll_interval},
        )

    def stop(self, timeout: float = 2.0) -> None:
        """Signal the thread to stop and wait for it to exit (idempotent)."""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        logger.info("cortex_bus_dispatcher_stopped")

    def _run(self) -> None:
        """Main loop: hint-wake or heartbeat, then poll_once."""
        elapsed = 0.0
        while not self._stop_event.is_set():
            # Wake early if the hint is raised, otherwise honour the heartbeat.
            if self._bus.hint_pending() or elapsed >= self._poll_interval:
                try:
                    self._bus.poll_once()
                except Exception:  # noqa: BLE001 — bus errors must not kill the thread
                    logger.exception("cortex_bus_poll_error")
                elapsed = 0.0
            self._stop_event.wait(timeout=_HINT_CHECK_INTERVAL)
            elapsed += _HINT_CHECK_INTERVAL

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


__all__ = ["CortexBusDispatcher"]
