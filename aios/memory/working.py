"""L1 Working memory: in-process, session-scoped, RAM-only state.

Per the blueprint, working memory is a ``RAM dict`` with a ``Session`` TTL: it
holds the active task context, tool variables, and conversation history for the
life of the process and is never persisted. This implementation is thread-safe
so concurrent agent loops can share one instance.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any, Optional


class WorkingMemory:
    """Session-scoped key/value store plus an ordered conversation buffer."""

    def __init__(self) -> None:
        self._kv: dict[str, dict[str, Any]] = defaultdict(dict)
        self._history: dict[str, list[dict[str, str]]] = defaultdict(list)
        self._lock = threading.RLock()

    def set(self, session_id: str, key: str, value: Any) -> None:
        """Store *value* under *key* for *session_id*."""
        with self._lock:
            self._kv[session_id][key] = value

    def get(self, session_id: str, key: str, default: Optional[Any] = None) -> Any:
        """Return the value for *key* in *session_id*, or *default* if absent."""
        with self._lock:
            return self._kv.get(session_id, {}).get(key, default)

    def append_message(self, session_id: str, role: str, content: str) -> None:
        """Append a turn to the session's in-memory conversation buffer."""
        with self._lock:
            self._history[session_id].append({"role": role, "content": content})

    def history(self, session_id: str) -> list[dict[str, str]]:
        """Return a shallow copy of the session's conversation buffer."""
        with self._lock:
            return list(self._history.get(session_id, []))

    def clear(self, session_id: str) -> None:
        """Drop all working state for a single session."""
        with self._lock:
            self._kv.pop(session_id, None)
            self._history.pop(session_id, None)

    def sessions(self) -> list[str]:
        """Return the ids of all sessions with live working state."""
        with self._lock:
            return list({*self._kv.keys(), *self._history.keys()})
