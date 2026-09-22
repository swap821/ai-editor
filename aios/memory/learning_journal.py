"""Append-only record of what the learning faculties actually did.

Every other learning table stores the CURRENT state — a skill's counts, a
playbook's status, a curriculum level's mastery. Each of those is an UPDATE, so
the transition is destroyed by the row recording its result. "This reflex is
retired" survives; "it was retired after two replay failures, having earned 4
promotable successes" does not.

That gap is what LC4 asks about. A faculty whose history can be overwritten
cannot be audited after the fact, only believed — and this repository's entire
claim to honesty is that evidence outlives the claim it supports.

DELIBERATELY WRITE-ONLY. There is no update, no delete, and no "correct a bad
entry" helper, because a journal with an edit path is a log. A wrong entry is
fixed by appending the correction, the way the audit ledger does it.

Failure here must never break learning: journalling is an observation of a
transition, not part of it. A `record()` that raises would mean a compile fails
because writing *about* the compile failed, which is the tail wagging the dog.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

from aios import config
from aios.logging_config import get_logger
from aios.memory.db import get_connection

logger = get_logger(__name__)

#: The faculties of the learning ledger. Kept here so a typo in a call site
#: becomes a visible unknown rather than a silently mis-filed entry.
FACULTIES = frozenset({"L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8"})


def record(
    faculty: str,
    transition: str,
    *,
    subject_id: Optional[int] = None,
    run_id: str = "",
    detail: Optional[dict[str, Any]] = None,
    db_path: Path = config.MEMORY_DB_PATH,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    """Append one transition. Never raises.

    *conn* lets a caller journal inside the transaction that performed the
    transition, so the entry and the state change commit together or not at
    all. Without it the entry could survive a rolled-back compile and describe
    something that never happened.
    """
    if faculty not in FACULTIES:
        logger.warning("learning journal: unknown faculty %r", faculty)
    payload = (
        faculty,
        transition,
        subject_id,
        json.dumps(detail or {}, ensure_ascii=False, default=str),
        run_id,
    )
    sql = (
        "INSERT INTO learning_events "
        "(faculty, transition, subject_id, detail_json, run_id) "
        "VALUES (?, ?, ?, ?, ?)"
    )
    try:
        if conn is not None:
            conn.execute(sql, payload)
            return
        with get_connection(db_path) as own:
            own.execute(sql, payload)
    except Exception as exc:  # noqa: BLE001 - observing a transition must not break it
        logger.warning(
            "learning journal: failed to record %s/%s",
            faculty,
            transition,
            exc_info=exc,
        )


def history(
    faculty: Optional[str] = None,
    *,
    limit: int = 50,
    db_path: Path = config.MEMORY_DB_PATH,
) -> list[dict[str, Any]]:
    """Recent transitions, newest first. Read-only."""
    sql = "SELECT id, ts, run_id, faculty, transition, subject_id, detail_json FROM learning_events"
    params: tuple = ()
    if faculty:
        sql += " WHERE faculty = ?"
        params = (faculty,)
    sql += " ORDER BY id DESC LIMIT ?"
    params = (*params, limit)
    try:
        with get_connection(db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []
    out = []
    for row in rows:
        entry = dict(row)
        try:
            entry["detail"] = json.loads(entry.pop("detail_json") or "{}")
        except json.JSONDecodeError:
            entry["detail"] = {}
        out.append(entry)
    return out
