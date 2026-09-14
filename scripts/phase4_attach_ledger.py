#!/usr/bin/env python3
"""Attach Phase 4 live-evidence artifact rows into ORGAN_GREEN_LEDGER.json.

Does NOT flip green (Phase 5). Clears ``Phase 4 absolute residual`` blockers
for organs that now hold tip-stamped live evidence. Leaves named Outside /
Docker / Ollama / frozen / browser / Phase-6 residuals intact.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# One derivation of 'has this file moved since that sha', two callers.
from verify_evidence_currency import changed_since  # noqa: E402

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    report = json.loads(args.artifact.read_text(encoding="utf-8"))
    if not report.get("all_passed"):
        print("artifact all_passed is false; refusing to attach", file=sys.stderr)
        return 1
    tip = report["tip_sha"]
    if len(tip) != 40:
        print(f"tip_sha not 40 chars: {tip!r}", file=sys.stderr)
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
                drift = changed_since(
                    str(old.get("commit_sha") or ""), entrypoints, tip
                )
                if drift:
                    superseded.append((oid, str(old.get("commit_sha") or "")[:12]))
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
                "superseded_stale_live_rows": [
                    f"organ {o}: {sha}" for o, sha in sorted(superseded)
                ],
            },
            indent=2,
        )
    )
    if args.dry_run:
        return 0
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
