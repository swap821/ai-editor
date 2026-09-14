#!/usr/bin/env python3
"""Flip organs whose evidence is current and whose conditions all pass.

THE FLIP IS A HYPOTHESIS, NOT A CONCLUSION
------------------------------------------
`verify_organ_twelve_conditions.py` only re-reads organs that are ALREADY green
-- `if record.status == "green"` gates both the proof-gap scan and the mechanical
checks. A yellow organ is therefore exempt from the very audit that would catch a
bad claim, and flipping one is what SUBJECTS it to that audit.

So this writes the flip and nothing else. It proves nothing on its own; the
verifier run immediately afterwards is the proof, and any organ it rejects must
be flipped back with the reason recorded. Run:

    python scripts/promote_verified_organs.py --apply
    python scripts/verify_organ_twelve_conditions.py     # must be rc=0

WHAT QUALIFIES, AND WHY EACH CLAUSE IS THERE
--------------------------------------------
* **status is yellow** -- greens are left alone; this tool only promotes.
* **not spine-attested** -- `evidence_digest` covers `status` for the organs the
  operator signed, so flipping one invalidates a signature only they can
  replace. Skipped by construction.
* **every condition PASS / N/A / MET** -- the twelve conditions are what green
  means. One unresolved condition is one too many.
* **no residual other than the Phase-4 attach note** -- that note says
  "Remaining: Phase 5 green flip only after adversarial re-read", i.e. it is a
  marker that the organ is READY, not a reason it is blocked. Any OTHER blocker
  (browser session, Outside-machine, no Ollama, operator attestation, staleness)
  is a real residual and disqualifies the row. This clause is the one doing the
  work: it is what keeps organs 20/44/46/48/49/51 yellow.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"
ATTESTATION_PATH = REPO_ROOT / ".aios" / "state" / "spine_release_attestation.json"

#: The marker `phase4_attach_ledger.py` writes when an organ holds tip-stamped
#: live evidence and is waiting only on the adversarial re-read.
READY_MARKER = "Phase 4 absolute: live evidence attached at tip"

#: Prefixes that count as a settled condition.
SETTLED = ("PASS", "N/A", "MET")


def _spine_attested_organ_ids() -> set[int]:
    try:
        data = json.loads(ATTESTATION_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {int(x) for x in (data.get("organ_ids") or [])}


def qualifies(row: dict, attested: set[int]) -> tuple[bool, str]:
    """Does this row qualify for promotion? Returns (ok, reason-if-not)."""
    oid = int(row["organ_id"])
    if oid in attested:
        return False, "spine-attested; only the operator may change its status"
    if row.get("status") != "yellow":
        return False, f"status is {row.get('status')}, not yellow"

    verdicts = row.get("condition_verdicts") or {}
    if not verdicts:
        return False, "no condition verdicts recorded"
    unsettled = sorted(k for k, v in verdicts.items() if not str(v).startswith(SETTLED))
    if unsettled:
        return False, f"unsettled conditions: {', '.join(unsettled)}"

    residuals = [
        b for b in (row.get("known_blockers") or []) if READY_MARKER not in str(b)
    ]
    if residuals:
        return False, f"named residual: {str(residuals[0])[:110]}"
    return True, ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the flip")
    args = parser.parse_args(argv)

    attested = _spine_attested_organ_ids()
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))

    promoted: list[int] = []
    held: list[tuple[int, str]] = []

    for row in ledger:
        ok, why = qualifies(row, attested)
        if ok:
            promoted.append(int(row["organ_id"]))
            if args.apply:
                row["status"] = "green"
                # The readiness marker has served its purpose; leaving it would
                # read as an open residual on a green row.
                row["known_blockers"] = [
                    b
                    for b in (row.get("known_blockers") or [])
                    if READY_MARKER not in str(b)
                ]
        elif row.get("status") == "yellow":
            held.append((int(row["organ_id"]), why))

    print(f"promotable: {len(promoted)} -> {promoted}")
    print(f"held back:  {len(held)}")
    for oid, why in held:
        print(f"   #{oid:>2} {why}")

    if args.apply:
        LEDGER_PATH.write_text(
            json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(
            "\nledger updated -- now run verify_organ_twelve_conditions.py; "
            "any organ it rejects must be flipped back."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
