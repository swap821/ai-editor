from __future__ import annotations

import threading
import time

import pytest

from aios.runtime.live_surface import LiveSurface, SignalType


def test_emit_and_query_resource(tmp_path):
    surface = LiveSurface(db_path=tmp_path / "surface.db")
    sig_id = surface.emit(SignalType.FILE_LOCK, "file.py", "worker-1")
    results = surface.query_resource("file.py")
    assert len(results) == 1
    assert results[0].signal_id == sig_id
    assert results[0].worker_id == "worker-1"
    assert surface.query_resource("other.py") == []


def test_ttl_expiry(tmp_path, monkeypatch):
    surface = LiveSurface(db_path=tmp_path / "surface.db")
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    surface.emit(SignalType.WORKER_ACTIVE, "res", "worker-1", ttl_seconds=5)
    assert len(surface.query_resource("res")) == 1
    monkeypatch.setattr(time, "time", lambda: now + 10)
    assert surface.query_resource("res") == []


def test_sweep_expired(tmp_path, monkeypatch):
    surface = LiveSurface(db_path=tmp_path / "surface.db")
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    surface.emit(SignalType.WORKER_ACTIVE, "res", "worker-1", ttl_seconds=5)
    surface.emit(SignalType.WORKER_ACTIVE, "res2", "worker-2", ttl_seconds=100)
    monkeypatch.setattr(time, "time", lambda: now + 10)
    removed = surface.sweep_expired()
    assert removed == 1
    snap = surface.snapshot()
    assert snap["total"] == 1


def test_query_worker(tmp_path):
    surface = LiveSurface(db_path=tmp_path / "surface.db")
    surface.emit(SignalType.PROGRESS_UPDATE, "res-a", "worker-1")
    surface.emit(SignalType.PROGRESS_UPDATE, "res-b", "worker-1")
    surface.emit(SignalType.PROGRESS_UPDATE, "res-c", "worker-2")
    assert len(surface.query_worker("worker-1")) == 2
    assert len(surface.query_worker("worker-2")) == 1
    assert surface.query_worker("worker-3") == []


def test_active_locks(tmp_path):
    surface = LiveSurface(db_path=tmp_path / "surface.db")
    surface.emit(SignalType.FILE_LOCK, "file.py", "worker-1")
    surface.emit(SignalType.WORKER_ACTIVE, "worker-1", "worker-1")
    locks = surface.active_locks()
    assert len(locks) == 1
    assert locks[0].stype == SignalType.FILE_LOCK


def test_revoke(tmp_path):
    surface = LiveSurface(db_path=tmp_path / "surface.db")
    sig_id = surface.emit(SignalType.FILE_LOCK, "file.py", "worker-1")
    assert surface.revoke(sig_id) is True
    assert surface.query_resource("file.py") == []
    assert surface.revoke(sig_id) is False


def test_snapshot(tmp_path):
    surface = LiveSurface(db_path=tmp_path / "surface.db")
    surface.emit(SignalType.FILE_LOCK, "file.py", "worker-1")
    surface.emit(SignalType.ATTENTION_NEEDED, "res", "worker-2", payload={"why": "stuck"})
    snap = surface.snapshot()
    assert snap["total"] == 2
    assert snap["by_type"][SignalType.FILE_LOCK.value] == 1
    assert snap["by_type"][SignalType.ATTENTION_NEEDED.value] == 1
    assert len(snap["signals"]) == 2


def test_crash_recovery(tmp_path):
    db_path = tmp_path / "surface.db"
    surface = LiveSurface(db_path=db_path)
    surface.emit(SignalType.FILE_LOCK, "file.py", "worker-1", ttl_seconds=300)

    recovered = LiveSurface(db_path=db_path)
    results = recovered.query_resource("file.py")
    assert len(results) == 1
    assert results[0].worker_id == "worker-1"


def test_thread_safety(tmp_path):
    surface = LiveSurface(db_path=tmp_path / "surface.db")
    errors: list[Exception] = []

    def worker(n: int) -> None:
        try:
            for i in range(50):
                surface.emit(SignalType.PROGRESS_UPDATE, f"res-{n}", f"worker-{n}", payload={"i": i})
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    snap = surface.snapshot()
    assert snap["total"] == 8 * 50
