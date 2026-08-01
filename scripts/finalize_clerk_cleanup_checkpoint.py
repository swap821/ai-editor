#!/usr/bin/env python3
"""Persist the current blocker and local-model cleanup checkpoint."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESUME = ROOT / ".aios" / "state" / "RESUME.md"
EXPERIENCES = ROOT / ".aios" / "memory" / "experiences.jsonl"


def main() -> int:
    resume = """# AI-OS Builder Resume

**Goal:** Continue comparing `artifactplan.md` Phases 1-6 with the codebase, close only provable gaps, and maintain a hardware-fit local clerk shortlist.

**Last completed + verified:** Ledger remains honestly **42 green / 12 yellow** at tip `92d871616ce630ff398cc18e5f9f16e2849713e9`; strict organ verification and manifest checks pass. Organ 46 now has a tip-stamped local live artifact proving all nine automated adversarial simulations, but remains yellow because that is not human red-team evidence. Failed and unsupported local models were removed; exactly five admitted clerks plus `nomic-embed-text` remain installed.

**Single next action:** Obtain external evidence for the remaining 12 yellows: §VIII controlled release for organs 1-5; operator-headed browser evidence for 20/48/49/51; two-provider cloud credentials/cohort for 44; and human/live red-team evidence for 46. Organ 23 remains gated by these.

**Open blockers/approvals:** frozen security-spine approval; browser connector RVF fsync/page-agent failure; cloud credentials; human red-team. `qwen3:4b` and `phi4-mini` were researched from official Ollama pages but their downloads did not complete inside the bounded window, so neither is admitted or retained.

**Active files:** `.aios/state/ORGAN_GREEN_LEDGER.json`, `release/phase4/organ46-local-simulation-92d871616ce6.json`, `release/phase4/local-clerk-candidate-cohort-92d871616ce6.json`, `release/phase4/local-clerk-inventory-20260801.json`, `release/phase6/`, `release/organ-proof-manifest.json`.

**Notes:** Removed explicit r15-v2 failures (`granite3.2:2b`, `llama3.2:3b`, `mistral:7b`, `qwen2.5-coder:3b`, `qwen3.5:0.8b`, `qwen3.5:2b`, `smollm2:1.7b-instruct-q4_K_M`), unsupported `deepseek-r1:8b`, and unqualified `qwen2.5-coder:1.5b-base`. Retained `qwen2.5:3b`, `gemma3:4b`, `qwen2.5:7b`, `qwen2.5-coder:7b`, `llama3.1:8b`, and the embedding model.
"""
    RESUME.write_text(resume, encoding="utf-8")
    experience = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "task_id": "artifactplan-clerk-cleanup-20260801",
        "goal": "Continue blocker closure and keep only admissible local clerk models on the laptop.",
        "plan": "Search official current Ollama candidates, attempt qualification, remove only explicit failures/unsupported models, run organ-46 evidence, and preserve external gates.",
        "actions": [
            "Searched official Ollama pages for qwen3:4b, phi4-mini, and ministral-3:3b.",
            "Attempted qwen3:4b and phi4-mini downloads; both exceeded the bounded network window and were not admitted.",
            "Removed seven explicit r15-v2 failures, DeepSeek R1 with known tool-schema incompatibility, and the unqualified base coder model.",
            "Retained exactly five qualified clerks and nomic-embed-text support; recorded post-cleanup inventory and free disk.",
            "Ran all nine real organ-46 automated simulations and attached local live evidence without claiming human red-team completion.",
            "Corrected stale Phase 6 no-Ollama wording and refreshed strict artifacts.",
        ],
        "outcome": "partial: 42/54 organs green; 12 named external residuals remain; five local clerks remain admitted and failed model storage was removed.",
        "failure_modes": "Two additional official candidates could not finish downloading in the network/time bound; browser, frozen-core, cloud, and human-red-team evidence remain external.",
        "fixes": "Stopped unfinished downloads, removed only exact unqualified/unsupported model targets, recorded inventory, and added organ-46 automated evidence while preserving its human-red-team residual.",
        "lessons": "A model’s official page is a search input, not qualification. Failed blobs should be removed after the failure is recorded, while support models must be distinguished from clerk candidates.",
        "confidence": 0.99,
    }
    with EXPERIENCES.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(experience, ensure_ascii=False) + "\n")
    print(json.dumps({"resume": str(RESUME), "experience": experience["task_id"], "status": "42 green / 12 yellow"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
