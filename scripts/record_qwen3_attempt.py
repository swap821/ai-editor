#!/usr/bin/env python3
"""Record Qwen3 1.7B qualification failure and post-removal inventory truth."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "release" / "phase4" / "local-clerk-inventory-20260801.json"
COHORT = ROOT / "release" / "phase4" / "local-clerk-candidate-cohort-wave3-20260801.json"
ATTEMPT = ROOT / "release" / "phase4" / "local-clerk-qwen3-1.7b-attempt-20260801.json"


def _installed() -> list[str]:
    listed = subprocess.check_output(["ollama", "list"], cwd=ROOT, text=True)
    return [line.split()[0] for line in listed.splitlines()[1:] if line.split()]


def main() -> int:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    installed = _installed()
    artifact = json.loads(COHORT.read_text(encoding="utf-8"))
    candidate = next(item for item in artifact["candidates"] if item["model"] == "qwen3:1.7b")
    attempt = {
        "schema": "local-clerk-candidate-attempt-v1",
        "generated_at": now,
        "tip_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "model": "qwen3:1.7b",
        "official_source": "https://ollama.com/library/qwen3:1.7b",
        "official_library_size_gb": 1.4,
        "qualification_result": candidate["status"],
        "elapsed_seconds": candidate.get("elapsed_seconds"),
        "failed_test_ids": candidate.get("failed_test_ids", []),
        "schema_validity": candidate.get("schema_validity"),
        "admitted": False,
        "retained_on_disk": False,
        "removed_with_ollama_rm": True,
        "installed_models_after_removal": installed,
        "note": "The official page identified a fit candidate; r15-v2 evidence, not size, rejected it.",
    }
    ATTEMPT.write_text(json.dumps(attempt, indent=2) + "\n", encoding="utf-8")

    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    inventory["generated_at"] = now
    inventory["machine"] = platform.node()
    inventory["installed_after_cleanup"] = installed
    inventory["disk_free_bytes_after_cleanup"] = shutil.disk_usage(ROOT.drive + "\\").free
    inventory.setdefault("removed_models", {})["qwen3:1.7b"] = (
        "r15-v2 failed: json_validity, extraction, repeated_run_reliability; removed from local disk"
    )
    inventory.setdefault("candidate_attempt_artifacts", []).append(str(ATTEMPT.relative_to(ROOT)))
    INVENTORY.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"attempt": str(ATTEMPT), "inventory": str(INVENTORY), "installed": installed}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
