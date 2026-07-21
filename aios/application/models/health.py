"""Provider health tracking and circuit breaker (Slice 31).

In-memory, per-process state -- matching `aios.runtime.budget_guard.
BudgetGuard`'s own established convention for this kind of runtime
accounting, not a new durability promise this slice doesn't back with real
persistence. Nothing here fabricates a health measurement: every recorded
success/failure must come from a caller that actually attempted a real call
(or a real probe); this module only turns those reported outcomes into a
deterministic circuit-breaker state and a typed snapshot.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from aios.domain.models.contracts import ProviderHealthSnapshot


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class _ProviderState:
    consecutive_failures: int = 0
    recent_failure_count: int = 0
    circuit_state: str = "closed"
    opened_at: float | None = None
    last_successful_call_at: str | None = None
    last_latency_ms: float | None = None
    credential_valid: bool = True
    reachable: bool = True


@dataclass
class ProviderHealthTracker:
    """Deterministic, threshold-based circuit breaker over reported outcomes.

    - `record_success`/`record_failure` are the only way state changes --
      there is no timer-based background probing here.
    - The circuit opens after `failure_threshold` consecutive failures.
    - Once open, `is_call_allowed` refuses until `recovery_after_seconds`
      has elapsed, then flips to `half_open` and allows exactly the next
      call through as a recovery probe. A failure during `half_open`
      re-opens the circuit immediately (regardless of the failure
      threshold); a success closes it and resets the failure count.
    """

    failure_threshold: int = 3
    recovery_after_seconds: float = 60.0
    clock: Callable[[], float] = time.time
    _states: dict[str, _ProviderState] = field(default_factory=dict)

    def _state(self, provider: str) -> _ProviderState:
        return self._states.setdefault(provider, _ProviderState())

    def record_success(
        self, provider: str, *, latency_ms: float | None = None
    ) -> None:
        state = self._state(provider)
        state.consecutive_failures = 0
        state.circuit_state = "closed"
        state.opened_at = None
        state.last_successful_call_at = _utc_now()
        state.last_latency_ms = latency_ms
        state.reachable = True

    def record_failure(
        self, provider: str, *, credential_invalid: bool = False
    ) -> None:
        state = self._state(provider)
        state.consecutive_failures += 1
        state.recent_failure_count += 1
        state.reachable = not credential_invalid and state.reachable
        if credential_invalid:
            state.credential_valid = False
        was_half_open = state.circuit_state == "half_open"
        if was_half_open or state.consecutive_failures >= self.failure_threshold:
            state.circuit_state = "open"
            state.opened_at = self.clock()

    def is_call_allowed(self, provider: str) -> bool:
        state = self._state(provider)
        if state.circuit_state == "closed":
            return True
        if state.circuit_state == "open":
            if (
                state.opened_at is not None
                and self.clock() - state.opened_at >= self.recovery_after_seconds
            ):
                state.circuit_state = "half_open"
                return True
            return False
        return True  # half_open: allow the recovery probe through

    def snapshot(
        self, provider: str, *, budget_remaining: float | None = None
    ) -> ProviderHealthSnapshot:
        state = self._state(provider)
        return ProviderHealthSnapshot(
            provider=provider,
            reachable=state.reachable,
            credential_valid=state.credential_valid,
            recent_failure_count=state.recent_failure_count,
            measured_latency_ms=state.last_latency_ms,
            budget_remaining=budget_remaining,
            circuit_state=state.circuit_state,
            last_successful_call_at=state.last_successful_call_at,
        )


__all__ = ["ProviderHealthTracker"]
