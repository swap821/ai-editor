#!/usr/bin/env python3
"""Record the post-cleanup local model inventory without changing admission evidence."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "release" / "phase4" / "local-clerk-inventory-20260801.json"
COHORT = ROOT / "release" / "phase4" / "local-clerk-candidate-cohort-92d871616ce6.json"

REMOVED = {
    "granite3.2:2b": "r15-v2 failed: summarisation; removed from local disk",
    "llama3.2:3b": "r15-v2 failed: summarisation; removed from local disk",
    "mistral:7b": "r15-v2 failed: context_completeness; removed from local disk",
    "qwen2.5-coder:3b": "r15-v2 failed: summarisation and prompt_injection; removed from local disk",
    "qwen3.5:0.8b": "r15-v2 failed multiple checks; removed from local disk",
    "qwen3.5:2b": "r15-v2 failed multiple checks; removed from local disk",
    "smollm2:1.7b-instruct-q4_K_M": "r15-v2 failed: missing_information; removed from local disk",
    "deepseek-r1:8b": "project compatibility note: Ollama endpoint rejects the agent tool schema; removed from local disk",
    "qwen2.5-coder:1.5b-base": "base model with no clerk qualification; removed from local disk",
}


def _tip() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def main() -> int:
    cohort = json.loads(COHORT.read_text(encoding="utf-8"))
    admitted = [item["model"] for item in cohort["recommendations"] if item.get("measured_pass")]
    listed = subprocess.check_output(["ollama", "list"], cwd=ROOT, text=True)
    installed = []
    for line in listed.splitlines()[1:]:
        fields = line.split()
        if fields:
            installed.append(fields[0])
    usage = shutil.disk_usage(ROOT.drive + "\\")
    artifact = {
        "schema": "local-clerk-inventory-v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "tip_sha": _tip(),
        "machine": platform.node(),
        "admitted_clerks": admitted,
        "installed_after_cleanup": installed,
        "retained_non_clerk_support": ["nomic-embed-text:latest"],
        "removed_models": REMOVED,
        "aborted_unqualified_downloads": {
            "qwen3:4b": "official 2.5 GB pull exceeded the 10-minute bound before registration; no model retained",
            "phi4-mini": "official 2.5 GB pull was stopped at the operator's cleanup request before qualification; no model retained",
        },
        "disk_free_bytes_after_cleanup": usage.free,
        "admission_rule": "Only models with a complete reproducible r15-v2 pass are admitted as clerks; vendor pages and downloads alone never qualify a model.",
    }
    OUT.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "admitted": admitted, "installed": installed, "free_bytes": usage.free}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
