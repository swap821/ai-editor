"""SQLite connection management and schema bootstrap for the memory layers.

Every memory module opens connections through :func:`get_connection` so that
the production PRAGMAs (WAL journaling, ``NORMAL`` synchronous, foreign keys)
and the :class:`sqlite3.Row` factory are applied uniformly. The schema is
defined declaratively in ``schema.sql`` and applied idempotently by
:func:`init_memory_db`.
"""

from __future__ import annotations

import functools
import hashlib
import json
import re
import shutil
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from aios import config
from aios.memory.relevance import content_hash, skill_signature_v2

#: Location of the declarative DDL applied by :func:`init_memory_db`.
_SCHEMA_PATH: Path = Path(__file__).resolve().parent / "schema.sql"


def retry_on_locked(max_retries: int = 3, base_delay: float = 0.1):
    """Retry a function on sqlite3.OperationalError with 'locked' in message.

    Exponential backoff: base_delay * 2^attempt (0.1s, 0.2s, 0.4s).
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_err = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    if "locked" not in str(e).lower():
                        raise
                    last_err = e
                    if attempt < max_retries:
                        time.sleep(base_delay * (2**attempt))
            raise last_err  # type: ignore[misc]

        return wrapper

    return decorator


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
        _commit_with_retry(conn)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _commit_with_retry(
    conn: sqlite3.Connection, max_retries: int = 3, base_delay: float = 0.1
) -> None:
    """Commit with exponential backoff on database-locked errors.

    Even with WAL mode, a writer can still collide with another writer holding
    the single write lock under heavy concurrent load. Retrying the commit a
    few times with backoff (0.1s, 0.2s, 0.4s) lets that transient contention
    clear instead of surfacing a spurious failure to the caller.
    """
    for attempt in range(max_retries + 1):
        try:
            conn.commit()
            return
        except sqlite3.OperationalError as e:
            if "locked" not in str(e).lower():
                raise
            if attempt == max_retries:
                raise
            time.sleep(base_delay * (2**attempt))


def init_memory_db(db_path: Path = config.MEMORY_DB_PATH) -> None:
    """Create all memory-layer tables and indexes if absent (idempotent).

    Reads ``schema.sql`` and executes it as a script, then applies in-place
    :func:`_migrate` steps for columns/indexes that ``CREATE TABLE IF NOT EXISTS``
    cannot add to a pre-existing table. Re-running is safe.
    """
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    _migrate_skill_signature_index(db_path)
    with get_connection(db_path) as conn:
        conn.executescript(schema_sql)
        _migrate(conn)


def _migrate_skill_signature_index(db_path: Path) -> None:
    """Make the legacy `signature` constraint mean what `signature_v2` means.

    `procedural_skills` carries two identity columns that disagree about what
    superseding means, and only one of them is right. `signature_v2`'s unique
    index is PARTIAL -- ``WHERE status != 'superseded'`` -- so a retired row
    steps aside and the arc can be learned again. The legacy `signature`
    column is ``NOT NULL UNIQUE`` at table level, with no such exemption.

    The consequence is a CRASH, not a stale row: `record_attempt` finds no
    active row (correct), INSERTs (correct), and dies on
    ``UNIQUE constraint failed`` -- in the middle of learning, after the model
    has already done the work. `_free_legacy_signature` repairs it at the write
    path and stays as a fallback; this removes the cause.

    SQLite cannot drop a column-level UNIQUE, so the table is rebuilt. Three
    things make that safe enough to do automatically:

    * **A backup first**, beside the database, named with a timestamp.
    * **ids are preserved**, so `compiled_playbooks.skill_id` foreign keys
      still point where they pointed.
    * **The row count is asserted** before the old table is dropped, and the
      whole thing runs in the caller's transaction, so a mismatch rolls the
      rebuild back rather than committing half of it.

    Runs on its OWN connection, outside the caller's transaction, because
    SQLite's documented rebuild procedure needs ``PRAGMA foreign_keys = OFF``
    and that pragma is a NO-OP inside a transaction. `defer_foreign_keys` is
    not a substitute here: `DROP TABLE` performs an implicit `DELETE FROM`
    that fires `compiled_playbooks`'s reference immediately.

    Idempotent: it does nothing once the partial index exists.
    """
    if not db_path.is_file():
        return  # nothing to rebuild in a database that does not exist yet
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        _rebuild_skills_table(conn, db_path)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()


def _rebuild_skills_table(conn: sqlite3.Connection, db_path: Path) -> None:
    """The rebuild itself. Separate so the PRAGMA/rollback dance stays readable."""
    have = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND tbl_name='procedural_skills'"
        )
    }
    if "idx_skills_active_sig" in have:
        return
    table_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='procedural_skills'"
    ).fetchone()
    if not table_sql or "UNIQUE" not in str(table_sql[0]):
        return  # a store created fresh from schema.sql has nothing to rebuild

    before = conn.execute("SELECT COUNT(*) FROM procedural_skills").fetchone()[0]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    shutil.copy2(db_path, db_path.with_suffix(f".{stamp}.pre-sigindex.bak"))

    columns = [row[1] for row in conn.execute("PRAGMA table_info(procedural_skills)")]
    column_list = ", ".join(columns)
    conn.execute("""
        CREATE TABLE procedural_skills_rebuilt (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            signature       TEXT NOT NULL,
            goal_pattern    TEXT NOT NULL,
            steps_json      TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'candidate'
                            CHECK (status IN ('candidate','verified','superseded')),
            success_count   INTEGER NOT NULL DEFAULT 0,
            failure_count   INTEGER NOT NULL DEFAULT 0,
            signature_v2 TEXT,
            reuse_success_count INTEGER NOT NULL DEFAULT 0,
            reuse_failure_count INTEGER NOT NULL DEFAULT 0,
            last_reused_at DATETIME,
            superseded_by INTEGER,
            weak_success_count INTEGER NOT NULL DEFAULT 0,
            verification_strength TEXT,
            consecutive_failures INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute(
        f"INSERT INTO procedural_skills_rebuilt ({column_list}) "
        f"SELECT {column_list} FROM procedural_skills"
    )
    after = conn.execute("SELECT COUNT(*) FROM procedural_skills_rebuilt").fetchone()[0]
    if after != before:
        # Raising rolls back the caller's transaction, so the original table is
        # untouched. Losing a learning row to a migration would be worse than
        # the bug being migrated away.
        raise RuntimeError(
            f"procedural_skills rebuild would lose rows ({before} -> {after}); "
            "refusing and leaving the original table in place"
        )
    conn.execute("DROP TABLE procedural_skills")
    conn.execute("ALTER TABLE procedural_skills_rebuilt RENAME TO procedural_skills")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_skills_status ON procedural_skills(status)"
    )
    # The PARTIAL UNIQUE indexes are deliberately NOT created here. `_migrate`
    # backfills `signature_v2` and then CONSOLIDATES rows that share an arc;
    # creating a unique index before that runs turns a pair of fragments
    # destined for consolidation into an IntegrityError mid-migration. They are
    # created at the end of `_migrate`, once the data is in a state that can
    # satisfy them.


def _migrate(conn: sqlite3.Connection) -> None:
    """Idempotent, in-place schema migrations for already-existing databases.

    ``CREATE TABLE IF NOT EXISTS`` is a no-op on an existing table, so a column
    added to ``schema.sql`` after a DB was first created must be applied with
    ``ALTER TABLE`` here. Runs inside the caller's transaction (after the script).
    """
    # mistake_pool.failed_command (added to persist fail->confirm tracking across
    # approval-replay boundaries; see schema.sql). Nullable-by-default, no backfill.
    mistake_cols = {row[1] for row in conn.execute("PRAGMA table_info(mistake_pool)")}
    if mistake_cols and "failed_command" not in mistake_cols:
        conn.execute(
            "ALTER TABLE mistake_pool ADD COLUMN failed_command TEXT NOT NULL DEFAULT ''"
        )

    # compiled_playbooks.decompiled_at_successes — the skill's promotable
    # success_count when a playbook was retired, so "re-earned since" is a
    # question the compile guard can actually ask. Existing decompiled rows are
    # backfilled to their skill's CURRENT count: we cannot know what it was, so
    # they require growth from here rather than being permanently barred (the
    # bug) or silently forgiven (the over-correction).
    playbook_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(compiled_playbooks)")
    }
    if playbook_cols and "decompiled_at_successes" not in playbook_cols:
        conn.execute(
            "ALTER TABLE compiled_playbooks ADD COLUMN decompiled_at_successes INTEGER"
        )
        playbook_cols.add("decompiled_at_successes")
    if "decompiled_at_successes" in playbook_cols:
        # Stamped whenever a retired row lacks a number, not only when the
        # column is created: an unstamped row means "needs more than it has
        # right now", and the compile guard cannot express that without a
        # number -- with NULL it would compare the skill's count against
        # itself and bar the reflex forever, the defect this column ends.
        #
        # READ FIRST. `init_memory_db` runs on essentially every memory
        # operation, and an unconditional UPDATE here takes a write lock every
        # time: it collided with concurrent writers and burned the full 30s
        # busy timeout before raising `database is locked`. A SELECT takes no
        # write lock, and in the steady state there is nothing to fix.
        unstamped = conn.execute(
            "SELECT 1 FROM compiled_playbooks "
            "WHERE status = 'decompiled' AND decompiled_at_successes IS NULL "
            "LIMIT 1"
        ).fetchone()
        if unstamped:
            conn.execute(
                "UPDATE compiled_playbooks SET decompiled_at_successes = ("
                "  SELECT ps.success_count FROM procedural_skills ps"
                "  WHERE ps.id = compiled_playbooks.skill_id"
                ") WHERE status = 'decompiled' AND decompiled_at_successes IS NULL"
            )

    # Correction transitions are first persisted in the conversation database
    # and then mirrored to the separate immutable authenticated ledger. Keep a
    # durable local marker when that second write fails and is compensated.
    correction_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(conversation_corrections)")
    }
    if correction_cols and "ledger_rejected_at" not in correction_cols:
        conn.execute(
            "ALTER TABLE conversation_corrections ADD COLUMN ledger_rejected_at DATETIME"
        )

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
    semantic_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(semantic_memory)")
    }
    semantic_additions = {
        "content_hash": "TEXT",
        "memory_type": "TEXT NOT NULL DEFAULT 'chat'",
        "verification_status": "TEXT NOT NULL DEFAULT 'unverified'",
        "occurrence_count": "INTEGER NOT NULL DEFAULT 1",
        "last_seen_at": "DATETIME",
    }
    for name, ddl in semantic_additions.items():
        if semantic_cols and name not in semantic_cols:
            if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
                raise ValueError(f"invalid column name: {name}")
            conn.execute(f"ALTER TABLE semantic_memory ADD COLUMN {name} {ddl}")  # noqa: S608

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
    # S2: confidence column on semantic_facts (default 1.0 for existing rows).
    if fact_cols and "confidence" not in fact_cols:
        conn.execute(
            "ALTER TABLE semantic_facts ADD COLUMN confidence REAL NOT NULL DEFAULT 1.0"
        )

    # Procedural skills: trail mechanics (arc-level signature_v2 + reuse
    # pheromone columns), backfill, and consolidation of fragmented trails.
    skill_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(procedural_skills)")
    }
    skill_additions = {
        "signature_v2": "TEXT",
        "reuse_success_count": "INTEGER NOT NULL DEFAULT 0",
        "reuse_failure_count": "INTEGER NOT NULL DEFAULT 0",
        "last_reused_at": "DATETIME",
        "superseded_by": "INTEGER",
        # Verification-strength taxonomy (roadmap Phase 1): weak greens are
        # recorded but ineligible to promote; the latest success's strength is kept.
        "weak_success_count": "INTEGER NOT NULL DEFAULT 0",
        "verification_strength": "TEXT",
        # Failures since the last success — the recent-record counter the reflex
        # compile guard uses in place of the lifetime `failure_count`. Existing
        # rows backfill to 0, which is the honest reading: their recent history
        # is unknown, and the `verified` status they already hold (>=3 STRONG
        # successes at >=80%) is the evidence that gates them either way.
        "consecutive_failures": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, ddl in skill_additions.items():
        if skill_cols and name not in skill_cols:
            if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
                raise ValueError(f"invalid column name: {name}")
            conn.execute(f"ALTER TABLE procedural_skills ADD COLUMN {name} {ddl}")  # noqa: S608

    # Swarm patterns: verification-strength taxonomy (roadmap Phase 1 extension) —
    # a below-floor green is recorded but ineligible to promote a pattern.
    swarm_cols = {row[1] for row in conn.execute("PRAGMA table_info(swarm_patterns)")}
    swarm_additions = {
        "weak_success_count": "INTEGER NOT NULL DEFAULT 0",
        "verification_strength": "TEXT",
    }
    for name, ddl in swarm_additions.items():
        if swarm_cols and name not in swarm_cols:
            if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
                raise ValueError(f"invalid column name: {name}")
            conn.execute(f"ALTER TABLE swarm_patterns ADD COLUMN {name} {ddl}")  # noqa: S608

    # Backfill arc identities (NULL-only => idempotent; pure function of stored
    # data, no clock).
    for row in conn.execute(
        "SELECT id, goal_pattern, steps_json FROM procedural_skills "
        "WHERE signature_v2 IS NULL"
    ).fetchall():
        sig_v2 = skill_signature_v2(
            str(row["goal_pattern"]), list(json.loads(str(row["steps_json"])))
        )
        conn.execute(
            "UPDATE procedural_skills SET signature_v2 = ? WHERE id = ?",
            (sig_v2, int(row["id"])),
        )

    # Consolidate active fragments that share an arc identity. The keeper is
    # the verified row if any (a verified trail must never be buried under a
    # candidate), then the row with the most direct evidence, then the oldest.
    # Losers become 'superseded' with a lineage pointer — counts, signature,
    # and steps stay intact as provenance; nothing is DELETEd (deliberate
    # divergence from the semantic-memory merge above: trail rows are
    # irreplaceable verifier evidence).
    groups: dict[str, list[sqlite3.Row]] = {}
    for row in conn.execute(
        "SELECT * FROM procedural_skills WHERE status != 'superseded' ORDER BY id"
    ).fetchall():
        groups.setdefault(str(row["signature_v2"]), []).append(row)
    for sig_v2, rows in groups.items():
        if len(rows) < 2:
            continue
        keeper = min(
            rows,
            key=lambda r: (
                str(r["status"]) != "verified",
                -(int(r["success_count"]) + int(r["failure_count"])),
                int(r["id"]),
            ),
        )
        keeper_id = int(keeper["id"])
        successes = sum(int(r["success_count"]) for r in rows)
        failures = sum(int(r["failure_count"]) for r in rows)
        reuse_s = sum(int(r["reuse_success_count"] or 0) for r in rows)
        reuse_f = sum(int(r["reuse_failure_count"] or 0) for r in rows)
        # Status is recomputed from DIRECT counts only, with the same rule as
        # SkillMemory.record_attempt (min_successes=3, min_success_rate=0.8 —
        # the ctor defaults in aios/memory/skills.py).
        rate = successes / max(successes + failures, 1)
        status = "verified" if successes >= 3 and rate >= 0.8 else "candidate"
        # The merged arc's recent record is the WORST of its fragments, not the
        # keeper's. Counts add up across fragments, but "failures since the last
        # success" does not, and there are no per-attempt timestamps to derive
        # it from. Taking the max errs toward "this arc has not shown a clean
        # run yet": that only delays a reflex until the next success clears it,
        # whereas taking the keeper's 0 would let an arc whose recent runs
        # failed compile immediately on the strength of a sibling row.
        streak = max(int(r["consecutive_failures"] or 0) for r in rows)
        conn.execute(
            "UPDATE procedural_skills SET success_count = ?, failure_count = ?, "
            "reuse_success_count = ?, reuse_failure_count = ?, status = ?, "
            "consecutive_failures = ?, "
            "updated_at = (SELECT MAX(updated_at) FROM procedural_skills "
            "WHERE signature_v2 = ? AND status != 'superseded') WHERE id = ?",
            (
                successes,
                failures,
                reuse_s,
                reuse_f,
                status,
                streak,
                sig_v2,
                keeper_id,
            ),
        )
        for row in rows:
            if int(row["id"]) == keeper_id:
                continue
            conn.execute(
                "UPDATE procedural_skills SET status = 'superseded', "
                "superseded_by = ? WHERE id = ?",
                (keeper_id, int(row["id"])),
            )
            print(
                f"[migrate] procedural_skills: consolidated trail {int(row['id'])} "
                f"into {keeper_id} (shared arc {sig_v2[:12]}…)"
            )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_skills_active_sig_v2 "
        "ON procedural_skills(signature_v2) WHERE status != 'superseded'"
    )
    # The legacy `signature`, same rule. Only possible once the table-level
    # UNIQUE has been rebuilt away (`_migrate_skill_signature_index`); on a
    # store that still has it this is a harmless duplicate of the constraint.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_skills_active_sig "
        "ON procedural_skills(signature) WHERE status != 'superseded'"
    )

    local_worker_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(local_worker_models)")
    }
    local_worker_additions = {
        "model_version": "TEXT",
        "artifact_digest": "TEXT",
        "qualification_suite_version": "TEXT",
        "qualification_evidence_digest": "TEXT",
        "limitations_json": "TEXT NOT NULL DEFAULT '[]'",
        "qualified_at": "DATETIME",
        "expires_at": "DATETIME",
        # Organ 36: the dispatcher needs a REAL QualificationResult. Before
        # this column existed, qualify() ran the suite and threw the result
        # away, so the call site fabricated a perfect one.
        "qualification_result_json": "TEXT",
    }
    for name, ddl in local_worker_additions.items():
        if local_worker_cols and name not in local_worker_cols:
            conn.execute(f"ALTER TABLE local_worker_models ADD COLUMN {name} {ddl}")
