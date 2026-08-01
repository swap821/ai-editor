#!/usr/bin/env python3
"""Persist the current Organ 23 evidence-wording checkpoint."""

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

**Last completed + verified:** Ledger remains honestly **42 green / 12 yellow** at tip `92d871616ce630ff398cc18e5f9f16e2849713e9`; strict organ verification, manifest checks, and focused release-conformance tests pass. Organ 46 has a tip-stamped local live artifact proving all nine automated adversarial simulations, but remains yellow because that is not human red-team evidence. Failed and unsupported local models were removed; exactly five admitted clerks plus `nomic-embed-text` remain installed.

**Single next action:** Obtain external evidence for the remaining 12 yellows: §VIII controlled release for organs 1-5; operator-headed browser evidence for 20/48/49/51; two-provider cloud credentials/cohort for 44; and human/live red-team evidence for 46. Organ 23 remains gated by these.

**Open blockers/approvals:** frozen security-spine approval; browser connector RVF fsync/page-agent failure; cloud credentials; human red-team. `qwen3:4b` and `phi4-mini` were researched from official Ollama pages but their downloads did not complete inside the bounded window, so neither is admitted or retained.

**Active files:** `.aios/state/ORGAN_GREEN_LEDGER.json`, `release/phase4/organ46-local-simulation-92d871616ce6.json`, `release/phase4/local-clerk-candidate-cohort-92d871616ce6.json`, `release/phase4/local-clerk-inventory-20260801.json`, `release/phase6/`, `release/organ-proof-manifest.json`, `scripts/refresh_organ23_residual.py`.

**Notes:** Organ 23's stale “no Ollama” wording was corrected to name only the remaining cloud, frozen-spine, browser-session, and human-red-team residuals; no verdict changed. The generated Phase 6 artifacts are current and no longer contain that phrase. Removed explicit r15-v2 failures (`granite3.2:2b`, `llama3.2:3b`, `mistral:7b`, `qwen2.5-coder:3b`, `qwen3.5:0.8b`, `qwen3.5:2b`, `smollm2:1.7b-instruct-q4_K_M`), unsupported `deepseek-r1:8b`, and unqualified `qwen2.5-coder:1.5b-base`. Retained `qwen2.5:3b`, `gemma3:4b`, `qwen2.5:7b`, `qwen2.5-coder:7b`, `llama3.1:8b`, and the embedding model.
""",
        encoding="utf-8",
    )
    experience = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "task_id": "artifactplan-organ23-wording-20260801",
        "goal": "Keep Phase 6 residual evidence truthful after local Ollama cleanup.",
        "plan": "Correct the stale Organ 23 wording, regenerate release artifacts, and verify strict contracts and focused tests.",
        "actions": [
            "Replaced Organ 23's stale no-Ollama residual wording with the remaining external blockers.",
            "Regenerated the release manifest and Phase 6 shortfall artifacts.",
            "Confirmed no stale no-Ollama phrase remains in the current ledger or generated shortfall.",
            "Ran strict organ verification, manifest check, and release-conformance tests.",
        ],
        "outcome": "partial: evidence wording and artifacts are current; 42/54 organs remain green and 12 external residuals remain.",
        "failure_modes": "The legacy Phase 6 writer still contains a historical marker/list fallback; current generated artifacts are normalized and verified.",
        "fixes": "Added a narrowly scoped Organ 23 refresh helper and regenerated current artifacts without changing verdicts.",
        "lessons": "After correcting a machine-capability residual, search both generated artifacts and their writers; never confuse available Ollama with human red-team evidence.",
        "confidence": 0.99,
    }
    with EXPERIENCES.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(experience, ensure_ascii=False) + "\n")
    print(json.dumps({"resume": str(RESUME), "experience": experience["task_id"], "status": "42 green / 12 yellow"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
