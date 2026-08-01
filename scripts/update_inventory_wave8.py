#!/usr/bin/env python3
"""Persist the measured Qwen2.5 1.5B admission."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "release" / "phase4" / "local-clerk-inventory-20260801.json"


def main() -> int:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    clerks = [
        "qwen2.5:1.5b",
        "qwen2.5:3b",
        "phi4-mini:3.8b",
        "gemma3:4b",
        "qwen2.5:7b",
        "qwen2.5-coder:7b",
        "llama3.1:8b",
    ]
    inventory["generated_at"] = datetime.now(timezone.utc).isoformat()
    inventory["admitted_clerks"] = clerks
    inventory["installed_after_cleanup"] = clerks + ["nomic-embed-text:latest"]
    inventory["disk_free_bytes_after_cleanup"] = shutil.disk_usage(ROOT).free
    artifact = "release/phase4/local-clerk-candidate-cohort-qwen15-wave8-20260801.json"
    qualification = inventory.setdefault("qualification_artifacts", [])
    if artifact not in qualification:
        qualification.append(artifact)
    INVENTORY.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"admitted_clerks": clerks, "disk_free_bytes": inventory["disk_free_bytes_after_cleanup"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
