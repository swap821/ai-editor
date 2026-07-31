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

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"
DEFAULT_ARTIFACT = REPO_ROOT / "release" / "phase4" / "live-evidence-latest.json"

PHASE4_RESIDUAL_MARKERS = ("Phase 4 absolute residual",)


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
    tip_artifact = (
        REPO_ROOT / "release" / "phase4" / f"live-evidence-{tip[:12]}.json"
    )
    if tip_artifact.exists():
        artifact_rel = tip_artifact.relative_to(REPO_ROOT).as_posix()

    by_organ: dict[int, list[dict]] = {}
    for proof in report["proofs"]:
        oid = int(proof["organ_id"])
        if oid <= 0 or not proof.get("passed"):
            continue
        by_organ.setdefault(oid, []).append(proof)

    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    updated: list[int] = []
    for row in ledger:
        oid = int(row["organ_id"])
        proofs = by_organ.get(oid)
        if not proofs:
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
        # Replace prior live rows for this tip; keep older distinct SHAs.
        prior = [
            e
            for e in (row.get("live_evidence") or [])
            if e.get("commit_sha") != tip
        ]
        row["live_evidence"] = prior + [evidence]
        row["last_verified_sha"] = tip
        blockers = list(row.get("known_blockers") or [])
        blockers = [
            b
            for b in blockers
            if not any(m in b for m in PHASE4_RESIDUAL_MARKERS)
        ]
        # Note Phase 5 gate only when still yellow and no other named Outside residual.
        named = ("frozen spine", "Phase 6 gate", "no Ollama", "Outside-machine",
                 "browser-session", "no Docker")
        has_named = any(
            any(n.lower() in b.lower() for n in named) for b in blockers
        )
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
            },
            indent=2,
        )
    )
    if args.dry_run:
        return 0
    LEDGER_PATH.write_text(
        json.dumps(ledger, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
