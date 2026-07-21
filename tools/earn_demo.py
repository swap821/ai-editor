"""Operator-authorized (2026-06-13): push the create_file:training_ground/*.py
class to EARNED via real verified single-agent turns (delegated approval, same
hard allowlist), then watch the bridge AUTO-GRANT the next write with ZERO human
approvals — earned autonomy firing on real evidence.
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

# curriculum_evidence_driver.py lives at the project root; this file lives
# in tools/, one level below.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from curriculum_evidence_driver import BASE, run_prompt


def cls_status():
    a = requests.get(f"{BASE}/api/v1/development/autonomy", timeout=20).json()
    entry = next(
        (x for x in a.get("entries", [])
         if x["action_type"] == "create_file" and x["target_shape"] == "training_ground/*.py"),
        {},
    )
    return a.get("summary"), entry


def main() -> None:
    print("BEFORE:", cls_status())
    for i in range(1, 6):
        prompt = (
            f"Create a file training_ground/test_proof{i}.py containing exactly one "
            f"pytest test function named test_proof{i} that asserts 1 + 1 == 2. "
            f"Create no other file."
        )
        result = run_prompt(prompt, session_id=f"earn-{i}")
        approvals = len(result.get("approvals", []))
        _, entry = cls_status()
        line = (f"turn {i}: outcome={result['outcome']} approvals={approvals} "
                f"-> status={entry.get('status')} streak={entry.get('streak')} "
                f"succ={entry.get('success_count')}")
        print(line)
        if approvals == 0 and entry.get("status") == "earned":
            print(f"  *** EARNED-AUTONOMY FIRED: turn {i}'s write applied with ZERO approvals.")
    print("AFTER:", cls_status())


if __name__ == "__main__":
    main()
