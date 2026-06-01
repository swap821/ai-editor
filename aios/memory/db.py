"""SQLite connection management and schema bootstrap for the memory layers.

Every memory module opens connections through :func:`get_connection` so that
the production PRAGMAs (WAL journaling, ``NORMAL`` synchronous, foreign keys)
and the :class:`sqlite3.Row` factory are applied uniformly. The schema is
defined declaratively in ``schema.sql`` and applied idempotently by
:func:`init_memory_db`.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from aios import config

#: Location of the declarative DDL applied by :func:`init_memory_db`.
_SCHEMA_PATH: Path = Path(__file__).resolve().parent / "schema.sql"


def connect(db_path: Path = config.MEMORY_DB_PATH) -> sqlite3.Connection:
    """Open a tuned SQLite connection.

    Applies WAL journaling (concurrent agent reads during writes), ``NORMAL``
    synchronous mode (durable enough for a local app, far faster than ``FULL``),
    foreign-key enforcement, and a :class:`sqlite3.Row` row factory so callers
    can address columns by name.

    Args:
        db_path: Database file to open. Parent directories are created.

    Returns:
        An open, configured :class:`sqlite3.Connection`.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def get_connection(
    db_path: Path = config.MEMORY_DB_PATH,
) -> Iterator[sqlite3.Connection]:
    """Context manager yielding a connection; commits on success, always closes.

    On any exception the transaction is rolled back and the error re-raised, so
    a failed write never leaves a half-applied transaction behind.
    """
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_memory_db(db_path: Path = config.MEMORY_DB_PATH) -> None:
    """Create all memory-layer tables and indexes if absent (idempotent).

    Reads ``schema.sql`` and executes it as a script. Re-running is safe because
    every statement uses ``IF NOT EXISTS``.
    """
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection(db_path) as conn:
        conn.executescript(schema_sql)
