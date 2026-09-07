#!/usr/bin/env python3
"""Bring back playbooks that a fixed bug killed.

WHAT HAPPENED. `_workflow_step` serialises a tool call as ``tool: key=value``,
and `_parse_step` is supposed to strip the ``key=`` before storing it. Some
playbooks were compiled while it did not, so their steps carry the prefix
twice::

    "command": "command=pytest lab/test_llp_reflex_xkj.py -q"

`_arg_value`'s own docstring describes exactly what that costs: the gateway
sees ``command=pytest ...``, does not recognise it, classifies Zone.RED, and
**every replay aborts**. Two consecutive aborts decompile the playbook.

Measured in the shipped database: three playbooks carry the doubled prefix and
are decompiled with zero replays; the one without it replayed twice with zero
failures. The engine was fine. The stored arguments were not.

WHY DELETE RATHER THAN PATCH. A decompiled playbook cannot recompile --
`try_compile_all` skips any skill that already owns a compiled-or-decompiled
row -- so the dead row is itself the blocker. Removing it lets the playbook be
rebuilt *from the skill*, which is the source of truth and is parsed by
today's fixed code. Rewriting the stored argument in place would instead
preserve whatever else that compilation got wrong.

WHAT IT REFUSES TO TOUCH. A playbook whose skill is no longer `verified`, or
whose skill carries failures, is left exactly where it is. Deleting one of
those would not repair anything -- it would erase the record of a skill that
genuinely has not earned recompilation, which is hiding a fact rather than
fixing a defect.

Dry run by default. `--apply` writes, and backs the database up first.

Run:  python scripts/repair_playbooks.py [--db PATH] [--apply]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def has_malformed_step(steps_json: str) -> bool:
    """True when any stored argument still carries its own ``key=`` prefix.

    Deliberately keyed on the ARGUMENT NAME repeating itself (``command`` whose
    value starts ``command=``), not on the mere presence of an ``=``. Plenty of
    legitimate commands contain one -- ``pytest -k x=1``, ``FOO=bar make`` --
    and a detector that matched those would delete healthy playbooks, which is
    a far worse failure than leaving a broken one alone.
    """
    try:
        steps = json.loads(steps_json)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(steps, list):
        return False
    for step in steps:
        if not isinstance(step, dict):
            continue
        for key, value in (step.get("args") or {}).items():
            if isinstance(value, str) and value.startswith(f"{key}="):
                return True
    return False


def survey(conn: sqlite3.Connection) -> list[dict]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT p.id, p.status, p.replay_count, p.consecutive_failures,
                  p.steps_json, p.skill_id,
                  s.status AS skill_status, s.failure_count AS skill_failures
           FROM compiled_playbooks p
           LEFT JOIN procedural_skills s ON s.id = p.skill_id
           ORDER BY p.id"""
    ).fetchall()

    out = []
    for r in rows:
        malformed = has_malformed_step(str(r["steps_json"]))
        recompilable = (
            r["skill_status"] == "verified" and (r["skill_failures"] or 0) == 0
        )
        if not malformed:
            verdict, why = "keep", "steps are well-formed"
        elif r["status"] != "decompiled":
            verdict, why = "keep", "malformed but still live; not this tool's business"
        elif not recompilable:
            verdict, why = (
                "keep",
                f"skill {r['skill_id']} is {r['skill_status']} "
                f"({r['skill_failures']} failures) -- cannot recompile",
            )
        else:
            verdict, why = "repair", f"skill {r['skill_id']} is verified, 0 failures"
        out.append(
            {
                "id": r["id"],
                "status": r["status"],
                "replays": r["replay_count"],
                "skill_id": r["skill_id"],
                "skill_status": r["skill_status"],
                "malformed": malformed,
                "verdict": verdict,
                "why": why,
            }
        )
    return out


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        str(s): int(n)
        for s, n in conn.execute(
            "SELECT status, COUNT(*) FROM compiled_playbooks GROUP BY status"
        )
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None, help="memory database")
    ap.add_argument("--apply", action="store_true", help="actually delete")
    args = ap.parse_args()

    if args.db is None:
        from aios import config

        args.db = Path(config.MEMORY_DB_PATH)
    if not args.db.exists():
        print(f"no database at {args.db}")
        return 1

    conn = sqlite3.connect(args.db)
    rows = survey(conn)
    before = counts(conn)

    print(f"database : {args.db}")
    print(f"mode     : {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"before   : {before}")
    print()
    for r in rows:
        mark = "REPAIR" if r["verdict"] == "repair" else "keep  "
        flag = "malformed" if r["malformed"] else "ok       "
        print(
            f"  [{mark}] playbook {r['id']:<3} {r['status']:<11} {flag} "
            f"replays={r['replays']}  {r['why']}"
        )

    doomed = [r["id"] for r in rows if r["verdict"] == "repair"]
    print()
    if not doomed:
        print("nothing to repair.")
        conn.close()
        return 0

    if not args.apply:
        print(f"would delete {len(doomed)} row(s): {doomed}")
        print("re-run with --apply to act (the database is backed up first).")
        conn.close()
        return 0

    conn.close()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = args.db.with_suffix(args.db.suffix + f".bak-{stamp}")
    shutil.copy2(args.db, backup)
    print(f"backup   : {backup}")

    conn = sqlite3.connect(args.db)
    conn.execute(
        f"DELETE FROM compiled_playbooks WHERE id IN ({','.join('?' * len(doomed))})",
        doomed,
    )
    conn.commit()
    conn.close()
    print(f"deleted  : {doomed}")

    # Rebuild from the skills, using today's parser.
    from aios.core.cerebellum import Cerebellum

    cb = Cerebellum(args.db)
    compiled = cb.try_compile_all()
    conn = sqlite3.connect(args.db)
    after = counts(conn)
    conn.close()

    print(f"recompiled: {compiled}")
    print(f"after    : {after}")
    print()
    if after.get("compiled", 0) > before.get("compiled", 0):
        print("RESULT: playbooks came back.")
    else:
        print("RESULT: nothing recompiled. The diagnosis was wrong, or the")
        print("skills no longer satisfy the compilation guards. Reported as-is;")
        print(f"the database before this run is at {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
