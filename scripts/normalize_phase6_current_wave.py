#!/usr/bin/env python3
"""Correct historical Phase-5 bookkeeping after a new organ is promoted."""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "release" / "phase6" / "organ23-shortfall.json"


def main() -> int:
    doc = json.loads(OUT.read_text(encoding="utf-8"))
    phase5 = doc["phase5_absolute"]
    phase5["flipped_green_this_wave"] = sorted(
        set(phase5["flipped_green_this_wave"]) | {40}
    )
    phase5["never_flipped"] = [oid for oid in phase5["never_flipped"] if oid != 40]
    OUT.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"flipped_green_this_wave": phase5["flipped_green_this_wave"], "never_flipped": phase5["never_flipped"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
