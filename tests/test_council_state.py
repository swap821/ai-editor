"""Tests for Phase 3A durable Council deliberation state."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aios.council.council_state import CouncilState
from aios.runtime.contracts import QueenVerdict


def test_connect_closes_the_underlying_connection_after_the_with_block(
    tmp_path: Path,
) -> None:
    # Regression: ``with self._connect() as conn:`` only commits-or-rolls-back
    # -- it never closes the connection, leaking one open sqlite3 connection
    # per call. After the fix, the connection must be closed by the time the
    # ``with`` block exits.
    state = CouncilState(db_path=tmp_path / "council_state.db")
    with state._connect() as conn:
        pass
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_records_and_replays_verdicts_per_mission(tmp_path: Path) -> None:
    state = CouncilState(db_path=tmp_path / "council_state.db")
    planner = QueenVerdict(
        queen="planner",
        verdict="allow_with_approval",
        risk="YELLOW",
        reason="drafted",
        constraints=["c1"],
        confidence=0.8,
    )
    security = QueenVerdict(
        queen="security", verdict="allow", risk="GREEN", reason="ok", confidence=0.9
    )
    state.record_verdict("m1", planner)
    state.record_verdict("m1", security)
    state.record_verdict("m2", planner)

    m1 = state.verdicts_for("m1")
    assert [v["queen_name"] for v in m1] == ["planner", "security"]
    assert m1[0]["constraints"] == ["c1"]
    assert m1[0]["risk"] == "YELLOW"
    assert m1[0]["confidence"] == 0.8
    assert [v["queen_name"] for v in state.verdicts_for("m2")] == ["planner"]


def test_records_and_replays_events(tmp_path: Path) -> None:
    state = CouncilState(db_path=tmp_path / "s.db")
    state.record_event("m1", event_type="worker_spawned", snapshot_id="snap-1", risk="YELLOW")
    state.record_event("m1", event_type="report", payload={"k": "v"})

    events = state.events_for("m1")
    assert [e["event_type"] for e in events] == ["worker_spawned", "report"]
    assert events[0]["snapshot_id"] == "snap-1"
    assert events[1]["payload"] == {"k": "v"}


def test_state_persists_across_instances(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    CouncilState(db_path=db).record_event("m1", event_type="x")
    assert len(CouncilState(db_path=db).events_for("m1")) == 1


def test_empty_mission_returns_no_rows(tmp_path: Path) -> None:
    state = CouncilState(db_path=tmp_path / "s.db")
    assert state.verdicts_for("missing") == []
    assert state.events_for("missing") == []
