#!/usr/bin/env python3
"""Attach Phase 4 live-evidence artifact rows into ORGAN_GREEN_LEDGER.json.

Does NOT flip green (Phase 5). Clears ``Phase 4 absolute residual`` blockers
for organs that now hold tip-stamped live evidence. Leaves named Outside /
Docker / Ollama / frozen / browser / Phase-6 residuals intact.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# One derivation of 'has this file moved since that sha', two callers.
from verify_evidence_currency import changed_since, is_reachable  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"
DEFAULT_ARTIFACT = REPO_ROOT / "release" / "phase4" / "live-evidence-latest.json"

PHASE4_RESIDUAL_MARKERS = ("Phase 4 absolute residual",)

ATTESTATION_PATH = REPO_ROOT / ".aios" / "state" / "spine_release_attestation.json"


def _spine_attested_organ_ids() -> set[int]:
    """Organ ids covered by the operator's spine attestation.

    Read from the attestation itself rather than hardcoded as 1-5, so that
    extending the attestation later extends this protection automatically. A
    missing or unreadable attestation yields the empty set -- this guard exists
    to avoid breaking a signature that exists, not to block work when none does.
    """
    try:
        data = json.loads(ATTESTATION_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {int(x) for x in (data.get("organ_ids") or [])}


def _tip_is_on_master(tip: str) -> bool:
    """Is *tip* already a commit on master, and therefore squash-proof?

    Checked against `origin/master` first and plain `master` second. When
    NEITHER resolves -- a shallow clone, a detached CI checkout, a fresh mirror
    -- the question is unanswerable and this returns True so the tool still
    works. That is a deliberate fail-open on the CHECK and not on the data: it
    guards an authoring decision made by a human at a keyboard, and the
    reachability of what actually gets written is enforced separately, by
    `is_reachable` here and by tests/test_unreachable_evidence_is_dropped.py in
    CI. A guard that bricks the tool in every clone without a master ref would
    simply be disabled by whoever hit it first.
    """
    for ref in ("origin/master", "master"):
        resolved = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if resolved.returncode == 0:
            return is_reachable(tip, resolved.stdout.strip())
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--allow-branch-tip",
        action="store_true",
        help=(
            "attach evidence gathered at a commit that is not yet on master. "
            "Only correct when this PR will be merged with a MERGE COMMIT; a "
            "squash merge will discard the commit and orphan every row."
        ),
    )
    args = parser.parse_args(argv)

    report = json.loads(args.artifact.read_text(encoding="utf-8"))
    if not report.get("all_passed"):
        print("artifact all_passed is false; refusing to attach", file=sys.stderr)
        return 1
    tip = report["tip_sha"]
    if len(tip) != 40:
        print(f"tip_sha not 40 chars: {tip!r}", file=sys.stderr)
        return 1
    if not args.allow_branch_tip and not _tip_is_on_master(tip):
        # THE THIRD TIME IS A DESIGN PROBLEM, NOT AN ACCIDENT.
        #
        # Evidence gathered at a BRANCH tip is discarded by a squash merge, and
        # the rows that cite it become claims nobody can resolve. It has now
        # happened twice in 48 hours -- #359's own tip, then #363's PR head --
        # and both times master went red AFTER the merge, where it is most
        # expensive to notice.
        #
        # The refusal lands here, at the moment somebody chooses which commit
        # to attest, because that is the only moment the choice is still free.
        # `--allow-branch-tip` exists for the one case where it is correct: a
        # PR that will be merged with a real merge commit, which preserves the
        # sha.
        print(
            f"REFUSING: {tip[:12]} is not on master.\n\n"
            "Evidence attached at a branch tip is orphaned the moment this PR is\n"
            "SQUASH-merged -- the commit it cites stops existing, every row\n"
            "becomes uncheckable, and master goes red after the merge. That has\n"
            "already happened twice.\n\n"
            "Do one of:\n"
            "  * re-gather at a commit already on master:\n"
            "      python scripts/phase4_live_evidence.py --tip $(git rev-parse origin/master)\n"
            "  * or, if this PR will be merged with a MERGE COMMIT (not a squash),\n"
            "    re-run with --allow-branch-tip.",
            file=sys.stderr,
        )
        return 1
    command = report["command"]
    artifact_rel = str(Path(args.artifact).resolve().relative_to(REPO_ROOT)).replace(
        "\\", "/"
    )
    # Prefer tip-stamped artifact name if present beside latest.
    tip_artifact = REPO_ROOT / "release" / "phase4" / f"live-evidence-{tip[:12]}.json"
    if tip_artifact.exists():
        artifact_rel = tip_artifact.relative_to(REPO_ROOT).as_posix()

    by_organ: dict[int, list[dict]] = {}
    for proof in report["proofs"]:
        oid = int(proof["organ_id"])
        if oid <= 0 or not proof.get("passed"):
            continue
        by_organ.setdefault(oid, []).append(proof)

    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    attested = _spine_attested_organ_ids()
    updated: list[int] = []
    skipped_attested: list[int] = []
    superseded: list[tuple[int, str]] = []
    unreachable: list[tuple[int, str]] = []
    for row in ledger:
        oid = int(row["organ_id"])
        proofs = by_organ.get(oid)
        if not proofs:
            continue
        # NEVER TOUCH A SPINE-ATTESTED ORGAN. `evidence_digest` covers status,
        # condition_verdicts, live_evidence AND known_blockers for the organs
        # the operator signed, so appending an evidence row here silently
        # invalidates their signature -- and only the operator can re-sign.
        #
        # This is not hypothetical: running this script against a passing
        # artifact rewrote live_evidence for organs 1-5 and the attestation
        # stopped verifying (digest 1b9fb0fa -> a1dbf4b3). The organs were
        # already green and gained nothing from the update; the only effect
        # available was to break them.
        #
        # Skipped by construction rather than by remembering.
        if oid in attested:
            skipped_attested.append(oid)
            continue
        # Build one consolidated live evidence row per organ (hostile-reader).
        bits = []
        for p in proofs:
            bits.append(f"{p['command']} => {p['evidence']}")
        description = (
            f"Phase 4 absolute live run on tip {tip}: command={command} exit=0; "
            f"artifact={artifact_rel}; " + " | ".join(bits)
        )[:2000]
        evidence = {
            "description": description,
            "commit_sha": tip,
            "proof_level": "live",
        }
        # Replace prior rows for this tip, keep older SHAs that still hold, and
        # DROP superseded live rows that no longer describe HEAD.
        #
        # C10 treats EVERY `proof_level: "live"` row as a current claim and
        # fails the organ if any one of them has entrypoint drift. Accumulating
        # rows therefore made green permanently unreachable: the first row goes
        # stale the moment its files move, and no amount of fresh evidence can
        # retire it. Observed directly -- 31 organs re-verified at HEAD, every
        # condition PASS, and all 31 still failed C10 on a row from a tip two
        # hundred commits back.
        #
        # Keeping a stale row is not preserving history, it is leaving a false
        # claim on the record: the row asserts a live proof at a sha that no
        # longer describes the code, which is exactly what the currency rule
        # exists to catch. The evidence itself is preserved -- the artifacts
        # under release/phase4/ are committed, and git holds every prior ledger
        # state. What is dropped is the CLAIM, not the proof.
        #
        # Older rows whose files have NOT moved are kept, because they are still
        # telling the truth; organs 15, 18 and 36 are green carrying two.
        entrypoints = [str(p) for p in (row.get("production_entrypoints") or [])]
        prior = []
        for old in row.get("live_evidence") or []:
            if old.get("commit_sha") == tip:
                continue
            if old.get("proof_level") == "live":
                old_sha = str(old.get("commit_sha") or "")
                # UNREACHABLE FIRST, because `changed_since` cannot see it. A
                # squash merge leaves the tree identical, so the drift check
                # below says "nothing moved" about a commit that no longer
                # exists -- and the row survives as a claim nobody can check.
                # That is how master went red after #359 was squashed.
                if not is_reachable(old_sha, tip):
                    unreachable.append((oid, old_sha[:12]))
                    continue
                if changed_since(old_sha, entrypoints, tip):
                    superseded.append((oid, old_sha[:12]))
                    continue
            prior.append(old)
        row["live_evidence"] = prior + [evidence]
        row["last_verified_sha"] = tip
        blockers = list(row.get("known_blockers") or [])
        blockers = [
            b for b in blockers if not any(m in b for m in PHASE4_RESIDUAL_MARKERS)
        ]
        # Note Phase 5 gate only when still yellow and no other named Outside residual.
        named = (
            "frozen spine",
            "Phase 6 gate",
            "no Ollama",
            "Outside-machine",
            "browser-session",
            "no Docker",
        )
        has_named = any(any(n.lower() in b.lower() for n in named) for b in blockers)
        if row.get("status") == "yellow" and not has_named:
            note = (
                f"Phase 4 absolute: live evidence attached at tip {tip[:12]} via "
                f"{artifact_rel}. Remaining: Phase 5 green flip only after "
                "adversarial re-read of all 12 conditions."
            )
            # Drop stale "Remaining: Phase 4-5..." prose by replacing C-only lines
            # that still say Remaining Phase 4-5 with the new note appended once.
            blockers = [
                b
                for b in blockers
                if "Remaining: Phase 4-5" not in b
                and "Remaining: Phase 5 green flip" not in b
            ]
            blockers.append(note)
        row["known_blockers"] = blockers
        updated.append(oid)

    print(
        json.dumps(
            {
                "tip_sha": tip,
                "artifact": artifact_rel,
                "organs_updated": sorted(updated),
                "count": len(updated),
                # Reported, never silent: a reader counting organs needs to know
                # these were deliberately left alone, not missed.
                "organs_skipped_spine_attested": sorted(skipped_attested),
                # Named, never silent: a dropped row is a claim withdrawn.
                # Two different ways a row dies, reported apart: one was
                # true once, the other can no longer be checked at all.
                "unreachable_live_rows": [
                    f"organ {o}: {sha}" for o, sha in sorted(unreachable)
                ],
                "superseded_stale_live_rows": [
                    f"organ {o}: {sha}" for o, sha in sorted(superseded)
                ],
            },
            indent=2,
        )
    )
    if args.dry_run:
        return 0
    # newline IS LOAD-BEARING. .gitattributes pins this file to eol=lf because
    # release/organ-proof-manifest.json hash-pins its BYTES. Python's default
    # translation writes CRLF on Windows, the manifest records the CRLF sha, git
    # stores the LF version, and CI computes a third number -- which is what
    # turned backend-tests red on all three platforms.
    LEDGER_PATH.write_text(
        json.dumps(ledger, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
