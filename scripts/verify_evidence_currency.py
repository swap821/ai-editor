#!/usr/bin/env python3
"""Re-derive whether each organ's evidence still describes HEAD.

WHY THIS EXISTS AS A VERIFIER AND NOT A CLEANUP SCRIPT
------------------------------------------------------
The ledger carried 41 `STALE ATTESTATION` blockers saying, correctly:

    N of this organ's own production_entrypoints changed after <sha>. The
    evidence below is preserved and was true at that commit; it is no longer
    known to describe HEAD. Re-verify at a current commit to restore green.

Nothing in the repository could answer the obvious follow-up: *is that still
true?* The blockers were prose written by a one-off pass at `1b4e1310`, so after
re-verifying at a newer tip they stayed on the rows, now describing a state that
no longer existed. Deleting them by hand would have been laundering; the honest
move is to recompute the condition they assert.

So this asks git the same question the original pass asked, and writes whichever
answer it gets. It can ADD staleness as readily as remove it -- that symmetry is
what makes it a verifier rather than a tool for making rows green.

SPINE-ATTESTED ORGANS ARE NEVER TOUCHED. `evidence_digest` covers
`known_blockers` for the organs the operator signed, so editing one -- even to
record something true -- invalidates a signature only the operator can replace.

Usage:
    python scripts/verify_evidence_currency.py            # report, exit 1 if stale
    python scripts/verify_evidence_currency.py --update   # rewrite the blockers
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"
ATTESTATION_PATH = REPO_ROOT / ".aios" / "state" / "spine_release_attestation.json"

#: Both spellings the ledger has used for the same rule. A pass that strips
#: one and not the other leaves an obsolete claim standing -- which is how
#: organ 13 sat yellow while holding evidence at HEAD with zero drift.
STALE_MARKERS = ("STALE ATTESTATION", "STALE LIVE EVIDENCE")
STALE_MARKER = STALE_MARKERS[0]


def _spine_attested_organ_ids() -> set[int]:
    """Organ ids the operator signed. Read, never hardcoded, so it tracks."""
    try:
        data = json.loads(ATTESTATION_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {int(x) for x in (data.get("organ_ids") or [])}


def _head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    ).stdout.strip()


def changed_since(sha: str, paths: list[str], head: str) -> list[str]:
    """Which of *paths* changed between *sha* and HEAD.

    `git diff --name-only A..B -- <paths>` rather than walking the log: the
    question is whether the FILE differs, not how many commits touched it. A
    file edited and reverted has not changed, and claiming otherwise would
    invent staleness that does not exist.
    """
    if not sha or not paths:
        return []
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{sha}..{head}", "--", *paths],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        # An unresolvable sha (orphaned by a squash merge, most often) cannot be
        # compared. Reported as unknown rather than guessed in either direction.
        return ["<unresolvable: " + (result.stderr.strip()[:80] or "bad sha") + ">"]
    return [line for line in result.stdout.splitlines() if line.strip()]


def build_blocker(changed: list[str], sha: str, head: str) -> str:
    """The blocker text, in the vocabulary the ledger already speaks."""
    shown = ", ".join(changed[:6]) + (" ..." if len(changed) > 6 else "")
    return (
        f"{STALE_MARKER} (recorded {head[:8]}): {len(changed)} of this organ's "
        f"own production_entrypoints changed after {sha[:12]} ({shown}). The "
        "evidence below is preserved and was true at that commit; it is no "
        "longer known to describe HEAD. Re-verify at a current commit to "
        "restore green."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update", action="store_true", help="rewrite blockers to match reality"
    )
    args = parser.parse_args(argv)

    head = _head()
    attested = _spine_attested_organ_ids()
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))

    stale: list[tuple[int, list[str]]] = []
    freshened: list[int] = []
    unknown: list[int] = []
    skipped: list[int] = []

    for row in ledger:
        oid = int(row["organ_id"])
        if oid in attested:
            skipped.append(oid)
            continue

        entrypoints = list(row.get("production_entrypoints") or [])
        blockers = list(row.get("known_blockers") or [])
        others = [b for b in blockers if not any(m in str(b) for m in STALE_MARKERS)]

        # MEASURED OVER THE LIVE EVIDENCE ROWS, because that is what C10
        # actually reads. An earlier version of this file asked only about
        # `last_verified_sha` and disagreed with the authority it exists to
        # anticipate: organ 13 held evidence at HEAD with zero drift and was
        # still carrying a `STALE LIVE EVIDENCE` blocker from an older pass,
        # because that marker was spelled differently from the one being
        # stripped. Two derivations of one rule, disagreeing quietly.
        #
        # `last_verified_sha` is the fallback for an organ with no live rows at
        # all -- there is still something to be stale about.
        live_shas = [
            str(e.get("commit_sha") or "")
            for e in (row.get("live_evidence") or [])
            if e.get("proof_level") == "live" and e.get("commit_sha")
        ]
        if not live_shas:
            fallback = str(row.get("last_verified_sha") or "")
            if not fallback:
                # No recorded commit is not freshness. Left exactly as found: an
                # organ that never claimed a verified tip has nothing to go
                # stale, and inventing a blocker here would be as wrong as
                # clearing one.
                unknown.append(oid)
                continue
            live_shas = [fallback]

        changed: list[str] = []
        worst_sha = live_shas[0]
        for sha in live_shas:
            drift = changed_since(sha, entrypoints, head)
            if drift and len(drift) > len(changed):
                changed, worst_sha = drift, sha
            elif drift and not changed:
                changed, worst_sha = drift, sha

        if changed:
            stale.append((oid, changed))
            if args.update:
                row["known_blockers"] = [
                    build_blocker(changed, worst_sha, head),
                    *others,
                ]
        else:
            if len(others) != len(blockers):
                freshened.append(oid)
            if args.update:
                row["known_blockers"] = others

    print(f"HEAD {head[:12]}")
    print(
        f"  fresh (evidence describes HEAD): {len(ledger) - len(stale) - len(unknown) - len(skipped)}"
    )
    print(f"  stale (entrypoints moved):       {len(stale)}")
    print(f"  no last_verified_sha:            {len(unknown)} {unknown}")
    print(f"  spine-attested, untouched:       {len(skipped)} {skipped}")
    if freshened:
        print(f"  staleness discharged this run:   {sorted(freshened)}")
    for oid, changed in stale:
        shown = ", ".join(changed[:3]) + (" ..." if len(changed) > 3 else "")
        print(f"    #{oid:>2} {shown}")

    if args.update:
        # newline IS LOAD-BEARING — see .gitattributes: this file is pinned to
        # eol=lf because the release manifest hash-pins its BYTES.
        LEDGER_PATH.write_text(
            json.dumps(ledger, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print("ledger updated")

    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
