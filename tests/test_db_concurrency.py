"""Verify SQLite concurrency hardening: WAL mode + retry-on-locked."""
import sqlite3
import threading
from pathlib import Path

import pytest

from aios.memory.db import connect, get_connection, init_memory_db, _commit_with_retry


@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test.db"
    init_memory_db(db_path)
    return db_path


class TestWALMode:
    def test_wal_mode_enabled(self, tmp_db):
        conn = connect(tmp_db)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert mode == "wal"

    def test_foreign_keys_enabled(self, tmp_db):
        conn = connect(tmp_db)
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        conn.close()
        assert fk == 1


class _FlakyConnection(sqlite3.Connection):
    """A real sqlite3.Connection whose ``commit`` can be made to fail on cue.

    ``sqlite3.Connection`` is an immutable C type in this Python build — you
    can neither assign over ``conn.commit`` on an instance (no ``__dict__``)
    nor monkeypatch ``sqlite3.Connection.commit`` at the class level (the type
    itself rejects attribute assignment). Subclassing sidesteps both: the
    subclass is an ordinary heap type, so overriding ``commit`` and adding
    instance state works normally, and ``sqlite3.connect(..., factory=...)``
    accepts any ``Connection`` subclass.
    """

    def _configure(self, fail_times: int, message: str) -> None:
        self.commit_calls = 0
        self._fail_times = fail_times
        self._fail_message = message

    def commit(self):
        self.commit_calls = getattr(self, "commit_calls", 0) + 1
        if self.commit_calls <= getattr(self, "_fail_times", 0):
            raise sqlite3.OperationalError(
                getattr(self, "_fail_message", "database is locked")
            )
        return super().commit()


def _flaky_connect(db_path: Path, fail_times: int, message: str = "database is locked"):
    conn = sqlite3.connect(str(db_path), timeout=30.0, factory=_FlakyConnection)
    conn._configure(fail_times, message)
    return conn


class TestRetryOnLocked:
    def test_commit_retries_on_locked(self, tmp_db):
        """Simulate a locked error that resolves on retry."""
        conn = _flaky_connect(tmp_db, fail_times=2)
        _commit_with_retry(conn)
        assert conn.commit_calls == 3
        conn.close()

    def test_commit_raises_after_max_retries(self, tmp_db):
        """If locked persists past max retries, the error propagates."""
        conn = _flaky_connect(tmp_db, fail_times=10**6)
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            _commit_with_retry(conn, max_retries=2)
        conn.close()

    def test_non_locked_errors_propagate_immediately(self, tmp_db):
        conn = _flaky_connect(tmp_db, fail_times=10**6, message="disk I/O error")
        with pytest.raises(sqlite3.OperationalError, match="disk I/O"):
            _commit_with_retry(conn)
        conn.close()


class TestConcurrentWrites:
    def test_parallel_inserts_no_data_loss(self, tmp_db):
        """Multiple threads writing concurrently should not lose rows."""
        n_threads = 8
        n_inserts_per_thread = 20
        errors = []

        def writer(thread_id):
            for i in range(n_inserts_per_thread):
                try:
                    with get_connection(tmp_db) as conn:
                        conn.execute(
                            "INSERT INTO episodic_memory "
                            "(session_id, role, content, timestamp) "
                            "VALUES (?, ?, ?, datetime('now'))",
                            (f"session_{thread_id}", "user", f"msg_{thread_id}_{i}"),
                        )
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=writer, args=(t,))
            for t in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent writes produced errors: {errors}"

        with get_connection(tmp_db) as conn:
            count = conn.execute("SELECT COUNT(*) FROM episodic_memory").fetchone()[0]
        assert count == n_threads * n_inserts_per_thread
