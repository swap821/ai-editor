"""Refresh organ 40's named residual after a bounded local Docker attempt.

This keeps the ledger honest when Docker Desktop is available but the
current-tip control-plane image cannot be built within the evidence budget.
It never changes status or creates live evidence.
"""

from __future__ import annotations

import json
from pathlib import Path


LEDGER = Path(__file__).resolve().parents[1] / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"
OLD = "no Docker — Docker Desktop daemon unavailable on this Windows host (npipe dockerDesktopLinuxEngine); historical CI Docker isolation evidence retained, not tip-restamped"
NEW = "Phase 4 absolute residual — Docker Desktop daemon is available, but the current-tip control-plane image build exceeded the 20-minute local evidence bound; no tip-valid organ 40 integration proof was produced"


def main() -> int:
    records = json.loads(LEDGER.read_text(encoding="utf-8"))
    organ = next(item for item in records if item["organ_id"] == 40)
    blockers = organ["known_blockers"]
    assert OLD in blockers, "organ 40 blocker already changed; refusing a blind rewrite"
    blockers[blockers.index(OLD)] = NEW
    LEDGER.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    print("organ 40 residual refreshed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
