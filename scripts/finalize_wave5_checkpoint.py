#!/usr/bin/env python3
"""Persist the wave-5 Phi qualification and browser-boundary checkpoint."""

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

**Last completed + verified:** Ledger remains honestly **42 green / 12 yellow** at tip `92d871616ce630ff398cc18e5f9f16e2849713e9`; strict organ verification, manifest checks, focused release-conformance tests, and diff checks pass. The local clerk cohort now has **six** measured passes: `qwen2.5:3b`, `phi4-mini:3.8b`, `gemma3:4b`, `qwen2.5:7b`, `qwen2.5-coder:7b`, and `llama3.1:8b`. Phi-4-mini passed the repeat suite at 46.09 seconds and 2.5 GB; no Ollama partial blobs remain. Organ 46 has a tip-stamped local artifact proving all nine automated adversarial simulations, but remains yellow because that is not human red-team evidence.

**Single next action:** Obtain external evidence for the remaining 12 yellows: §VIII controlled release for organs 1-5; operator-headed browser evidence for 20/48/49/51; two-provider cloud credentials/cohort for 44; and human/live red-team evidence for 46. Organ 23 remains gated by these.

**Open blockers/approvals:** frozen security-spine approval; the browser recorder now fails at durable RVF creation with `FsyncFailed` before page capture; cloud credential variables are absent; human red-team. Official Qwen3 1.7B failed r15-v2 and was removed. These blockers are not resolved by the six-model local cohort.

**Active files:** `.aios/state/ORGAN_GREEN_LEDGER.json`, `release/phase4/local-clerk-candidate-cohort-phi4-wave5-20260801.json`, `release/phase4/local-clerk-inventory-20260801.json`, `release/phase4/local-clerk-qwen3-1.7b-attempt-20260801.json`, `release/phase4/browser-evidence-attempt-wave5-20260801.json`, `release/phase4/browser-evidence-attempt-wave4-20260801.json`, `release/phase6/`, `release/organ-proof-manifest.json`.

**Notes:** Local model admission remains pass-only: vendor pages and downloads never qualify a clerk. The machine has about 31.9 GB free after admitting Phi-4-mini and retains only six clerks plus `nomic-embed-text:latest`; previously failed/unqualified models remain removed. HTTP 200 is not promoted as browser proof because the recorder cannot durably create its evidence container.
""",
        encoding="utf-8",
    )
    experience = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "task_id": "artifactplan-wave5-20260801",
        "goal": "Expand the web-backed local clerk cohort while retrying the external browser evidence boundary.",
        "plan": "Pull one official laptop-sized candidate, run the reproducible clerk suite, update only pass-qualified inventory, retry browser recording, and rerun release gates.",
        "actions": [
            "Pulled official phi4-mini:3.8b from Ollama; the 2.5 GB model registered successfully and left no partial blobs.",
            "Ran the existing qualification suite; Phi-4-mini passed with 100% schema and identifier validity, zero failed tests, and 46.09 seconds measured elapsed time.",
            "Persisted six admitted clerks and current free space of 31,885,602,816 bytes; no unqualified model was retained.",
            "Retried the real browser recorder; frontend HTTP status was 200 but durable RVF creation failed with FsyncFailed before capture.",
            "Verified strict organ contracts, release manifest, focused conformance tests, and diff hygiene all pass.",
        ],
        "outcome": "partial: local clerk shortlist improved from five to six; ledger remains 42 green / 12 yellow because external evidence blockers remain.",
        "failure_modes": "Browser recorder durable-storage fsync failure; cloud provider variables absent; frozen security approvals and human red-team evidence remain outside autonomous scope.",
        "fixes": "Added the official Phi-4-mini pass artifact and inventory update; recorded the browser failure without promoting HTTP 200 as UI proof.",
        "lessons": "A downloaded model earns admission only after the same repeated structured-output gate; a reachable frontend is not browser evidence when the durable recorder cannot write its trace.",
        "confidence": 0.99,
    }
    with EXPERIENCES.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(experience, ensure_ascii=False) + "\n")
    print(json.dumps({"resume": str(RESUME), "experience": experience["task_id"], "status": "42 green / 12 yellow", "clerks": 6}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
