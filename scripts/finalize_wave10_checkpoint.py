#!/usr/bin/env python3
"""Persist wave-10 browser/auth and local-clerk candidate evidence."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release" / "phase4"
RESUME = ROOT / ".aios" / "state" / "RESUME.md"
EXPERIENCES = ROOT / ".aios" / "memory" / "experiences.jsonl"
INVENTORY = RELEASE / "local-clerk-inventory-20260801.json"
TIP_SHA = "92d871616ce630ff398cc18e5f9f16e2849713e9"


def write_json(path: Path, payload: dict) -> str:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path.relative_to(ROOT).as_posix()


def main() -> int:
    now = datetime.now(timezone.utc).isoformat()
    granite_pointer = write_json(
        RELEASE / "local-clerk-granite4-attempt-wave10-20260801.json",
        {
            "schema": "local-clerk-candidate-attempt-v1",
            "attempted_at": now,
            "tip_sha": TIP_SHA,
            "model": "granite4:3b",
            "source_url": "https://ollama.com/library/granite4:3b",
            "official_library_size_gb": 2.1,
            "status": "pull_timeout",
            "pull_bound_seconds": 600,
            "qualification_run": False,
            "retained": False,
            "cleanup": {
                "manifest_and_unshared_blobs_removed": True,
                "removed_blob_count": 4,
                "model_registered_after_cleanup": False,
            },
            "interpretation": "The official candidate never completed download, so it has no qualification result and is not a clerk recommendation.",
        },
    )
    gemma_pointer = "release/phase4/local-clerk-candidate-cohort-gemma1-wave10-20260801.json"
    auth_pointer = write_json(
        RELEASE / "browser-evidence-auth-boundary-wave10-20260801.json",
        {
            "schema": "browser-evidence-auth-boundary-v1",
            "captured_at": now,
            "tip_sha": TIP_SHA,
            "frontend": {
                "url": "http://localhost:5173/",
                "http_status": 200,
                "headed": True,
                "browser": "Chrome/150.0.7871.187",
                "screenshot": "release/phase4/browser-runtime-wave10/localhost-approval.png",
            },
            "backend": {
                "url": "http://localhost:8000/health",
                "health_status": 200,
                "router_cloud_tasks": [],
                "session_created": True,
                "csrf_proof_cookie_present": True,
                "operator_id_present": False,
            },
            "action_probe": {
                "endpoint": "POST /api/generate",
                "status": 401,
                "detail": "authenticated operator session required",
                "proposal_file_created": False,
                "approval_clicked": False,
            },
            "prior_wrong_origin_probe": {
                "origin": "http://127.0.0.1:5173",
                "status": 403,
                "detail": "Mutation requires a bearer token or a valid session, exact Origin, and session-bound CSRF proof",
            },
            "promoted_to_organ_evidence": False,
            "interpretation": "The canonical localhost origin fixes the origin/CSRF mismatch, but the supervised action remains blocked until the real Human Sovereign operator is enrolled and authenticated. No credential or secret was fabricated or persisted.",
        },
    )

    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    attempts = inventory.setdefault("candidate_attempt_artifacts", [])
    for pointer in (granite_pointer, gemma_pointer):
        if pointer not in attempts:
            attempts.append(pointer)
    browser_attempts = inventory.setdefault("browser_attempt_artifacts", [])
    if auth_pointer not in browser_attempts:
        browser_attempts.append(auth_pointer)
    inventory["disk_free_bytes_after_cleanup"] = shutil.disk_usage(ROOT).free
    INVENTORY.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")

    RESUME.write_text(
        """# AI-OS Builder Resume

**Goal:** Continue comparing `artifactplan.md` Phases 1-6 with the codebase, close only provable gaps, and maintain a hardware-fit local clerk shortlist.

**Last completed + verified:** Ledger remains honestly **42 green / 12 yellow** at tip `92d871616ce630ff398cc18e5f9f16e2849713e9`; strict organ verification, manifest checks, focused release-conformance tests, and diff checks pass. The local clerk cohort still has **seven** measured passes: `qwen2.5:1.5b`, `qwen2.5:3b`, `phi4-mini:3.8b`, `gemma3:4b`, `qwen2.5:7b`, `qwen2.5-coder:7b`, and `llama3.1:8b`. Gemma 3 1B was downloaded, failed six r15-v2 checks, and was removed. Granite 4 3B hit the ten-minute pull bound, never qualified, and its unshared partial manifest/blobs were removed. A headed localhost browser probe reached the live backend and established a session/CSRF cookie, but `/api/generate` returned `401 authenticated operator session required`; no file was created and no approval was clicked.

**Single next action:** Obtain the operator’s real enrollment/login for the supervised browser action, then capture a pending approval without authorizing it. Independently, obtain §VIII controlled release for organs 1-5, two-provider cloud credentials/cohort for 44, and human/live red-team evidence for 46. Organs 20/48/49/51 remain yellow until operator-attested live UI and exercised approval/heartbeat evidence exists; organ 23 remains gated.

**Open blockers/approvals:** Human Sovereign enrollment/authentication; frozen security-spine approval; cloud credential variables; human red-team; isolated browser recorder missing its npx/agent-browser runtime. The seven-clerk cohort is the current pass-only recommendation set; failed candidates are removed from disk.

**Active files:** `.aios/state/ORGAN_GREEN_LEDGER.json`, `release/phase4/local-clerk-inventory-20260801.json`, `release/phase4/local-clerk-candidate-cohort-qwen15-wave8-20260801.json`, `release/phase4/local-clerk-candidate-cohort-gemma1-wave10-20260801.json`, `release/phase4/local-clerk-granite4-attempt-wave10-20260801.json`, `release/phase4/browser-evidence-auth-boundary-wave10-20260801.json`, `release/phase4/browser-runtime-wave10/`, `release/phase6/`, `release/organ-proof-manifest.json`.

**Notes:** Official web metadata is candidate discovery only. Admission still requires the complete reproducible r15-v2 suite. Run one model at a time; 7B/8B options are fallbacks, not simultaneous installs/runs.
""",
        encoding="utf-8",
    )

    experience = {
        "ts": now,
        "task_id": "artifactplan-wave10-20260801",
        "goal": "Advance the supervised browser blocker and expand local clerk candidates without fabricating authority or retaining failures.",
        "plan": "Retry the live action on the canonical localhost origin, diagnose the exact auth boundary, search official Ollama candidates, qualify one small candidate, clean every failure, and persist current evidence.",
        "actions": [
            "Started the local-only backend with router_cloud_tasks empty and reached the frontend through a separate headed Chrome profile.",
            "Corrected the first 127.0.0.1 origin probe diagnosis: the action route rejected it with exact-Origin/CSRF 403.",
            "Retried on localhost:5173, established the normal CSRF/session cookie, and received the exact 401 authenticated operator session required response from POST /api/generate.",
            "Confirmed no proposal was approved and no file was created.",
            "Searched official Ollama pages; Granite 4 3B timed out at ten minutes and its four unshared blobs plus manifest were removed.",
            "Downloaded Gemma 3 1B; r15-v2 failed six checks (schema_validity 0.647, unsupported_claim_rate 1.0, one mutation/tool request), then removed the model with ollama rm.",
            "Updated the pass-only inventory and checkpoint; strict release gates remain at 42 green / 12 yellow.",
        ],
        "outcome": "partial: the next browser blocker is now precisely authenticated Human Sovereign enrollment, and the seven qualified clerks remain clean; no new model passed.",
        "failure_modes": "No authenticated operator exists in the temporary browser session; Granite download timed out; Gemma 1B failed the safety/clerical contract.",
        "fixes": "Used the canonical origin, recorded the exact auth response, removed all failed model storage, and preserved the yellow verdicts.",
        "lessons": "A session cookie and CSRF proof are not an authenticated Human Sovereign. A small official model is not a clerk until it passes the same safety and fidelity contract.",
        "confidence": 0.99,
    }
    with EXPERIENCES.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(experience, ensure_ascii=False) + "\n")
    print(json.dumps({"auth_artifact": auth_pointer, "granite_artifact": granite_pointer, "status": "42 green / 12 yellow", "qualified_clerks": 7}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
