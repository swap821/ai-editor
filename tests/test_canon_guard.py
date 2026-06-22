"""Tests for the texture/asset-canon guard (tools/check_canon_frozen.py).

Operator re-scope (2026-06-19): the broad 3D-canon freeze was REMOVED. The 3D
scene CODE (components/canvas/**, shaders, structure) is now FREE — the lab is an
unrestricted build space. The guard is a default-deny tripwire on ONLY the
operator's hand-authored ASSET files (brain GLB + cortex/cosmic textures + grain
overlay), in both the product mirror and the lab. The color palette itself is
guarded separately by check_css_canon.py. The break-glass `--allow-canon` flag
permits AUTHORIZED, operator-reviewed asset edits. These pin both behaviours via
the `--check` path (no git needed).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_GUARD_PATH = Path(__file__).resolve().parents[1] / "tools" / "check_canon_frozen.py"
_spec = importlib.util.spec_from_file_location("check_canon_frozen", _GUARD_PATH)
assert _spec and _spec.loader
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

# The ONLY sacred canon now: his texture/GLB asset files.
FROZEN_GLB = "frontend/public/models/brain.glb"
FROZEN_TEXTURE = "frontend/public/textures/brain/diffuse.png"
FROZEN_GRAIN = "frontend/public/grain.svg"
LAB_FROZEN_TEXTURE = "GAG demo/gag-orchestrator/public/textures/cortex.png"

# FREE now (was frozen before the re-scope): all 3D scene CODE, in product + lab.
FREE_SCENE = "frontend/src/superbrain/components/canvas/SuperbrainScene.tsx"
LAB_FREE_SCENE = "GAG demo/gag-orchestrator/src/components/canvas/PostFX.tsx"
FREE_HUD = "frontend/src/superbrain/components/ui/SuperbrainHUD.tsx"


def test_is_frozen_identifies_only_the_texture_assets() -> None:
    assert guard.is_frozen(FROZEN_GLB)
    assert guard.is_frozen(FROZEN_TEXTURE)
    assert guard.is_frozen(FROZEN_GRAIN)
    assert guard.is_frozen(LAB_FROZEN_TEXTURE)


def test_3d_scene_code_is_now_free() -> None:
    # The re-scope: scene CODE (geometry/shaders/structure) is no longer frozen.
    assert not guard.is_frozen(FREE_SCENE)
    assert not guard.is_frozen(LAB_FREE_SCENE)


def test_non_canon_paths_are_free() -> None:
    assert not guard.is_frozen(FREE_HUD)
    assert not guard.is_frozen("frontend/src/superbrain/lib/aiosAdapter.ts")
    assert not guard.is_frozen("frontend/src/App.jsx")
    assert not guard.is_frozen("aios/api/main.py")


def test_asset_edit_blocked_by_default() -> None:
    """The tripwire: a texture/asset edit with no flag fails (exit 1)."""
    assert guard.main(["--check", FROZEN_TEXTURE]) == 1


def test_asset_edit_allowed_with_break_glass() -> None:
    """Authorized, operator-reviewed asset edit passes with --allow-canon."""
    assert guard.main(["--check", "--allow-canon", FROZEN_TEXTURE]) == 0


def test_scene_code_edit_always_passes() -> None:
    """Editing the 3D scene code (now free) passes without any flag."""
    assert guard.main(["--check", FREE_SCENE]) == 0


def test_break_glass_does_not_falsely_pass_when_nothing_frozen() -> None:
    """--allow-canon on a clean (non-asset) change set still reports OK, not break-glass."""
    assert guard.main(["--check", "--allow-canon", FREE_HUD]) == 0
