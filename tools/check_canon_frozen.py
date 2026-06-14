#!/usr/bin/env python
"""Canon-freeze guard — reject edits to the operator's CORE DESIGN.

Operator-narrowed boundary (2026-06-14): the inviolable core is the **3D brain**
and the **deep-vast knowledge space** — the WebGL scene under `components/canvas/`
(brain, aura, nervous system, cortical signals, memory galaxy, cosmic background,
knowledge horizon, post-FX) plus his brain GLB + cortex/cosmic textures, in BOTH
the product mirror and the lab source. That is his authored soul
([[superbrain-core-theme]], [[fidelity-is-sacred-ui-laws]]) and must NEVER change.

Everything else is RENOVATABLE to embody the soul: the 2D HUD overlay
(`SuperbrainHUD` + chrome), tokens (`superbrain.css` / lab `globals.css`), the lib,
the workbench organs, and the seam files (SuperbrainApp/Shell.jsx). HUD/token edits
are authored lab-first and ported (the 3D scene is never touched in the lab either).

Usage:
  python tools/check_canon_frozen.py            # check `git diff` (working tree vs HEAD)
  python tools/check_canon_frozen.py --staged   # check staged changes (pre-commit)
  python tools/check_canon_frozen.py --check P1 P2 ...   # test specific paths
Exit code 1 if any frozen path is modified; 0 otherwise.
"""
from __future__ import annotations

import subprocess
import sys

# Frozen ROOTS = the operator's CORE DESIGN ONLY (operator-narrowed 2026-06-14):
# the 3D BRAIN and the deep-vast knowledge SPACE. The 2D HUD overlay
# (SuperbrainHUD etc.), tokens, lib, and chrome are now RENOVATABLE to embody the
# soul — only the 3D world below is inviolable. See [[superbrain-core-theme]].
FROZEN_ROOTS = (
    # The whole 3D scene: brain, accretion core, neural aura, nervous system,
    # cortical signals, cognitive grasp, memory galaxy, cosmic background,
    # knowledge horizon, post-FX, region pins — brain + background space.
    "frontend/src/superbrain/components/canvas/",
    "GAG demo/gag-orchestrator/src/components/canvas/",   # the LAB 3D scene source
    # His visual assets (brain GLB + hand-painted cortex + cosmic textures).
    "frontend/public/models/brain.glb",
    "frontend/public/textures/brain/",
    "frontend/public/grain.svg",
    "GAG demo/gag-orchestrator/public/models/",
    "GAG demo/gag-orchestrator/public/textures/",
)

# No special whitelist needed now: the freeze is scoped to the 3D world, so the
# HUD/lib/tokens/seams are allowed by simply not being under a frozen root.
WHITELIST: tuple[str, ...] = ()


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
