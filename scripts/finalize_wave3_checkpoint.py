#!/usr/bin/env python3
"""Persist wave-3 qualification, cleanup, and browser-boundary evidence."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESUME = ROOT / ".aios" / "state" / "RESUME.md"
EXPERIENCES = ROOT / ".aios" / "memory" / "experiences.jsonl"
INVENTORY = ROOT / "release" / "phase4" / "local-clerk-inventory-20260801.json"


def _installed() -> list[str]:
    listed = subprocess.check_output(["ollama", "list"], cwd=ROOT, text=True)
    return [line.split()[0] for line in listed.splitlines()[1:] if line.split()]


def main() -> int:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    installed = _installed()
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    inventory["generated_at"] = now
    inventory["installed_after_cleanup"] = installed
    inventory["disk_free_bytes_after_cleanup"] = shutil.disk_usage(ROOT.drive + "\\").free
    inventory.setdefault("qualification_artifacts", [])
    for relative in (
        "release/phase4/local-clerk-candidate-cohort-rerun-20260801.json",
        "release/phase4/local-clerk-candidate-cohort-wave3-20260801.json",
    ):
        if relative not in inventory["qualification_artifacts"]:
            inventory["qualification_artifacts"].append(relative)
    inventory.setdefault("browser_attempt_artifacts", [])
    browser_artifact = "release/phase4/browser-evidence-attempt-wave3-20260801.json"
    if browser_artifact not in inventory["browser_attempt_artifacts"]:
        inventory["browser_attempt_artifacts"].append(browser_artifact)
    INVENTORY.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")

    RESUME.write_text(
        """# AI-OS Builder Resume

**Goal:** Continue comparing `artifactplan.md` Phases 1-6 with the codebase, close only provable gaps, and maintain a hardware-fit local clerk shortlist.

**Last completed + verified:** Ledger remains honestly **42 green / 12 yellow** at tip `92d871616ce630ff398cc18e5f9f16e2849713e9`; strict organ verification, manifest checks, and focused release-conformance tests pass. A current five-model rerun passed all five retained clerks. Organ 46 has a tip-stamped local live artifact proving all nine automated adversarial simulations, but remains yellow because that is not human red-team evidence.

**Single next action:** Obtain external evidence for the remaining 12 yellows: §VIII controlled release for organs 1-5; operator-headed browser evidence for 20/48/49/51; two-provider cloud credentials/cohort for 44; and human/live red-team evidence for 46. Organ 23 remains gated by these.

**Open blockers/approvals:** frozen security-spine approval; browser recorder repeats `command not found: npx` despite the live frontend returning HTTP 200; cloud credential variables are absent; human red-team. Official Qwen3 1.7B was downloaded but failed r15-v2 and was removed.

**Active files:** `.aios/state/ORGAN_GREEN_LEDGER.json`, `release/phase4/local-clerk-candidate-cohort-wave3-20260801.json`, `release/phase4/local-clerk-candidate-cohort-rerun-20260801.json`, `release/phase4/local-clerk-inventory-20260801.json`, `release/phase4/local-clerk-qwen3-1.7b-attempt-20260801.json`, `release/phase4/browser-evidence-attempt-wave3-20260801.json`, `release/phase6/`, `release/organ-proof-manifest.json`.

**Notes:** The five retained clerk candidates passed the current repeat suite: `qwen2.5:3b`, `gemma3:4b`, `qwen2.5:7b`, `qwen2.5-coder:7b`, and `llama3.1:8b`. Qwen3 1.7B failed `json_validity`, `extraction`, and `repeated_run_reliability`, and was removed. No Ollama partial blobs remain. Browser evidence remains unpromoted because a successful frontend HTTP response is not a durable operator browser session.
""",
        encoding="utf-8",
    )
    experience = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "task_id": "artifactplan-wave3-20260801",
        "goal": "Continue current-tip clerk qualification and attack remaining external artifact-plan blockers.",
        "plan": "Repeat all retained clerks, test one smaller official web candidate, remove failures, retry browser recording, and run strict release checks.",
        "actions": [
            "Reran all five retained clerks through r15-v2; all five passed.",
            "Normalized the rerun artifact so llama3.1:8b was included with official provenance despite a runner recommendation-order bug.",
            "Downloaded official qwen3:1.7b, ran r15-v2, recorded failures, and removed the model.",
            "Retried durable browser recording with a live HTTP-200 frontend; recorder again failed at missing npx.",
            "Checked cloud credential presence without reading secret values; no provider credentials were available.",
        ],
        "outcome": "partial: five current clerk options remain proven; 42/54 organs remain green and 12 external residuals remain.",
        "failure_modes": "Qwen3 1.7B failed three qualification checks; browser recorder could not find npx; cloud credentials are absent.",
        "fixes": "Removed the failed model, normalized current cohort metadata, and persisted exact external-boundary failures.",
        "lessons": "A repeat run can expose release-metadata bugs even when model tests pass; normalize recommendations from measured status, and never turn HTTP reachability into browser evidence.",
        "confidence": 0.99,
    }
    with EXPERIENCES.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(experience, ensure_ascii=False) + "\n")
    print(json.dumps({"resume": str(RESUME), "experience": experience["task_id"], "status": "42 green / 12 yellow", "installed": installed}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
