#!/usr/bin/env python3
"""Persist the wave-7 browser-runtime diagnosis."""

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

**Last completed + verified:** Ledger remains honestly **42 green / 12 yellow** at tip `92d871616ce630ff398cc18e5f9f16e2849713e9`; strict organ verification, manifest checks, focused release-conformance tests, and diff checks pass. Six local clerks are measured passes: `qwen2.5:3b`, `phi4-mini:3.8b`, `gemma3:4b`, `qwen2.5:7b`, `qwen2.5-coder:7b`, and `llama3.1:8b`. A new browser boundary test pre-created the RVF directory and proved native RVF creation works, but the isolated recorder failed at `command not found: npx`; the session was finalized as `fail` and not indexed or promoted.

**Single next action:** Obtain external evidence for the remaining 12 yellows: §VIII controlled release for organs 1-5; operator-headed browser evidence for 20/48/49/51; two-provider cloud credentials/cohort for 44; and human/live red-team evidence for 46. Organ 23 remains gated by these.

**Open blockers/approvals:** frozen security-spine approval; isolated recorder lacks the `npx`/agent-browser runtime even though native RVF works; browser fallback lacks `page-agent`; headed Playwright fallback lacks a browser and system Chrome spawn is blocked; cloud credential variables are absent; human red-team. These are evidence/infrastructure boundaries, not reasons to flip a row green.

**Active files:** `.aios/state/ORGAN_GREEN_LEDGER.json`, `release/phase4/local-clerk-candidate-cohort-phi4-wave5-20260801.json`, `release/phase4/local-clerk-inventory-20260801.json`, `release/phase4/browser-evidence-attempt-wave7-20260801.json`, `release/phase4/browser-evidence-attempt-wave5-20260801.json`, `release/phase6/`, `release/organ-proof-manifest.json`.

**Notes:** Local model admission remains pass-only and no Ollama partial blobs remain. The browser attempts created only exact temporary probes/profiles, which were cleaned after recording. HTTP 200 and a failed durable session are not operator UI proof.
""",
        encoding="utf-8",
    )
    experience = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "task_id": "artifactplan-wave7-20260801",
        "goal": "Continue attacking the browser evidence blocker without converting infrastructure failures into organ proof.",
        "plan": "Pre-create the RVF directory, retry the durable recorder, finalize the failed session, test a headed browser fallback, clean exact temporary artifacts, and preserve the truthful ledger.",
        "actions": [
            "Direct native RVF creation succeeded in C:\\tmp, proving the Windows filesystem/native backend can fsync a 384-dimensional container.",
            "Pre-created the recorder directory; browser_session_record then created the RVF but failed to open the page because the isolated runtime could not find npx.",
            "Finalized the failed session with verdict=fail; it was not indexed and was not promoted to UI evidence.",
            "Confirmed browser_act degraded because page-agent is absent; Playwright import succeeded but bundled Chromium was absent and system Chrome spawn returned EPERM.",
            "Removed only the exact temporary browser profiles, logs, and RVF probes created during the attempt.",
        ],
        "outcome": "partial: browser root cause narrowed from generic fsync failure to missing isolated npx/agent-browser runtime; ledger remains 42 green / 12 yellow.",
        "failure_modes": "The MCP recorder's process environment cannot resolve npx; the browser fallback packages/binary are unavailable or blocked by process spawn policy.",
        "fixes": "Pre-created the RVF directory, recorded a durable failed-session artifact, and cleaned bounded temporary state; no organ verdict was changed.",
        "lessons": "When a durable wrapper fails, test the native primitive separately and then retry at the next boundary; distinguish filesystem success from browser-runtime availability and never promote a failed session.",
        "confidence": 0.99,
    }
    with EXPERIENCES.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(experience, ensure_ascii=False) + "\n")
    print(json.dumps({"resume": str(RESUME), "experience": experience["task_id"], "status": "42 green / 12 yellow"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
