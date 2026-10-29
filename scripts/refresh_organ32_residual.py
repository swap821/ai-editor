#!/usr/bin/env python3
"""Replace organ 32's two 2026-10-12 universality blockers with its residual.

On 2026-10-29 the model-call ledger began refusing an ungated production call
(docs/ONE_GATEWAY.md, "2026-10-29"), and the inventory, driven with refusing
on, reached the sites it had missed. What is still open is said here, dated.
The organ stays yellow: its green flip waits on the adversarial re-read.
"""

from __future__ import annotations

import json
from pathlib import Path

LEDGER = (
    Path(__file__).resolve().parents[1] / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"
)
UNMEASURED = "UNIVERSALITY UNMEASURED (2026-10-12)"
NOT_ENFORCED = "UNIVERSALITY NOT ENFORCED (2026-10-12)"
ENFORCED = (
    "UNIVERSALITY ENFORCED, FOUR SITES NOT DRIVEN (2026-10-29, docs/ONE_GATEWAY.md "
    "'2026-10-29'): aios/core/model_calls.py refuses a production model call that "
    "came through no entrance before the adapter sends it (AIOS_GATEWAY_ENFORCE, on "
    "by default; a tools/ or scripts/ program's own process is exempt unless it is "
    "set to 1, and its calls are still recorded and judged), and "
    "tests/test_gateway_enforcement.py pins that only the provider adapters can "
    "reach a model. The inventory, driven with refusing on "
    "(release/one-gateway/inventory-2026-10-29.json), made 74 calls on 15 surfaces, "
    "all gated, and observed 21 of 29 candidate sites; 2 are not model calls and 2 "
    "have no production caller, each checked. Not driven: "
    "self_analysis_agent.propose_fix and local_workforce/service."
    "_execute_advisory_job, each of which wraps its client in a gateway adapter, and "
    "this organ's own aios/runtime/intelligence_gateway.py worker reasoning, pinned "
    "at unit level: the worker's restricted environment cannot be pointed at the "
    "inventory's fake model."
)
SWITCH = (
    "ENFORCEMENT SWITCH OUTSIDE THE FREEZE (2026-10-29): AIOS_GATEWAY_ENFORCE=0 "
    "turns refusing off. It is read in aios/config.py, not with the other egress "
    "guardrails in aios/security/limits.py, because aios/security/* is frozen to "
    "agents; moving it behind the freeze is a Section VIII proposal for the operator."
)


def main() -> int:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    row = next(item for item in ledger if int(item["organ_id"]) == 32)
    blockers = list(row.get("known_blockers") or [])
    assert any(b.startswith(UNMEASURED) for b in blockers), "already refreshed?"
    assert any(b.startswith(NOT_ENFORCED) for b in blockers), "already refreshed?"
    refreshed: list[str] = []
    for blocker in blockers:
        if blocker.startswith(UNMEASURED):
            refreshed.append(ENFORCED)
        elif blocker.startswith(NOT_ENFORCED):
            refreshed.append(SWITCH)
        else:
            refreshed.append(blocker)
    row["known_blockers"] = refreshed
    LEDGER.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    print("organ 32 residual refreshed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
