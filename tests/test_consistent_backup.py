"""A backup taken while GAGOS runs restores to a consistent, complete state.

Found 2026-10-11 while hardening for 24/7 production: ``create_backup``
copied each SQLite database as raw bytes, its ``-wal``/``-shm`` beside it
captured at a different instant, and read every file twice -- once to hash,
once to archive. A scheduled backup of a running system could restore a
database missing committed writes, or corrupt, or produce an archive that
disagrees with its own manifest. Pinned:

* committed writes that live only in the WAL are in the backup;
* no sidecar is archived; the restored database passes integrity_check;
* a writer hammering the database during the backup cannot make the archive
  disagree with its manifest, and the snapshot is a consistent instant;
* other files are archived byte-identical; a file merely NAMED like a
  sidecar, with no database beside it, is kept.
"""

from __future__ import annotations

import sqlite3
import tarfile
import threading
from pathlib import Path

from aios.core.autonomy import UNGOVERNED_FIXTURE
from aios.operations.recovery import create_backup, restore_backup, verify_backup


def _wal_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA wal_autocheckpoint = 0")  # keep commits in the WAL
    conn.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.commit()
    return conn


def _restore(bundle: Path, tmp_path: Path) -> Path:
    target = tmp_path / "restored"
    restore_backup(bundle=bundle, data_dir=target, emergency_stop=UNGOVERNED_FIXTURE)
    return target


def _rows(db: Path) -> int:
    with sqlite3.connect(str(db)) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        return conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]


def test_commits_still_in_the_wal_are_backed_up(tmp_path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    live = _wal_db(data / "memory.db")
    live.executemany(
        "INSERT INTO t (v) VALUES (?)", [(f"row-{i}",) for i in range(500)]
    )
    live.commit()
    assert (data / "memory.db-wal").stat().st_size > 0, (
        "the rows must still be in the WAL"
    )

    bundle = tmp_path / "gagos-test.tar.gz"
    manifest = create_backup(data_dir=data, destination=bundle)
    live.close()

    assert not any(name.endswith(("-wal", "-shm")) for name in manifest.files)
    with tarfile.open(bundle) as archive:
        assert not any(n.endswith(("-wal", "-shm")) for n in archive.getnames())
    assert _rows(_restore(bundle, tmp_path) / "memory.db") == 500


def test_a_backup_during_writes_matches_its_manifest(tmp_path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    live = _wal_db(data / "memory.db")
    live.executemany(
        "INSERT INTO t (v) VALUES (?)", [("x" * 200,) for _ in range(2000)]
    )
    live.commit()
    stop = threading.Event()

    def write() -> None:
        while not stop.is_set():
            live.execute("INSERT INTO t (v) VALUES (?)", ("y" * 200,))
            live.commit()

    writer = threading.Thread(target=write)
    writer.start()
    try:
        bundles = []
        for i in range(5):
            bundle = tmp_path / f"gagos-{i}.tar.gz"
            create_backup(data_dir=data, destination=bundle)
            bundles.append(bundle)
    finally:
        stop.set()
        writer.join()
        live.close()
    for bundle in bundles:
        verify_backup(bundle)  # raises on any manifest/content disagreement
    restored = _rows(_restore(bundles[-1], tmp_path) / "memory.db")
    assert restored >= 2000


def test_other_files_are_archived_byte_identical(tmp_path) -> None:
    data = tmp_path / "data"
    (data / "nested").mkdir(parents=True)
    payload = bytes(range(256)) * 10
    (data / "nested" / "blob.bin").write_bytes(payload)
    (data / "notes-wal").write_text("not a database sidecar", encoding="utf-8")
    bundle = tmp_path / "gagos-files.tar.gz"
    manifest = create_backup(data_dir=data, destination=bundle)
    assert "notes-wal" in manifest.files, "a file named like a sidecar is still a file"
    restored = _restore(bundle, tmp_path)
    assert (restored / "nested" / "blob.bin").read_bytes() == payload
    assert (restored / "notes-wal").read_text(
        encoding="utf-8"
    ) == "not a database sidecar"


def test_the_schedule_runs_the_idempotent_daily_backup() -> None:
    """The installer registers exactly the command doctor's staleness check
    and the scoreboard's backups gate expect to have run."""
    script = (
        Path(__file__).resolve().parents[1] / "tools" / "install_backup_schedule.ps1"
    ).read_text(encoding="utf-8")
    assert "-m aios backup create --if-stale --stale-after-seconds 86400" in script
    assert "-StartWhenAvailable" in script, (
        "a missed backup must run when the laptop wakes"
    )
    assert "New-ScheduledTaskTrigger -Daily" in script
