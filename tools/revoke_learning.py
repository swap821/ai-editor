#!/usr/bin/env python3
"""Revoke learned rows -- the operator's act (plan Phase 6e, threat T6).

A lesson, a semantic memory or a fact the operator no longer trusts is
REVOKED here, one named row at a time. A revocation:

* signs the row's current content as ``transition: revoked``, naming the
  approver -- recall refuses a revoked row, and no machine transition can
  build on it (a recurrence onto a revoked lesson is never signed);
* tombstones its CONTENT for its principal (lessons and semantic memory), so
  the same lesson learned again from another task is withdrawn at birth;
* cascades: every row recorded as derived from it (``learning_derivations``)
  is withdrawn too, and so on down;
* is journalled, so a cached self-model built before it is rebuilt.

It is a withdrawal, so the emergency stop does not refuse it: revoking what
the system remembers is exactly what an operator may need mid-incident. Only
``tools/readmit_learning.py`` -- the operator again -- brings a row back.

    python tools/revoke_learning.py --table mistake_pool --ids 3,7 \\
        --approver operator:swap --reason "wrong fix"           # dry run
    python tools/revoke_learning.py --table mistake_pool --ids 3,7 \\
        --approver operator:swap --reason "wrong fix" --apply   # sign

Operator-run only. It signs with ``AIOS_LEARNING_KEY_LIVE`` from YOUR
environment and refuses without it. It never prints a key. There is no "all".
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Any, Callable, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aios import config  # noqa: E402
from aios.application.memory.provenance_policy import (  # noqa: E402
    lesson_content_key,
    semantic_content_key,
)
from aios.memory.db import init_memory_db  # noqa: E402
from aios.memory.learning_journal import record as journal  # noqa: E402
from aios.memory.provenance import (  # noqa: E402
    REVOKED,
    LearningSigner,
    Provenance,
    ProvenanceStore,
)
from tools.readmit_learning import CHANNELS  # noqa: E402

#: Content keys for the channels a machine LEARNS into. A fact is not keyed:
#: putting a revoked triple back takes a human approval, which is itself the
#: operator's act.
CONTENT_KEYS: dict[str, Callable[[Any], str]] = {
    "mistake_pool": lesson_content_key,
    "semantic_memory": semantic_content_key,
}

#: Where a revocation is journalled: lessons are the lesson-transfer faculty;
#: memory and facts are what turns leave behind.
_FACULTY = {"mistake_pool": "L2", "semantic_memory": "L1", "semantic_facts": "L1"}


class RevokeError(RuntimeError):
    """A revocation that must not happen: said plainly, never half-done."""


def _row(db: Path, table: str, row_id: int) -> Optional[sqlite3.Row]:
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            f"SELECT * FROM {table} WHERE id = ?",  # noqa: S608 - table from CHANNELS
            (row_id,),
        ).fetchone()


def revoke(
    db: Path,
    store: ProvenanceStore,
    signer: LearningSigner,
    *,
    table: str,
    ids: list[int],
    approver: str,
    reason: str = "",
) -> dict[str, list[str]]:
    """Revoke each named row; return ``{"revoked": [...], "withdrawn": [...]}``.

    All-or-nothing up front: an unknown table, no approver, no live key or an
    id that is not a row refuses the whole call before anything is written.
    """
    if table not in CHANNELS:
        raise RevokeError(f"unknown channel {table!r}: {sorted(CHANNELS)}")
    if not approver.strip():
        raise RevokeError("an approver is required: revocation is a human act")
    if "live" not in signer.kinds:
        raise RevokeError(
            "no live signing key in this environment (AIOS_LEARNING_KEY_LIVE); a "
            "revocation names who revoked, under the signature, so it cannot run here"
        )
    init_memory_db(db)
    rows = {row_id: _row(db, table, row_id) for row_id in ids}
    unknown = [i for i, r in rows.items() if r is None]
    if unknown:
        raise RevokeError(f"no such rows of {table}: {unknown}; nothing was revoked")
    digest_of = CHANNELS[table][0]
    revoked: list[str] = []
    for row_id, row in rows.items():
        principal = row["principal_id"]
        provenance = Provenance(
            table=table,
            row_id=str(row_id),
            content_sha256=digest_of(row),
            source_kind="live",
            transition=REVOKED,
            approver=approver.strip(),
            principal=principal,
        )
        store.append(provenance, signer.sign(provenance))
        if table in CONTENT_KEYS:
            store.tombstone(
                table,
                CONTENT_KEYS[table](row),
                principal=principal,
                approver=approver.strip(),
            )
        revoked.append(f"{table}:{row_id}")
        journal(
            _FACULTY[table],
            "revoked",
            subject_id=row_id,
            detail={
                "table": table,
                "approver": approver.strip(),
                "reason": reason,
                "principal": principal,
            },
            db_path=db,
        )
    withdrawn = _cascade(db, store, [(table, str(i)) for i in rows])
    return {"revoked": revoked, "withdrawn": withdrawn}


def _cascade(
    db: Path, store: ProvenanceStore, roots: list[tuple[str, str]]
) -> list[str]:
    """Withdraw every row recorded as derived from *roots*, all the way down."""
    seen = set(roots)
    queue = list(roots)
    withdrawn: list[str] = []
    while queue:
        parent = queue.pop(0)
        for child_table, child_id, relation in store.children_of(*parent):
            child = (child_table, child_id)
            if child in seen:
                continue
            seen.add(child)
            row = (
                _row(db, child_table, int(child_id))
                if child_table in CHANNELS and child_id.isdigit()
                else None
            )
            digest = CHANNELS[child_table][0](row) if row is not None else "withdrawn"
            store.append(
                Provenance(
                    table=child_table,
                    row_id=child_id,
                    content_sha256=digest,
                    source_kind="live",
                    transition="withdrawn",
                    parents=(f"{parent[0]}:{parent[1]}",),
                    principal=row["principal_id"] if row is not None else None,
                ),
                None,
            )
            withdrawn.append(f"{child_table}:{child_id} ({relation})")
            queue.append(child)
    return withdrawn


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--memory-db", type=Path, default=config.MEMORY_DB_PATH)
    parser.add_argument("--table", choices=sorted(CHANNELS), required=True)
    parser.add_argument("--ids", default="", help="comma-separated row ids")
    parser.add_argument("--approver", default="", help="who is revoking them")
    parser.add_argument("--reason", default="", help="why, for the journal")
    parser.add_argument("--apply", action="store_true", help="sign (default: dry run)")
    args = parser.parse_args(argv)
    ids = [int(part) for part in args.ids.split(",") if part.strip()]
    if not ids:
        print("name the rows: --ids 3,7 (there is no 'all')")
        return 2
    if not args.apply:
        text_field = CHANNELS[args.table][2]
        for row_id in ids:
            row = _row(args.memory_db, args.table, row_id)
            shown = str(row[text_field])[:200] if row is not None else "<no such row>"
            print(f"would revoke {args.table}:{row_id}  {shown}")
        print("\nDRY RUN: nothing signed. Add --apply to revoke.")
        return 0
    try:
        done = revoke(
            args.memory_db,
            ProvenanceStore(args.memory_db),
            LearningSigner.from_env(),
            table=args.table,
            ids=ids,
            approver=args.approver,
            reason=args.reason,
        )
    except RevokeError as exc:
        print(f"REFUSED: {exc}")
        return 1
    print(f"revoked: {done['revoked']}; withdrawn by cascade: {done['withdrawn']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
