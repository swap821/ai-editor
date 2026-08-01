#!/usr/bin/env python3
"""Record a browser evidence attempt without promoting a failed recorder run."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "release" / "phase4" / "browser-evidence-attempt-wave3-20260801.json"


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
        "session_id": "artifactplan-wave3-20260801",
        "rvf_path": "C:\\tmp\\aios-browser-wave3-20260801\\artifactplan-wave3-20260801.rvf",
        "recorder_success": False,
        "recorder_error": "browser open failed",
        "recorder_detail": "command not found: npx",
        "live_evidence_promoted": False,
        "reason": "A live frontend response is not equivalent to operator browser evidence; the recorder could not navigate.",
    }
    OUT.write_text(json.dumps(attempt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "promoted": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
