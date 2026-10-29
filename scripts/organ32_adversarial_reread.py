#!/usr/bin/env python3
"""Record organ 32's adversarial re-read of 2026-10-29 in the ledger.

The Phase 4 note on organ 32 read "Remaining: Phase 5 green flip only after
adversarial re-read of all 12 conditions". This is that re-read's record. It
writes no status: promotion is scripts/promote_verified_organs.py's, and the
proof is scripts/verify_organ_twelve_conditions.py run afterwards.

What it records (docs/ONE_GATEWAY.md, "2026-10-29"):

* C9 was FAIL on two residuals, both discharged:
  - "universality unmeasured / not enforced": refused by construction
    (aios/core/model_calls.py), with only the gateway able to open an entrance
    and only the adapters able to reach a model;
  - "the switch outside the freeze": defined in aios/security/limits.py under
    release/section-viii/2026-10-29-gateway-enforcement-behind-the-freeze.md.
* The claim now rests on aios/core/model_calls.py and aios/security/limits.py,
  so they join the organ's production_entrypoints: a change to either stales
  its evidence. The tests that prove it join its focused_tests, so C6/C9 run
  them.
* C10-C12 are restated from the row's own evidence, which must already be
  attached at the tip that has those entrypoints (run after
  phase4_live_evidence.py and phase4_attach_ledger.py).

Idempotent: run twice, the row is the same.
"""

from __future__ import annotations

import json
from pathlib import Path

LEDGER = (
    Path(__file__).resolve().parents[1] / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"
)
DISCHARGED = (
    "UNIVERSALITY ENFORCED, FOUR SITES NOT DRIVEN (2026-10-29",
    "ENFORCEMENT SWITCH OUTSIDE THE FREEZE (2026-10-29)",
)
ENTRYPOINTS = ("aios/core/model_calls.py", "aios/security/limits.py")
FOCUSED = (
    "tests/test_gateway_enforcement.py",
    "tests/test_model_calls.py",
    "tests/test_crag_model_calls_gated.py",
    "tests/test_route_picker_gateway.py",
)
C9 = (
    "PASS - adversarial re-read 2026-10-29 (docs/ONE_GATEWAY.md '2026-10-29'; "
    "release/section-viii/2026-10-29-gateway-enforcement-behind-the-freeze.md). "
    "Both residuals that held it FAIL are discharged: universality is refused by "
    "construction, not measured (only the provider adapters can reach a model; "
    "each records before it sends; observe() refuses a production call that came "
    "through no entrance; only the gateway can open an entrance), and the switch "
    "and its exemptions are defined behind the freeze. Attacks tried: a call passed "
    "off as a tool's through a tools/ helper (closed: judged by the full stack), a "
    "faked entrance (pinned: gateway_scope/scoped_iter only in gateway.py), an SDK "
    "reached through an adapter's private client or an endpoint string (pinned), "
    "pseudo-filename frames counted as repo code (fixed), a typo turning refusing "
    "off (pinned), frontend calls straight to a provider (none), in-process "
    "inference (embeddings, voice: nothing sent), approved commands (sandbox "
    "--network none). Failure-path tests in this organ's own suites: "
    "tests/test_gateway_enforcement.py, tests/test_crag_model_calls_gated.py, "
    "tests/test_runtime_intelligence_gateway.py. Not driven by the inventory, "
    "gated by construction and refused otherwise: self_analysis_agent.propose_fix, "
    "local_workforce/service._execute_advisory_job, worker reasoning "
    "(unit-tested). Read by one reviewer (the agent); the verifier executes the tests."
)


def main() -> int:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    row = next(item for item in ledger if int(item["organ_id"]) == 32)

    row["known_blockers"] = [
        b
        for b in (row.get("known_blockers") or [])
        if not any(str(b).startswith(prefix) for prefix in DISCHARGED)
    ]
    entrypoints = list(row.get("production_entrypoints") or [])
    row["production_entrypoints"] = entrypoints + [
        p for p in ENTRYPOINTS if p not in entrypoints
    ]
    focused = list(row.get("focused_tests") or [])
    row["focused_tests"] = focused + [p for p in FOCUSED if p not in focused]

    sha = str(row.get("last_verified_sha") or "")
    live = [e for e in (row.get("live_evidence") or []) if e.get("commit_sha") == sha]
    assert sha and live, "attach live evidence at this tip first"
    verdicts = dict(row.get("condition_verdicts") or {})
    verdicts["C9"] = C9
    verdicts["C10"] = (
        f"PASS - live evidence at {sha} (the route, and an ungated production "
        "call refused before it was sent): "
        + str(live[-1].get("description", ""))[:240]
    )
    verdicts["C11"] = f"PASS - last_verified_sha={sha}"
    verdicts["C12"] = (
        f"PASS - {sha} must be an ancestor of HEAD (--require-sha-ancestry); after "
        "a rebase merge the evidence is re-gathered at master's tip."
    )
    row["condition_verdicts"] = verdicts

    # LF: the ledger is hash-pinned (tests/test_spine_release.py).
    LEDGER.write_text(
        json.dumps(ledger, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print("organ 32: adversarial re-read recorded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
