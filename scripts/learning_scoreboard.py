#!/usr/bin/env python3
"""The animal's ledger: is this system actually learning, and by how much?

WHY THIS EXISTS
---------------
The governance side of this repo measures itself relentlessly -- 55 organs, a
twelve-condition gate, live-evidence artifacts, a spine attestation, CI and a
nightly. It refuses vacuous passes and says so loudly.

The learning side had no equivalent. The chain is real and wired into every
turn, and `.aios/audit/learning-loop-runs.jsonl` records a 19/19 run with every
hard link green. But nothing measured whether ORDINARY USE accumulates
anything. "Is it learning?" had no answer, so every change to the learning path
was unfalsifiable -- exactly the vacuous-result trap the governance side spent
months removing.

This prints the counts that would move if learning were compounding, and
`--record` appends a dated row so the TREND is the evidence. A flat line across
runs means the learning work did nothing, which is precisely what a scoreboard
must be able to say.

READ-ONLY BY CONSTRUCTION. The database is opened `mode=ro`, so this cannot
create, migrate, or write the store it measures -- a scoreboard that can change
the score is not a scoreboard. (It also means a machine that has never run the
system reports "no database" rather than fabricating a fresh empty one.)

Usage:
    python scripts/learning_scoreboard.py            # report
    python scripts/learning_scoreboard.py --record   # report + append a row
    python scripts/learning_scoreboard.py --json     # machine-readable
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

TRAIL = REPO_ROOT / ".aios" / "audit" / "learning-scoreboard.jsonl"


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {str(row[0]) for row in rows}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    # Several learning columns (`weak_success_count`, `verification_strength`)
    # exist only as `_migrate` ALTERs, not in schema.sql, so a database created
    # before that migration genuinely lacks them. Absent must read as absent,
    # not as zero -- reporting a missing column as 0 is how a broken measurement
    # disguises itself as a bad result.
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def collect(db_path: Path) -> dict:
    """Every number that would move if the system were learning."""
    stats: dict[str, object] = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "db_present": db_path.exists(),
    }
    if not db_path.exists():
        return stats

    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        present = _tables(conn)

        # --- lessons -------------------------------------------------------
        # A lesson promotes pending -> verified only when the failed command
        # succeeds again. Until then no other session will ever recall it, so
        # `pending` climbing while `verified` stays flat is the signature of
        # lessons that are recorded and never transfer.
        if "mistake_pool" in present:
            stats["lessons_total"] = _scalar(conn, "SELECT COUNT(*) FROM mistake_pool")
            for state in ("pending", "verified", "superseded"):
                stats[f"lessons_{state}"] = _scalar(
                    conn,
                    "SELECT COUNT(*) FROM mistake_pool WHERE verification_status = ?",
                    (state,),
                )
            stats["lessons_recurring"] = _scalar(
                conn, "SELECT COUNT(*) FROM mistake_pool WHERE occurrence_count > 1"
            )

        # --- skills --------------------------------------------------------
        if "procedural_skills" in present:
            cols = _columns(conn, "procedural_skills")
            for state in ("candidate", "verified", "superseded"):
                stats[f"skills_{state}"] = _scalar(
                    conn,
                    "SELECT COUNT(*) FROM procedural_skills WHERE status = ?",
                    (state,),
                )
            # `success_count` counts successes at or above the LEARNING floor
            # (MEDIUM since the floor split) -- not STRONG. Calling this column
            # "strong" in the report would be a lie the moment a checker-backed
            # skill promotes, and a scoreboard that mislabels its own columns is
            # how a number stops meaning anything.
            stats["successes_promotable"] = _scalar(
                conn, "SELECT SUM(success_count) FROM procedural_skills"
            )
            stats["failures"] = _scalar(
                conn, "SELECT SUM(failure_count) FROM procedural_skills"
            )
            if "weak_success_count" in cols:
                stats["successes_weak"] = _scalar(
                    conn, "SELECT SUM(weak_success_count) FROM procedural_skills"
                )

        # --- reflexes ------------------------------------------------------
        # The end of the chain: a compiled playbook replays a proven arc with
        # no LLM call at all. This is the number that says the system got
        # faster at something it already knows, which is what learning is for.
        if "compiled_playbooks" in present:
            for state in ("compiled", "decompiled"):
                stats[f"playbooks_{state}"] = _scalar(
                    conn,
                    "SELECT COUNT(*) FROM compiled_playbooks WHERE status = ?",
                    (state,),
                )
            stats["reflex_replays"] = _scalar(
                conn, "SELECT SUM(replay_count) FROM compiled_playbooks"
            )

        # Two ways a verified skill can sit one link short of a reflex.
        #
        # The first is recoverable by design: `try_compile_all` skips a skill
        # whose last run failed (`consecutive_failures > 0`), and the next
        # success clears it. Worth showing, not worth alarm.
        #
        # The second is not: a playbook that was decompiled once keeps its skill
        # out forever, because the NOT EXISTS clause matches 'decompiled' rows
        # too. Nothing ever clears that, so it is counted separately.
        if {"procedural_skills", "compiled_playbooks"} <= present:
            if "consecutive_failures" in _columns(conn, "procedural_skills"):
                stats["skills_awaiting_a_clean_run"] = _scalar(
                    conn,
                    "SELECT COUNT(*) FROM procedural_skills "
                    "WHERE status = 'verified' AND consecutive_failures > 0",
                )
            stats["skills_blocked_by_decompile"] = _scalar(
                conn,
                "SELECT COUNT(DISTINCT skill_id) FROM compiled_playbooks "
                "WHERE status = 'decompiled'",
            )

        # --- curriculum ----------------------------------------------------
        if "curriculum_tasks" in present:
            stats["curriculum_tasks"] = _scalar(
                conn, "SELECT COUNT(*) FROM curriculum_tasks"
            )
            stats["curriculum_levels"] = _scalar(
                conn,
                "SELECT COUNT(*) FROM "
                "(SELECT 1 FROM curriculum_tasks GROUP BY skill_name, level)",
            )
            stats["curriculum_levels_mastered"] = _scalar(
                conn,
                "SELECT COUNT(*) FROM (SELECT skill_name, level FROM curriculum_tasks "
                "GROUP BY skill_name, level "
                "HAVING SUM(CASE WHEN status = 'mastered' THEN 0 ELSE 1 END) = 0)",
            )
            # A level with no held-out task can NEVER master: `_refresh_level`
            # gates on `bool(held_out) and all(...)`, so with none defined the
            # transition is a permanent silent no-op while the counters climb.
            stats["curriculum_levels_unreachable"] = _scalar(
                conn,
                "SELECT COUNT(*) FROM (SELECT skill_name, level FROM curriculum_tasks "
                "GROUP BY skill_name, level HAVING SUM(held_out) = 0)",
            )
    finally:
        conn.close()
    return stats


def render(stats: dict) -> str:
    if not stats.get("db_present"):
        return (
            "LEARNING SCOREBOARD\n\n"
            "  no memory database yet — nothing has been learned on this machine.\n"
            "  (not an error: the store is created by running the system, and this\n"
            "  script is read-only on purpose so it cannot fake one into existence)"
        )

    def g(key: str) -> int:
        return int(stats.get(key) or 0)

    def has(key: str) -> bool:
        return key in stats

    lines = ["LEARNING SCOREBOARD", ""]
    lines.append(
        f"  lessons     {g('lessons_verified')} verified / {g('lessons_total')} total"
        f"  ({g('lessons_pending')} pending, {g('lessons_recurring')} recurring)"
    )
    lines.append(
        f"  skills      {g('skills_verified')} verified / "
        f"{g('skills_verified') + g('skills_candidate')} live"
        f"  ({g('skills_candidate')} candidate)"
    )
    lines.append(
        f"  reflexes    {g('playbooks_compiled')} compiled playbooks, "
        f"{g('reflex_replays')} replays served without an LLM"
    )
    evidence = f"  evidence    {g('successes_promotable')} promotable successes"
    if has("successes_weak"):
        evidence += f" / {g('successes_weak')} below-floor (can never promote)"
    evidence += f", {g('failures')} failures"
    lines.append(evidence)
    lines.append(
        f"  curriculum  {g('curriculum_levels_mastered')} of {g('curriculum_levels')} "
        f"levels mastered  ({g('curriculum_tasks')} tasks)"
    )

    # Every note below names something STRUCTURAL -- a reason the numbers above
    # cannot rise no matter how much the system is used. That distinction is
    # the whole point: "low" is a result, "impossible" is a defect.
    notes: list[str] = []
    if g("curriculum_levels_unreachable"):
        notes.append(
            f"{g('curriculum_levels_unreachable')} curriculum level(s) have no "
            "held-out task, so mastery there is UNREACHABLE, not merely unearned"
        )
    if g("skills_awaiting_a_clean_run"):
        notes.append(
            f"{g('skills_awaiting_a_clean_run')} verified skill(s) failed their last "
            "run, so they cannot compile until they succeed once more (recoverable)"
        )
    if g("skills_blocked_by_decompile"):
        notes.append(
            f"{g('skills_blocked_by_decompile')} skill(s) were decompiled once and "
            "are excluded from recompilation forever"
        )
    if g("lessons_pending") and not g("lessons_verified"):
        notes.append(
            f"all {g('lessons_pending')} lesson(s) are still pending — not one has "
            "ever been confirmed by a later success"
        )
    if g("successes_weak") and not g("successes_promotable"):
        notes.append(
            "every recorded success was below the floor — nothing can promote, "
            "so no skill can verify and no reflex can compile"
        )
    if g("skills_verified") and not g("playbooks_compiled"):
        notes.append(
            "skills are verifying but none has compiled — the chain stops one link "
            "before the reflex that would make it pay off"
        )
    if not has("successes_weak"):
        notes.append(
            "this database predates the weak/strong split, so the WEAK count is "
            "unavailable rather than zero"
        )
    if notes:
        lines.append("")
        lines.append("  STRUCTURAL LIMITS (why these numbers may not move):")
        lines.extend(f"    - {note}" for note in notes)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report whether the learning chain is accumulating anything."
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="append this reading to the trail so the trend becomes the evidence",
    )
    parser.add_argument("--json", action="store_true", help="emit raw JSON instead")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(config.MEMORY_DB_PATH),
        help="memory database to read (default: the configured store)",
    )
    args = parser.parse_args(argv)

    stats = collect(args.db)
    print(json.dumps(stats, indent=2) if args.json else render(stats))

    if args.record:
        TRAIL.parent.mkdir(parents=True, exist_ok=True)
        with TRAIL.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(stats, ensure_ascii=False) + "\n")
        print(f"\nrecorded to {TRAIL.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
