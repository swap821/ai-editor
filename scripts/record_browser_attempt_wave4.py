#!/usr/bin/env python3
"""Record the isolated-browser-runtime diagnosis from the wave-4 retry."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "release" / "phase4" / "browser-evidence-attempt-wave4-20260801.json"


def main() -> int:
    attempt = {
        "schema": "browser-evidence-attempt-v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "tip_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "url": "http://127.0.0.1:5173/",
        "frontend_http_status": 200,
        "affected_organs": [20, 48, 49, 51],
        "session_id": "artifactplan-wave4-20260801",
        "rvf_path": "C:\\tmp\\aios-browser-wave4-20260801\\artifactplan-wave4-20260801.rvf",
        "repo_npx_shim_test": "11.13.0",
        "recorder_success": False,
        "recorder_error": "browser open failed",
        "recorder_detail": "command not found: npx",
        "repo_shim_effective": False,
        "live_evidence_promoted": False,
        "diagnosis": "The MCP browser recorder runs in an isolated runtime that does not inherit the repository or Windows Node PATH.",
    }
    OUT.write_text(json.dumps(attempt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "promoted": False, "diagnosis": attempt["diagnosis"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
