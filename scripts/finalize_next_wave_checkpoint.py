#!/usr/bin/env python3
"""Write the durable handoff after the current-tip Docker proof wave."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESUME = ROOT / ".aios" / "state" / "RESUME.md"
EXPERIENCES = ROOT / ".aios" / "memory" / "experiences.jsonl"


def main() -> int:
    resume = """# AI-OS Builder Resume

**Goal:** Compare `artifactplan.md` Phases 1-6 with the codebase and close only locally provable gaps.

**Last completed + verified:** Current-tip organ-40 Docker proof passed `4 passed` before and after executor restart using `release/phase4/organ40-live-proof-92d871616ce6.json`; strict organ verification and manifest check pass at `92d871616ce630ff398cc18e5f9f16e2849713e9`; ledger is honestly **42 green / 12 yellow**. The backend suite previously passed 4275 with 7 skips and 0 failures; frontend Vite build passed. The local-clerk cohort has five reproducibly passing candidates under `r15-v2`, with explicit failed candidates retained.

**Single next action:** Obtain external evidence/authority for the 12 residual yellows: §VIII controlled release for organs 1-5; an operator-headed browser session for 20/48/49/51; two-provider cloud credentials/cohort for 44; and human/live red-team evidence for 46. Organ 23 remains gated by these.

**Open blockers/approvals:** frozen security-spine approval; browser connector fails RVF durable `fsync` and its fallback lacks `page-agent`, so no UI evidence was claimed; cloud credentials and human red-team are outside this session. Do not flip rows by prose.

**Active files:** `.aios/state/ORGAN_GREEN_LEDGER.json`, `release/phase4/`, `release/phase6/`, `release/organ-proof-manifest.json`, `scripts/local_clerk_candidate_cohort.py`, `scripts/local_clerk_candidate_shortlist.py`, `scripts/organ40*`, `scripts/normalize_*`.

**Notes:** The temporary Docker executor/network were stopped and removed; images and project data were retained. The five admitted clerk options are `qwen2.5:3b`, `gemma3:4b`, `qwen2.5:7b`, `qwen2.5-coder:7b`, and `llama3.1:8b`; use one 7B/8B model at a time on this 16 GB / 4 GB-VRAM laptop. `granite3.2:2b` remains excluded after a non-reproducible rerun.
"""
    RESUME.write_text(resume, encoding="utf-8")
    experience = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "task_id": "artifactplan-next-wave-20260801",
        "goal": "Continue artifactplan verification and close current-tip evidence gaps honestly while qualifying web-backed local clerk candidates.",
        "plan": "Run a lean Docker-backed organ-40 proof, retry browser evidence, refresh residuals and release artifacts, and preserve external blockers.",
        "actions": [
            "Built a lean control-plane proof image from the local AIOS image without rebuilding the 16.6 GB production image.",
            "Corrected the Docker Desktop socket group mapping from 999 to the detected group 0; integration suite passed 4 tests before and after executor restart.",
            "Recorded tip-stamped organ-40 evidence and promoted only that organ; regenerated manifest and Phase 6 shortfall.",
            "Corrected organ 46's stale no-Ollama residual because Ollama is available; retained the real human/live red-team blocker.",
            "Retried browser evidence; RVF durable fsync failed in both repository and temp paths, and page-agent fallback was unavailable.",
            "Corrected official Ollama URLs and measured metadata for the five passing clerk recommendations.",
        ],
        "outcome": "partial: 42/54 organs green, 12 named external residuals remain; organ 40 has current-tip pre/post-restart live evidence; five local clerk candidates pass r15-v2.",
        "failure_modes": "Browser connector could not create a durable RVF session because fsync failed; page-agent fallback was not installed. Frozen-core approval, cloud credentials, and human red-team remain outside this session.",
        "fixes": "Corrected socket-group setup, recorded the real Docker proof, removed stale organ-40/46 residual wording, regenerated strict release artifacts, and repaired clerk provenance metadata.",
        "lessons": "When infrastructure fails, diagnose the exact boundary before changing a verdict: organ-40 initially failed from a socket-group mismatch, then passed after the correct group was used. Availability of Ollama is not equivalent to human red-team evidence.",
        "confidence": 0.99,
    }
    with EXPERIENCES.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(experience, ensure_ascii=False) + "\n")
    print(json.dumps({"resume": str(RESUME), "experience": experience["task_id"], "ledger": "42 green / 12 yellow"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
