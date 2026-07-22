from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aios.application.read_models.projection import IncrementalSystemProjection
from aios.operations.doctor import doctor_report
from aios.operations.recovery import (
    RecoveryError,
    create_backup,
    rebuild_projections,
    restore_backup,
    verify_backup,
)
from aios.operations.tracing import (
    bind_trace_context,
    get_trace_context,
    new_trace_context,
)
from aios.runtime.cortex_bus import CortexBus
from tests.cortex_event_helpers import append_event


def test_trace_context_rejects_unbounded_or_invalid_header_values() -> None:
    trace = new_trace_context(
        {
            "x-request-id": "../../secrets",
            "x-turn-id": "turn-1",
            "x-mission-id": "m" * 200,
            "x-worker-id": "worker:1",
        }
    )

    assert trace.request_id != "../../secrets"
    assert trace.turn_id == "turn-1"
    assert trace.mission_id is None
    assert trace.worker_id == "worker:1"
    with bind_trace_context(trace):
        assert get_trace_context() == trace


def test_doctor_reports_executor_as_fatal_only_in_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aios import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "AUDIT_DB_PATH", tmp_path / "audit.db")
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "data" / "backups")
    monkeypatch.setattr(config, "API_TOKEN", "")

    demo = doctor_report(
        profile="demo",
        project_roots=(tmp_path,),
        executor_probe=lambda: (False, "not available"),
    )
    production = doctor_report(
        profile="production",
        project_roots=(tmp_path,),
        executor_probe=lambda: (False, "not available"),
    )

    assert demo.ok
    assert any(
        check.status == "warning" and check.name == "executor" for check in demo.checks
    )
    assert not production.ok
    assert {check.name for check in production.checks if check.status == "fatal"} >= {
        "executor",
        "operator_token",
    }


def test_doctor_uses_explicit_profile_for_audit_severity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aios import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "AUDIT_DB_PATH", tmp_path / "audit.db")
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "data" / "backups")
    monkeypatch.setattr(config, "API_TOKEN", "t" * 32)
    monkeypatch.setenv("AIOS_PROFILE", "development")

    report = doctor_report(
        profile="production",
        project_roots=(tmp_path,),
        executor_probe=lambda: (True, "available"),
    )

    audit_check = next(
        check for check in report.checks if check.name == "audit_integrity"
    )
    assert audit_check.status == "fatal"


def test_doctor_backup_check_missing_directory_is_warning_in_dev_fatal_in_prod(
    tmp_path: Path,
) -> None:
    missing_dir = tmp_path / "no-backups-here"

    demo = doctor_report(
        profile="demo",
        project_roots=(tmp_path,),
        executor_probe=lambda: (True, "available"),
        backup_dir=missing_dir,
    )
    production = doctor_report(
        profile="production",
        project_roots=(tmp_path,),
        executor_probe=lambda: (True, "available"),
        backup_dir=missing_dir,
    )

    demo_check = next(c for c in demo.checks if c.name == "backup_freshness")
    production_check = next(
        c for c in production.checks if c.name == "backup_freshness"
    )
    assert demo_check.status == "warning"
    assert production_check.status == "fatal"


def test_doctor_backup_check_empty_directory_is_warning_in_dev_fatal_in_prod(
    tmp_path: Path,
) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    demo = doctor_report(
        profile="demo",
        project_roots=(tmp_path,),
        executor_probe=lambda: (True, "available"),
        backup_dir=backup_dir,
    )
    production = doctor_report(
        profile="production",
        project_roots=(tmp_path,),
        executor_probe=lambda: (True, "available"),
        backup_dir=backup_dir,
    )

    assert next(c for c in demo.checks if c.name == "backup_freshness").status == (
        "warning"
    )
    assert (
        next(c for c in production.checks if c.name == "backup_freshness").status
        == "fatal"
    )


def test_doctor_backup_check_fresh_backup_passes_even_in_production(
    tmp_path: Path,
) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    (backup_dir / "gagos-20260722T000000Z.tar.gz").write_bytes(b"fake-archive")

    report = doctor_report(
        profile="production",
        project_roots=(tmp_path,),
        executor_probe=lambda: (True, "available"),
        backup_dir=backup_dir,
    )

    check = next(c for c in report.checks if c.name == "backup_freshness")
    assert check.status == "measured"


def test_doctor_backup_check_stale_backup_is_warning_not_fatal_in_production(
    tmp_path: Path,
) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    stale = backup_dir / "gagos-20260101T000000Z.tar.gz"
    stale.write_bytes(b"fake-archive")
    eight_days_ago = datetime.now(timezone.utc).timestamp() - (8 * 24 * 60 * 60)
    os.utime(stale, (eight_days_ago, eight_days_ago))

    report = doctor_report(
        profile="production",
        project_roots=(tmp_path,),
        executor_probe=lambda: (True, "available"),
        backup_dir=backup_dir,
    )

    check = next(c for c in report.checks if c.name == "backup_freshness")
    assert check.status == "warning"
    assert "day(s) old" in check.message


def test_doctor_backup_check_picks_the_newest_of_several_archives(
    tmp_path: Path,
) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    older = backup_dir / "gagos-20260101T000000Z.tar.gz"
    newer = backup_dir / "gagos-20260722T000000Z.tar.gz"
    older.write_bytes(b"old")
    newer.write_bytes(b"new")
    now = datetime.now(timezone.utc).timestamp()
    os.utime(older, (now - (30 * 24 * 60 * 60), now - (30 * 24 * 60 * 60)))
    os.utime(newer, (now, now))

    report = doctor_report(
        profile="demo",
        project_roots=(tmp_path,),
        executor_probe=lambda: (True, "available"),
        backup_dir=backup_dir,
    )

    check = next(c for c in report.checks if c.name == "backup_freshness")
    assert check.status == "measured"
    assert newer.name in check.message


def test_backup_manifest_excludes_environment_files_and_round_trips_state(
    tmp_path: Path,
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "state.json").write_text('{"ok": true}', encoding="utf-8")
    (data / ".env").write_text("SECRET=do-not-back-up", encoding="utf-8")
    bundle = tmp_path / "backup.tar.gz"

    manifest = create_backup(data_dir=data, destination=bundle)
    assert manifest.files == {"state.json": manifest.files["state.json"]}
    assert verify_backup(bundle).files == manifest.files

    (data / "state.json").write_text('{"ok": false}', encoding="utf-8")
    with pytest.raises(RecoveryError, match="safety backup"):
        restore_backup(bundle=bundle, data_dir=data)

    restored = restore_backup(
        bundle=bundle,
        data_dir=data,
        safety_backup=tmp_path / "pre-restore.tar.gz",
    )
    assert restored is not None
    assert json.loads((data / "state.json").read_text(encoding="utf-8")) == {"ok": True}
    assert (tmp_path / "pre-restore.tar.gz").exists()


def test_projection_rebuild_replays_only_durable_observations(tmp_path: Path) -> None:
    bus = CortexBus(db_path=tmp_path / "cortex.db", retention_max=100)
    append_event(
        bus, "worker.started", "worker-1", {"worker_id": "worker-1", "role": "tester"}
    )
    append_event(bus, "model.selected", "model-1", {"model": "local"})

    assert rebuild_projections(bus=bus) == 2
    projection = IncrementalSystemProjection(tmp_path / "system_portrait.db")
    snapshot = projection.snapshot()
    assert snapshot.active_workers == ("worker-1",)
    assert snapshot.active_models == ("local",)
    assert bus.consumer_cursor("system-portrait").last_event_id == 2
