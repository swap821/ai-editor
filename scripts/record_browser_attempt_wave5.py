#!/usr/bin/env python3
"""Record the wave-5 browser recorder failure and preserve release truth."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "release" / "phase4" / "browser-evidence-attempt-wave5-20260801.json"
INVENTORY = ROOT / "release" / "phase4" / "local-clerk-inventory-20260801.json"


def main() -> int:
    artifact = {
        "schema": "browser-evidence-attempt-v1",
        "attempted_at": datetime.now(timezone.utc).isoformat(),
        "tip_sha": "92d871616ce630ff398cc18e5f9f16e2849713e9",
        "url": "http://127.0.0.1:5173/",
        "frontend_http_status": 200,
        "recorder": "mcp__claude_flow__browser_session_record",
        "success": False,
        "error": "rvf create failed",
        "detail": "Durable write (fsync) failed: RVF error 0x0303: FsyncFailed",
        "rvf_path": "release/phase4/browser-runtime-wave5/20260801090153-capture-operator-facing-evidence.rvf",
        "promoted_to_organ_evidence": False,
        "interpretation": "The local frontend is reachable, but the recorder cannot create its durable evidence container; no operator-headed browser proof exists.",
    }
    ARTIFACT.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    attempts = inventory.setdefault("browser_attempt_artifacts", [])
    pointer = "release/phase4/browser-evidence-attempt-wave5-20260801.json"
    if pointer not in attempts:
        attempts.append(pointer)
    INVENTORY.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": pointer, "promoted": False, "frontend_http_status": 200}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
