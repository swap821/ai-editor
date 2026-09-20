#!/usr/bin/env python3
"""Re-derive whether each organ's ``last_verified_sha`` is still IN the lineage.

WHY THIS EXISTS AS A VERIFIER AND NOT A CLEANUP SCRIPT
------------------------------------------------------
C12 asks that ``last_verified_sha`` be an ancestor of HEAD. Five green organs
(20, 23, 33, 37, 48) failed it while being otherwise current, and the reason is
mechanical rather than dishonest: their evidence was gathered on branch
``organs/re-verify-at-current-tip``, which was **squash-merged** as #344. A
squash lands the CONTENT and discards the commits, so the sha those rows name
is real, reachable by branch, and permanently not an ancestor of master. No
amount of re-running tests fixes that -- the commit itself is gone from the
lineage.

The dishonest repair is to stamp HEAD onto the row, which asserts the evidence
was gathered at a commit it never saw. The honest one is to ask the question
C12 is actually standing behind: *does this evidence still describe code that
is in HEAD's history?* So this compares the organ's own
``production_entrypoints`` BLOB BY BLOB between the orphaned sha and each
ancestor commit that touched them, and re-points the row only to a commit whose
content is byte-identical -- the commit where this exact code entered the
mainline.

It can refuse as readily as it can re-point. An organ whose entrypoints differ
at every ancestor is NOT re-pointed: its evidence genuinely describes code that
is not in HEAD, which is real staleness and needs re-verification, not a new
sha. That asymmetry is what makes this a verifier rather than a tool for making
rows green.

SPINE-ATTESTED ORGANS ARE NEVER TOUCHED. ``evidence_digest`` covers their rows,
so editing one -- even to record something true -- invalidates a signature only
the operator can replace.

Usage:
    python scripts/verify_evidence_lineage.py            # report, exit 1 if any orphaned
    python scripts/verify_evidence_lineage.py --update   # re-point what is provable
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER = REPO_ROOT / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"
SPINE = {1, 2, 3, 4, 5}


def _git(*args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=120
    )
    return proc.returncode, proc.stdout.strip()


def _is_ancestor(sha: str) -> bool:
    return _git("merge-base", "--is-ancestor", sha, "HEAD")[0] == 0


def _blob(sha: str, path: str) -> str | None:
    code, out = _git("rev-parse", f"{sha}:{path}")
    return out if code == 0 else None


def _fingerprint(sha: str, paths: list[str]) -> tuple[str | None, ...]:
    return tuple(_blob(sha, p) for p in paths)


def _commit_date(sha: str) -> str:
    """Committer date, ISO-8601, sortable as a plain string."""
    return _git("log", "-1", "--format=%cI", sha)[1]


def _candidates(paths: list[str], floor: str) -> list[str]:
    """Ancestor commits that touched these paths, oldest first, plus HEAD.

    Oldest-first, but never older than the verification itself. Picking the
    globally earliest ancestor with matching content was wrong and measured so:
    organ 23's evidence was gathered 2026-09-14 and the earliest matching
    ancestor is 2026-09-04, so re-pointing there would assert a verification ten
    days before it happened. Entrypoint content being equal at an older commit
    does not mean the organ was verified at that commit. The honest target is
    the first ancestor AT OR AFTER the orphaned commit's own date -- the point
    where the verified content entered the mainline.
    """
    # EVERY ancestor at or after the floor, not only those that touched these
    # paths. A squash merge is the commit where the verified branch's work
    # entered mainline, and it is the correct target -- but it does not
    # necessarily touch this organ's entrypoints (their content may have been
    # settled days earlier), so a path-filtered walk misses it entirely and
    # falls through to HEAD.
    code, out = _git("log", "--format=%H", "--reverse", f"--since={floor}", "HEAD")
    commits = (
        [line.strip() for line in out.splitlines() if line.strip()] if code == 0 else []
    )
    head = _git("rev-parse", "HEAD")[1]
    if head and head not in commits:
        commits.append(head)
    return commits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args()

    payload = json.loads(LEDGER.read_text(encoding="utf-8"))
    rows = (
        payload["organs"]
        if isinstance(payload, dict) and "organs" in payload
        else payload
    )
    seq = rows if isinstance(rows, list) else list(rows.values())

    in_lineage: list[int] = []
    repointed: list[str] = []
    unprovable: list[str] = []
    skipped_spine: list[int] = []
    changed = False

    for row in seq:
        oid = int(row.get("organ_id"))
        sha = str(row.get("last_verified_sha") or "")
        if oid in SPINE:
            skipped_spine.append(oid)
            continue
        if not sha:
            continue
        if _is_ancestor(sha):
            in_lineage.append(oid)
            continue

        paths = [str(p) for p in (row.get("production_entrypoints") or [])]
        if not paths:
            unprovable.append(
                f"#{oid} orphaned sha {sha[:12]} and no production_entrypoints to compare"
            )
            continue
        want = _fingerprint(sha, paths)
        if any(b is None for b in want):
            unprovable.append(
                f"#{oid} orphaned sha {sha[:12]}; entrypoints do not resolve there"
            )
            continue

        floor = _commit_date(sha)
        match = next(
            (c for c in _candidates(paths, floor) if _fingerprint(c, paths) == want),
            None,
        )
        if match is None:
            unprovable.append(
                f"#{oid} orphaned sha {sha[:12]}: no ancestor of HEAD carries identical "
                f"entrypoint content -- this is real staleness, re-verify rather than re-point"
            )
            continue

        repointed.append(
            f"#{oid} {sha[:12]} ({_commit_date(sha)[:10]}) -> {match[:12]} "
            f"({_commit_date(match)[:10]}), {len(paths)} entrypoint(s) byte-identical"
        )
        if args.update:
            row["last_verified_sha"] = match
            note = (
                f"Evidence sha re-pointed {sha[:12]} -> {match[:12]} on lineage grounds: "
                f"the original commit is real but was squash-merged, so it is permanently "
                f"not an ancestor of HEAD. All {len(paths)} of this organ's own "
                f"production_entrypoints are byte-identical at both commits, so the evidence "
                f"still describes code in HEAD's history. Verified by "
                f"scripts/verify_evidence_lineage.py, which re-points only to a commit whose "
                f"content matches and refuses otherwise."
            )
            verdicts = row.get("condition_verdicts") or {}
            verdicts["C11"] = f"PASS - last_verified_sha={match}"
            verdicts["C12"] = (
                f"PASS - {match} must be an ancestor of HEAD (ordinary CI "
                f"--require-sha-ancestry); exact tip match is --strict-release at tagged "
                f"evidence tip. {note}"
            )
            row["condition_verdicts"] = verdicts
            changed = True

    head = _git("rev-parse", "HEAD")[1]
    print(f"HEAD {head[:12]}")
    print(f"  sha in HEAD's lineage:        {len(in_lineage)}")
    print(
        f"  spine-attested, untouched:    {len(skipped_spine)} {sorted(skipped_spine)}"
    )
    print(f"  orphaned but provable:        {len(repointed)}")
    for line in repointed:
        print(f"    {line}")
    print(f"  orphaned and NOT provable:    {len(unprovable)}")
    for line in unprovable:
        print(f"    {line}")

    if args.update and changed:
        LEDGER.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print("ledger updated")
    return 1 if (repointed and not args.update) or unprovable else 0


if __name__ == "__main__":
    sys.exit(main())
