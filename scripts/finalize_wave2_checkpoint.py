#!/usr/bin/env python3
"""Persist the second evidence-wave results for the shared builder notebook."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESUME = ROOT / ".aios" / "state" / "RESUME.md"
EXPERIENCES = ROOT / ".aios" / "memory" / "experiences.jsonl"


def main() -> int:
    RESUME.write_text(
        """# AI-OS Builder Resume

**Goal:** Continue comparing `artifactplan.md` Phases 1-6 with the codebase, close only provable gaps, and maintain a hardware-fit local clerk shortlist.

**Last completed + verified:** Ledger remains honestly **42 green / 12 yellow** at tip `92d871616ce630ff398cc18e5f9f16e2849713e9`; strict organ verification, manifest checks, and focused release-conformance tests pass. Organ 46 has a tip-stamped local live artifact proving all nine automated adversarial simulations, but remains yellow because that is not human red-team evidence. Exactly five admitted clerks plus `nomic-embed-text` remain installed.

**Single next action:** Obtain external evidence for the remaining 12 yellows: §VIII controlled release for organs 1-5; operator-headed browser evidence for 20/48/49/51; two-provider cloud credentials/cohort for 44; and human/live red-team evidence for 46. Organ 23 remains gated by these.

**Open blockers/approvals:** frozen security-spine approval; browser recorder cannot find `npx` even though the project shell has Node/npm; cloud credentials; human red-team. A bounded official `ministral-3:3b` attempt timed out before registration, so it was not qualified or retained.

**Active files:** `.aios/state/ORGAN_GREEN_LEDGER.json`, `release/phase4/organ46-local-simulation-92d871616ce6.json`, `release/phase4/local-clerk-candidate-cohort-92d871616ce6.json`, `release/phase4/local-clerk-inventory-20260801.json`, `release/phase4/local-clerk-ministral-attempt-20260801.json`, `release/phase6/`, `release/organ-proof-manifest.json`.

**Notes:** The failed Ministral pull left verified partial Ollama blobs; 67 exact partial files totaling about 7.94 GB were removed, and no `*-partial*` blobs remain. The installed set is unchanged: `qwen2.5:3b`, `gemma3:4b`, `qwen2.5:7b`, `qwen2.5-coder:7b`, `llama3.1:8b`, plus `nomic-embed-text:latest`. Browser attempts remain unpromoted because recorder navigation failed at the missing-`npx` boundary; headless substitutes are prohibited by the organ contract.
""",
        encoding="utf-8",
    )
    experience = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "task_id": "artifactplan-wave2-20260801",
        "goal": "Continue attacking artifact-plan external blockers and expand the local clerk search without admitting unqualified models.",
        "plan": "Retry one official edge candidate, clean exact failed pull remnants, retry browser evidence, and refresh durable evidence.",
        "actions": [
            "Searched the official Ollama library and selected Ministral 3B as a bounded 3.0 GB candidate.",
            "Ran the pull for the full 10-minute bound; Ollama never registered the model and r15-v2 was not run.",
            "Removed 67 exact partial blobs totaling about 7.94 GB and verified zero partial blobs remain.",
            "Retried durable browser recording against the live frontend; it failed because the recorder runtime cannot find npx.",
            "Recorded the candidate attempt and post-cleanup inventory without changing clerk admission or organ verdicts.",
        ],
        "outcome": "partial: five qualified clerks remain, failed storage is cleaned, and 42/54 organs remain green; external evidence blockers persist.",
        "failure_modes": "Ministral download timed out; browser recorder navigation failed at missing npx; neither produced admissible evidence.",
        "fixes": "Stopped the exact pull process, removed only verified partial blobs, and preserved failed-attempt artifacts.",
        "lessons": "A bounded retry is useful only if timeout remnants are cleaned and the model is explicitly recorded as not qualified; a browser tool error cannot be converted into UI proof.",
        "confidence": 0.99,
    }
    with EXPERIENCES.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(experience, ensure_ascii=False) + "\n")
    print(json.dumps({"resume": str(RESUME), "experience": experience["task_id"], "status": "42 green / 12 yellow"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
