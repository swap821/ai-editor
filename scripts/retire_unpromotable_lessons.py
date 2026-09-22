#!/usr/bin/env python3
"""Retire lessons that can never be confirmed, and say exactly what changed.

THE SITUATION
-------------
A lesson is promoted when the command that produced it later succeeds. The
match is against `mistake_pool.failed_command`. That column was added in the
same change that started populating it, so every lesson written before that day
has an empty one and is **structurally unpromotable** -- not unlucky, not
pending, incapable.

All 87 lessons in the live pool are in that state. So "0 verified / 87" has
been read as a broken promotion path for weeks, and it is not: the path works
and has never had anything it could act on. A number that cannot move is worse
than a bad number, because people stop looking at it.

WHAT THIS DOES, AND DOES NOT DO
-------------------------------
Sets `verification_status = 'superseded'` on those rows. That value is already
in the table's CHECK constraint and is already what recall filters out, so this
needs no schema change and removes nothing.

It does NOT delete. Those lessons are real history -- they record failures that
really happened -- and deleting them to tidy a counter would be the same
instinct as rewriting an arc to get a green. They remain readable, and
`--undo` puts them back.

    python scripts/retire_unpromotable_lessons.py --dry-run
    python scripts/retire_unpromotable_lessons.py
    python scripts/retire_unpromotable_lessons.py --undo
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from aios import config  # noqa: E402
from aios.memory.db import get_connection  # noqa: E402

_UNPROMOTABLE = (
    "verification_status = 'pending' "
    "AND (failed_command IS NULL OR TRIM(failed_command) = '')"
)


def _backup(db: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    target = db.with_suffix(f".{stamp}.bak")
    shutil.copy2(db, target)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path(config.MEMORY_DB_PATH))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--undo",
        action="store_true",
        help="return retired rows to 'pending' (they were never deleted)",
    )
    args = parser.parse_args(argv)

    if not args.db.is_file():
        print(f"no memory database at {args.db}")
        return 2

    with get_connection(args.db) as conn:
        if args.undo:
            rows = conn.execute(
                "SELECT COUNT(*) n FROM mistake_pool WHERE verification_status = "
                "'superseded' AND (failed_command IS NULL OR TRIM(failed_command) = '')"
            ).fetchone()["n"]
            print(f"{rows} retired lesson(s) would return to 'pending'")
            if args.dry_run:
                return 0
            print(f"backup: {_backup(args.db).name}")
            conn.execute(
                "UPDATE mistake_pool SET verification_status = 'pending' "
                "WHERE verification_status = 'superseded' "
                "  AND (failed_command IS NULL OR TRIM(failed_command) = '')"
            )
            print(f"restored {rows}")
            return 0

        by_type = conn.execute(
            f"SELECT error_type, COUNT(*) n FROM mistake_pool WHERE {_UNPROMOTABLE} "
            "GROUP BY error_type ORDER BY n DESC"
        ).fetchall()
        total = sum(int(r["n"]) for r in by_type)
        promotable = conn.execute(
            "SELECT COUNT(*) n FROM mistake_pool WHERE verification_status = 'pending' "
            "AND failed_command IS NOT NULL AND TRIM(failed_command) != ''"
        ).fetchone()["n"]

        print(f"{total} unpromotable lesson(s) — no failed_command to ever match:")
        for row in by_type:
            print(f"  {int(row['n']):>4}  {row['error_type']}")
        print(f"\n{promotable} pending lesson(s) CAN still promote and are untouched.")

        if not total:
            return 0
        if args.dry_run:
            print("\ndry run — nothing changed")
            return 0

        print(f"\nbackup: {_backup(args.db).name}")
        conn.execute(
            f"UPDATE mistake_pool SET verification_status = 'superseded' "
            f"WHERE {_UNPROMOTABLE}"
        )
        print(
            f"retired {total} (status='superseded', nothing deleted; "
            "re-run with --undo to reverse)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
