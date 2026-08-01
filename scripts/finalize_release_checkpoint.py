"""Write the durable handoff after an artifact-plan verification pass."""

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

**Last completed + verified:** Full backend suite: 4275 passed, 7 skipped, 0 failed, 89% coverage. Focused owner/release tests pass; strict organ verification and manifest check pass at `92d871616ce630ff398cc18e5f9f16e2849713e9`; frontend Vite build passes. Current ledger is honestly **41 green / 13 yellow**, not 54/54. The local-clerk cohort records five live-passing candidates and seven explicit failures under `r15-v2`.

**Single next action:** Obtain the external evidence/authority needed for the 13 residual yellows: §VIII controlled release for organs 1-5; a working headed browser session for 20/48/49/51; a current-tip control-plane Docker image plus organ-40 integration proof; two-provider cloud credentials/cohort for 44; and human/live red-team evidence for 46. Organ 23 remains gated by these.

**Open blockers/approvals:** frozen security-spine approval; browser connector currently lacks `npx`; current-tip Docker control-plane build exceeded the 20-minute local bound; cloud credentials and human red-team are outside this session. Do not flip rows by prose.

**Active files:** `.aios/state/ORGAN_GREEN_LEDGER.json`, `release/phase4/`, `release/phase6/`, `release/organ-proof-manifest.json`, `scripts/local_clerk_candidate_cohort.py`, `scripts/local_clerk_candidate_shortlist.py`.

**Notes:** Docker Desktop was started for a bounded attempt, the executor container/network were cleaned up, and no secrets were persisted. The passing clerk shortlist is `qwen2.5:3b`, `gemma3:4b`, `qwen2.5:7b`, `qwen2.5-coder:7b`, and `llama3.1:8b`; `granite3.2:2b` was not counted after a non-reproducible rerun.
"""
    RESUME.write_text(resume, encoding="utf-8")
    experience = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "task_id": "artifactplan-continue-20260801",
        "goal": "Continue remaining artifactplan blockers and qualify web-backed local clerk candidates.",
        "plan": "Re-audit the ledger, run current-tip evidence, qualify models, and verify release artifacts.",
        "actions": [
            "Started Docker Desktop and attempted the real executor path.",
            "Qualified installed and web-backed Ollama candidates with the production r15-v2 suite.",
            "Regenerated cohort, Phase 6 shortfall, and release manifest artifacts.",
            "Ran focused tests, full backend tests, strict release verification, and frontend build.",
        ],
        "outcome": "partial: machine-checkable gates green; 41/54 organs green; 13 external residuals remain.",
        "failure_modes": "Browser connector lacked npx; current-tip Docker control-plane build exceeded 20 minutes; organ 40 integration proof was not produced.",
        "fixes": "Corrected stale manifest hash and organ 40 blocker text; retained failed model candidates explicitly.",
        "lessons": "A vendor/library candidate is not an admitted clerk until the exact production qualification suite passes reproducibly on this laptop.",
        "confidence": 0.95,
    }
    with EXPERIENCES.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(experience, ensure_ascii=False) + "\n")
    print(json.dumps({"resume": str(RESUME), "experience": experience["task_id"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
