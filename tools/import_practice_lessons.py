#!/usr/bin/env python3
"""Bring chosen, VERIFIED lessons from a practice store into a memory store.

Practice runs in an isolated store (a worktree's own ``data/``), so a run can
never write to the operator's live memory. What it learned reaches the live
store only through this tool and then through re-admission, which is the
operator's act:

    python tools/import_practice_lessons.py --from <practice>/aios_memory.db
        # list the verified lessons it holds
    python tools/import_practice_lessons.py --from ... --ids 12,15
        # dry run: what would be imported
    python tools/import_practice_lessons.py --from ... --ids 12,15 --apply
        # import, unsigned
    python tools/readmit_learning.py --table mistake_pool --ids <new ids>
        --approver operator:you --principal operator:you --apply  # the review

An imported lesson is **unsigned**, so recall refuses it (Phase 3c) until the
operator reads it and re-admits it. Only VERIFIED lessons are offered: a
pending lesson is recalled only within its own practice task, so it would
never reach a live turn. Every id is named; there is no "all". A lesson whose
text the destination already holds is refused, not duplicated. Writes go
through the store's own API, so its secret scrubbing and the learning freeze
apply as they do to any lesson.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aios import config  # noqa: E402
from aios.core.verification_strength import VerificationStrength  # noqa: E402
from aios.memory.db import init_memory_db  # noqa: E402
from aios.memory.learning_freeze import assert_learning_permitted  # noqa: E402
from aios.memory.mistake import MistakeMemory  # noqa: E402
from aios.memory.relevance import content_hash  # noqa: E402


class ImportError_(RuntimeError):
    """The import was refused; nothing was written."""


def _verified(db: Path) -> dict[int, sqlite3.Row]:
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM mistake_pool WHERE verification_status = 'verified' "
            "ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return {int(r["id"]): r for r in rows}


def _texts(db: Path) -> set[str]:
    init_memory_db(db)
    with sqlite3.connect(db) as conn:
        return {
            content_hash(str(t))
            for (t,) in conn.execute(
                "SELECT lesson_text FROM mistake_pool "
                "WHERE verification_status != 'superseded'"
            )
        }


def import_lessons(source: Path, destination: Path, ids: list[int]) -> dict[int, int]:
    """Import *ids* from *source* into *destination*: ``{source id: new id}``.

    Every check runs before any write, so a refused call writes nothing."""
    if not ids:
        raise ImportError_("name the lessons: --ids 3,7 (there is no 'all')")
    if source.resolve() == destination.resolve():
        raise ImportError_("source and destination are the same store")
    offered = _verified(source)
    missing = [i for i in ids if i not in offered]
    if missing:
        raise ImportError_(f"not verified lessons of the practice store: {missing}")
    held = _texts(destination)
    duplicate = [i for i in ids if content_hash(str(offered[i]["lesson_text"])) in held]
    if duplicate:
        raise ImportError_(
            f"the destination already holds the text of {duplicate}; nothing written"
        )
    assert_learning_permitted("lessons.import")
    store = MistakeMemory(db_path=destination)
    done: dict[int, int] = {}
    for source_id in ids:
        row = offered[source_id]
        new_id = store.record(
            f"practice:{row['task_id']}",
            str(row["error_type"]),
            str(row["root_cause"]),
            str(row["fix_applied"]),
            str(row["lesson_text"]),
            float(row["confidence_delta"]),
        )
        # Verified in practice: the identical command passed after the
        # failure that taught it. Still unsigned, so recall refuses it until
        # the operator re-admits it.
        store.promote(new_id, strength=VerificationStrength.STRONG)
        done[source_id] = new_id
    return done


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--from", dest="source", type=Path, required=True)
    parser.add_argument(
        "--to", dest="destination", type=Path, default=config.MEMORY_DB_PATH
    )
    parser.add_argument("--ids", default="", help="comma-separated practice lesson ids")
    parser.add_argument(
        "--apply", action="store_true", help="import (default: dry run)"
    )
    args = parser.parse_args(argv)

    offered = _verified(args.source)
    ids = [int(part) for part in args.ids.split(",") if part.strip()]
    if not ids:
        listing: list[dict[str, Any]] = [
            {
                "id": i,
                "error_type": r["error_type"],
                "lesson_text": r["lesson_text"],
                "task": r["task_id"],
            }
            for i, r in offered.items()
        ]
        print(json.dumps(listing, indent=2))
        print(f"\n{len(listing)} verified lesson(s). Name the ones to import: --ids")
        return 0
    if not args.apply:
        for i in ids:
            row = offered.get(i)
            shown = (
                str(row["lesson_text"])[:200]
                if row is not None
                else "<not a verified lesson>"
            )
            print(f"would import #{i}: {shown}")
        print(f"\nDRY RUN into {args.destination}: nothing written. Add --apply.")
        return 0
    try:
        done = import_lessons(args.source, args.destination, ids)
    except ImportError_ as exc:
        print(f"REFUSED: {exc}")
        return 1
    print(f"imported (practice id -> new id): {done}")
    print(
        "They are UNSIGNED: recall refuses them until you re-admit each one with "
        "tools/readmit_learning.py --table mistake_pool --ids "
        + ",".join(str(v) for v in done.values())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
