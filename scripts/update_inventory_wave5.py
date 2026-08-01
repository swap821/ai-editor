#!/usr/bin/env python3
"""Persist the measured Phi-4-mini admission without changing prior removals."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "release" / "phase4" / "local-clerk-inventory-20260801.json"


def main() -> int:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    phi = "phi4-mini:3.8b"
    clerks = [
        "qwen2.5:3b",
        phi,
        "gemma3:4b",
        "qwen2.5:7b",
        "qwen2.5-coder:7b",
        "llama3.1:8b",
    ]
    inventory["generated_at"] = datetime.now(timezone.utc).isoformat()
    inventory["admitted_clerks"] = clerks
    inventory["installed_after_cleanup"] = clerks + ["nomic-embed-text:latest"]
    inventory.setdefault("retained_non_clerk_support", ["nomic-embed-text:latest"])
    inventory.setdefault("aborted_unqualified_downloads", {}).pop("phi4-mini", None)
    artifact = "release/phase4/local-clerk-candidate-cohort-phi4-wave5-20260801.json"
    artifacts = inventory.setdefault("qualification_artifacts", [])
    if artifact not in artifacts:
        artifacts.append(artifact)
    inventory["disk_free_bytes_after_cleanup"] = shutil.disk_usage(ROOT).free
    INVENTORY.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"admitted_clerks": clerks, "disk_free_bytes": inventory["disk_free_bytes_after_cleanup"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
