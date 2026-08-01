#!/usr/bin/env python3
"""Record the browser-runtime boundary after pre-creating the RVF directory."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "release" / "phase4" / "browser-evidence-attempt-wave7-20260801.json"
INVENTORY = ROOT / "release" / "phase4" / "local-clerk-inventory-20260801.json"


def main() -> int:
    artifact = {
        "schema": "browser-evidence-attempt-v1",
        "attempted_at": datetime.now(timezone.utc).isoformat(),
        "tip_sha": "92d871616ce630ff398cc18e5f9f16e2849713e9",
        "url": "http://127.0.0.1:5173/",
        "frontend_http_status": 200,
        "recorder": "mcp__claude_flow__browser_session_record",
        "rvf_directory_precreated": True,
        "native_rvf_probe": {
            "success": True,
            "command": "node ruvector/bin/cli.js rvf create C:\\tmp\\rvf-direct-wave6-20260801.rvf --dimension 384",
            "result": "created and removed exact probe file",
        },
        "capture": {
            "success": False,
            "session": "artifactplan-wave7",
            "rvf_path": "C:\\tmp\\aios-browser-wave7-20260801\\artifactplan-wave7.rvf",
            "error": "browser open failed",
            "detail": "command not found: npx",
        },
        "session_end": {
            "success": True,
            "verdict": "fail",
            "indexed": False,
            "index_error": "command not found: npx",
        },
        "fallbacks": [
            "browser_act degraded because page-agent is not installed",
            "Playwright is importable, but its bundled Chromium is absent",
            "system Chrome headed launch through Node REPL returned spawn EPERM",
        ],
        "promoted_to_organ_evidence": False,
        "interpretation": "Pre-creating the directory proves native RVF durability works; the isolated recorder remains blocked because its agent-browser/npx runtime is unavailable. No truthful operator UI proof exists.",
    }
    ARTIFACT.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    attempts = inventory.setdefault("browser_attempt_artifacts", [])
    pointer = "release/phase4/browser-evidence-attempt-wave7-20260801.json"
    if pointer not in attempts:
        attempts.append(pointer)
    INVENTORY.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": pointer, "promoted": False, "native_rvf": True, "recorder": "npx missing"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
