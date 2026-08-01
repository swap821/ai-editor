#!/usr/bin/env python3
"""Promote organ 40 only after a current-tip live Docker proof passes twice."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"
ARTIFACT_PATH = REPO_ROOT / "release" / "phase4" / "organ40-live-proof-92d871616ce6.json"


def main() -> int:
    artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    tip = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
    ).strip()
    assert artifact["all_passed"] is True
    assert artifact["tip_sha"] == tip
    assert len(artifact["checks"]) == 2
    assert all(check["exit_code"] == 0 for check in artifact["checks"])
    assert all("4 passed" in check["pytest_summary"] for check in artifact["checks"])

    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    row = next(item for item in ledger if int(item["organ_id"]) == 40)
    old_blockers = list(row.get("known_blockers") or [])
    residual = [
        blocker
        for blocker in old_blockers
        if "Phase 4 absolute residual" not in blocker
    ]
    assert len(residual) < len(old_blockers), "organ 40 residual was not present"
    artifact_rel = ARTIFACT_PATH.relative_to(REPO_ROOT).as_posix()
    evidence = {
        "description": (
            f"Current-tip Docker Desktop live proof on {tip}: {artifact_rel}; "
            "tests/test_executor_integration.py passed 4 tests before and after "
            "docker compose executor restart, with real isolation, trace, timeout, "
            "and missing-service assertions."
        ),
        "commit_sha": tip,
        "proof_level": "live",
    }
    row["live_evidence"] = [
        item for item in (row.get("live_evidence") or []) if item.get("commit_sha") != tip
    ] + [evidence]
    row["known_blockers"] = residual
    row["status"] = "green"
    row["last_verified_sha"] = tip
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"organ_id": 40, "status": "green", "tip_sha": tip, "artifact": artifact_rel}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
