#!/usr/bin/env python
"""Texture/asset-canon guard — reject edits to the operator's hand-authored ASSETS.

Operator re-scope (2026-06-19): the BROAD 3D-canon freeze is REMOVED. The lab
(`GAG demo/gag-orchestrator`) is an UNRESTRICTED build space and the whole 3D scene
under `components/canvas/` — geometry, anatomy, nerve positions, shaders, structure,
motion — is now FREE to evolve toward a 100%-working alive-brain. The ONLY sacred
canon is his **palette + textures** ("that's what I imagined; everything else doesn't
matter"): the color palette is guarded by `check_css_canon.py`; this tool now guards
ONLY his texture/GLB asset files (brain GLB + cortex/cosmic texture maps + grain
overlay), in both the product mirror and the lab. See [[fidelity-is-sacred-ui-laws]].

Everything that is CODE — the 3D scene, HUD, tokens, lib, organs, seams — is freely
editable. Product is byte-synced from the lab via `npm run port`; the operator's
`:5173` look at port time is the gate there, not this tripwire.

Usage:
  python tools/check_canon_frozen.py            # check `git diff` (working tree vs HEAD)
  python tools/check_canon_frozen.py --staged   # check staged changes (pre-commit)
  python tools/check_canon_frozen.py --check P1 P2 ...   # test specific paths
  python tools/check_canon_frozen.py --allow-canon       # break-glass: permit AUTHORIZED,
       # operator-reviewed texture/asset edits (he signed off on before/after in HIS
       # browser). Default (no flag) HARD-blocks asset edits = the accidental/
       # unauthorized-edit tripwire is always on for his imagined palette + texture.
Exit code 1 if a protected asset changed WITHOUT --allow-canon; 0 otherwise.
"""
from __future__ import annotations

import subprocess
import sys

# Frozen ROOTS = the operator's TEXTURE/ASSET identity ONLY (operator re-scope
# 2026-06-19: "palette + texture is what I imagined; everything else doesn't
# matter"). The 3D scene CODE (geometry/shaders/structure) is NO LONGER frozen —
# the lab is unrestricted. Only his hand-authored asset files remain sacred; the
# color palette itself is guarded separately by check_css_canon.py.
FROZEN_ROOTS = (
    # His visual ASSETS: brain GLB + hand-painted cortex/cosmic textures + grain
    # overlay, in both the product mirror and the lab. (Touch via --allow-canon.)
    "frontend/public/models/brain.glb",
    "frontend/public/textures/brain/",
    "frontend/public/grain.svg",
    "GAG demo/gag-orchestrator/public/models/",
    "GAG demo/gag-orchestrator/public/textures/",
)

# No special whitelist needed: the freeze is scoped to his asset files, so all
# CODE (the 3D scene, HUD, lib, tokens, seams) is allowed by simply not being a
# protected asset.
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
        print("TEXTURE-CANON VIOLATION — these are the operator's hand-authored texture/GLB assets")
        print("(his imagined palette + texture — the one sacred canon):")
        for p in frozen_hits:
            print(f"  ✗ {p}")
        print("\nThis is the accidental/unauthorized-edit tripwire. The 3D scene CODE is FREE now;")
        print("only his asset files are guarded. If you ARE deliberately changing a texture/asset")
        print("with the operator's sign-off (before/after in HIS browser), re-run with --allow-canon.")
        return 1
    if frozen_hits and allow_canon:
        print("TEXTURE-CANON BREAK-GLASS (--allow-canon) — permitting AUTHORIZED asset edits:")
        for p in frozen_hits:
            print(f"  ● {p}")
        print("\nREMINDER: palette + textures are the operator's imagination — the one thing that")
        print("matters most. Change them only with his eye on before/after, and keep a backup.")
        return 0
    print(f"texture-canon OK — {len(paths)} changed path(s), no protected assets touched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
