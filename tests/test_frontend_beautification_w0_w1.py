"""Regression guards for FRONTEND_BEAUTIFICATION_BLUEPRINT waves 0-1."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKENS_CSS = ROOT / "frontend" / "src" / "styles" / "tokens.css"
GAGOS_CHROME_CSS = ROOT / "frontend" / "src" / "workbench" / "GagosChrome.css"
COUNCIL_DASHBOARD_CSS = ROOT / "frontend" / "src" / "workbench" / "CouncilDashboard.css"
CYBER_CURSOR_CSS = (
    ROOT / "frontend" / "src" / "superbrain" / "components" / "ui" / "CyberCursor.module.css"
)
BOOT_SEQUENCE_CSS = (
    ROOT / "frontend" / "src" / "superbrain" / "components" / "ui" / "BootSequence.module.css"
)
CSS_CANON_PATH = ROOT / "tools" / "check_css_canon.py"

_spec = importlib.util.spec_from_file_location("check_css_canon", CSS_CANON_PATH)
assert _spec and _spec.loader
css_canon = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(css_canon)


def test_wave0_defines_poster_tetrad_tokens() -> None:
    css = TOKENS_CSS.read_text(encoding="utf-8")

    assert "--neon-cyan:   #7bf5fb;" in css
    assert "--neon-purple: #b06eff;" in css
    assert "--neon-green:  #54f0a0;" in css
    assert "--neon-orange: #ff7e40;" in css


def test_wave0_reduced_motion_disables_mic_pseudo_pulse() -> None:
    css = GAGOS_CHROME_CSS.read_text(encoding="utf-8")

    assert ".gagos-mic.is-listening, .gagos-mic.is-listening::after { animation: none; }" in css


def test_wave1_removes_off_tetrad_chrome_literals() -> None:
    workbench_css = (
        GAGOS_CHROME_CSS.read_text(encoding="utf-8")
        + COUNCIL_DASHBOARD_CSS.read_text(encoding="utf-8")
    )
    cyber_cursor_css = CYBER_CURSOR_CSS.read_text(encoding="utf-8")
    boot_sequence_css = BOOT_SEQUENCE_CSS.read_text(encoding="utf-8")

    assert "rgba(96, 165, 250" not in workbench_css
    assert "#5ce1e6" not in cyber_cursor_css.lower()
    assert "92, 225, 230" not in cyber_cursor_css
    assert "#5ee1ff" not in boot_sequence_css.lower()
    assert "94, 225, 255" not in boot_sequence_css
    assert "#2fe6c8" not in boot_sequence_css.lower()


def test_wave1_canon_guard_scans_superbrain_component_css() -> None:
    assert "frontend/src/superbrain/components/**/*.css" in css_canon.RENOVATABLE_GLOBS
