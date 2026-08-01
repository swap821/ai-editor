#!/usr/bin/env python3
"""Persist the live headed-browser evidence checkpoint without promoting organs."""

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

**Last completed + verified:** Ledger remains honestly **42 green / 12 yellow** at tip `92d871616ce630ff398cc18e5f9f16e2849713e9`; strict organ verification, manifest checks, focused release-conformance tests, and diff checks pass. The local clerk cohort now has **seven** measured passes: `qwen2.5:1.5b` (13.86s, 986 MB), `qwen2.5:3b` (16.83s), `phi4-mini:3.8b` (46.09s), `gemma3:4b` (47.19s), `qwen2.5:7b` (51.83s), `qwen2.5-coder:7b` (56.97s), and `llama3.1:8b` (51.40s). All have zero failed qualification checks; no Ollama partial blobs remain; about 30.8 GB is free. A real headed Chrome 150 session against a live loopback backend captured all council and lower navigation surfaces; the UI reported measured online/idle/empty-state values. Candidate evidence is recorded in `release/phase4/browser-evidence-live-wave9-20260801.json`, but it is not promoted because no human operator attestation or approval/mission interaction occurred.

**Single next action:** Have the non-builder reviewer/operator inspect the wave-9 headed-browser screenshots and attest the live UI/approval surfaces; keep 20/48/49/51 yellow until that review and an approval/mission interaction are real. Separately, obtain §VIII controlled release for organs 1-5, two-provider cloud credentials/cohort for 44, and human/live red-team evidence for 46. Organ 23 remains gated by these.

**Open blockers/approvals:** frozen security-spine approval; wave-9 headed evidence exists but lacks human operator attestation and exercised approval/mission state; the isolated browser recorder still lacks the `npx`/agent-browser runtime even though native RVF works; cloud credential variables are absent; human red-team. These are evidence/authority boundaries, not reasons to flip a row green.

**Active files:** `.aios/state/ORGAN_GREEN_LEDGER.json`, `release/phase4/local-clerk-candidate-cohort-qwen15-wave8-20260801.json`, `release/phase4/local-clerk-inventory-20260801.json`, `release/phase4/browser-evidence-attempt-wave7-20260801.json`, `release/phase4/browser-evidence-live-wave9-20260801.json`, `release/phase4/browser-runtime-wave9/`, `release/phase6/`, `release/organ-proof-manifest.json`.

**Notes:** Official library metadata is recorded for every admitted clerk, but admission is based only on the repeated local qualification suite. Run one model at a time; the 7B/8B options are fallbacks, not simultaneous installs/runs. Failed/unqualified model storage remains removed.
""",
        encoding="utf-8",
    )
    experience = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "task_id": "artifactplan-wave9-20260801",
        "goal": "Obtain truthful browser-runtime evidence for the remaining organ blockers without inventing operator approval.",
        "plan": "Start the canonical loopback backend, drive an isolated visible Chrome profile over CDP, capture the council and navigation surfaces, record the observations, and preserve yellow verdicts pending human review.",
        "actions": [
            "Started the canonical .venv\\Scripts\\python.exe -m aios process on 127.0.0.1:8000; /health returned 200 and startup reported offline_mode=False.",
            "Connected Playwright over CDP to a separate headed Chrome 150 profile and captured 12 UI screenshots at http://127.0.0.1:5173/.",
            "Observed measured Control plane online, Directive phase idle, zero active missions/workers/models, Approval none reported, and truthful empty Governance/Operations/History states.",
            "Recorded release/phase4/browser-evidence-live-wave9-20260801.json with operator_attestation=false and mission_and_approval_exercised=false.",
            "Stopped only the exact temporary Chrome profile and backend process and removed the exact temporary profile directory.",
            "Re-ran strict organ verification, release-manifest check, focused conformance tests, and git diff --check; all passed with 42 green / 12 yellow.",
        ],
        "outcome": "partial: real headed runtime evidence now exists, but the evidence does not prove human operator attestation, approval interaction, cloud endurance, human red-team, or frozen-core release authority; ledger remains 42 green / 12 yellow.",
        "failure_modes": "The durable MCP browser recorder still cannot resolve npx/agent-browser; the live CDP capture is automated and did not exercise a mission or approval.",
        "fixes": "Used a separate visible Chrome process and live backend to capture candidate evidence, then kept organ verdicts unchanged and cleaned bounded temporary state.",
        "lessons": "A headed browser plus a live API can prove measured rendering and fail-safe empty states, but it cannot substitute for operator attestation or a exercised approval workflow. Preserve that distinction in the ledger.",
        "confidence": 0.99,
    }
    with EXPERIENCES.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(experience, ensure_ascii=False) + "\n")
    print(json.dumps({"resume": str(RESUME), "experience": experience["task_id"], "status": "42 green / 12 yellow", "headed_evidence": True}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
