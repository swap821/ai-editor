#!/usr/bin/env python
"""Canon-freeze guard — reject edits to the operator's inviolable superbrain canon.

The frozen set is DERIVED FROM the port manifest
(`GAG demo/gag-orchestrator/tools/port-to-frontend.mjs`): every file `npm run port`
regenerates is byte-identical-to-lab, so a product-side edit is silently destroyed on
the next port. Those product mirrors + their lab sources + the operator's visual assets
are his authored soul ([[superbrain-core-theme]], [[fidelity-is-sacred-ui-laws]]) and
must NEVER be edited by the frontend renovation.

The LEGAL SEAM is product-authored (NOT in the manifest) and is explicitly allowed:
  frontend/src/superbrain/SuperbrainApp.jsx   (mount/routing — authored in product)
  frontend/src/superbrain/SuperbrainShell.jsx (the children seam ports plug into)

Everything else the renovation needs (frontend/src/workbench, components, styles,
App.jsx, main.jsx) is outside the frozen roots and always allowed.

Usage:
  python tools/check_canon_frozen.py            # check `git diff` (working tree vs HEAD)
  python tools/check_canon_frozen.py --staged   # check staged changes (pre-commit)
  python tools/check_canon_frozen.py --check P1 P2 ...   # test specific paths
Exit code 1 if any frozen path is modified; 0 otherwise.
"""
from __future__ import annotations

import subprocess
import sys

# Frozen ROOTS (a changed path under one of these is frozen unless whitelisted).
FROZEN_ROOTS = (
    "frontend/src/superbrain/",                 # the ported canon mirror (clobbered by port)
    "frontend/public/models/brain.glb",         # his GLB
    "frontend/public/grain.svg",
    "frontend/public/textures/brain/",          # his hand-painted cortex
    "GAG demo/gag-orchestrator/src/",           # the LAB canon source = the soul
    "GAG demo/gag-orchestrator/public/",        # lab assets
)

# The legal seam: product-authored files under a frozen root that ARE editable
# (verified absent from the port manifest's FILES list).
WHITELIST = (
    "frontend/src/superbrain/SuperbrainApp.jsx",
    "frontend/src/superbrain/SuperbrainShell.jsx",
)


def is_frozen(path: str) -> bool:
    p = path.replace("\\", "/").strip().strip('"')
    if p in WHITELIST:
        return False
    return any(p == root or p.startswith(root) for root in FROZEN_ROOTS)


def changed_paths(staged: bool) -> list[str]:
    cmd = ["git", "diff", "--name-only"]
    if staged:
        cmd.append("--cached")
    out = subprocess.run(cmd, capture_output=True, text=True, check=False).stdout
    return [line for line in out.splitlines() if line.strip()]


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--check":
        paths = argv[1:]
    else:
        paths = changed_paths(staged="--staged" in argv)
    frozen_hits = [p for p in paths if is_frozen(p)]
    if frozen_hits:
        print("CANON FREEZE VIOLATION — these files are the operator's inviolable canon:")
        for p in frozen_hits:
            print(f"  ✗ {p}")
        print("\nFix: author canon changes in the lab (GAG demo/gag-orchestrator) + `npm run port`,")
        print("or move the change to the legal seam (SuperbrainShell.jsx / workbench / components).")
        return 1
    print(f"canon-freeze OK — {len(paths)} changed path(s), none frozen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
