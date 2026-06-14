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
  python tools/check_canon_frozen.py --allow-canon       # break-glass: permit AUTHORIZED,
       # FIDELITY-reviewed canon-elevation edits (operator signed off on before/after
       # screenshots in HIS browser). Default (no flag) still HARD-blocks canon = the
       # accidental/unauthorized-edit tripwire is always on.
Exit code 1 if a frozen path changed WITHOUT --allow-canon; 0 otherwise.
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
    if staged:
        out = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            capture_output=True, text=True, check=False,
        ).stdout
        return [line for line in out.splitlines() if line.strip()]
    # Tracked CONTENT changes via `git diff --name-only` — this honors git's EOL
    # normalization, so a port's CRLF<->LF re-copy of a frozen file (byte-identical
    # content) is NOT flagged. Plus UNTRACKED additions from status (a brand-new
    # file under a frozen root IS a real breach `git diff` would miss).
    tracked = subprocess.run(
        ["git", "diff", "--name-only"], capture_output=True, text=True, check=False,
    ).stdout.splitlines()
    status = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True, check=False,
    ).stdout.splitlines()
    paths: list[str] = [l for l in tracked if l.strip()]
    for line in status:
        if line.startswith("??"):  # untracked only (content changes covered above)
            p = line[3:]
            paths.append(p.strip().strip('"'))
    return paths


def main(argv: list[str]) -> int:
    allow_canon = "--allow-canon" in argv
    if "--check" in argv:
        flags = {"--check", "--staged", "--allow-canon"}
        paths = [a for a in argv if a not in flags]
    else:
        paths = changed_paths(staged="--staged" in argv)
    frozen_hits = [p for p in paths if is_frozen(p)]
    if frozen_hits and not allow_canon:
        print("CANON FREEZE VIOLATION — these files are the operator's cherished 3D canon:")
        for p in frozen_hits:
            print(f"  ✗ {p}")
        print("\nThis is the accidental/unauthorized-edit tripwire. If this IS an authorized,")
        print("FIDELITY-reviewed canon-elevation change (operator signed off on before/after")
        print("screenshots in HIS browser, against a canon tag + goldens), re-run with")
        print("--allow-canon. Otherwise: author in the lab (GAG demo/gag-orchestrator) +")
        print("`npm run port`, or move the change to a non-canon seam (SuperbrainShell.jsx /")
        print("workbench / components).")
        return 1
    if frozen_hits and allow_canon:
        print("CANON BREAK-GLASS (--allow-canon) — permitting AUTHORIZED canon-elevation edits:")
        for p in frozen_hits:
            print(f"  ● {p}")
        print("\nFIDELITY REMINDER (the laws still hold): enhance, never replace · his GLB +")
        print("textures untouched · before/after screenshots reviewed in HIS browser · canon")
        print("tag + goldens captured for rollback.")
        return 0
    print(f"canon-freeze OK — {len(paths)} changed path(s), none frozen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
