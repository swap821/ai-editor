"""Operator-authorized swarm build (explicitly delegated, 2026-06-13).

Drives the WORKER SWARM (``swarm=true``) to build a real multi-file Python
toolkit in ``training_ground/``, approving ONLY within the exact same hard
allowlist as ``curriculum_evidence_driver`` (create/edit ``training_ground/*.py``
and ``pytest training_ground/<file>`` verifies; anything else is rejected and the
run aborts, fail-closed). It reuses that driver's audited helpers verbatim.

Earned autonomy is ON: as verified writes accrue past the threshold, the
``create_file:training_ground/*.py`` class graduates to ``earned`` and later
writes auto-grant without a human pause — the bridge firing on real evidence.
"""
from __future__ import annotations

import sys

import requests

from curriculum_evidence_driver import (
    BASE,
    MAX_REPLAYS,
    TURN_TIMEOUT_S,
    check_allowlist,
    parse_sse,
    reject_and_abort,
)

TASK = (
    "Build a small text-utilities toolkit in the training_ground directory. "
    "Split it into independent subtasks, one deliverable each, that separate "
    "workers can build without talking to each other. "
    "Subtask 1: create training_ground/wordcount.py with a function "
    "count_words(text: str) -> int returning the count of whitespace-separated "
    "words, and create training_ground/test_wordcount.py with pytest tests "
    "(cover the empty string returning 0). "
    "Subtask 2: create training_ground/titlecase.py with a function "
    "to_title(text: str) -> str that capitalizes the first letter of each word, "
    "and create training_ground/test_titlecase.py with pytest tests for it."
)


def autonomy() -> dict:
    try:
        return requests.get(f"{BASE}/api/v1/development/autonomy", timeout=20).json()
    except requests.RequestException:
        return {}


def main() -> None:
    session = "swarm-build-demo"
    before = autonomy()
    print(f"earned-autonomy: enabled={before.get('enabled')} "
          f"min_successes={before.get('min_successes')} summary={before.get('summary')}\n")

    tokens: list[str] = []
    approvals = 0
    earned_grants = 0
    for replay in range(MAX_REPLAYS):
        body = {
            "messages": [{"role": "user", "content": [{"text": TASK}]}],
            "modelId": "auto",
            "sessionId": session,
            "approvalTokens": tokens,
            "swarm": True,
        }
        print(f"--- swarm turn (replay {replay}) ---")
        resp = requests.post(f"{BASE}/api/generate", json=body, stream=True, timeout=TURN_TIMEOUT_S)
        resp.raise_for_status()
        paused = None
        finished = False
        for event, data in parse_sse(resp):
            if event == "step":
                tool = str(data.get("tool", ""))
                role = str(data.get("role", ""))
                typ = str(data.get("type", ""))
                out = str(data.get("output", ""))
                if tool == "swarm":
                    print(f"  caste: {role}")
                elif typ == "earned_autonomy":
                    earned_grants += 1
                    print(f"  *** EARNED-AUTONOMY auto-grant [{role}]: {data.get('command')}")
                elif out.startswith(("[VERIFY PASS]", "[VERIFY FAIL]", "[VERIFY SKIPPED]")):
                    print(f"    [{role}] {out[:90]}")
            elif event == "human_required":
                paused = data
                break
            elif event == "error":
                sys.exit(f"turn error: {data}")
            elif event == "done":
                finished = True
        if finished and paused is None:
            print("\n=== swarm DONE ===")
            break
        if paused is None:
            print("  (truncated; retrying)")
            continue
        ok, why = check_allowlist(paused)
        token = paused.get("input", {}).get("approvalToken")
        if not ok or not token:
            reject_and_abort(token, session, why, paused)
        approvals += 1
        print(f"  approved[{replay}] (delegated, allowlist): {why}")
        tokens = [token]
    else:
        print(f"\n(stopped after {MAX_REPLAYS} replays)")

    after = autonomy()
    print("\n=== earned-autonomy ledger AFTER ===")
    print("summary:", after.get("summary"))
    for entry in after.get("entries", []):
        print(f"  {entry['status']:>9}  {entry['action_type']}:{entry['target_shape']}  "
              f"succ={entry['success_count']} streak={entry['streak']}")
    print(f"\nhuman approvals (delegated): {approvals} | earned-autonomy auto-grants: {earned_grants}")


if __name__ == "__main__":
    main()
