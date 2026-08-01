#!/usr/bin/env python3
"""Run organ 46's real nine simulations and bank local live evidence."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"
OUT = ROOT / "release" / "phase4" / "organ46-local-simulation-92d871616ce6.json"


def main() -> int:
    from aios.application.governance.adversarial_simulations import run_adversarial_simulations
    from aios.application.governance.amendment_authority import propose_amendment

    tip = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    proposal = propose_amendment(
        proposal_id="organ46-local-live-proof",
        target_articles=("article-9-reauth-policy",),
        proposed_diff="cache reauth for a short trusted window",
        motivation="reduce operator friction on routine approvals",
        migration_plan="roll out behind a flag",
        rollback_plan="flip the flag back",
        proposed_by="organ46-local-proof",
        proposer_type="human",
    )
    results = run_adversarial_simulations(proposal)
    assert len(results) == 9
    assert all(result.passed for result in results)
    artifact = {
        "schema": "organ46-local-simulation-v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "tip_sha": tip,
        "all_nine_passed": True,
        "proposal_id": proposal.proposal_id,
        "runner": "ConstitutionalLearningAuthority production simulation path",
        "human_red_team_claimed": False,
        "results": [result.model_dump(mode="json") for result in results],
        "residual": "This proves the automated nine-check floor only; it does not replace a human/live external red-team cohort.",
    }
    OUT.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")

    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    row = next(item for item in ledger if int(item["organ_id"]) == 46)
    evidence = {
        "description": (
            f"Local live organ-46 simulation run on tip {tip}: "
            "all nine real production-mechanism checks passed against a disposable proposal; "
            "artifact=release/phase4/organ46-local-simulation-92d871616ce6.json. "
            "This is not human red-team evidence and does not close that residual."
        ),
        "commit_sha": tip,
        "proof_level": "live",
    }
    row["live_evidence"] = [
        item for item in (row.get("live_evidence") or []) if item.get("commit_sha") != tip
    ] + [evidence]
    row["last_verified_sha"] = tip
    LEDGER.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"organ_id": 46, "all_nine_passed": True, "tip_sha": tip, "artifact": str(OUT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
