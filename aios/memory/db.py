"""SQLite connection management and schema bootstrap for the memory layers.

Every memory module opens connections through :func:`get_connection` so that
the production PRAGMAs (WAL journaling, ``NORMAL`` synchronous, foreign keys)
and the :class:`sqlite3.Row` factory are applied uniformly. The schema is
defined declaratively in ``schema.sql`` and applied idempotently by
:func:`init_memory_db`.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from aios import config
from aios.memory.relevance import content_hash

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

    Reads ``schema.sql`` and executes it as a script, then applies in-place
    :func:`_migrate` steps for columns/indexes that ``CREATE TABLE IF NOT EXISTS``
    cannot add to a pre-existing table. Re-running is safe.
    """
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection(db_path) as conn:
        conn.executescript(schema_sql)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """Idempotent, in-place schema migrations for already-existing databases.

    ``CREATE TABLE IF NOT EXISTS`` is a no-op on an existing table, so a column
    added to ``schema.sql`` after a DB was first created must be applied with
    ``ALTER TABLE`` here. Runs inside the caller's transaction (after the script).
    """
    # self_analysis_report.fingerprint (added post-PR#4 for finding reconcile).
    cols = {row[1] for row in conn.execute("PRAGMA table_info(self_analysis_report)")}
    if cols and "fingerprint" not in cols:
        conn.execute("ALTER TABLE self_analysis_report ADD COLUMN fingerprint TEXT")
        # Pre-migration 'open' rows carry no fingerprint and are deterministically
        # regenerable on the next scan; drop them so the open set stays clean.
        # NEVER touch decided rows (proposed/approved/applied/...): that is lineage.
        conn.execute(
            "DELETE FROM self_analysis_report WHERE status = 'open' AND fingerprint IS NULL"
        )
    # self_analysis_report.proposed_by (added for T2 propose-diff; §6.3 groundwork
    # so T3 can require a human approver != the proposer). Nullable, no backfill.
    if cols and "proposed_by" not in cols:
        conn.execute("ALTER TABLE self_analysis_report ADD COLUMN proposed_by TEXT")
    # self_analysis_report.approved_by (added for T3 apply; the HUMAN approver of an
    # applied/rolled_back proposal — enforced != proposed_by, §6.3). Nullable.
    if cols and "approved_by" not in cols:
        conn.execute("ALTER TABLE self_analysis_report ADD COLUMN approved_by TEXT")
    # Enforce the invariant — at most one OPEN row per fingerprint. Created HERE
    # (not in schema.sql) so it runs only after the column is guaranteed to exist on
    # both fresh and migrated DBs. (``cols`` is empty only if the table is somehow
    # absent after executescript — the ``if cols`` guard above is harmless defense.)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_sar_open_fp "
        "ON self_analysis_report(fingerprint) WHERE status = 'open'"
    )

    # Episodic session identifiers were historically stored raw. Convert them
    # in-place to the same non-reversible lookup key used by current writes.
    for row in conn.execute("SELECT DISTINCT session_id FROM episodic_memory"):
        session_id = str(row["session_id"])
        if re.fullmatch(r"[0-9a-f]{64}", session_id):
            continue
        digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
        conn.execute(
            "UPDATE episodic_memory SET session_id = ? WHERE session_id = ?",
            (digest, session_id),
        )

    # Semantic memories originally stored only text/vector ids. Add lifecycle
    # metadata, backfill stable hashes, and merge exact normalized duplicates.
    semantic_cols = {row[1] for row in conn.execute("PRAGMA table_info(semantic_memory)")}
    semantic_additions = {
        "content_hash": "TEXT",
        "memory_type": "TEXT NOT NULL DEFAULT 'chat'",
        "verification_status": "TEXT NOT NULL DEFAULT 'unverified'",
        "occurrence_count": "INTEGER NOT NULL DEFAULT 1",
        "last_seen_at": "DATETIME",
    }
    for name, ddl in semantic_additions.items():
        if semantic_cols and name not in semantic_cols:
            conn.execute(f"ALTER TABLE semantic_memory ADD COLUMN {name} {ddl}")

    semantic_rows = conn.execute(
        "SELECT id, text_content, occurrence_count FROM semantic_memory "
        "WHERE verification_status != 'superseded' ORDER BY id"
    ).fetchall()
    keeper_by_hash: dict[str, int] = {}
    for row in semantic_rows:
        digest = content_hash(str(row["text_content"]))
        keeper = keeper_by_hash.get(digest)
        if keeper is None:
            keeper_by_hash[digest] = int(row["id"])
            conn.execute(
                "UPDATE semantic_memory SET content_hash = ?, "
                "last_seen_at = COALESCE(last_seen_at, timestamp) WHERE id = ?",
                (digest, int(row["id"])),
            )
            continue
        conn.execute(
            "UPDATE semantic_memory SET occurrence_count = occurrence_count + ? "
            "WHERE id = ?",
            (int(row["occurrence_count"] or 1), keeper),
        )
        conn.execute("DELETE FROM semantic_memory WHERE id = ?", (int(row["id"]),))
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_semantic_active_hash "
        "ON semantic_memory(content_hash) WHERE verification_status != 'superseded'"
    )

    fact_cols = {row[1] for row in conn.execute("PRAGMA table_info(semantic_facts)")}
    if fact_cols and "approved_by" not in fact_cols:
        conn.execute("ALTER TABLE semantic_facts ADD COLUMN approved_by TEXT")
