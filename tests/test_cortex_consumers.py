from __future__ import annotations

from pathlib import Path

import pytest

from aios.runtime.cortex_bus import ConsumerReplayGap, CortexBus
from tests.cortex_event_helpers import append_event


def test_consumers_have_independent_durable_cursors(tmp_path: Path) -> None:
    path = tmp_path / "cortex.db"
    bus = CortexBus(path)
    first = append_event(bus, "mission.running", "mission-1", {"n": 1})
    second = append_event(bus, "worker.started", "worker-1", {"n": 2})
    assert first == 1

    assert [event.id for event in bus.consumer_batch("portrait")] == [1, 2]
    bus.ack_consumer("portrait", first)
    assert bus.consumer_cursor("portrait").last_event_id == first
    assert [event.id for event in bus.consumer_batch("portrait")] == [second]
    assert [event.id for event in bus.consumer_batch("audit")] == [first, second]

    reopened = CortexBus(path)
    assert reopened.consumer_cursor("portrait").last_event_id == first


def test_failed_consumer_retries_without_blocking_another(tmp_path: Path) -> None:
    bus = CortexBus(tmp_path / "cortex.db")
    event_id = append_event(bus, "mission.running", "mission-1", {})
    bus.register_consumer("slow")
    bus.register_consumer("healthy")

    cursor = bus.fail_consumer("slow", event_id, "observer unavailable", max_attempts=3)
    assert cursor.status == "retrying"
    assert bus.consumer_cursor("healthy").last_event_id == 0
    bus.ack_consumer("healthy", event_id)
    assert bus.consumer_cursor("healthy").last_event_id == event_id
    assert [event.id for event in bus.consumer_batch("slow")] == [event_id]


def test_repeated_failure_quarantines_only_that_event_for_that_consumer(
    tmp_path: Path,
) -> None:
    bus = CortexBus(tmp_path / "cortex.db")
    first = append_event(bus, "mission.running", "mission-1", {})
    second = append_event(bus, "worker.started", "worker-1", {})
    bus.register_consumer("portrait")

    bus.fail_consumer("portrait", first, "bad payload", max_attempts=2)
    cursor = bus.fail_consumer("portrait", first, "bad payload", max_attempts=2)
    assert cursor.status == "quarantined"
    assert cursor.last_event_id == first
    assert [event.id for event in bus.consumer_batch("portrait")] == [second]


def test_retention_boundary_requires_snapshot_rebuild(tmp_path: Path) -> None:
    bus = CortexBus(tmp_path / "cortex.db", retention_max=2)
    bus.register_consumer("portrait")
    append_event(bus, "mission.running", "mission-1", {})
    append_event(bus, "worker.started", "worker-1", {})
    append_event(bus, "worker.completed", "worker-1", {})

    with pytest.raises(ConsumerReplayGap, match="snapshot required"):
        bus.consumer_batch("portrait")


def test_ack_is_idempotent_but_skipping_is_rejected(tmp_path: Path) -> None:
    bus = CortexBus(tmp_path / "cortex.db")
    first = append_event(bus, "mission.running", "mission-1", {})
    second = append_event(bus, "worker.started", "worker-1", {})
    bus.register_consumer("audit")
    bus.ack_consumer("audit", first)
    bus.ack_consumer("audit", first)
    with pytest.raises(ValueError, match="cannot skip"):
        bus.ack_consumer("audit", second + 1)
