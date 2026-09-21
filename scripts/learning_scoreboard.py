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

#: A TRACKED summary, unlike the trail. `.aios/audit/` is gitignored, so every
#: learning claim this project makes currently lives on one laptop with no
#: backup and no way for anyone else to check it. The detail stays untracked
#: (it is long, and it carries run specifics), but the handful of numbers the
#: claims actually rest on belong in the repository next to `RESUME.md`.
TREND = REPO_ROOT / ".aios" / "state" / "LEARNING_TREND.md"

#: Rows kept in the tracked summary. Enough to see a trend, few enough that the
#: file stays readable in a diff.
_TREND_ROWS = 20


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
        # The second used to be permanent: a playbook decompiled once kept its
        # skill out forever, because the compile guard matched 'decompiled'
        # rows and nothing ever cleared them. It is now recoverable -- the
        # skill must earn MORE promotable successes than it had when the
        # reflex was retired -- but it is still counted separately, because
        # "needs fresh evidence" and "ready to compile" are different states.
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
            f"{g('skills_blocked_by_decompile')} skill(s) have a retired reflex "
            "and must earn NEW promotable successes before it can recompile "
            "(recoverable since the decompile-recovery fix; it used to be "
            "permanent)"
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


#: Counters that may only ever go UP. Each is a thing the system has proven
#: at least once; losing one means either a real regression or that something
#: rewrote history, and both deserve a red build rather than a quieter number
#: on the next dashboard. `failures` is deliberately absent -- failures rising
#: is the loop working, not the loop breaking.
_MONOTONIC = (
    "skills_verified",
    "playbooks_compiled",
    "reflex_replays",
    "successes_promotable",
    "lessons_verified",
    "curriculum_levels_mastered",
)


def last_recorded(trail: Path = TRAIL) -> dict | None:
    """The previous reading, or None when there is nothing to compare against."""
    if not trail.exists():
        return None
    rows = [
        line for line in trail.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    for line in reversed(rows):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


def detect_regressions(stats: dict, trail: Path = TRAIL) -> list[str]:
    """Counters that went DOWN since the last recorded reading.

    A scoreboard that only ever prints is a dashboard, and a dashboard nobody
    alarms on is how a loop quietly stops working for a month. This is the
    smallest honest alarm: not "is the number good", which nobody can agree
    on, but "did something the system had already proven stop being true".
    """
    previous = last_recorded(trail)
    if previous is None:
        return []
    out: list[str] = []
    for key in _MONOTONIC:
        was, now = previous.get(key), stats.get(key)
        if isinstance(was, int) and isinstance(now, int) and now < was:
            out.append(f"{key}: {was} -> {now}")
    return out


_TREND_COLUMNS = (
    ("ts", "when"),
    ("skills_verified", "skills"),
    ("playbooks_compiled", "reflexes"),
    ("reflex_replays", "replays"),
    ("lessons_verified", "lessons"),
    ("curriculum_levels_mastered", "levels"),
)


#: The run trails, summarised into the TRACKED trend file. The trails
#: themselves are gitignored (they carry per-attempt detail), so without this a
#: third party cannot check a single organic-learning claim this project makes
#: — which is L7's standing blocker, and an evidence problem rather than a
#: presentation one.
SELF_CORPUS_TRAIL = REPO_ROOT / ".aios" / "audit" / "reverse-engineering-runs.jsonl"
ORGANIC_CHAIN_TRAIL = REPO_ROOT / ".aios" / "audit" / "organic-chain-runs.jsonl"


def _summarise_runs(trail: Path, limit: int = 6) -> list[str]:
    """One markdown row per run: what it did, and what it refused to score."""
    if not trail.exists():
        return []
    rows = []
    for line in trail.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("kind") == "attempt":
            continue  # per-attempt rows are detail, not summary
        rows.append(row)

    out = []
    for row in rows[-limit:]:
        attempts = row.get("attempts") or []
        graded = [
            a
            for a in attempts
            if a.get("outcome") not in ("model_error", "no_code_block")
        ]
        not_scored = len(attempts) - len(graded)
        links = row.get("links") or []
        fired = ", ".join(link["faculty"] for link in links if link.get("fired")) or "-"
        outcome = row.get("outcome", "completed")
        if outcome == "aborted":
            # A refusal belongs in the public summary. Publishing only clean
            # runs is how "we ran it" quietly starts to mean "it worked".
            detail = f"REFUSED — {' '.join(str(row.get('error', '')).split())[:90]}"
        else:
            earned = row.get("earned")
            if earned is None:
                earned = len([a for a in attempts if a.get("earned")])
            detail = (
                f"{earned} earned, {len(graded)} graded, "
                f"{not_scored} not scored (model unreachable)"
            )
        out.append(
            f"| {str(row.get('ts', '?'))[:19]} | {outcome} | {fired} | {detail} |"
        )
    return out


def write_trend(trail: Path = TRAIL, trend: Path = TREND) -> None:
    """Render the last few readings into a tracked markdown table.

    Deliberately derived, never authored: it is regenerated from the trail on
    every `--record`, so it cannot drift from the numbers it summarises. If
    this file and the trail ever disagree, the trail is right and this is
    stale -- which is why it says so at the top.
    """
    if not trail.exists():
        return
    rows: list[dict] = []
    for line in trail.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    rows = rows[-_TREND_ROWS:]

    header = "| " + " | ".join(label for _key, label in _TREND_COLUMNS) + " |"
    divider = "|" + "|".join("---" for _ in _TREND_COLUMNS) + "|"
    body = []
    for row in rows:
        cells = []
        for key, _label in _TREND_COLUMNS:
            value = row.get(key)
            cells.append(str(value) if value is not None else "-")
        body.append("| " + " | ".join(cells) + " |")

    trend.parent.mkdir(parents=True, exist_ok=True)
    trend.write_text(
        "# Learning trend\n\n"
        "Generated by `scripts/learning_scoreboard.py --record`. Do not edit by\n"
        "hand: it is rewritten from `.aios/audit/learning-scoreboard.jsonl` on\n"
        "every recording, and if the two ever disagree the trail is the truth.\n\n"
        "This file is TRACKED and the trail is not, so these are the only\n"
        "learning numbers anyone but this machine can check. A flat table means\n"
        "the loop is not accumulating, which is a finding rather than a gap.\n\n"
        f"{header}\n{divider}\n" + "\n".join(body) + "\n" + _runs_section(),
        encoding="utf-8",
    )


def _runs_section() -> str:
    """The organic runs behind the numbers above, so they can be checked.

    Without this, every organic-learning claim rests on files under
    `.aios/audit/` that are gitignored — readable by this machine and nobody
    else. That is L7's standing blocker, and it is an evidence problem rather
    than a presentation one.
    """
    parts = []
    for title, trail_path in (
        ("Self-corpus runs", SELF_CORPUS_TRAIL),
        ("Organic chain runs", ORGANIC_CHAIN_TRAIL),
    ):
        rows = _summarise_runs(trail_path)
        if not rows:
            continue
        parts.append(
            f"\n## {title}\n\n"
            "| when | outcome | links fired | detail |\n|---|---|---|---|\n"
            + "\n".join(rows)
            + "\n"
        )
    if not parts:
        return ""
    return (
        "\nThe run detail lives under `.aios/audit/`, which is gitignored, so "
        "these\nsummaries are the only part anyone but this machine can check. "
        "A REFUSED\nrow is a result, not a gap: the grader declining to score "
        "is the behaviour\nthat makes the other rows worth believing.\n"
        + "".join(parts)
    )


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
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if learning REGRESSED against the last recorded row",
    )
    args = parser.parse_args(argv)

    stats = collect(args.db)
    print(json.dumps(stats, indent=2) if args.json else render(stats))

    if args.check:
        regressions = detect_regressions(stats)
        if regressions:
            print("\nREGRESSION — learning went backwards:")
            for line in regressions:
                print(f"  {line}")
            return 1
        print("\nno regression against the last recorded reading")

    if args.record:
        TRAIL.parent.mkdir(parents=True, exist_ok=True)
        with TRAIL.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(stats, ensure_ascii=False) + "\n")
        write_trend()
        print(
            f"\nrecorded to {TRAIL.relative_to(REPO_ROOT).as_posix()}"
            f" (tracked summary: {TREND.relative_to(REPO_ROOT).as_posix()})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
