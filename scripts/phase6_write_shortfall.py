#!/usr/bin/env python3
"""Write Phase 6 absolute itemised shortfall under release/phase6/."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"
OUT = REPO / "release" / "phase6"
EVIDENCE_TIP = "5d482164707c6c6e62f3da6a37cff79f252f9260"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
    ).strip()
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    green = [o for o in ledger if o["status"] == "green"]
    yellow = [o for o in ledger if o["status"] == "yellow"]
    live_ids = sorted(
        {
            o["organ_id"]
            for o in ledger
            if any(e.get("proof_level") == "live" for e in (o.get("live_evidence") or []))
        }
    )
    named = []
    for o in yellow:
        kb = " | ".join(o.get("known_blockers") or [])
        reason = "unnamed"
        for marker in (
            "frozen spine",
            "Phase 6 gate",
            "no Ollama",
            "Outside-machine",
            "browser-session",
            "no Docker",
        ):
            if marker.lower() in kb.lower():
                reason = marker
                break
        named.append(
            {
                "organ_id": o["organ_id"],
                "name": o["name"],
                "status": o["status"],
                "failing_condition_or_residual": reason,
                "known_blockers": o.get("known_blockers") or [],
                "has_live_evidence": any(
                    e.get("proof_level") == "live"
                    for e in (o.get("live_evidence") or [])
                ),
                "last_verified_sha": o.get("last_verified_sha"),
            }
        )

    residual_only = sorted(
        oid for oid in (o["organ_id"] for o in named) if oid not in live_ids
    )
    # organ 40 has historical CI live evidence but still named no Docker residual
    accounted = sorted(set(live_ids) | {o["organ_id"] for o in named})

    doc = {
        "schema": "phase6-organ23-shortfall-v1",
        "generated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "evaluated_at_commit": sha,
        "evidence_tip_sha": EVIDENCE_TIP,
        "verdict": (
            "NOT 54/54 — itemised shortfall "
            "(Outside-machine and other named residuals remain)"
        ),
        "counts": {
            "total": 54,
            "green": len(green),
            "yellow": len(yellow),
            "with_live_evidence": len(live_ids),
        },
        "phase4_absolute": {
            "live_evidence_organs": live_ids,
            "named_residual_organs": sorted(o["organ_id"] for o in named),
            "residual_without_this_wave_live": residual_only,
            "all_54_accounted": accounted == list(range(1, 55)),
        },
        "phase5_absolute": {
            "flipped_green_this_wave": [
                6,
                7,
                8,
                10,
                11,
                12,
                13,
                14,
                17,
                21,
                22,
                24,
                25,
                26,
                27,
                28,
                29,
                30,
                31,
                32,
                34,
                38,
                39,
                41,
                42,
                43,
                45,
                47,
                50,
                53,
                54,
            ],
            "prior_green": [9, 15, 16, 18, 19, 36, 52],
            "green_total": len(green),
            "yellow_total": len(yellow),
            "never_flipped": [1, 2, 3, 4, 5, 20, 23, 33, 35, 37, 40, 44, 46, 48, 49, 51],
        },
        "phase6_absolute": {
            "manifest": "release/organ-proof-manifest.json (script-generated)",
            "strict_release_report": "release/phase6/strict-release-report.txt",
            "organ_23": "yellow — Phase 6 gate; shortfall list below",
            "honest_54_of_54": False,
            "absolute_met_via": "itemised shortfall document + strict-release report",
        },
        "itemised_shortfall": named,
    }
    (OUT / "organ23-shortfall.json").write_text(
        json.dumps(doc, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# Phase 6 Organ-23 Absolute — Itemised Shortfall",
        "",
        "**Verdict:** NOT 54/54. Absolute Phase 6 met via itemised shortfall "
        "(not fake greens).",
        f"**Evaluated at:** `{sha}`",
        f"**Live-evidence tip:** `{EVIDENCE_TIP}`",
        f"**Counts:** {len(green)} green / {len(yellow)} yellow / 54 total; "
        f"live evidence on {len(live_ids)} organs.",
        "",
        "## Why not 54/54",
        "",
        "Outside-machine and other named residuals remain. Organ 23 stays yellow "
        "until every below-organ is honestly green.",
        "",
        "## Itemised non-green organs",
        "",
        "| ID | Name | Residual |",
        "|----|------|----------|",
    ]
    for row in named:
        lines.append(
            f"| {row['organ_id']} | {row['name']} | "
            f"{row['failing_condition_or_residual']} |"
        )
    lines.extend(
        [
            "",
            "## Strict-release",
            "",
            "See `release/phase6/strict-release-report.txt`.",
            "",
            "## Phase 4 accounting",
            "",
            f"- Live evidence organs ({len(live_ids)}): {live_ids}",
            f"- Named residual yellows ({len(named)}): "
            f"{[o['organ_id'] for o in named]}",
            f"- All 54 accounted: {doc['phase4_absolute']['all_54_accounted']}",
            "",
        ]
    )
    (OUT / "organ23-shortfall.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"yellow": len(named), "green": len(green), "sha": sha}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
