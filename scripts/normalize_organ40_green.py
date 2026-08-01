#!/usr/bin/env python3
"""Remove non-blocking residual prose from organ 40 after green promotion."""

from __future__ import annotations

import json
from pathlib import Path

LEDGER_PATH = Path(__file__).resolve().parents[1] / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"


def main() -> int:
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    row = next(item for item in ledger if int(item["organ_id"]) == 40)
    assert row["status"] == "green"
    row["known_blockers"] = []
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    print("organ 40 green row normalized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
