#!/usr/bin/env python3
"""Re-admit reviewed learned rows into recall -- the operator's act (plan Phase 3d).

Since Phase 3c a lesson, a semantic memory or a fact reaches a live prompt only
if its newest provenance record verifies under the pinned LIVE key. Rows
written before provenance existed are never backfill-signed: signing them now
would forge a history nobody recorded (``docs/learning/PHASE3_DESIGN.md``).
They come back one of two ways: re-earned by the loop, or re-admitted here,
by the operator, one reviewed row at a time.

A re-admission signs the row's CURRENT content, as ``transition: readmitted``,
naming the approver -- and, since plan Phase 4c, the PRINCIPAL the row belongs
to. A row learned before principal scoping names nobody, so recall withholds it
from everyone (operator decision 2026-10-04) until the operator attributes it
here. An already-attributed row is never moved to another principal.

It vouches for what the operator read, and nothing else: a later edit to the
row breaks the signature again.

    python tools/readmit_learning.py                       # list what is refused
    python tools/readmit_learning.py --table mistake_pool --ids 3,7 \\
        --approver operator:swap --principal operator:swap  # dry run
    python tools/readmit_learning.py --table mistake_pool --ids 3,7 \\
        --approver operator:swap --principal operator:swap --apply  # sign

Operator-run only. It signs with ``AIOS_LEARNING_KEY_LIVE`` from YOUR
environment and refuses without it. It never prints a key. There is no "all":
every id is named.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aios import config  # noqa: E402
from aios.memory.db import init_memory_db  # noqa: E402
from aios.memory import provenance as provenance_module  # noqa: E402
from aios.application.memory.provenance_policy import (  # noqa: E402
    fact_digest,
    lesson_digest,
    semantic_digest,
)
from aios.memory.provenance import (  # noqa: E402
    LearningSigner,
    LearningVerifier,
    Provenance,
    ProvenanceStore,
)

#: The recall channels a row can be re-admitted into, and what "worth
#: reviewing" means for each: only rows recall could show.
CHANNELS: dict[str, tuple[Callable[[Any], str], str, str]] = {
    "mistake_pool": (
        lesson_digest,
        "SELECT * FROM mistake_pool WHERE verification_status IN "
        "('verified', 'pending') ORDER BY id",
        "lesson_text",
    ),
    "semantic_memory": (
        semantic_digest,
        "SELECT * FROM semantic_memory WHERE verification_status = 'verified' "
        "ORDER BY id",
        "text_content",
    ),
    "semantic_facts": (
        fact_digest,
        "SELECT * FROM semantic_facts WHERE status = 'active' "
        "AND approved_by IS NOT NULL ORDER BY id",
        "object",
    ),
}


#: Attribute an unattributed row to a principal (plan Phase 4c). Static per
#: table, so no identifier is interpolated; ``principal_id IS NULL`` so a row
#: someone already owns is never moved.
_ATTRIBUTE = {
    "mistake_pool": (
        "UPDATE mistake_pool SET principal_id = ? WHERE id = ? AND principal_id IS NULL"
    ),
    "semantic_memory": (
        "UPDATE semantic_memory SET principal_id = ? "
        "WHERE id = ? AND principal_id IS NULL"
    ),
    "semantic_facts": (
        "UPDATE semantic_facts SET principal_id = ? WHERE id = ? AND principal_id IS NULL"
    ),
}


class ReadmitError(RuntimeError):
    """A re-admission that must not happen: said plainly, never half-done."""


def _rows(db: Path, table: str) -> list[sqlite3.Row]:
    _digest, sql, _text = CHANNELS[table]
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return list(conn.execute(sql).fetchall())
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def status(
    db: Path, store: ProvenanceStore, verifier: LearningVerifier
) -> dict[str, list[dict[str, Any]]]:
    """Every recall-eligible row per channel that the live gate would REFUSE."""
    refused: dict[str, list[dict[str, Any]]] = {}
    for table, (digest, _sql, text_field) in CHANNELS.items():
        for row in _rows(db, table):
            verdict = verifier.verify(
                store.latest(table, str(row["id"])),
                content_sha256=digest(row),
                context="live",
            )
            reason = verdict.reason
            if verdict.admitted:
                signed = store.latest(table, str(row["id"]))
                if signed is not None and signed.provenance.principal:
                    continue
                # Signed, but by no principal (plan Phase 4c): withheld from
                # every principal until attributed here.
                reason = "unattributed: learned before principal scoping"
            refused.setdefault(table, []).append(
                {
                    "id": int(row["id"]),
                    "reason": reason,
                    "text": str(row[text_field])[:160],
                }
            )
    return refused


def readmit(
    db: Path,
    store: ProvenanceStore,
    signer: LearningSigner,
    *,
    table: str,
    ids: list[int],
    approver: str,
    principal: str,
) -> list[int]:
    """Sign each named row's CURRENT state as re-admitted by *approver*, as
    *principal*'s.

    All-or-nothing up front: an unknown table, a missing approver or
    principal, no live key, an id that is not a recall-eligible row, or a row
    another principal already owns refuses the whole call before anything is
    written.
    """
    if table not in CHANNELS:
        raise ReadmitError(f"unknown channel {table!r}: {sorted(CHANNELS)}")
    if not approver.strip():
        raise ReadmitError("an approver is required: re-admission is a human act")
    if not principal.strip():
        raise ReadmitError(
            "a principal is required (plan Phase 4c): a re-admitted row is "
            "someone's, and recall returns it to that principal only"
        )
    if "live" not in signer.kinds:
        raise ReadmitError(
            "no live signing key in this environment (AIOS_LEARNING_KEY_LIVE); "
            "re-admission signs as the live store, so it cannot run here"
        )
    digest_of, _sql, _text = CHANNELS[table]
    # The additive principal_id column (plan Phase 4c) may not exist yet if the
    # backend has not restarted since the upgrade: apply it, as startup would.
    init_memory_db(db)
    eligible = {int(row["id"]): row for row in _rows(db, table)}
    unknown = [i for i in ids if i not in eligible]
    if unknown:
        raise ReadmitError(
            f"not recall-eligible rows of {table}: {unknown}; nothing was signed"
        )
    owner = principal.strip()
    owned = [i for i in ids if eligible[i]["principal_id"] not in (None, owner)]
    if owned:
        raise ReadmitError(
            f"rows of {table} that another principal owns: {owned}; a row is "
            "never moved between principals, and nothing was signed"
        )
    # Every check before any write: the emergency stop refuses the whole call
    # here, through the same check the provenance store makes, so a refused
    # re-admission never leaves a row attributed but unsigned.
    provenance_module.assert_learning_permitted("learning.readmit")
    with sqlite3.connect(db) as conn:
        for row_id in ids:
            conn.execute(_ATTRIBUTE[table], (owner, row_id))
    attributed = {int(row["id"]): row for row in _rows(db, table)}
    done: list[int] = []
    for row_id in ids:
        provenance = Provenance(
            table=table,
            row_id=str(row_id),
            content_sha256=digest_of(attributed[row_id]),
            source_kind="live",
            transition="readmitted",
            approver=approver.strip(),
            principal=owner,
        )
        store.append(provenance, signer.sign(provenance))
        done.append(row_id)
    return done


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--memory-db", type=Path, default=config.MEMORY_DB_PATH)
    parser.add_argument("--table", choices=sorted(CHANNELS))
    parser.add_argument("--ids", default="", help="comma-separated row ids")
    parser.add_argument("--approver", default="", help="who reviewed them")
    parser.add_argument(
        "--principal",
        default="",
        help="whose rows they become (plan Phase 4c); recall returns them to "
        "this principal only",
    )
    parser.add_argument("--apply", action="store_true", help="sign (default: dry run)")
    args = parser.parse_args(argv)

    store = ProvenanceStore(args.memory_db)
    verifier = LearningVerifier.from_pinned_file()
    if not args.table:
        print(json.dumps(status(args.memory_db, store, verifier), indent=2))
        return 0
    ids = [int(part) for part in args.ids.split(",") if part.strip()]
    if not ids:
        print("name the rows: --ids 3,7 (there is no 'all')")
        return 2
    if not args.apply:
        rows = {int(r["id"]): r for r in _rows(args.memory_db, args.table)}
        text_field = CHANNELS[args.table][2]
        for row_id in ids:
            row = rows.get(row_id)
            shown = str(row[text_field])[:200] if row is not None else "<not eligible>"
            print(
                f"would re-admit {args.table}:{row_id} as "
                f"{args.principal or '<no principal: refused>'}  {shown}"
            )
        print("\nDRY RUN: nothing signed. Add --apply to sign.")
        return 0
    try:
        done = readmit(
            args.memory_db,
            store,
            LearningSigner.from_env(),
            table=args.table,
            ids=ids,
            approver=args.approver,
            principal=args.principal,
        )
    except ReadmitError as exc:
        print(f"REFUSED: {exc}")
        return 1
    print(f"re-admitted {args.table}: {done} (approver {args.approver.strip()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
