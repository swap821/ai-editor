"""Tests for the canon-freeze guard (tools/check_canon_frozen.py).

The guard is a default-deny tripwire on the operator's cherished 3D canon
(components/canvas/** + brain GLB/textures, in both the product mirror and the
lab). The break-glass `--allow-canon` flag permits AUTHORIZED, FIDELITY-reviewed
canon-elevation edits while keeping the default block as the accidental/
unauthorized-edit tripwire. These pin both behaviours via the `--check` path
(no git needed).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_GUARD_PATH = Path(__file__).resolve().parents[1] / "tools" / "check_canon_frozen.py"
_spec = importlib.util.spec_from_file_location("check_canon_frozen", _GUARD_PATH)
assert _spec and _spec.loader
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

CANON_SCENE = "frontend/src/superbrain/components/canvas/SuperbrainScene.tsx"
LAB_CANON = "GAG demo/gag-orchestrator/src/components/canvas/PostFX.tsx"
NON_CANON_HUD = "frontend/src/superbrain/components/ui/SuperbrainHUD.tsx"


def test_is_frozen_identifies_the_3d_canon() -> None:
    assert guard.is_frozen(CANON_SCENE)
    assert guard.is_frozen(LAB_CANON)
    assert guard.is_frozen("frontend/public/models/brain.glb")
    assert guard.is_frozen("frontend/public/textures/brain/diffuse.png")


def test_non_canon_paths_are_free() -> None:
    assert not guard.is_frozen(NON_CANON_HUD)
    assert not guard.is_frozen("frontend/src/superbrain/lib/aiosAdapter.ts")
    assert not guard.is_frozen("frontend/src/App.jsx")
    assert not guard.is_frozen("aios/api/main.py")


def test_canon_edit_blocked_by_default() -> None:
    """The tripwire: a canon edit with no flag fails (exit 1)."""
    assert guard.main(["--check", CANON_SCENE]) == 1


def test_canon_edit_allowed_with_break_glass() -> None:
    """Authorized, FIDELITY-reviewed canon edit passes with --allow-canon."""
    assert guard.main(["--check", "--allow-canon", CANON_SCENE]) == 0


def test_non_canon_edit_always_passes() -> None:
    assert guard.main(["--check", NON_CANON_HUD]) == 0


def test_break_glass_does_not_falsely_pass_when_nothing_frozen() -> None:
    """--allow-canon on a clean (non-canon) change set still reports OK, not break-glass."""
    assert guard.main(["--check", "--allow-canon", NON_CANON_HUD]) == 0
