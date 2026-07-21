"""Unit tests for aios.runtime.turn_state -- the approval-resume convo-tail store.

Covers: stash/take (pop semantics), overwrite-on-restash, TTL expiry resolved
fresh at call time (the config monkeypatch-staleness trap), explicit clear,
and cross-session isolation.
"""
from __future__ import annotations

from aios import config
from aios.runtime.turn_state import TurnStateStore


def _tail(marker: str) -> list[dict[str, str]]:
    return [{"role": "assistant", "content": marker}]


def test_stash_then_take_returns_the_tail() -> None:
    store = TurnStateStore()
    store.stash("s1", _tail("hello"))
    assert store.take("s1") == _tail("hello")


def test_take_pops_the_entry_second_take_is_none() -> None:
    store = TurnStateStore()
    store.stash("s1", _tail("hello"))
    assert store.take("s1") is not None
    assert store.take("s1") is None


def test_take_on_unknown_session_returns_none() -> None:
    store = TurnStateStore()
    assert store.take("never-stashed") is None


def test_stash_overwrites_prior_tail_for_same_session() -> None:
    store = TurnStateStore()
    store.stash("s1", _tail("first"))
    store.stash("s1", _tail("second"))
    assert store.take("s1") == _tail("second")


def test_stash_stores_a_copy_caller_mutation_does_not_leak() -> None:
    store = TurnStateStore()
    original = _tail("original")
    store.stash("s1", original)
    original.append({"role": "tool", "content": "mutated after stash"})
    assert store.take("s1") == _tail("original")


def test_cross_session_isolation() -> None:
    store = TurnStateStore()
    store.stash("s1", _tail("session-one"))
    store.stash("s2", _tail("session-two"))
    assert store.take("s1") == _tail("session-one")
    assert store.take("s2") == _tail("session-two")


def test_clear_discards_without_returning() -> None:
    store = TurnStateStore()
    store.stash("s1", _tail("hello"))
    store.clear("s1")
    assert store.take("s1") is None


def test_clear_on_unknown_session_is_a_no_op() -> None:
    store = TurnStateStore()
    store.clear("never-stashed")  # must not raise


def test_ttl_expiry_via_injected_clock() -> None:
    now = [1000.0]
    store = TurnStateStore(clock=lambda: now[0])
    store.stash("s1", _tail("hello"))
    # Advance the clock past config.YELLOW_APPROVAL_TIMEOUT_MS (default 60_000ms = 60s).
    now[0] += 61.0
    assert store.take("s1") is None


def test_ttl_resolves_config_fresh_at_call_time(monkeypatch) -> None:
    """The monkeypatch-staleness trap: TTL must be read from config INSIDE
    stash()/take(), never captured once as a constructor default or module
    constant -- otherwise a test (or a live runtime config change) that
    monkeypatches config.YELLOW_APPROVAL_TIMEOUT_MS after construction would
    silently have no effect, exactly the pre-existing ApprovalStore bug this
    store must not repeat.
    """
    now = [1000.0]
    store = TurnStateStore(clock=lambda: now[0])
    # Shrink the timeout to 1ms AFTER construction.
    monkeypatch.setattr(config, "YELLOW_APPROVAL_TIMEOUT_MS", 1)
    store.stash("s1", _tail("hello"))
    now[0] += 1.0  # 1 full second later -- well past a 1ms timeout.
    assert store.take("s1") is None, (
        "TTL must resolve config.YELLOW_APPROVAL_TIMEOUT_MS fresh at stash() "
        "call time, not as a stale constructor/module-level default"
    )


def test_lazy_expiry_sweep_drops_other_expired_sessions_on_access() -> None:
    now = [1000.0]
    store = TurnStateStore(clock=lambda: now[0])
    store.stash("expired-session", _tail("old"))
    now[0] += 61.0
    store.stash("fresh-session", _tail("new"))
    # Accessing fresh-session's take() should sweep the expired one lazily.
    assert store.take("fresh-session") == _tail("new")
    assert store.take("expired-session") is None
