#!/usr/bin/env python
"""CSS canon lint — mechanize the Design-System Law for the frontend renovation.

This guards the renovatable product CSS against the two most load-bearing laws of
`.aios/state/FRONTEND_RENOVATION_BLUEPRINT.md` §2 (the Design-System Law):

  (1) PAINT-TRAP LAW (most load-bearing). A rule with `backdrop-filter` MUST NOT
      animate a PAINT property (`transition`/`animation` on, or `@keyframes`
      touching, any of: box-shadow | border | border-color | background |
      background-color | top | left | right | bottom). On a blurred element this
      re-rasters the glass + its shadow blur EVERY FRAME (~9 FPS on the probe
      machine). Flares belong on a dedicated NON-blurred child overlay; focus
      states toggle the static `--rim-top` var; sweeps/meters animate
      transform/opacity only. (See blueprint §2.2 law 1, §7.)

  (2) OFF-CANON COLOR. A hardcoded hex (#rrggbb / #rgb) or rgba()/rgb() literal
      that DUPLICATES a canon `:root` token value from superbrain.css must be
      `var(--token)` instead — never a re-typed equivalent (blueprint §2 / §2.1).
      We also flag the blueprint's explicitly-named Wave-0 off-canon literals
      (the indigo `#6366f1`, the off-canon panel bg `rgba(7,9,14,0.82)`, and the
      wrong glass recipe `blur(16px) saturate(1.4)` — canon is
      `blur(14px) saturate(140%) brightness(1.08)`).

The canon token VALUES are read live from superbrain.css `:root` (the source of
truth) so this lint never drifts from the tokens it enforces.

SCOPE — the SUPERBRAIN RENOVATION surfaces only:
  frontend/src/workbench/*.css
  frontend/src/styles/*.css
  frontend/src/*.css
  frontend/src/components/*.css
  (frontend/src/superbrain/superbrain.css is FROZEN and is never scanned.)

Canon governs the SUPERBRAIN renovation, NOT the classic ?ui=classic fallback nor
DEAD stylesheets. Two explicit, documented exclusions keep the lint focused on
real superbrain debt (see DEAD_FILES_EXCLUDED and CLASSIC_LEGACY_RULE_EXCLUSIONS):
  • DEAD files (imported nowhere; classes unused in JSX) — excluded whole-file,
    flagged for a later operator removal decision, not restyled.
  • The classic-only `@keyframes approvalGlow` rule in the live-global index.css —
    suppressed by identity (the rest of index.css stays governed), because only
    App.jsx (the classic fallback) consumes it; the superbrain faces use the
    non-paint-trap `.approval-actions` instead.

Usage:
  python tools/check_css_canon.py                 # scan the renovatable set
  python tools/check_css_canon.py --check FILE...  # scan explicit files
Exit code 1 if any violation is found; 0 otherwise.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# ── Locate the repo root (this file lives in <root>/tools/) ──────────────────
ROOT = Path(__file__).resolve().parent.parent
CANON_CSS = ROOT / "frontend" / "src" / "superbrain" / "superbrain.css"

# Globs (relative to ROOT) defining the renovatable set. superbrain.css is under
# a different dir, so it can never be matched here — but we ALSO hard-exclude it.
RENOVATABLE_GLOBS = (
    "frontend/src/workbench/*.css",
    "frontend/src/styles/*.css",
    "frontend/src/*.css",
    "frontend/src/components/*.css",
)
FROZEN_NEVER_SCAN = (ROOT / "frontend" / "src" / "superbrain" / "superbrain.css").resolve()

# ── SCOPE: govern the SUPERBRAIN RENOVATION surfaces, not the classic fallback ──
# The Design-System Law (blueprint §2) is the canon of the SUPERBRAIN UI — the
# official frontend (`SuperbrainApp` at no flag, `SuperbrainShell` at ?ui=shell).
# It does NOT govern:
#   (a) the classic IDE fallback at ?ui=classic (`App.jsx`), a deliberately
#       separate look the operator keeps as a legacy escape hatch; nor
#   (b) DEAD stylesheets that are imported nowhere and whose classes appear in no
#       JSX (verified by import-graph + className grep). Those are flagged for a
#       later operator removal decision, not restyled to canon.
# So the canon lint is SCOPED to the renovation surfaces below. The exclusions are
# explicit + documented so the lint keeps catching REAL superbrain violations and
# only steps aside for surfaces canon was never meant to police.

# (b) DEAD files — imported nowhere; classes used in no JSX. Excluded WHOLE-FILE
# from both the default scan and an explicit --check (they are not a renovation
# surface). Flagged for removal; do NOT restyle. Re-audit before deleting.
DEAD_FILES_EXCLUDED = {
    (ROOT / "frontend" / "src" / "styles" / "App.css").resolve(),
    (ROOT / "frontend" / "src" / "styles" / "design-system.css").resolve(),
    (ROOT / "frontend" / "src" / "styles" / "nexgen-3d.css").resolve(),
    (ROOT / "frontend" / "src" / "styles" / "nexgen-layout.css").resolve(),
}

# (a) CLASSIC-LEGACY rule exclusions — index.css IS live-global (imported by
# main.jsx for every face), so it stays governed for real superbrain violations.
# But its single flagged rule, `@keyframes approvalGlow`, is a CLASSIC-ONLY
# artifact: it is referenced solely by App.jsx (the ?ui=classic fallback); the
# superbrain faces use `.approval-actions` (approval-safety-net.css), an explicit
# non-paint-trap. So we suppress that ONE rule by identity (not the whole file),
# keeping the global token/reset layer under canon governance.
# Map: resolved-file-path → tuple of substrings; a violation line containing any
# substring for its file is suppressed (with a one-line scope note).
CLASSIC_LEGACY_RULE_EXCLUSIONS = {
    (ROOT / "frontend" / "src" / "index.css").resolve(): (
        "@keyframes approvalGlow",
    ),
}

# Paint properties that, when animated on a backdrop-filtered element, re-blur
# every frame. (Sub-properties like border-top-color collapse to these stems.)
PAINT_PROPS = (
    "box-shadow",
    "border-color",
    "border",            # any border shorthand / longhand that carries color
    "background-color",
    "background",
    "top",
    "left",
    "right",
    "bottom",
)

# Blueprint §2.1 / §5 explicitly-named off-canon literals to flag even though they
# are NOT exact duplicates of a canon token (they are the Wave-0 conformance targets).
NAMED_OFFCANON = {
    "#6366f1": "off-canon indigo accent — use var(--accent) (#5ce1e6); the ONE accent is cyan, never indigo",
    "rgba(7,9,14,0.82)": "off-canon panel background — use var(--bg-panel) per the GLASS RECIPE",
}

# The wrong glass recipe (canon is blur(14px) saturate(140%) brightness(1.08)).
# Matched loosely on the backdrop-filter value: any saturate < ~1.5 expressed as a
# bare multiplier (1.4) instead of 140%, or a blur radius other than 14px.
CANON_BLUR_PX = 14
GLASS_RECIPE_HINT = "canon GLASS RECIPE is `backdrop-filter: blur(14px) saturate(140%) brightness(1.08)`"


# ── Color normalization ──────────────────────────────────────────────────────
def _norm_hex(h: str) -> str:
    """#RGB / #RRGGBB → lowercase #rrggbb."""
    h = h.lower().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "#" + h


def _norm_rgba(call: str) -> str | None:
    """rgba(...)/rgb(...) → canonical 'r,g,b,a' (alpha defaults to 1) for value
    comparison. Whitespace removed; alpha trimmed of trailing zeros."""
    m = re.match(r"rgba?\(([^)]*)\)", call, re.IGNORECASE)
    if not m:
        return None
    parts = [p.strip() for p in re.split(r"[,\s/]+", m.group(1).strip()) if p.strip()]
    if len(parts) < 3:
        return None
    r, g, b = parts[0], parts[1], parts[2]
    a = parts[3] if len(parts) >= 4 else "1"
    # Normalize alpha "0.50" -> "0.5", "1.0" -> "1".
    try:
        af = float(a)
        a = ("%g" % af)
    except ValueError:
        pass
    return f"{r},{g},{b},{a}"


def parse_canon_tokens(css_text: str) -> dict[str, str]:
    """Read `--token: <color>;` declarations from superbrain.css :root and index
    them by NORMALIZED color value → token name (so a literal can be looked up)."""
    by_value: dict[str, str] = {}
    # Grab the :root block(s).
    for root_block in re.findall(r":root\s*\{([^}]*)\}", css_text, re.DOTALL):
        for name, raw in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", root_block):
            val = raw.strip()
            hexm = re.fullmatch(r"#[0-9a-fA-F]{3,8}", val)
            rgbam = re.fullmatch(r"rgba?\([^)]*\)", val)
            if hexm:
                by_value[_norm_hex(val)] = name
            elif rgbam:
                norm = _norm_rgba(val)
                if norm:
                    by_value[norm] = name
    return by_value


# ── Block-level CSS scanning (brace-balanced rule extraction) ────────────────
_HEX_RE = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?(?:[0-9a-fA-F]{2})?\b")
_RGBA_RE = re.compile(r"rgba?\([^)]*\)", re.IGNORECASE)


def strip_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.DOTALL)


def line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def iter_rules(text: str):
    """Yield (selector, body, body_start_index) for each top-level/nested rule
    block. Simple brace matcher; good enough for our flat product CSS (it also
    yields @keyframes blocks and their inner frames as separate rules)."""
    depth = 0
    i = 0
    n = len(text)
    sel_start = 0
    while i < n:
        c = text[i]
        if c == "{":
            selector = text[sel_start:i].strip()
            # find matching close
            d = 1
            j = i + 1
            while j < n and d:
                if text[j] == "{":
                    d += 1
                elif text[j] == "}":
                    d -= 1
                j += 1
            body = text[i + 1:j - 1]
            yield selector, body, i + 1
            # recurse into body for nested @keyframes frames / nested rules
            yield from ((s, b, off + (i + 1)) for s, b, off in iter_rules(body))
            i = j
            sel_start = j
        elif c == "}":
            sel_start = i + 1
            i += 1
        else:
            i += 1


def _animates_paint_prop(decl_body: str) -> list[str]:
    """Return the paint props named inside transition:/animation: shorthands or
    explicit transition-property in this rule body."""
    hits: list[str] = []
    body_l = decl_body.lower()
    # Pull transition / transition-property / animation declarations.
    for prop in ("transition", "transition-property", "animation"):
        for m in re.finditer(rf"(?<![\w-]){prop}\s*:\s*([^;]+);?", body_l):
            val = m.group(1)
            for paint in PAINT_PROPS:
                # match the paint prop as a transitioned property token
                if re.search(rf"(?<![\w-]){re.escape(paint)}(?![\w-])", val):
                    # `border` would also fire on `border-color`; de-dup later.
                    hits.append(paint)
    return hits


def _keyframes_touch_paint(frame_bodies: str) -> list[str]:
    """Given the concatenated bodies of an @keyframes' frames, return the paint
    props it SETS (and thus animates)."""
    hits: list[str] = []
    body_l = frame_bodies.lower()
    for paint in PAINT_PROPS:
        if re.search(rf"(?<![\w-]){re.escape(paint)}\s*:", body_l):
            hits.append(paint)
    return hits


def _dedup_border(props: list[str]) -> list[str]:
    """If both 'border' and 'border-color' are present, keep the more specific."""
    s = set(props)
    if "border-color" in s and "border" in s:
        s.discard("border")
    return sorted(s)


# ── Per-file lint ─────────────────────────────────────────────────────────────
def lint_file(path: Path, canon_by_value: dict[str, str]) -> list[str]:
    violations: list[str] = []
    raw = path.read_text(encoding="utf-8")
    text = strip_comments(raw)
    rel = path.as_posix()

    # ---- 1) PAINT-TRAP ------------------------------------------------------
    # First collect which @keyframes touch paint, and their names.
    kf_paint: dict[str, list[str]] = {}
    for sel, body, off in iter_rules(text):
        m = re.match(r"@keyframes\s+([\w-]+)", sel.strip())
        if m:
            touched = _dedup_border(_keyframes_touch_paint(body))
            if touched:
                kf_paint[m.group(1)] = touched
                # A @keyframes that animates paint is itself reportable IF used by
                # a backdrop-filter element — checked at the using rule. But also
                # flag the keyframes outright as a latent paint animation.
                violations.append(
                    f"{rel}:{line_of(text, off)}: PAINT-TRAP (keyframes) "
                    f"@keyframes {m.group(1)} animates paint {touched} — "
                    f"if applied to a backdrop-filter element it re-blurs every frame; "
                    f"move to a non-blurred child overlay / transform-opacity only."
                )

    # Base selectors (e.g. `.forge-port`) that are backdrop-filtered AND carry a
    # paint TRANSITION — a state class on them (`.forge-port.is-flaring`) that
    # SETS those paint props is therefore animated-on-a-blurred-element too.
    blurred_with_paint_transition: dict[str, list[str]] = {}

    # Now the rules with backdrop-filter.
    for sel, body, off in iter_rules(text):
        if sel.strip().startswith("@"):
            continue
        body_l = body.lower()
        if "backdrop-filter" not in body_l:
            continue
        ln = line_of(text, off)
        # (a) transition/animation shorthand naming a paint prop directly
        direct = _dedup_border(_animates_paint_prop(body))
        if direct:
            for base in re.split(r"\s*,\s*", sel.strip()):
                blurred_with_paint_transition[base.strip()] = direct
            violations.append(
                f"{rel}:{ln}: PAINT-TRAP `{sel.strip()[:70]}` has backdrop-filter AND "
                f"transitions/animates paint {direct} — this re-blurs every frame "
                f"(blueprint §2.2 law 1). Toggle --rim-top / flare a non-blurred child instead."
            )
        # (b) animation: <name> where <name> is a paint-touching @keyframes
        for m in re.finditer(r"(?<![\w-])animation(?:-name)?\s*:\s*([^;]+);?", body_l):
            for kf_name, touched in kf_paint.items():
                if re.search(rf"(?<![\w-]){re.escape(kf_name.lower())}(?![\w-])", m.group(1)):
                    violations.append(
                        f"{rel}:{ln}: PAINT-TRAP `{sel.strip()[:70]}` has backdrop-filter AND "
                        f"runs @keyframes {kf_name} which animates paint {touched} — "
                        f"re-blurs every frame; move the flare to a non-blurred child overlay."
                    )

    # (c) state-class rules on a blurred+paint-transition base that SET paint
    #     props — these are the TARGET of the parent's transition, so they are
    #     animated on the blurred element (e.g. `.forge-port.is-flaring`).
    for sel, body, off in iter_rules(text):
        s = sel.strip()
        if s.startswith("@") or "{" in s:
            continue
        for base, trans_props in blurred_with_paint_transition.items():
            # state class = base + suffix on the SAME element (no descendant
            # combinator before the suffix): `.forge-port.is-flaring`, not
            # `.forge-port .child`.
            m = re.match(rf"^{re.escape(base)}([.:#][\w-]+)+$", s)
            if not m or s == base:
                continue
            set_props = _dedup_border(
                [p for p in PAINT_PROPS
                 if re.search(rf"(?<![\w-]){re.escape(p)}\s*:", body.lower())]
            )
            # only the props the parent actually transitions matter for the trap
            trapped = [p for p in set_props if p in trans_props]
            if trapped:
                violations.append(
                    f"{rel}:{line_of(text, off)}: PAINT-TRAP `{s[:70]}` statically sets paint "
                    f"{trapped} on `{base}` which is backdrop-filtered with a paint transition — "
                    f"the state-swap is animated on the blurred element, re-blurring every frame. "
                    f"Flare a non-blurred child overlay instead."
                )

    # ---- 2) OFF-CANON COLOR (+ named off-canon + glass recipe) --------------
    for sel, body, off in iter_rules(text):
        if sel.strip().startswith("@keyframes"):
            # still scan declarations inside frames for off-canon colors
            pass
        # scan declarations line-by-line for precise line numbers
        seg_start = off
        for line in body.split("\n"):
            lstripped = line.strip()
            abs_line = line_of(text, seg_start)
            seg_start += len(line) + 1
            if not lstripped or lstripped.startswith("--"):
                # skip token DEFINITIONS (var declarations) — those are allowed
                # only in :root of canon, but here in renovatable files a `--x:`
                # def is a local var; still, comparing it would be noise. Skip.
                continue

            # named off-canon literals (case/space-insensitive on the rgba form)
            ll_compact = re.sub(r"\s+", "", lstripped.lower())
            for lit, why in NAMED_OFFCANON.items():
                if re.sub(r"\s+", "", lit.lower()) in ll_compact:
                    violations.append(
                        f"{path.as_posix()}:{abs_line}: OFF-CANON COLOR literal `{lit}` — {why}."
                    )

            # exact-duplicate of a canon token value: hex
            for hexlit in _HEX_RE.findall(lstripped):
                tok = canon_by_value.get(_norm_hex(hexlit))
                if tok:
                    violations.append(
                        f"{path.as_posix()}:{abs_line}: OFF-CANON COLOR literal `{hexlit}` "
                        f"duplicates canon token {tok} — use var({tok})."
                    )
            # exact-duplicate of a canon token value: rgba/rgb
            for rgblit in _RGBA_RE.findall(lstripped):
                norm = _norm_rgba(rgblit)
                if norm and norm in canon_by_value:
                    tok = canon_by_value[norm]
                    violations.append(
                        f"{path.as_posix()}:{abs_line}: OFF-CANON COLOR literal `{rgblit}` "
                        f"duplicates canon token {tok} — use var({tok})."
                    )

            # glass-recipe drift on backdrop-filter declarations
            bf = re.search(r"backdrop-filter\s*:\s*([^;]+)", lstripped, re.IGNORECASE)
            if bf:
                val = bf.group(1).lower()
                blur_m = re.search(r"blur\(\s*(\d+(?:\.\d+)?)px\s*\)", val)
                sat_m = re.search(r"saturate\(\s*([0-9.]+%?)\s*\)", val)
                bad_blur = blur_m and float(blur_m.group(1)) != CANON_BLUR_PX
                bad_sat = sat_m and not sat_m.group(1).endswith("%")  # bare 1.4 not 140%
                if bad_blur or bad_sat:
                    detail = []
                    if bad_blur:
                        detail.append(f"blur({blur_m.group(1)}px)≠blur({CANON_BLUR_PX}px)")
                    if bad_sat:
                        detail.append(f"saturate({sat_m.group(1)}) should be percent (140%)")
                    violations.append(
                        f"{path.as_posix()}:{abs_line}: OFF-CANON GLASS `backdrop-filter: "
                        f"{bf.group(1).strip()}` [{', '.join(detail)}] — {GLASS_RECIPE_HINT}."
                    )

    # Classic-legacy rule exclusions: drop violations whose message names a rule
    # that canon does not govern on this live-global file (e.g. the classic-only
    # `@keyframes approvalGlow` in index.css). The file stays scanned for all
    # other (superbrain-relevant) violations.
    suppress = CLASSIC_LEGACY_RULE_EXCLUSIONS.get(path.resolve())
    if suppress:
        violations = [v for v in violations if not any(s in v for s in suppress)]

    return violations


# ── File discovery ────────────────────────────────────────────────────────────
def discover_renovatable() -> list[Path]:
    seen: dict[str, Path] = {}
    for g in RENOVATABLE_GLOBS:
        for p in ROOT.glob(g):
            rp = p.resolve()
            if rp == FROZEN_NEVER_SCAN:
                continue
            if rp in DEAD_FILES_EXCLUDED:
                continue  # not a renovation surface — flagged for removal, not restyling
            seen[rp.as_posix()] = p
    return [seen[k] for k in sorted(seen)]


def main(argv: list[str]) -> int:
    if not CANON_CSS.exists():
        print(f"ERROR: canon source of truth not found: {CANON_CSS}", file=sys.stderr)
        return 2
    canon_by_value = parse_canon_tokens(CANON_CSS.read_text(encoding="utf-8"))
    if not canon_by_value:
        print(f"ERROR: parsed 0 canon tokens from {CANON_CSS}", file=sys.stderr)
        return 2

    if argv and argv[0] == "--check":
        files = [Path(a) for a in argv[1:]]
        if not files:
            print("ERROR: --check needs at least one FILE", file=sys.stderr)
            return 2
    else:
        files = discover_renovatable()

    all_violations: list[str] = []
    scanned = 0
    for f in files:
        if not f.exists():
            print(f"WARN: skipping missing file {f}", file=sys.stderr)
            continue
        if f.resolve() == FROZEN_NEVER_SCAN:
            print(f"WARN: refusing to scan FROZEN canon {f}", file=sys.stderr)
            continue
        if f.resolve() in DEAD_FILES_EXCLUDED:
            print(
                f"WARN: skipping DEAD (off-scope) {f.as_posix()} — imported nowhere; "
                f"flagged for removal, not canon-governed (re-audit before deleting)",
                file=sys.stderr,
            )
            continue
        scanned += 1
        all_violations.extend(lint_file(f, canon_by_value))

    if all_violations:
        print("CSS CANON VIOLATIONS — the Design-System Law (blueprint §2) is broken:\n")
        for v in all_violations:
            print(f"  ✗ {v}")
        print(
            f"\n{len(all_violations)} violation(s) across {scanned} file(s). "
            f"Canon tokens loaded: {len(canon_by_value)} from superbrain.css :root."
        )
        return 1

    print(
        f"css-canon OK — {scanned} renovatable file(s) clean against "
        f"{len(canon_by_value)} canon tokens (superbrain.css frozen, never scanned)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
