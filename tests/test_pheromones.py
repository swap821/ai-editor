from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from aios.memory.pheromones import Pheromone, PheromoneStore, PheromoneType


def _store(tmp_path: Path, **kwargs) -> PheromoneStore:
    return PheromoneStore(db_path=tmp_path / "pheromones.sqlite3", **kwargs)


def test_deposit_and_query(tmp_path: Path) -> None:
    store = _store(tmp_path)
    pid = store.deposit(
        PheromoneType.SUCCESS_TRAIL,
        "src/foo.py",
        "worker-1",
        strength=0.9,
        payload={"summary": "passed 2 times"},
    )
    assert isinstance(pid, int)
    results = store.query(resource="src/foo.py")
    assert len(results) == 1
    result = results[0]
    assert isinstance(result, Pheromone)
    assert result.resource == "src/foo.py"
    assert result.ptype == PheromoneType.SUCCESS_TRAIL
    assert result.depositor == "worker-1"
    assert result.payload == {"summary": "passed 2 times"}
    assert 0.0 < result.strength <= 0.9


def test_decay_formula(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base_time = 1_800_000_000.0
    monkeypatch.setattr(time, "time", lambda: base_time)
    store = _store(tmp_path, lambda_decay=0.02, floor=0.01)
    pid = store.deposit(PheromoneType.SUCCESS_TRAIL, "src/bar.py", "worker-2", strength=1.0)

    hours_elapsed = 35.0
    monkeypatch.setattr(time, "time", lambda: base_time + hours_elapsed * 3600.0)
    results = store.query(resource="src/bar.py", min_strength=0.0)
    assert len(results) == 1
    expected = 1.0 * math.exp(-0.02 * hours_elapsed)
    assert results[0].strength == pytest.approx(expected, rel=1e-9)
    assert results[0].strength == pytest.approx(0.5, rel=0.02)
    assert results[0].pheromone_id == pid


def test_reinforce(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base_time = 1_800_000_000.0
    monkeypatch.setattr(time, "time", lambda: base_time)
    store = _store(tmp_path)
    pid = store.deposit(PheromoneType.SUCCESS_TRAIL, "src/baz.py", "worker-3", strength=0.5)

    monkeypatch.setattr(time, "time", lambda: base_time + 10 * 3600.0)
    before = store.query(resource="src/baz.py", min_strength=0.0)[0]

    store.reinforce(pid, boost=0.3)
    after_reinforce_time = base_time + 10 * 3600.0
    monkeypatch.setattr(time, "time", lambda: after_reinforce_time)
    after = store.query(resource="src/baz.py", min_strength=0.0)[0]

    assert after.strength > before.strength
    assert after.strength == pytest.approx(0.8, rel=1e-9)


def test_query_min_strength_filter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base_time = 1_800_000_000.0
    monkeypatch.setattr(time, "time", lambda: base_time)
    store = _store(tmp_path, lambda_decay=0.02, floor=0.01)
    store.deposit(PheromoneType.SUCCESS_TRAIL, "src/old.py", "worker-4", strength=1.0)

    monkeypatch.setattr(time, "time", lambda: base_time + 500 * 3600.0)
    results = store.query(resource="src/old.py", min_strength=0.1)
    assert results == []

    results_low_threshold = store.query(resource="src/old.py", min_strength=0.0)
    assert len(results_low_threshold) == 1


def test_decay_all_prunes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base_time = 1_800_000_000.0
    monkeypatch.setattr(time, "time", lambda: base_time)
    store = _store(tmp_path, lambda_decay=0.02, floor=0.01)
    store.deposit(PheromoneType.FAILURE_WARNING, "src/expired.py", "worker-5", strength=0.5)
    store.deposit(PheromoneType.FAILURE_WARNING, "src/fresh.py", "worker-5", strength=1.0)

    monkeypatch.setattr(time, "time", lambda: base_time + 400 * 3600.0)
    pruned = store.decay_all()
    assert pruned == 2

    monkeypatch.setattr(time, "time", lambda: base_time)
    store2 = _store(tmp_path, lambda_decay=0.02, floor=0.01)
    store2.deposit(PheromoneType.FAILURE_WARNING, "src/keep.py", "worker-6", strength=1.0)
    monkeypatch.setattr(time, "time", lambda: base_time + 3600.0)
    pruned2 = store2.decay_all()
    assert pruned2 == 0
    assert len(store2.query(resource="src/keep.py", min_strength=0.0)) == 1


def test_for_contract(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.deposit(
        PheromoneType.SUCCESS_TRAIL,
        "path/to/file.py",
        "worker-7",
        strength=0.85,
        payload={"outcome": "passed", "count": 3},
    )
    contexts = store.for_contract(["path/to/file.py", "path/to/other.py"])
    assert len(contexts) == 1
    assert contexts[0].startswith("[success-trail] path/to/file.py (strength=0.")
    assert "passed 3 times" in contexts[0]


def test_query_by_type(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.deposit(PheromoneType.SUCCESS_TRAIL, "src/mixed.py", "worker-8", strength=0.9)
    store.deposit(PheromoneType.FAILURE_WARNING, "src/mixed.py", "worker-8", strength=0.9)
    store.deposit(PheromoneType.FILE_LOCK, "src/mixed.py", "worker-8", strength=0.9)

    success_only = store.query(resource="src/mixed.py", ptype=PheromoneType.SUCCESS_TRAIL)
    assert len(success_only) == 1
    assert success_only[0].ptype == PheromoneType.SUCCESS_TRAIL

    all_results = store.query(resource="src/mixed.py")
    assert len(all_results) == 3


def test_empty_store(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.query() == []
    assert store.query(resource="does/not/exist.py") == []
    assert store.for_contract([]) == []
    assert store.for_contract(["does/not/exist.py"]) == []
    assert store.decay_all() == 0


def test_multiple_resources(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.deposit(PheromoneType.SUCCESS_TRAIL, "src/a.py", "worker-9", strength=0.7)
    store.deposit(PheromoneType.SUCCESS_TRAIL, "src/b.py", "worker-9", strength=0.9)

    results_a = store.query(resource="src/a.py")
    results_b = store.query(resource="src/b.py")
    assert len(results_a) == 1
    assert len(results_b) == 1
    assert results_a[0].resource == "src/a.py"
    assert results_b[0].resource == "src/b.py"

    all_results = store.query()
    assert len(all_results) == 2
