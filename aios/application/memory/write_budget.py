"""Bounded learning writes (plan Phase 6, slice 6b; threat T10, red-team RT-12).

Every write that creates or grows learned content -- a lesson, a skill
attempt, a semantic memory, a fact -- first spends from one process-wide
budget: at most ``per_minute`` writes per table in any rolling 60 seconds.

The unit is a burst, not a day. A real turn writes one skill attempt and a
lesson or two, and a turn takes tens of seconds, so no genuine cadence --
a live session, a payoff cohort, an organic chain -- comes near the cap. A
runaway loop or a flooding adversary writes hundreds a second; it is refused
past the cap, and the refusal names its control so a caller, a log and the
red-team reel can all see it.

A refused write writes nothing: the budget is spent before the store is
touched. Callers on the live path are best-effort (a turn never fails because
learning was refused), so a refusal costs one lesson, never a turn.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Callable, Deque, Optional

logger = logging.getLogger(__name__)

#: The control a refusal names.
WRITE_CAP_CONTROL = "learning_write_cap"

WINDOW_SECONDS = 60.0


class LearningWriteCapExceeded(RuntimeError):
    """A learning write refused because its table's budget is spent."""

    control = WRITE_CAP_CONTROL

    def __init__(self, table: str, per_minute: int) -> None:
        super().__init__(
            f"learning write refused: {table} already took {per_minute} writes "
            f"in the last {int(WINDOW_SECONDS)} s ({WRITE_CAP_CONTROL})"
        )
        self.table = table
        self.per_minute = per_minute


class LearningWriteBudget:
    """At most *per_minute* writes per table in any rolling window. Thread-safe."""

    def __init__(
        self, per_minute: int, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        if per_minute < 1:
            raise ValueError("a learning write cap must admit at least one write")
        self.per_minute = int(per_minute)
        self._clock = clock
        self._lock = threading.Lock()
        self._spent: dict[str, Deque[float]] = {}
        #: Refusals by table, for the operator's doctor view.
        self.refused: dict[str, int] = {}

    def spend(self, table: str) -> None:
        """Take one write from *table*'s budget, or raise before anything is written."""
        now = self._clock()
        with self._lock:
            spent = self._spent.setdefault(table, deque())
            while spent and now - spent[0] >= WINDOW_SECONDS:
                spent.popleft()
            if len(spent) >= self.per_minute:
                self.refused[table] = self.refused.get(table, 0) + 1
                first = self.refused[table] == 1
            else:
                spent.append(now)
                return
        if first:
            logger.warning(
                "learning write cap reached for %s (%d per %ds); refusing further "
                "writes until the window frees",
                table,
                self.per_minute,
                int(WINDOW_SECONDS),
            )
        raise LearningWriteCapExceeded(table, self.per_minute)

    def status(self) -> dict[str, Any]:
        return {
            "per_minute": self.per_minute,
            "refused": dict(self.refused),
        }


def spend(adapter: Any, table: str) -> None:
    """Spend from *adapter*'s attached budget, if it has one.

    Production attaches a budget to every learning adapter in
    ``build_memory_authority`` (a test pins that); an adapter built without
    one, in a unit test, is unbounded.
    """
    budget: Optional[LearningWriteBudget] = getattr(adapter, "write_budget", None)
    if budget is not None:
        budget.spend(table)


__all__ = [
    "LearningWriteBudget",
    "LearningWriteCapExceeded",
    "WRITE_CAP_CONTROL",
    "spend",
]
