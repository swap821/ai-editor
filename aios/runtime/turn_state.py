"""In-memory, per-session convo-tail store for approval-resume continuation.

When a turn pauses on a YELLOW ``human_required`` action, the model context
accumulated so far this turn (the "convo tail" -- everything ``ToolAgent.run``
appended on top of its initial ``[system] + messages`` prefix) would otherwise
be discarded. Without it, a resumed turn starts the model fresh with no memory
of the tool call it just paused on, so the model may re-plan from scratch or
contradict its own prior step.

``TurnStateStore`` stashes that tail, keyed by session id, so main.py can pop
it back out on resume and splice it into the next ``ToolAgent.run`` invocation
BEFORE the replayed grant-anchor messages are appended (see ``ToolAgent``'s
``resume_tail`` kwarg). The stored tail is MODEL CONTEXT ONLY: it carries no
authority of its own. Everything it induces the model to do still flows
through the same gated tool-dispatch loop (RED refused, YELLOW pauses again
for a real token) -- it is never a substitute for the approval token, and it
must never be emitted to an SSE client.

Durability class matches ``ApprovalStore``'s in-memory mode: a server restart
loses all stashed tails. That's fine -- it's the same fail-soft path a restart
already takes for pending approvals, and this store's fail-soft law is: absent
or expired state simply means the resumed turn starts with no tail, i.e.
exactly today's behaviour before this feature existed.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional

from aios import config


class TurnStateStore:
    """Thread-safe, TTL-expiring, single-use-on-read store of per-session convo tails."""

    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        #: session_id -> (tail, expires_at_epoch_seconds)
        self._store: dict[str, tuple[list[dict[str, Any]], float]] = {}

    def _timeout_s(self) -> float:
        # Resolved FRESH on every call (never cached as a constructor default or
        # module-level constant) so a test's ``monkeypatch.setattr(config,
        # "YELLOW_APPROVAL_TIMEOUT_MS", ...)`` actually takes effect -- the exact
        # staleness trap already present in ApprovalStore.__init__'s default arg.
        return max(config.YELLOW_APPROVAL_TIMEOUT_MS, 1) / 1000.0

    def _sweep_locked(self) -> None:
        """Drop expired entries. Caller must hold ``self._lock``."""
        now = self._clock()
        expired = [sid for sid, (_, exp) in self._store.items() if exp <= now]
        for sid in expired:
            del self._store[sid]

    def stash(self, session_id: str, tail: list[dict[str, Any]]) -> None:
        """Store (overwriting any prior tail) the convo tail for ``session_id``."""
        expires_at = self._clock() + self._timeout_s()
        with self._lock:
            self._sweep_locked()
            # Store a shallow copy of the list so later caller-side mutation of
            # the original list can't retroactively change what was stashed.
            self._store[session_id] = (list(tail), expires_at)

    def take(self, session_id: str) -> Optional[list[dict[str, Any]]]:
        """Pop and return the stashed tail for ``session_id``, or ``None``.

        Single-use: a second ``take`` for the same session returns ``None``
        until another ``stash`` happens. Also returns ``None`` (and drops the
        entry) if the tail expired.
        """
        with self._lock:
            self._sweep_locked()
            entry = self._store.pop(session_id, None)
        if entry is None:
            return None
        tail, _expires_at = entry
        return tail

    def clear(self, session_id: str) -> None:
        """Discard any stashed tail for ``session_id`` without returning it."""
        with self._lock:
            self._store.pop(session_id, None)


#: Module-level singleton, matching the codebase's established convention for
#: this durability class (see ``ApprovalStore``/``_APPROVALS`` in
#: ``aios/api/main.py``, plus ``_bedrock_lock``/``_gemini_lock``).
_TURN_STATE = TurnStateStore()


def stash(session_id: str, tail: list[dict[str, Any]]) -> None:
    _TURN_STATE.stash(session_id, tail)


def take(session_id: str) -> Optional[list[dict[str, Any]]]:
    return _TURN_STATE.take(session_id)


def clear(session_id: str) -> None:
    _TURN_STATE.clear(session_id)
