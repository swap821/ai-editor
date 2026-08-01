#!/usr/bin/env python3
"""Record a bounded official Ministral candidate attempt without admitting it."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "release" / "phase4" / "local-clerk-inventory-20260801.json"
ATTEMPT = ROOT / "release" / "phase4" / "local-clerk-ministral-attempt-20260801.json"


def _installed() -> list[str]:
    listed = subprocess.check_output(["ollama", "list"], cwd=ROOT, text=True)
    return [line.split()[0] for line in listed.splitlines()[1:] if line.split()]


def main() -> int:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    installed = _installed()
    attempt = {
        "schema": "local-clerk-candidate-attempt-v1",
        "generated_at": now,
        "tip_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "model": "ministral-3:3b",
        "official_source": "https://ollama.com/library/ministral-3:3b",
        "official_library_size_gb": 3.0,
        "hardware_fit_reason": "edge-oriented 3B candidate for a 16 GB RAM / 4 GB VRAM laptop",
        "pull_bound_seconds": 600,
        "pull_result": "timeout",
        "qualification_result": "not_run_model_never_registered",
        "admitted": False,
        "retained_on_disk": False,
        "partial_storage_removed": True,
        "installed_models_after_attempt": installed,
        "note": "Official metadata is candidate discovery only; no r15-v2 pass exists for this model.",
    }
    ATTEMPT.write_text(json.dumps(attempt, indent=2) + "\n", encoding="utf-8")

    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    inventory["generated_at"] = now
    inventory["machine"] = platform.node()
    inventory["installed_after_cleanup"] = installed
    inventory["disk_free_bytes_after_cleanup"] = shutil.disk_usage(ROOT.drive + "\\").free
    inventory.setdefault("aborted_unqualified_downloads", {})[
        "ministral-3:3b"
    ] = (
        "official 3.0 GB pull hit the 10-minute bound before Ollama registration; "
        "qualification was not run and all verified partial blobs were removed"
    )
    inventory.setdefault("candidate_attempt_artifacts", []).append(str(ATTEMPT.relative_to(ROOT)))
    INVENTORY.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"attempt": str(ATTEMPT), "inventory": str(INVENTORY), "installed": installed}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
