"""Tests for the Rollback Registry (aios.runtime.rollback_registry)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from aios.runtime.rollback_registry import RollbackRegistry


def _registry(tmp_path: Path, retention_days: int = 30) -> RollbackRegistry:
    return RollbackRegistry(
        db_path=tmp_path / "rollback.db", retention_days=retention_days
    )


def test_register_and_get(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.register(
        "snap-1",
        "mission-1",
        "/workspace/a",
        files_covered=["a.py", "b.py"],
        metadata={"reason": "pre-edit"},
        created_at="2026-01-01T00:00:00+00:00",
    )

    entry = reg.get("snap-1")

    assert entry is not None
    assert entry.snapshot_id == "snap-1"
    assert entry.mission_id == "mission-1"
    assert entry.workspace_root == "/workspace/a"
    assert entry.files_covered == ["a.py", "b.py"]
    assert entry.metadata == {"reason": "pre-edit"}
    assert entry.created_at == "2026-01-01T00:00:00+00:00"


def test_register_idempotent(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.register(
        "snap-1", "mission-1", "/workspace/a",
        created_at="2026-01-01T00:00:00+00:00",
    )
    reg.register(
        "snap-1",
        "mission-1",
        "/workspace/a",
        files_covered=["c.py"],
        metadata={"note": "updated"},
        created_at="2026-01-02T00:00:00+00:00",
    )

    assert reg.count() == 1
    entry = reg.get("snap-1")
    assert entry is not None
    assert entry.files_covered == ["c.py"]
    assert entry.metadata == {"note": "updated"}
    assert entry.created_at == "2026-01-02T00:00:00+00:00"


def test_query_by_mission(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.register("snap-1", "mission-a", "/ws", created_at="2026-01-01T00:00:00+00:00")
    reg.register("snap-2", "mission-b", "/ws", created_at="2026-01-02T00:00:00+00:00")
    reg.register("snap-3", "mission-a", "/ws", created_at="2026-01-03T00:00:00+00:00")

    results = reg.query(mission_id="mission-a")

    assert {e.snapshot_id for e in results} == {"snap-1", "snap-3"}


def test_query_by_time_range(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.register("snap-1", "mission-1", "/ws", created_at="2026-01-01T00:00:00+00:00")
    reg.register("snap-2", "mission-1", "/ws", created_at="2026-01-05T00:00:00+00:00")
    reg.register("snap-3", "mission-1", "/ws", created_at="2026-01-10T00:00:00+00:00")

    after_only = reg.query(after="2026-01-02T00:00:00+00:00")
    before_only = reg.query(before="2026-01-05T00:00:00+00:00")
    ranged = reg.query(
        after="2026-01-02T00:00:00+00:00", before="2026-01-09T00:00:00+00:00"
    )

    assert {e.snapshot_id for e in after_only} == {"snap-2", "snap-3"}
    assert {e.snapshot_id for e in before_only} == {"snap-1", "snap-2"}
    assert {e.snapshot_id for e in ranged} == {"snap-2"}


def test_query_by_file_pattern(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.register(
        "snap-1", "mission-1", "/ws",
        files_covered=["src/main.py", "README.md"],
        created_at="2026-01-01T00:00:00+00:00",
    )
    reg.register(
        "snap-2", "mission-1", "/ws",
        files_covered=["src/other.ts"],
        created_at="2026-01-02T00:00:00+00:00",
    )

    py_only = reg.query(file_pattern="*.py")
    src_any = reg.query(file_pattern="src/*")

    assert {e.snapshot_id for e in py_only} == {"snap-1"}
    assert {e.snapshot_id for e in src_any} == {"snap-1", "snap-2"}


def test_query_by_workspace(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.register("snap-1", "mission-1", "/ws/a", created_at="2026-01-01T00:00:00+00:00")
    reg.register("snap-2", "mission-1", "/ws/b", created_at="2026-01-02T00:00:00+00:00")

    results = reg.query(workspace_root="/ws/a")

    assert {e.snapshot_id for e in results} == {"snap-1"}


def test_prune_removes_old(tmp_path: Path) -> None:
    reg = _registry(tmp_path, retention_days=30)
    old_ts = (
        datetime.now(timezone.utc) - timedelta(days=40)
    ).replace(microsecond=0).isoformat()
    reg.register("snap-old", "mission-1", "/ws", created_at=old_ts)

    removed = reg.prune()

    assert removed == 1
    assert reg.get("snap-old") is None
    assert reg.count() == 0


def test_prune_keeps_recent(tmp_path: Path) -> None:
    reg = _registry(tmp_path, retention_days=30)
    recent_ts = (
        datetime.now(timezone.utc) - timedelta(days=1)
    ).replace(microsecond=0).isoformat()
    reg.register("snap-recent", "mission-1", "/ws", created_at=recent_ts)

    removed = reg.prune()

    assert removed == 0
    assert reg.get("snap-recent") is not None
    assert reg.count() == 1


def test_health_report(tmp_path: Path) -> None:
    reg = _registry(tmp_path, retention_days=15)
    reg.register("snap-1", "mission-1", "/ws/a", created_at="2026-01-01T00:00:00+00:00")
    reg.register("snap-2", "mission-1", "/ws/a", created_at="2026-01-05T00:00:00+00:00")
    reg.register("snap-3", "mission-2", "/ws/b", created_at="2026-01-10T00:00:00+00:00")

    report = reg.health()

    assert report["total"] == 3
    assert report["workspaces"] == {"/ws/a": 2, "/ws/b": 1}
    assert report["oldest"] == "2026-01-01T00:00:00+00:00"
    assert report["newest"] == "2026-01-10T00:00:00+00:00"
    assert report["retention_days"] == 15


def test_count(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    assert reg.count() == 0

    reg.register("snap-1", "mission-1", "/ws", created_at="2026-01-01T00:00:00+00:00")
    reg.register("snap-2", "mission-1", "/ws", created_at="2026-01-02T00:00:00+00:00")

    assert reg.count() == 2


def test_empty_registry(tmp_path: Path) -> None:
    reg = _registry(tmp_path)

    assert reg.query() == []
    assert reg.get("nope") is None
    assert reg.count() == 0

    report = reg.health()
    assert report["total"] == 0
    assert report["workspaces"] == {}
    assert report["oldest"] is None
    assert report["newest"] is None
    assert report["retention_days"] == 30
