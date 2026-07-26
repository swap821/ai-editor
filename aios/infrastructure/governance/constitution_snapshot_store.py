"""SQLite persistence for `ConstitutionSnapshotV1` (organ 45).

Closes the gap `build_constitution_snapshot()`'s own docstring names: "this
function... does not persist a chain across process restarts". Snapshots
are content-addressed (keyed by `snapshot_digest`); a separate "current
pointer" table tracks which snapshot is live per `constitution_id`, so
`rollback_amendment()`'s "revert to the exact predecessor" can move the
pointer back to an already-existing row instead of inserting a duplicate.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from aios.domain.governance.constitution import (
    ConstitutionSnapshotV1,
    snapshot_digest_from_record,
)
from aios.infrastructure.storage.migrations import apply_migrations


class RecordTamperedError(RuntimeError):
    """Raised when a stored record's digest no longer matches its content."""


class ConcurrentActivationError(RuntimeError):
    """Raised when a compare-and-swap activation loses the race.

    The caller read a "current" snapshot, decided what should follow it, and
    by the time it wrote, the current pointer had already moved. Refusing the
    write is what keeps the chain single-threaded: two concurrent activations
    produce one ordered chain plus one loser, never two competing "current"
    versions.
    """


class _Unchecked:
    """Type of :data:`UNCHECKED`."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "UNCHECKED"


#: Explicit opt-out of the compare-and-swap. ``expected_previous_digest`` is a
#: REQUIRED argument precisely so this cannot be reached by accident: a bare
#: ``store.save(snapshot)`` is a TypeError, not a silent unprotected write.
#:
#: Distinct from ``expected_previous_digest=None``, which is a real assertion
#: that *no* current pointer exists yet (the first activation).
#:
#: No production call site should use this. It exists for test fixtures that
#: are seeding state rather than exercising activation, and for a documented
#: one-time migration. Grepping for ``UNCHECKED`` finds every such write.
UNCHECKED = _Unchecked()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ConstitutionSnapshotStore:
    """Durable, content-addressed history of constitution snapshots, plus
    the current live pointer per `constitution_id`."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            apply_migrations(conn, scope="constitution")
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        # ``isolation_level=None`` puts this connection in autocommit mode so
        # ``save()`` can issue its own explicit ``BEGIN IMMEDIATE`` -- the
        # only way to make the pointer read and the pointer write one
        # atomic, write-locked step. WAL plus a real busy timeout is what
        # lets a second uvicorn worker block on that lock instead of
        # immediately failing with "database is locked".
        conn = sqlite3.connect(str(self.db_path), timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def save(
        self,
        snapshot: ConstitutionSnapshotV1,
        *,
        expected_previous_digest: str | None | _Unchecked,
    ) -> None:
        """Record `snapshot` (a no-op if this exact digest is already
        stored) and point `constitution_id`'s current snapshot at it.

        ``expected_previous_digest`` is REQUIRED and makes this a
        compare-and-swap:

        * ``None`` -- assert that *no* current pointer exists yet. This is
          the first-activation/bootstrap case; if another writer got there
          first, that is a real race and this raises rather than clobbering.
        * a digest -- assert the current pointer is exactly that snapshot.
        * :data:`UNCHECKED` -- explicitly opt out (test fixtures only).

        There is deliberately no default. An unprotected write into the
        current pointer is the exact hazard this organ exists to close, so
        reaching one has to be a decision somebody typed, greppable as
        ``UNCHECKED`` -- not the thing that happens when you forget a keyword.

        On a failed assertion nothing is written and
        :class:`ConcurrentActivationError` is raised. The compare and the
        write share one ``BEGIN IMMEDIATE`` transaction, so the check cannot
        be invalidated between reading and writing.
        """
        payload = snapshot.as_dict()
        now = _utc_now()
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if not isinstance(expected_previous_digest, _Unchecked):
                    row = conn.execute(
                        "SELECT snapshot_digest FROM constitution_current_pointer "
                        "WHERE constitution_id = ?",
                        (snapshot.constitution_id,),
                    ).fetchone()
                    actual = row["snapshot_digest"] if row is not None else None
                    if actual != expected_previous_digest:
                        raise ConcurrentActivationError(
                            f"constitution {snapshot.constitution_id!r} moved "
                            f"under this activation: expected current "
                            f"{expected_previous_digest!r}, found {actual!r}"
                        )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO constitution_snapshots (
                        snapshot_digest, constitution_id, version, snapshot_json,
                        recorded_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot.snapshot_digest,
                        snapshot.constitution_id,
                        snapshot.version,
                        json.dumps(payload, sort_keys=True),
                        now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO constitution_current_pointer (
                        constitution_id, snapshot_digest, updated_at
                    ) VALUES (?, ?, ?)
                    ON CONFLICT(constitution_id) DO UPDATE SET
                        snapshot_digest = excluded.snapshot_digest,
                        updated_at = excluded.updated_at
                    """,
                    (snapshot.constitution_id, snapshot.snapshot_digest, now),
                )
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")

    def get_current(self, constitution_id: str) -> ConstitutionSnapshotV1 | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT s.* FROM constitution_snapshots s
                INNER JOIN constitution_current_pointer p
                    ON p.snapshot_digest = s.snapshot_digest
                WHERE p.constitution_id = ?
                """,
                (constitution_id,),
            ).fetchone()
        if row is None:
            return None
        return _snapshot_from_row(row)

    def get_by_digest(self, snapshot_digest: str) -> ConstitutionSnapshotV1 | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM constitution_snapshots WHERE snapshot_digest = ?",
                (snapshot_digest,),
            ).fetchone()
        if row is None:
            return None
        return _snapshot_from_row(row)

    def get_history(self, constitution_id: str) -> tuple[ConstitutionSnapshotV1, ...]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM constitution_snapshots WHERE constitution_id = ? "
                "ORDER BY version ASC",
                (constitution_id,),
            ).fetchall()
        return tuple(_snapshot_from_row(row) for row in rows)


def _snapshot_from_row(row: sqlite3.Row) -> ConstitutionSnapshotV1:
    payload = json.loads(row["snapshot_json"])
    record = ConstitutionSnapshotV1.model_validate(payload)
    recomputed = snapshot_digest_from_record(record)
    if recomputed != row["snapshot_digest"]:
        raise RecordTamperedError(
            f"stored constitution snapshot digest mismatch for "
            f"{row['constitution_id']!r} version {row['version']}: the row "
            "was altered outside this store"
        )
    return record


__all__ = [
    "UNCHECKED",
    "ConcurrentActivationError",
    "ConstitutionSnapshotStore",
    "RecordTamperedError",
]
