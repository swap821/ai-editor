#!/usr/bin/env python3
"""Phase 2 slice 2.4c: retire every reflex that no operator activation backs.

Operator decision (2026-09-25): playbooks are not copied into the institutional
library. Reflexes are recompiled from ACTIVE skills only, and the existing ones
are retired with a recorded reason. This tool does the retiring.

A compiled reflex is KEPT only if the operator activated its skill in the
library with exactly the steps the reflex replays. That is the same question
the live gate asks (`Cerebellum.activation_backs`, one derivation, two
callers). Every other compiled reflex is retired: status `retired`, a reason,
and an L5 journal entry.

Retirement is not decompilation. A decompiled reflex can be earned back; a
retired one cannot, because the skill that compiled it was self-promoted. If
the operator later activates that skill, a NEW reflex compiles from the
activated procedure.

    python tools/retire_legacy_playbooks.py            # dry run (default)
    python tools/retire_legacy_playbooks.py --apply    # backup, then retire
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from aios import config  # noqa: E402

REASON = (
    "Phase 2.4c: compiled from a skill the legacy store promoted by itself; "
    "reflexes now compile only from operator-activated library skills"
)


def _gated_cerebellum(memory_db: Path, library_db: Path):
    from aios.application.memory.institutional_skills import (
        InstitutionalSkillAdapter,
        SkillTrailIndex,
    )
    from aios.core.cerebellum import Cerebellum
    from aios.domain.learning.repository import SkillRepository

    repository = SkillRepository(library_db)
    cerebellum = Cerebellum(memory_db)
    cerebellum.attach_reflex_gate(
        InstitutionalSkillAdapter(repository, SkillTrailIndex(library_db))
    )
    return cerebellum


def plan(memory_db: Path, library_db: Path) -> tuple[list[dict], list[dict]]:
    """(to_retire, to_keep): every COMPILED reflex, split by activation."""
    cerebellum = _gated_cerebellum(memory_db, library_db)
    retire: list[dict] = []
    keep: list[dict] = []
    for row in cerebellum.playbook_map():
        entry = {
            "id": row["id"],
            "skill_id": row["skill_id"],
            "goal_pattern": str(row["goal_pattern"])[:100],
        }
        playbook = cerebellum._cache[row["id"]]
        (keep if cerebellum.activation_backs(playbook) else retire).append(entry)
    return retire, keep


def apply(memory_db: Path, backup_dir: Path, ids: list[int]) -> Path:
    """Back up, then retire *ids* in one transaction, journalling each."""
    from aios.memory.db import get_connection
    from aios.memory.learning_freeze import assert_learning_permitted
    from aios.memory.learning_journal import record as journal

    assert_learning_permitted("cerebellum.retire_legacy_playbooks")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = backup_dir / f"{memory_db.stem}.pre-reflex-retirement.{stamp}.db"
    source = sqlite3.connect(f"file:{memory_db.as_posix()}?mode=ro", uri=True)
    target = sqlite3.connect(backup)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    with get_connection(memory_db) as conn:
        for playbook_id in ids:
            conn.execute(
                "UPDATE compiled_playbooks SET status = 'retired', retired_reason = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'compiled'",
                (REASON, playbook_id),
            )
            journal(
                "L5",
                "retired",
                subject_id=playbook_id,
                detail={"reason": REASON},
                conn=conn,
            )
    return backup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--apply", action="store_true", help="retire (default: dry run)"
    )
    parser.add_argument("--memory-db", type=Path, default=config.MEMORY_DB_PATH)
    parser.add_argument(
        "--library-db", type=Path, default=config.OPERATIONAL_STATE_DB_PATH
    )
    parser.add_argument(
        "--backup-dir", type=Path, default=REPO_ROOT / "data" / "backups"
    )
    args = parser.parse_args(argv)

    retire, keep = plan(args.memory_db, args.library_db)
    print(
        json.dumps({"to_retire": retire, "to_keep": keep, "reason": REASON}, indent=2)
    )
    if not args.apply:
        print(f"\nDRY RUN: {len(retire)} to retire, {len(keep)} backed by activation.")
        return 0
    backup = apply(args.memory_db, args.backup_dir, [r["id"] for r in retire])
    remaining, _kept = plan(args.memory_db, args.library_db)
    print(f"\nretired {len(retire)}; backup {backup}")
    if remaining:
        print(f"SELF-CHECK FAILED: {len(remaining)} unbacked reflex(es) still compiled")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
