#!/usr/bin/env python3
"""Replace organ 46's stale no-Ollama wording with its actual residual."""

from __future__ import annotations

import json
from pathlib import Path

LEDGER = Path(__file__).resolve().parents[1] / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"
OLD_MARKER = "no Ollama"
NEW = (
    "Outside-machine / human-red-team residual — local Ollama is available and "
    "the clerk qualification suite passed for five candidates, but constitutional "
    "learning still lacks a human red-team or equivalent live external cohort."
)


def main() -> int:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    row = next(item for item in ledger if int(item["organ_id"]) == 46)
    blockers = list(row.get("known_blockers") or [])
    assert any(OLD_MARKER.lower() in blocker.lower() for blocker in blockers)
    row["known_blockers"] = [
        NEW if OLD_MARKER.lower() in blocker.lower() else blocker
        for blocker in blockers
    ]
    LEDGER.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    print("organ 46 residual refreshed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
