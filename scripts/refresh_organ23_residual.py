#!/usr/bin/env python3
"""Replace Organ 23's stale machine-capability wording with current truth."""

from __future__ import annotations

import json
from pathlib import Path


LEDGER = Path(__file__).resolve().parents[1] / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"
OLD_MARKER = "Outside-machine / no Docker / no Ollama / frozen spine / browser-session residuals remain"
NEW = (
    "cloud, frozen-spine, browser-session, and human-red-team residuals remain; "
    "local Docker and Ollama evidence is available where recorded."
)


def main() -> int:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    row = next(item for item in ledger if int(item["organ_id"]) == 23)
    blockers = list(row.get("known_blockers") or [])
    matches = [blocker for blocker in blockers if OLD_MARKER in blocker]
    assert len(matches) == 1, f"expected one stale Organ 23 blocker, found {len(matches)}"
    row["known_blockers"] = [blocker.replace(OLD_MARKER, NEW) for blocker in blockers]
    LEDGER.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    print("organ 23 residual refreshed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
