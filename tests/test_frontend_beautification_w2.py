"""Regression guards for FRONTEND_BEAUTIFICATION_BLUEPRINT wave 2."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COUNCIL_DASHBOARD_CSS = ROOT / "frontend" / "src" / "workbench" / "CouncilDashboard.css"
GAGOS_CHROME_CSS = ROOT / "frontend" / "src" / "workbench" / "GagosChrome.css"
SUPERBRAIN_CSS = ROOT / "frontend" / "src" / "superbrain" / "superbrain.css"


def test_wave2_materializes_council_panel_shell_without_redefining_hud_enter() -> None:
    council_css = COUNCIL_DASHBOARD_CSS.read_text(encoding="utf-8")
    chrome_css = GAGOS_CHROME_CSS.read_text(encoding="utf-8")
    superbrain_css = SUPERBRAIN_CSS.read_text(encoding="utf-8")

    assert "@keyframes hud-enter" in superbrain_css
    assert "@keyframes hud-enter" not in council_css
    assert "@keyframes hud-enter" not in chrome_css
    assert "border-radius: 14px;" in council_css
    assert "animation: hud-enter 450ms var(--ease-out-expo) 80ms both;" in council_css
    assert "0 0 0 1px rgba(123, 245, 251, 0.22)" in council_css
    assert "inset 0 1px 0 rgba(123, 245, 251, 0.28)" in council_css


def test_wave2_forms_are_etched_controls_with_bespoke_action_focus() -> None:
    css = COUNCIL_DASHBOARD_CSS.read_text(encoding="utf-8")

    assert "appearance: none;" in css
    assert "inset 0 0 18px rgba(123, 245, 251, 0.05)" in css
    assert ".council-dashboard__originate textarea::placeholder," in css
    assert ".council-dashboard__origin-files::placeholder" in css
    assert ".council-dashboard__originate button:focus-visible," in css
    assert ".council-dashboard__decision-actions button:focus-visible," in css
    assert ".council-dashboard__recovery button:focus-visible" in css
    assert "box-shadow: 0 0 0 3px rgba(123, 245, 251, 0.18), 0 0 24px rgba(123, 245, 251, 0.26);" in css


def test_wave2_mission_cards_empty_state_and_danger_glow() -> None:
    css = COUNCIL_DASHBOARD_CSS.read_text(encoding="utf-8")

    assert "inset 0 0 16px rgba(123, 245, 251, 0.04)" in css
    assert "0 0 0 1px rgba(123, 245, 251, 0.32), 0 0 24px rgba(123, 245, 251, 0.18)" in css
    assert "border: 1px dashed rgba(123, 245, 251, 0.26);" in css
    assert ".council-dashboard__badge.is-danger," in css
    assert ".council-dashboard__verdict.is-danger" in css
    assert "box-shadow: 0 0 18px rgba(248, 113, 113, 0.18);" in css
    assert ".council-dashboard__badge.is-ok" in css
    assert ".council-dashboard__badge.is-warn" in css
    ok_warn_section = css.split(".council-dashboard__risk-dot.is-danger", maxsplit=1)[0]
    assert "box-shadow: 0 0 18px rgba(248, 113, 113, 0.18);" not in ok_warn_section


def test_wave2_swarm_entrance_and_reduced_motion_paths() -> None:
    council_css = COUNCIL_DASHBOARD_CSS.read_text(encoding="utf-8")
    chrome_css = GAGOS_CHROME_CSS.read_text(encoding="utf-8")

    assert ".gagos-send.is-busy svg { animation: none; }" not in chrome_css
    assert "animation: hud-enter 400ms var(--ease-out-expo) 0ms both;" in chrome_css
    assert ".council-dashboard { animation: none; }" in council_css
    assert ".swarm-hud { animation: none; }" in chrome_css
