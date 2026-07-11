from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GAGOS_CSS = ROOT / "frontend" / "src" / "workbench" / "GagosChrome.css"
GAGOS_JSX = ROOT / "frontend" / "src" / "workbench" / "GagosChrome.jsx"
AIOS_ADAPTER = ROOT / "frontend" / "src" / "superbrain" / "lib" / "aiosAdapter.ts"


def _block(css: str, selector: str) -> str:
    start = css.index(selector)
    open_brace = css.index("{", start)
    close_brace = css.index("}", open_brace)
    return css[open_brace + 1 : close_brace]


def test_w3_status_chips_are_materialized_state_tokens() -> None:
    css = GAGOS_CSS.read_text(encoding="utf-8")

    pill = _block(css, ".gagos-pill {")
    assert "padding:" in pill
    assert "border-radius: 999px" in pill
    assert "max-width: 220px" in pill
    assert "background:" in pill
    assert "border:" in pill
    assert "box-shadow:" in pill

    assert ".gagos-pill--model" in css
    assert ".gagos-pill--model" in css and "var(--neon-purple)" in _block(css, ".gagos-pill--model {")
    assert ".gagos-pill--supervised" in css
    assert "var(--neon-green)" in _block(css, ".gagos-pill--supervised {")
    assert ".gagos-pill__main" in css and "text-overflow: ellipsis" in _block(css, ".gagos-pill__main {")
    assert ".gagos-pill__meta" in css and "opacity: 0.6" in _block(css, ".gagos-pill__meta {")

    mobile = css[css.index("@media (max-width: 640px)") :]
    assert ".gagos-pill { padding:" not in mobile


def test_w3_thinking_echo_is_visible_above_dock_and_reuses_typing_dots() -> None:
    jsx = GAGOS_JSX.read_text(encoding="utf-8")
    css = GAGOS_CSS.read_text(encoding="utf-8")

    assert "gagos-thinking-echo" in jsx
    assert "thinking…" in jsx
    assert 'className="gagos-typing"' in jsx

    echo = _block(css, ".gagos-thinking-echo {")
    assert "pointer-events: none" in echo
    assert "var(--neon-cyan)" in echo
    assert "animation:" not in echo


def test_w3_adapter_humanizes_redaction_markers_before_body_labels() -> None:
    source = AIOS_ADAPTER.read_text(encoding="utf-8")
    mirror_source = (ROOT / "frontend" / "src" / "superbrain" / "lib" / "aiosMirror.ts").read_text(encoding="utf-8")

    assert "BACKEND_REDACTION_MARKER_RE" in source
    assert "function humanizeRedactionMarkers" in source
    assert "(a sensitive value was withheld)" in source
    assert source.count("BACKEND_REDACTION_MARKER_RE") == 2

    assert "humanizeRedactionMarkers" in mirror_source
