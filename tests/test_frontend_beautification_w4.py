"""Regression guards for FRONTEND_BEAUTIFICATION_BLUEPRINT wave 4 (motion niceties).

Pattern-matches tests/test_frontend_beautification_w2.py and w3.py: plain
Path.read_text() + substring/regex assertions against the raw source. No JS
runtime execution here — behavior-level coverage (spin-on-manual-not-poll,
leaving-state timing, key-remount) lives in the *.test.tsx vitest files.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAGOS_CSS = ROOT / "frontend" / "src" / "workbench" / "GagosChrome.css"
GAGOS_JSX = ROOT / "frontend" / "src" / "workbench" / "GagosChrome.jsx"
COUNCIL_CSS = ROOT / "frontend" / "src" / "workbench" / "CouncilDashboard.css"
COUNCIL_JSX = ROOT / "frontend" / "src" / "workbench" / "CouncilDashboard.jsx"
AIOS_ADAPTER = ROOT / "frontend" / "src" / "superbrain" / "lib" / "aiosAdapter.ts"


def _block(css: str, selector: str) -> str:
    start = css.index(selector)
    open_brace = css.index("{", start)
    close_brace = css.index("}", open_brace)
    return css[open_brace + 1 : close_brace]


def _balanced_block(css: str, needle: str) -> str:
    """Like _block but brace-depth aware — for @keyframes blocks that contain
    their own nested `{ ... }` rules (e.g. `from { opacity: 1; }`)."""
    start = css.index(needle)
    open_brace = css.index("{", start)
    depth = 0
    i = open_brace
    while i < len(css):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                return css[open_brace + 1 : i]
        i += 1
    raise ValueError(f"unbalanced braces after {needle!r}")


def test_w4_1_verify_toast_has_authored_exit_with_reduced_motion_skip() -> None:
    css = GAGOS_CSS.read_text(encoding="utf-8")
    cog_bus = (ROOT / "frontend" / "src" / "workbench" / "hooks" / "useCognitionBus.js").read_text(encoding="utf-8")
    jsx = GAGOS_JSX.read_text(encoding="utf-8") + "\n" + cog_bus


    # Mirrored exit keyframe: opacity 1->0, translateY(0)->-6px.
    assert "@keyframes gagos-verify-out" in css
    out_kf = _balanced_block(css, "@keyframes gagos-verify-out")
    assert "opacity: 1" in out_kf
    assert "opacity: 0" in out_kf
    assert "translateY(0)" in out_kf
    assert "translateY(-6px)" in out_kf

    # A leaving sub-state selector wired to the exit animation.
    assert "--leaving" in css
    leaving_block = css[css.index("--leaving") :]
    assert "gagos-verify-out" in leaving_block[: leaving_block.index("}") + 200]

    # JS: a two-phase timer (leaving:true then null ~250ms later), reduced-motion
    # skips the delay and unmounts immediately.
    assert "leaving" in jsx
    assert "useReducedMotion" in jsx
    # Window widened 1800->2400 (reviewer, 2026-07-03): the correct
    # cross-environment two-phase timer (closure-array cleanup, not a property
    # on setTimeout's numeric browser return) is a few lines longer than the
    # first-cut version, pushing the 250ms delay just past 1800 chars. The
    # guard's intent — a 250ms two-phase timer AND a reducedMotion branch inside
    # the verify effect — is unchanged.
    verify_effect_start = jsx.index("event.type === 'verify'")
    verify_effect = jsx[verify_effect_start : verify_effect_start + 2400]
    assert "250" in verify_effect
    assert "reducedMotion" in verify_effect


def test_w4_2_manual_refresh_spin_never_fires_on_background_poll() -> None:
    jsx = COUNCIL_JSX.read_text(encoding="utf-8")
    css = COUNCIL_CSS.read_text(encoding="utf-8")

    assert "manualRefreshing" in jsx
    # The manual button's onClick must set it; the poll effect must not reference it.
    button_idx = jsx.index("aria-label=\"Refresh council reports\"")
    button_block = jsx[max(0, button_idx - 400) : button_idx + 100]
    assert "manualRefreshing" in button_block

    poll_idx = jsx.index("window.setInterval(() => {")
    poll_block = jsx[poll_idx : poll_idx + 300]
    assert "manualRefreshing" not in poll_block

    assert ".council-dashboard__icon-btn.is-refreshing svg" in css
    spin_block = _block(css, ".council-dashboard__icon-btn.is-refreshing svg {")
    assert "animation:" in spin_block
    assert "900ms" in spin_block
    assert "linear" in spin_block

    reduced = css[css.index("@media (prefers-reduced-motion: reduce)") :]
    assert ".council-dashboard__icon-btn.is-refreshing svg" in reduced


def test_w4_3_tone_changes_get_luminance_settle_transition_only() -> None:
    css = COUNCIL_CSS.read_text(encoding="utf-8")

    badge_verdict_base = _block(css, ".council-dashboard__badge,\n.council-dashboard__verdict {")
    assert "transition:" in badge_verdict_base
    assert "background" in badge_verdict_base
    assert "border-color" in badge_verdict_base
    assert "220ms" in badge_verdict_base

    risk_dot_base = _block(css, ".council-dashboard__risk-dot {")
    assert "transition:" in risk_dot_base
    assert "220ms" in risk_dot_base

    # A RED escalation must not be softened: no opacity/box-shadow entering the
    # transition list (transition only on background/border-color).
    assert "opacity" not in badge_verdict_base.split("transition:")[1].split(";")[0]
    assert "box-shadow" not in badge_verdict_base.split("transition:")[1].split(";")[0]


def test_w4_4_mission_detail_cross_fades_on_selection_change() -> None:
    jsx = COUNCIL_JSX.read_text(encoding="utf-8")
    css = COUNCIL_CSS.read_text(encoding="utf-8")

    assert 'key={selectedSummary.missionId}' in jsx
    # B3 added sibling dashboard views (Self-Analysis / Sovereign State) that
    # legitimately reuse the council-dashboard__detail class for the same
    # cross-fade treatment; the mission-key invariant applies to the MISSION
    # detail specifically, so check every occurrence for one carrying the key
    # instead of pinning the first occurrence in file order.
    detail_needle = 'className="council-dashboard__detail"'
    detail_starts = []
    cursor = jsx.find(detail_needle)
    while cursor != -1:
        detail_starts.append(cursor)
        cursor = jsx.find(detail_needle, cursor + 1)
    assert detail_starts
    assert any(
        "key={selectedSummary.missionId}" in jsx[max(0, idx - 200) : idx]
        for idx in detail_starts
    )

    assert "@keyframes council-detail-in" in css
    kf = _balanced_block(css, "@keyframes council-detail-in")
    assert "opacity" in kf
    assert "translateY(2px)" in kf

    detail_block = _block(css, ".council-dashboard__detail {")
    assert "animation:" in detail_block
    assert "council-detail-in" in detail_block
    assert "220ms" in detail_block

    reduced = css[css.index("@media (prefers-reduced-motion: reduce)") :]
    assert ".council-dashboard__detail { animation: none; }" in reduced


def test_w4_5_shared_redaction_marker_constant_is_exported_and_deduped() -> None:
    adapter_source = AIOS_ADAPTER.read_text(encoding="utf-8")
    jsx = GAGOS_JSX.read_text(encoding="utf-8")

    assert "export const BACKEND_REDACTION_MARKER_RE" in adapter_source
    # W3's guard pins count == 2 in aiosAdapter.ts; W4 must not add a third
    # textual occurrence of the identifier there.
    assert adapter_source.count("BACKEND_REDACTION_MARKER_RE") == 2

    # GagosChrome no longer defines its own local copy of the pattern.
    assert "const REDACTION_TOKEN =" not in jsx
    assert "BACKEND_REDACTION_MARKER_RE" in jsx
    assert "from '../superbrain/lib/aiosAdapter'" in jsx
