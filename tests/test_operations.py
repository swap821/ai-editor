from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aios.application.read_models.projection import IncrementalSystemProjection
from aios.operations.doctor import doctor_report, newest_backup_age_seconds
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


# --------------------------------------------------------------------------- #
# newest_backup_age_seconds -- shared by doctor's freshness check and the
# CLI's `backup create --if-stale` (organ 54: scheduled backup cadence)
# --------------------------------------------------------------------------- #


def test_newest_backup_age_seconds_is_none_for_missing_directory(
    tmp_path: Path,
) -> None:
    assert newest_backup_age_seconds(tmp_path / "no-such-dir") is None


def test_newest_backup_age_seconds_is_none_for_empty_directory(
    tmp_path: Path,
) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    assert newest_backup_age_seconds(backup_dir) is None


def test_newest_backup_age_seconds_measures_the_newest_archive(
    tmp_path: Path,
) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    archive = backup_dir / "gagos-20260722T000000Z.tar.gz"
    archive.write_bytes(b"fake-archive")
    one_hour_ago = datetime.now(timezone.utc).timestamp() - 3600
    os.utime(archive, (one_hour_ago, one_hour_ago))

    age = newest_backup_age_seconds(backup_dir)

    assert age is not None
    assert 3500 < age < 3700


def test_cli_backup_create_if_stale_skips_when_fresh_creates_when_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Organ 54: makes `backup create --if-stale` safe for an OS-level
    scheduler (cron/systemd timer/Task Scheduler) to invoke on a fixed
    cadence -- a fresh existing archive means no-op, a stale or missing one
    means a real backup is created, matching the same freshness threshold
    doctor_report() already reports on."""
    import types

    from aios import __main__ as cli
    from aios import config

    backup_dir = tmp_path / "backups"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "aios_memory.db").write_bytes(b"state")
    monkeypatch.setattr(config, "BACKUP_DIR", backup_dir)
    monkeypatch.setattr(config, "DATA_DIR", data_dir)

    args = types.SimpleNamespace(
        backup_command="create",
        output=None,
        if_stale=True,
        stale_after_seconds=None,
        json=True,
    )

    # No backup exists yet -- must create one.
    assert cli._cmd_backup(args) == 0
    assert json.loads(capsys.readouterr().out)["created"] is True
    assert len(list(backup_dir.glob("gagos-*.tar.gz"))) == 1

    # Freshly created -- a second invocation must skip, not pile up archives.
    assert cli._cmd_backup(args) == 0
    skipped_payload = json.loads(capsys.readouterr().out)
    assert skipped_payload["created"] is False
    assert skipped_payload["reason"] == "most recent backup is still fresh"
    assert len(list(backup_dir.glob("gagos-*.tar.gz"))) == 1

    # Force staleness via a negative threshold -- must decide to create
    # again (the decision itself, not the collidable same-second filename,
    # is what this proves). A threshold of exactly 0 is a real boundary bug
    # magnet: on a fast CI runner, back-to-back calls can land within the
    # filesystem's mtime resolution, making age_seconds compute as 0.0,
    # which incorrectly satisfies "age_seconds <= threshold" and skips.
    # age_seconds can never be negative, so -1 is unambiguous.
    stale_args = types.SimpleNamespace(
        backup_command="create",
        output=None,
        if_stale=True,
        stale_after_seconds=-1,
        json=True,
    )
    assert cli._cmd_backup(stale_args) == 0
    assert json.loads(capsys.readouterr().out)["created"] is True


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
