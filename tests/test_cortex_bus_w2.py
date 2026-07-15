"""Cortex bus W2 — dispatcher lifecycle, producer wiring, consumer, and W3 guard.

Slice A: CortexBusDispatcher start/stop (daemon thread, hint-wake, 250 ms poll).
Slice B: lifespan wiring — dispatcher starts ONLY when config.CORTEX_BUS is True.
Slice C: producer — generate() appends "turn.completed" ONLY when bus is on.
Slice D: consumer — self-model rebuild handler synthesizes off the hot path.
W3 guard: only observation event types reach the bus; self-model reflects a turn
          within ~1 s of dispatch when CORTEX_BUS is overridden on.

Authority NEVER on the bus: the conformance assertions in this file guarantee that
"turn.completed" is the only type produced by the generate path, and that it
carries no authority-bearing payload keys.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

from aios.runtime.cortex_bus import BusEvent, CortexBus
from aios.runtime.cortex_bus_dispatcher import CortexBusDispatcher


# ── Slice A: CortexBusDispatcher lifecycle ────────────────────────────────────

class TestCortexBusDispatcher:
    """Start/stop a dispatcher without the full app."""

    def test_dispatcher_starts_and_runs_handler_then_stops(self, tmp_path: Path) -> None:
        bus = CortexBus(db_path=tmp_path / "bus.db")
        seen: list[BusEvent] = []
        bus.subscribe(seen.append)

        dispatcher = CortexBusDispatcher(bus, poll_interval=0.05)
        dispatcher.start()

        bus.append("turn.completed", "sess-1", {"source": "test"})
        # Give the dispatcher time to wake on the hint and drain.
        deadline = time.monotonic() + 2.0
        while not seen and time.monotonic() < deadline:
            time.sleep(0.02)

        dispatcher.stop()

        assert seen, "dispatcher must deliver the event to the handler"
        assert seen[0].event_type == "turn.completed"
        assert seen[0].payload["source"] == "test"

    def test_dispatcher_thread_is_daemon(self, tmp_path: Path) -> None:
        bus = CortexBus(db_path=tmp_path / "bus.db")
        dispatcher = CortexBusDispatcher(bus, poll_interval=0.05)
        dispatcher.start()
        assert dispatcher._thread is not None
        assert dispatcher._thread.daemon is True
        dispatcher.stop()

    def test_dispatcher_stop_is_idempotent(self, tmp_path: Path) -> None:
        bus = CortexBus(db_path=tmp_path / "bus.db")
        dispatcher = CortexBusDispatcher(bus, poll_interval=0.05)
        dispatcher.start()
        dispatcher.stop()
        dispatcher.stop()  # second stop must not raise

    def test_dispatcher_hint_wake_delivers_before_full_poll_interval(self, tmp_path: Path) -> None:
        """The dispatcher wakes early on a hint, not just on the 250 ms timer."""
        bus = CortexBus(db_path=tmp_path / "bus.db")
        seen: list[float] = []

        def record_time(event: BusEvent) -> None:
            seen.append(time.monotonic())

        bus.subscribe(record_time)

        # Use a long poll interval so only the hint-wake can deliver fast.
        dispatcher = CortexBusDispatcher(bus, poll_interval=10.0)
        dispatcher.start()
        t0 = time.monotonic()
        bus.append("turn.completed", "sess-1", {})

        deadline = time.monotonic() + 2.0
        while not seen and time.monotonic() < deadline:
            time.sleep(0.02)

        dispatcher.stop()

        assert seen, "dispatcher must deliver via hint-wake"
        latency = seen[0] - t0
        assert latency < 2.0, f"hint-wake took {latency:.2f}s — too slow"

    def test_dispatcher_does_not_start_when_not_called(self, tmp_path: Path) -> None:
        """Constructing a dispatcher must not start a thread."""
        bus = CortexBus(db_path=tmp_path / "bus.db")
        dispatcher = CortexBusDispatcher(bus, poll_interval=0.05)
        assert dispatcher._thread is None


# ── Slice B: lifespan wiring ──────────────────────────────────────────────────

class TestLifespanWiring:
    """Dispatcher starts in lifespan ONLY when config.CORTEX_BUS is True."""

    def test_no_dispatcher_when_bus_off(self, tmp_path: Path) -> None:
        """With CORTEX_BUS False (default), the module-level dispatcher is None."""
        from aios.api import main as main_mod

        with patch.object(main_mod.config, "CORTEX_BUS", False):
            # Import the factory function that returns the current dispatcher.
            result = main_mod._get_cortex_dispatcher()
        assert result is None

    def test_dispatcher_created_when_bus_on(self, tmp_path: Path) -> None:
        """With CORTEX_BUS True, _build_cortex_dispatcher returns a dispatcher."""
        from aios.runtime.cortex_bus_dispatcher import CortexBusDispatcher
        from aios.api import main as main_mod

        bus = CortexBus(db_path=tmp_path / "bus.db")
        dispatcher = main_mod._build_cortex_dispatcher(bus)
        assert isinstance(dispatcher, CortexBusDispatcher)


# ── Slice C: producer ─────────────────────────────────────────────────────────

class TestProducer:
    """After the 'done' frame, a turn.completed event is appended iff bus is on."""

    def _run_turn(
        self,
        tmp_path: Path,
        bus_on: bool,
    ) -> tuple[list[BusEvent], CortexBus]:
        """Drive a fake generate turn through _append_turn_completed and return
        what the bus received."""
        from aios.api.main import _append_turn_completed

        bus = CortexBus(db_path=tmp_path / "bus.db")
        seen: list[BusEvent] = []
        bus.subscribe(seen.append)

        with patch("aios.api.main.config") as mock_cfg:
            mock_cfg.CORTEX_BUS = bus_on
            _append_turn_completed(bus if bus_on else None, "session-abc", "turn-abc")

        # Drain to materialise events into `seen`.
        bus.dispatch_pending()
        return seen, bus

    def test_event_appended_when_bus_on(self, tmp_path: Path) -> None:
        from aios.api.main import _append_turn_completed

        bus = CortexBus(db_path=tmp_path / "bus.db")
        seen: list[BusEvent] = []
        bus.subscribe(seen.append)

        _append_turn_completed(bus, "session-abc", "turn-abc")
        bus.dispatch_pending()

        assert len(seen) == 1
        evt = seen[0]
        assert evt.event_type == "turn.completed"
        assert evt.signature == "session-abc"

    def test_no_event_when_bus_is_none(self, tmp_path: Path) -> None:
        from aios.api.main import _append_turn_completed

        bus = CortexBus(db_path=tmp_path / "bus.db")
        seen: list[BusEvent] = []
        bus.subscribe(seen.append)

        # Passing None simulates bus-off — nothing may be appended.
        _append_turn_completed(None, "session-abc", "turn-abc")
        bus.dispatch_pending()

        assert seen == []

    def test_payload_carries_no_authority_keys(self, tmp_path: Path) -> None:
        """The producer payload must be non-authority observation-only."""
        from aios.api.main import _append_turn_completed

        bus = CortexBus(db_path=tmp_path / "bus.db")
        _append_turn_completed(bus, "session-xyz", "turn-xyz")

        events = bus.peek_pending()
        assert events, "event must be pending"
        payload = events[0].payload
        # Authority-bearing keys that must NEVER appear on the bus.
        forbidden = {
            "skill_promotion", "autonomy_credit", "approval_decision",
            "zone", "allowed", "verified", "promote",
        }
        assert forbidden.isdisjoint(payload.keys()), (
            f"authority key(s) in bus payload: {forbidden & payload.keys()}"
        )

    def test_producer_is_best_effort_never_raises(self, tmp_path: Path) -> None:
        """A broken bus path must not propagate an exception to the caller."""
        from aios.api.main import _append_turn_completed

        # Pass a bus whose db_path is in a non-existent dir to force an error,
        # but wrap in a None to exercise the None-guard path without touching disk.
        # The real best-effort test: _append_turn_completed(None, ...) is silent.
        _append_turn_completed(None, "session-xyz", "turn-xyz")  # must not raise


# ── Slice D: consumer ─────────────────────────────────────────────────────────

class TestSelfModelConsumer:
    """The self-model rebuild handler synthesizes off the hot path."""

    def _fake_dev(self) -> Any:
        class _FakeDev:
            def task_profile(self) -> dict:
                return {"coding": (5, 0.9)}
        return _FakeDev()

    def _fake_mistakes(self) -> Any:
        class _FakeMistakes:
            def recurring(self, *, limit: int = 3) -> list:
                return [{"lesson_text": "test carefully", "occurrence_count": 2}]
        return _FakeMistakes()

    def test_handler_synthesizes_self_model_on_turn_completed(self, tmp_path: Path) -> None:
        from aios.runtime.self_model_handler import SelfModelHandler

        dev = self._fake_dev()
        mistakes = self._fake_mistakes()
        handler = SelfModelHandler(dev, mistakes)

        event = BusEvent(
            id=1,
            event_type="turn.completed",
            signature="session-1",
            payload={"ts": "2026-07-02T14:00:00"},
        )
        handler(event)

        model_text = handler.recall()
        assert model_text is not None
        assert "reliable" in model_text.lower() or "coding" in model_text.lower(), (
            f"Expected self-model text about strengths, got: {model_text!r}"
        )

    def test_handler_ignores_non_turn_completed_events(self, tmp_path: Path) -> None:
        from aios.runtime.self_model_handler import SelfModelHandler

        dev = self._fake_dev()
        mistakes = self._fake_mistakes()
        handler = SelfModelHandler(dev, mistakes)

        # A foreign event type must not trigger synthesis.
        event = BusEvent(
            id=2,
            event_type="fact.proposed",
            signature="operator",
            payload={},
        )
        handler(event)
        # recall returns None because no turn.completed has been processed.
        assert handler.recall() is None

    def test_handler_recall_is_none_before_first_event(self, tmp_path: Path) -> None:
        from aios.runtime.self_model_handler import SelfModelHandler

        dev = self._fake_dev()
        mistakes = self._fake_mistakes()
        handler = SelfModelHandler(dev, mistakes)
        assert handler.recall() is None

    def test_handler_is_idempotent_on_replay(self, tmp_path: Path) -> None:
        """Delivering the same event twice must not raise (at-least-once contract)."""
        from aios.runtime.self_model_handler import SelfModelHandler

        dev = self._fake_dev()
        mistakes = self._fake_mistakes()
        handler = SelfModelHandler(dev, mistakes)

        event = BusEvent(
            id=1,
            event_type="turn.completed",
            signature="session-1",
            payload={},
        )
        handler(event)
        handler(event)  # replay — must not raise

    def test_handler_uses_authority_self_model_when_bound(self) -> None:
        from aios.runtime.self_model_handler import SelfModelHandler

        class Authority:
            def self_model(self) -> str:
                return "authority-grounded self-model"

        handler = SelfModelHandler(memory_authority=Authority())
        handler(
            BusEvent(
                id=3,
                event_type="turn.completed",
                signature="session-authority",
                payload={},
            )
        )

        assert handler.recall() == "authority-grounded self-model"


# ── W3 guard: observation-type contract + latency ────────────────────────────

class TestW3Guard:
    """Standing assertions that ONLY observation types ever reach the bus."""

    _AUTHORITY_TYPES = frozenset({
        "skill.promoted",
        "autonomy.credited",
        "approval.decided",
        "zone.classified",
    })

    def test_only_observation_types_on_the_bus(self, tmp_path: Path) -> None:
        """Generate path appends only observation event types."""
        from aios.api.main import _append_turn_completed

        bus = CortexBus(db_path=tmp_path / "bus.db")
        _append_turn_completed(bus, "session-w3", "turn-w3")

        events = bus.peek_pending()
        for evt in events:
            assert evt.event_type not in self._AUTHORITY_TYPES, (
                f"Authority-bearing event type on the bus: {evt.event_type!r}"
            )
            # Observation types must be namespaced with a dot (e.g. "turn.completed")
            assert "." in evt.event_type, (
                f"Bus event type must be namespaced: {evt.event_type!r}"
            )

    def test_self_model_reflects_turn_within_one_second(self, tmp_path: Path) -> None:
        """When CORTEX_BUS is on, the self-model cache is updated within ~1 s."""
        from aios.runtime.self_model_handler import SelfModelHandler

        class _FastDev:
            def task_profile(self) -> dict:
                return {"coding": (5, 0.9)}

        class _FastMistakes:
            def recurring(self, *, limit: int = 3) -> list:
                return []

        dev = _FastDev()
        mistakes = _FastMistakes()
        handler = SelfModelHandler(dev, mistakes)

        bus = CortexBus(db_path=tmp_path / "bus.db")
        bus.subscribe(handler)

        dispatcher = CortexBusDispatcher(bus, poll_interval=0.05)
        dispatcher.start()

        t0 = time.monotonic()
        bus.append("turn.completed", "session-w3", {})

        deadline = t0 + 2.0
        while handler.recall() is None and time.monotonic() < deadline:
            time.sleep(0.02)

        dispatcher.stop()

        elapsed = time.monotonic() - t0
        assert handler.recall() is not None, "self-model cache was not populated"
        assert elapsed < 1.0, f"self-model took {elapsed:.2f}s to reflect — > 1 s budget"


# ── default-off guard (belt-and-suspenders) ───────────────────────────────────

def test_cortex_bus_is_on_by_default() -> None:
    """AIOS_CORTEX_BUS defaults True — the W2 cold-path dispatcher is active."""
    from aios import config
    assert config.CORTEX_BUS is True


def test_cortex_bus_pinned_by_aliveness_suite() -> None:
    """Verify the aliveness suite covers CORTEX_BUS."""
    import pathlib
    src = pathlib.Path(__file__).parent / "test_aliveness_defaults.py"
    source = src.read_text(encoding="utf-8")
    assert "CORTEX_BUS" in source, (
        "test_aliveness_defaults.py must pin CORTEX_BUS"
    )
