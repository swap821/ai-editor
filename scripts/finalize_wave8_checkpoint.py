#!/usr/bin/env python3
"""Persist the wave-8 lightweight clerk qualification checkpoint."""

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

**Last completed + verified:** Ledger remains honestly **42 green / 12 yellow** at tip `92d871616ce630ff398cc18e5f9f16e2849713e9`; strict organ verification, manifest checks, focused release-conformance tests, and diff checks pass. The local clerk cohort now has **seven** measured passes: `qwen2.5:1.5b` (13.86s, 986 MB), `qwen2.5:3b` (16.83s), `phi4-mini:3.8b` (46.09s), `gemma3:4b` (47.19s), `qwen2.5:7b` (51.83s), `qwen2.5-coder:7b` (56.97s), and `llama3.1:8b` (51.40s). All have zero failed qualification checks; no Ollama partial blobs remain; about 30.8 GB is free.

**Single next action:** Obtain external evidence for the remaining 12 yellows: §VIII controlled release for organs 1-5; operator-headed browser evidence for 20/48/49/51; two-provider cloud credentials/cohort for 44; and human/live red-team evidence for 46. Organ 23 remains gated by these.

**Open blockers/approvals:** frozen security-spine approval; isolated browser recorder lacks the `npx`/agent-browser runtime even though native RVF works; browser fallback lacks `page-agent`; headed fallback could not start a browser through the available runtime; cloud credential variables are absent; human red-team. These are evidence/infrastructure boundaries, not reasons to flip a row green.

**Active files:** `.aios/state/ORGAN_GREEN_LEDGER.json`, `release/phase4/local-clerk-candidate-cohort-qwen15-wave8-20260801.json`, `release/phase4/local-clerk-inventory-20260801.json`, `release/phase4/browser-evidence-attempt-wave7-20260801.json`, `release/phase6/`, `release/organ-proof-manifest.json`.

**Notes:** Official library metadata is recorded for every admitted clerk, but admission is based only on the repeated local qualification suite. Run one model at a time; the 7B/8B options are fallbacks, not simultaneous installs/runs. Failed/unqualified model storage remains removed.
""",
        encoding="utf-8",
    )
    experience = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "task_id": "artifactplan-wave8-20260801",
        "goal": "Expand the web-backed local clerk cohort with a lightweight candidate while preserving truthful artifact-plan blockers.",
        "plan": "Search the official Ollama library, pull Qwen2.5 1.5B, run the exact qualification suite, retain it only after a pass, update inventory, and preserve the external browser diagnosis.",
        "actions": [
            "Searched the official Ollama library and selected qwen2.5:1.5b, listed as a 986 MB official variant.",
            "Downloaded qwen2.5:1.5b and ran the existing r15-v2 clerk cohort runner; it passed with 13.86 seconds elapsed, schema_validity=1.0, identifier_preservation=1.0, and no failed test IDs.",
            "Normalized official source/size metadata and promoted the candidate to the admitted inventory; no partial blobs remain.",
            "Preserved the browser wave-7 finding: native RVF creation succeeds, but the isolated recorder cannot resolve npx and no UI evidence was promoted.",
        ],
        "outcome": "partial: seven local clerk options are now qualified; ledger remains 42 green / 12 yellow because external evidence blockers remain.",
        "failure_modes": "Browser recorder runtime still lacks npx/agent-browser; cloud credentials, frozen-core approval, and human red-team evidence remain external.",
        "fixes": "Added qwen2.5:1.5b only after measured qualification, updated the pass-only inventory, and left organ verdicts unchanged.",
        "lessons": "A sub-1 GB candidate can be a useful low-latency clerk, but it still must pass the same structured-output and safety gate; official size alone is never admission evidence.",
        "confidence": 0.99,
    }
    with EXPERIENCES.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(experience, ensure_ascii=False) + "\n")
    print(json.dumps({"resume": str(RESUME), "experience": experience["task_id"], "status": "42 green / 12 yellow", "clerks": 7}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
