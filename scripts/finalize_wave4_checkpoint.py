#!/usr/bin/env python3
"""Persist the wave-4 browser-runtime diagnosis and current clerk truth."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESUME = ROOT / ".aios" / "state" / "RESUME.md"
EXPERIENCES = ROOT / ".aios" / "memory" / "experiences.jsonl"
INVENTORY = ROOT / "release" / "phase4" / "local-clerk-inventory-20260801.json"


def main() -> int:
    RESUME.write_text(
        """# AI-OS Builder Resume

**Goal:** Continue comparing `artifactplan.md` Phases 1-6 with the codebase, close only provable gaps, and maintain a hardware-fit local clerk shortlist.

**Last completed + verified:** Ledger remains honestly **42 green / 12 yellow** at tip `92d871616ce630ff398cc18e5f9f16e2849713e9`; strict organ verification, manifest checks, and focused release-conformance tests pass. The current five-model rerun passed all five retained clerks. Organ 46 has a tip-stamped local live artifact proving all nine automated adversarial simulations, but remains yellow because that is not human red-team evidence.

**Single next action:** Obtain external evidence for the remaining 12 yellows: §VIII controlled release for organs 1-5; operator-headed browser evidence for 20/48/49/51; two-provider cloud credentials/cohort for 44; and human/live red-team evidence for 46. Organ 23 remains gated by these.

**Open blockers/approvals:** frozen security-spine approval; MCP browser recorder remains isolated from the Windows/repository PATH and returns `command not found: npx`; cloud credential variables are absent; human red-team. Official Qwen3 1.7B failed r15-v2 and was removed.

**Active files:** `.aios/state/ORGAN_GREEN_LEDGER.json`, `release/phase4/local-clerk-candidate-cohort-wave3-20260801.json`, `release/phase4/local-clerk-inventory-20260801.json`, `release/phase4/local-clerk-qwen3-1.7b-attempt-20260801.json`, `release/phase4/browser-evidence-attempt-wave3-20260801.json`, `release/phase4/browser-evidence-attempt-wave4-20260801.json`, `release/phase6/`, `release/organ-proof-manifest.json`.

**Notes:** Five retained clerks pass the current r15-v2 repeat: `qwen2.5:3b`, `gemma3:4b`, `qwen2.5:7b`, `qwen2.5-coder:7b`, and `llama3.1:8b`. Qwen3 1.7B failed `json_validity`, `extraction`, and `repeated_run_reliability`, and is removed. No Ollama partial blobs remain. A repo-local npx shim worked in the project shell but did not affect the isolated MCP recorder, so it was removed and no headless evidence was promoted.
""",
        encoding="utf-8",
    )
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    inventory.setdefault("browser_attempt_artifacts", [])
    artifact = "release/phase4/browser-evidence-attempt-wave4-20260801.json"
    if artifact not in inventory["browser_attempt_artifacts"]:
        inventory["browser_attempt_artifacts"].append(artifact)
    INVENTORY.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    experience = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "task_id": "artifactplan-wave4-20260801",
        "goal": "Repair the browser evidence boundary while preserving current clerk and release truth.",
        "plan": "Verify the live frontend, test a repo-local npx shim, retry durable browser recording, and preserve the actual runtime diagnosis.",
        "actions": [
            "Verified the frontend still returned HTTP 200 on port 5173.",
            "Verified Windows npx exists and a repo-local delegating shim ran successfully in the project shell.",
            "Retried the MCP durable browser recorder with a fresh RVF path; it still reported command not found: npx.",
            "Removed the ineffective shim and recorded the isolated-runtime diagnosis without promoting UI evidence.",
            "Re-read current five-model recommendations and clean installed inventory.",
        ],
        "outcome": "partial: browser boundary diagnosed more precisely; five local clerks remain proven; 42/54 organs remain green.",
        "failure_modes": "The browser MCP runtime does not inherit the repository or Windows Node PATH; operator browser evidence remains unavailable.",
        "fixes": "Tested and removed a no-op shim; retained an explicit failure artifact rather than changing the ledger.",
        "lessons": "A local executable-path fix is not evidence until the actual recorder process observes it; keep environment diagnosis separate from UI proof.",
        "confidence": 0.99,
    }
    with EXPERIENCES.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(experience, ensure_ascii=False) + "\n")
    print(json.dumps({"resume": str(RESUME), "experience": experience["task_id"], "status": "42 green / 12 yellow"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
