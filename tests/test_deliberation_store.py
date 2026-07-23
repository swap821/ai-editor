"""Organ 39: durable, append-only history for DeliberationRecord."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aios.application.intelligence.deliberation import synthesize_deliberation
from aios.domain.intelligence.deliberation import ModelPosition
from aios.infrastructure.intelligence.deliberation_store import (
    DeliberationStore,
    RecordTamperedError,
)


def _record(deliberation_id: str = "deliberation-1", mission_id: str | None = "mission-1"):
    positions = (
        ModelPosition(
            role="primary",
            provider="ollama",
            exact_model_id="qwen2.5-coder:7b",
            answer="reject",
            confidence=1.0,
        ),
        ModelPosition(
            role="critic",
            provider="gemini",
            exact_model_id="gemini-2.5-flash",
            answer="reject",
            confidence=0.7,
            security_concerns=("unvalidated user input",),
        ),
    )
    return synthesize_deliberation(
        deliberation_id=deliberation_id,
        trigger_reasons=("high_consequence",),
        positions=positions,
        final_disposition="reject",
        mission_id=mission_id,
    )


def test_save_and_get_current_round_trips(tmp_path: Path) -> None:
    store = DeliberationStore(tmp_path / "deliberations.db")
    record = _record()

    revision = store.save(record)

    assert revision == 1
    current = store.get_current(record.deliberation_id)
    assert current is not None
    assert current.deliberation_id == record.deliberation_id
    assert current.final_disposition == "reject"
    assert len(current.positions) == 2
    assert current.unresolved_minority_concerns == ("unvalidated user input",)


def test_get_current_none_when_never_saved(tmp_path: Path) -> None:
    store = DeliberationStore(tmp_path / "deliberations.db")
    assert store.get_current("never-saved") is None


def test_second_save_appends_a_new_revision_not_an_overwrite(tmp_path: Path) -> None:
    store = DeliberationStore(tmp_path / "deliberations.db")
    first = _record()
    store.save(first)

    positions = (
        ModelPosition(
            role="primary", provider="ollama", exact_model_id="qwen2.5-coder:7b",
            answer="reject", confidence=1.0,
        ),
        ModelPosition(
            role="critic", provider="gemini", exact_model_id="gemini-2.5-flash",
            answer="reject", confidence=0.7,
            security_concerns=(),  # resolved this time
        ),
    )
    second = synthesize_deliberation(
        deliberation_id=first.deliberation_id,
        trigger_reasons=("high_consequence",),
        positions=positions,
        final_disposition="reject",
        mission_id="mission-1",
    )
    revision = store.save(second)

    assert revision == 2
    history = store.get_history(first.deliberation_id)
    assert len(history) == 2
    assert history[0].unresolved_minority_concerns == ("unvalidated user input",)
    assert history[1].unresolved_minority_concerns == ()
    # get_current returns the LATEST revision, not the first
    assert store.get_current(first.deliberation_id).unresolved_minority_concerns == ()


def test_for_mission_returns_latest_revision_per_deliberation(tmp_path: Path) -> None:
    store = DeliberationStore(tmp_path / "deliberations.db")
    store.save(_record("deliberation-a", mission_id="mission-1"))
    store.save(_record("deliberation-b", mission_id="mission-1"))
    store.save(_record("deliberation-c", mission_id="mission-2"))

    records = store.for_mission("mission-1")

    assert {r.deliberation_id for r in records} == {"deliberation-a", "deliberation-b"}


def test_for_mission_empty_when_nothing_recorded(tmp_path: Path) -> None:
    store = DeliberationStore(tmp_path / "deliberations.db")
    assert store.for_mission("no-such-mission") == ()


def test_tampered_row_is_detected_at_read_time(tmp_path: Path) -> None:
    db_path = tmp_path / "deliberations.db"
    store = DeliberationStore(db_path)
    record = _record()
    store.save(record)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE deliberation_records SET final_disposition = ? "
        "WHERE deliberation_id = ? AND revision = 1",
        ("approve", record.deliberation_id),
    )
    conn.commit()
    conn.close()

    with pytest.raises(RecordTamperedError):
        store.get_current(record.deliberation_id)
