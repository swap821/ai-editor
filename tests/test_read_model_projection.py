from __future__ import annotations

from pathlib import Path

from aios.application.read_models.projection import IncrementalSystemProjection
from aios.runtime.cortex_bus import CortexBus
from tests.cortex_event_helpers import append_event


def test_projection_applies_events_incrementally_and_is_idempotent(
    tmp_path: Path,
) -> None:
    projection = IncrementalSystemProjection(tmp_path / "portrait.db")
    bus = CortexBus(tmp_path / "cortex.db")
    turn = append_event(bus, "turn.started", "turn-1", {"turnId": "turn-1"})
    worker = append_event(
        bus,
        "worker.started",
        "worker-1",
        {"workerId": "worker-1", "missionId": "mission-1", "role": "code"},
    )
    projection.process_available(bus)
    projection.process_available(bus)
    snapshot = projection.snapshot()
    assert snapshot.last_event_id == worker
    assert snapshot.active_turns == ("turn-1",)
    assert snapshot.active_workers == ("worker-1",)
    assert snapshot.active_castes == ("code",)
    assert snapshot.metrics["active_workers"].status == "measured"
    assert turn < worker


def test_projection_active_castes_disappears_with_its_worker(tmp_path: Path) -> None:
    """Castes are derived from currently active workers, not a parallel table --
    a dissolved worker's role must vanish with it, with no separate cleanup."""
    projection = IncrementalSystemProjection(tmp_path / "portrait.db")
    bus = CortexBus(tmp_path / "cortex.db")
    append_event(
        bus, "worker.started", "worker-a", {"workerId": "worker-a", "role": "coder"}
    )
    append_event(
        bus, "worker.started", "worker-b", {"workerId": "worker-b", "role": "reviewer"}
    )
    append_event(
        bus, "worker.dissolved", "worker-a", {"workerId": "worker-a", "role": "coder"}
    )
    projection.process_available(bus)

    snapshot = projection.snapshot()

    assert snapshot.active_workers == ("worker-b",)
    assert snapshot.active_castes == ("reviewer",)


def test_projection_active_castes_deduplicates_across_workers(tmp_path: Path) -> None:
    projection = IncrementalSystemProjection(tmp_path / "portrait.db")
    bus = CortexBus(tmp_path / "cortex.db")
    append_event(
        bus, "worker.started", "worker-a", {"workerId": "worker-a", "role": "coder"}
    )
    append_event(
        bus, "worker.started", "worker-b", {"workerId": "worker-b", "role": "coder"}
    )
    projection.process_available(bus)

    snapshot = projection.snapshot()

    assert snapshot.active_workers == ("worker-a", "worker-b")
    assert snapshot.active_castes == ("coder",)


def test_projection_removes_only_affected_active_entities(tmp_path: Path) -> None:
    projection = IncrementalSystemProjection(tmp_path / "portrait.db")
    projection.apply(
        type(
            "Event",
            (),
            {
                "id": 1,
                "event_type": "worker.started",
                "signature": "a",
                "payload": {"workerId": "a"},
            },
        )()
    )
    projection.apply(
        type(
            "Event",
            (),
            {
                "id": 2,
                "event_type": "worker.started",
                "signature": "b",
                "payload": {"workerId": "b"},
            },
        )()
    )
    projection.apply(
        type(
            "Event",
            (),
            {
                "id": 3,
                "event_type": "worker.dissolved",
                "signature": "a",
                "payload": {"workerId": "a"},
            },
        )()
    )
    assert projection.snapshot().active_workers == ("b",)


def test_projection_persists_across_restart_without_history_scan(
    tmp_path: Path,
) -> None:
    path = tmp_path / "portrait.db"
    projection = IncrementalSystemProjection(path)
    projection.apply(
        type(
            "Event",
            (),
            {
                "id": 7,
                "event_type": "mission.running",
                "signature": "m",
                "payload": {"missionId": "m"},
            },
        )()
    )
    reopened = IncrementalSystemProjection(path)
    snapshot = reopened.snapshot()
    assert snapshot.active_missions == ("m",)
    assert snapshot.last_event_id == 7
