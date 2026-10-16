#!/usr/bin/env python3
"""Gate a learning red-team reel report (plan Phase 8b).

    python scripts/learning_reel_gate.py reel.json

Exit 1 if any runnable STRUCTURAL mission was ``breached`` or ``not_reached``.

* ``breached`` -- a control failed.
* ``not_reached`` -- the instrument never reached the control it measures, so
  the run says nothing about it. "Not reached" is never counted as defended.

Behavioural missions are scored on a real model and are ``blocked`` without
one; blocked is never a pass, and a CI runner with no model cannot make it
one, so they are reported and not gated here. A structural mission declared
blocked (one not yet buildable, e.g. RT-11 without Docker) is reported too.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.learning_redteam_runner import MISSIONS_BY_KEY  # noqa: E402

FAILING = ("breached", "not_reached")


def failures(report: dict) -> list[str]:
    """The verdicts that fail the gate, as printable lines."""
    out: list[str] = []
    seen = set()
    for verdict in report.get("verdicts", []):
        key = verdict.get("mission")
        seen.add(key)
        mission = MISSIONS_BY_KEY.get(key)
        if mission is None:
            out.append(f"{key}: not a mission this runner defines")
            continue
        if mission.kind != "structural" or mission.blocked_reason is not None:
            continue
        if verdict.get("outcome") in FAILING:
            out.append(f"{key} {verdict.get('outcome')}: {verdict.get('reason')}")
    runnable = {
        k
        for k, m in MISSIONS_BY_KEY.items()
        if m.kind == "structural" and m.blocked_reason is None
    }
    for key in sorted(runnable - seen):
        out.append(f"{key}: missing from the report (it was never run)")
    return out


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__)
        return 2
    report = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    print(json.dumps(report.get("counts", {})))
    failed = failures(report)
    for line in failed:
        print(f"FAIL {line}")
    if failed:
        return 1
    print("every runnable structural mission held")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
