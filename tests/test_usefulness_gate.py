"""The usefulness gate: does what the animal learned reach a live turn, and did
a judged run show it helps?

Measured 2026-10-12 on the operator's live store (read-only): 23 candidate
lessons, 0 admitted (every one unsigned), 0 active skills. Memory reached no
live turn, so usefulness was structurally zero before any payoff question.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools import production_readiness as pr


def _world(tmp_path: Path) -> pr.World:
    repo, data = tmp_path / "repo", tmp_path / "data"
    (repo / "docs" / "learning").mkdir(parents=True)
    data.mkdir()
    return pr.World(
        repo=repo,
        data_dir=data,
        env={},
        run=lambda argv, env: (1, ""),
        http_json=lambda url: None,
        http_status=lambda url: None,
        now=datetime(2026, 10, 12, tzinfo=timezone.utc),
    )


def _census(lessons: int, reach: int, refused: dict | None = None) -> dict:
    refused_lessons = dict(refused or {})
    if reach:
        refused_lessons["another principal"] = reach
    return {
        "principal": "scoreboard:owns-nothing",
        "lessons": 0,
        "skills": 0,
        "candidates": {"lessons": lessons, "skills": 0},
        "refused": {"lessons": refused_lessons, "skills": {}},
    }


@pytest.fixture
def census(monkeypatch):
    from tools import learning_payoff

    box: dict = {}
    calls: list = []

    def fake(principal, *, db=None, library_db=None):
        calls.append((principal, db, library_db))
        return box["value"]

    monkeypatch.setattr(learning_payoff, "gate_census", fake)
    box["calls"] = calls
    return box


def test_memory_that_reaches_no_turn_fails_and_says_why(tmp_path, census) -> None:
    world = _world(tmp_path)
    census["value"] = _census(23, 0, {"unsigned": 23})
    gate = pr.animal_usefulness(world)
    assert gate.status == pr.FAIL
    assert "0 of 23 lessons" in gate.evidence and "unsigned" in gate.evidence
    assert gate.owner == "operator"
    (principal, db, library_db) = census["calls"][0]
    assert db == world.data_dir / "aios_memory.db", "the LIVE store, not the harness's"
    assert library_db == world.data_dir / "aios_operational_state.db"
    assert principal == "scoreboard:owns-nothing"


def test_reachable_memory_without_a_judged_run_is_not_measured(
    tmp_path, census
) -> None:
    census["value"] = _census(23, 5, {"unsigned": 18})
    gate = pr.animal_usefulness(_world(tmp_path))
    assert gate.status == pr.NOT_MEASURED
    assert "5 of 23 lessons" in gate.evidence


@pytest.mark.parametrize("met,status", [(True, pr.PASS), (False, pr.FAIL)])
def test_a_judged_run_decides(tmp_path, census, met, status) -> None:
    world = _world(tmp_path)
    census["value"] = _census(23, 5)
    (world.repo / pr.JUDGED_PAYOFF).write_text(
        json.dumps({"h1_met": met, "summary": "Holm over the family"}),
        encoding="utf-8",
    )
    gate = pr.animal_usefulness(world)
    assert gate.status == status
    assert "Holm over the family" in gate.evidence


def test_a_judged_pass_cannot_outlive_memory_that_no_longer_reaches(
    tmp_path, census
) -> None:
    world = _world(tmp_path)
    (world.repo / pr.JUDGED_PAYOFF).write_text(
        json.dumps({"h1_met": True}), encoding="utf-8"
    )
    census["value"] = _census(23, 0, {"revoked": 23})
    assert pr.animal_usefulness(world).status == pr.FAIL


def test_the_census_reads_the_store_it_is_given(tmp_path) -> None:
    """A real census over a real (tiny) store: one verified, unsigned lesson."""
    from aios.memory.db import init_memory_db
    from tools import learning_payoff

    db = tmp_path / "aios_memory.db"
    init_memory_db(db)
    with sqlite3.connect(db) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(mistake_pool)")}
        values = {
            "task_id": "t",
            "confidence_delta": -0.1,
            "error_type": "e",
            "root_cause": "r",
            "fix_applied": "f",
            "lesson_text": "l",
            "verification_status": "verified",
        }
        values = {k: v for k, v in values.items() if k in columns}
        conn.execute(
            f"INSERT INTO mistake_pool ({', '.join(values)}) "
            f"VALUES ({', '.join('?' for _ in values)})",
            tuple(values.values()),
        )
    census = learning_payoff.gate_census(
        "scoreboard:owns-nothing", db=db, library_db=tmp_path / "absent.db"
    )
    assert census["candidates"] == {"lessons": 1, "skills": 0}
    assert census["lessons"] == 0
    assert "another principal" not in census["refused"]["lessons"], (
        "an unsigned lesson reaches no one"
    )
