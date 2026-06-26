# P3-2 Typography Lens — Design Spec

> Scope: the fifth sub-project of the 132-finding superbrain micro-detail renovation.
> Source: `.aios/state/RECOVERED_micro_detail_findings.md`, `typography` section.
> Work location: `GAG demo/gag-orchestrator/` lab.
> Port to product: deferred until the lab WIP snapshot is verified (same as sound/interaction/glass/motion lenses).

## Goal

Apply the remaining Fable typography findings in the GAG lab so the HUD's type system is consistent, legible, and truthful. The lens touches only CSS and one string constant; it changes no geometry, motion, or palette.

## Background

The recovered audit listed 19 typography findings. Several were already absorbed by parallel lab work:

| Finding | Status | Where fixed |
|---|---|---|
| Panel-heading live digits lack tabular figures | Fixed | `.panel-heading h3` has `font-variant-numeric: tabular-nums` |
| Topbar numeral tracking too loose | Fixed | `.system-summary strong` has `letter-spacing: normal` |
| Topbar label/value pairs center-aligned | Fixed | `.system-summary span` uses `align-items: baseline` |
| Region-pin tracking off-token / digits tracked | Fixed | `.region-pin` uses `letter-spacing: 0.12em`; `.region-pin strong` resets to normal |
| Hero title re-centers on mode switch | Fixed | `.core-readout h2` has `font-variant-numeric: tabular-nums` |
| Agent name/state center-aligned | Fixed | `.agent-info strong` uses `align-items: baseline` |

The remaining findings form a coherent typography lens:

1. **Global `case` feature pollutes mixed-case text.** `html { font-feature-settings: "case" 1, "cv05" 1; }` raises punctuation to cap-height on every element, which looks wrong next to lowercase Inter copy. The `case` feature should apply only to all-caps roles.
2. **`--text-3` is below the legibility floor.** At 10px on `#010307`, `rgba(120,130,150,0.38)` yields ~1.6:1 contrast. Raise alpha to `0.48` (~2.0:1). The same issue compounds in `.region-pin-graph em` where `opacity: 0.6` on `--text-2` produces an effective ~0.36 alpha.
3. **Approval panel uses off-scale sizes and trackings.** `.approval-title` uses `0.22em`, `.approval-summary` is `12.5px`, and `.approval-actions button` is `10.5px`/`0.18em` — the only half-pixel sizes and ad-hoc trackings in the file. Normalize to the established integer scale and the single `0.12em` mono-caps tracking token.
4. **Secure button flips case register.** The shield renders `TAMPER`/`HOLD` (caps) but `Supervised` (sentence case) in the same slot, breaking the all-caps topbar discipline. Change to `SUPERVISED` and add `letter-spacing: 0.08em` to match the 11px caps scale.
5. **Section-label weight drift.** `.eyebrow` is `font-weight: 510` while identical 10px mono caps labels (`.objective-head`, `.agent-heading span`, `.terminal-log span`) default to `400`. Unify at `510`.

## Architecture

Changes are confined to two files:

- `GAG demo/gag-orchestrator/src/app/globals.css` — token fixes, feature-settings scoping, weight/tracking/size normalizations.
- `GAG demo/gag-orchestrator/src/components/ui/SuperbrainHUD.tsx` — secure-button label string.

No new modules, no new dependencies, no public API changes.

## Detailed changes

### 1. Scope the `case` OpenType feature to caps roles

- Change `html { font-feature-settings: "case" 1, "cv05" 1; }` to `html { font-feature-settings: "cv05" 1; }`.
- Add a grouped rule for caps roles with both features (because `font-feature-settings` replaces, it does not merge):
  ```css
  .system-summary,
  .eyebrow,
  .build-tag,
  .core-sub,
  .command-field label,
  .source-name strong,
  .approval-title {
    font-feature-settings: "case" 1, "cv05" 1;
  }
  ```

### 2. Raise `--text-3` and the pin-graph em opacity

- `--text-3: rgba(120, 130, 150, 0.38)` → `rgba(120, 130, 150, 0.48)`.
- `.region-pin-graph em { opacity: 0.6; }` → `opacity: 0.8;`.

### 3. Normalize approval-panel type scale

- `.approval-title { letter-spacing: 0.22em; }` → `letter-spacing: 0.12em;`.
- `.approval-summary { font-size: 12.5px; }` → `font-size: 13px;`.
- `.approval-actions button { font-size: 10.5px; letter-spacing: 0.18em; }` → `font-size: 11px; letter-spacing: 0.12em;`.

### 4. Unify secure-button case

- In `SuperbrainHUD.tsx`, change the default shield label from `'Supervised'` to `'SUPERVISED'`.
- In `globals.css`, add `letter-spacing: 0.08em;` to `.secure-button`.

### 5. Unify section-label weight

- Add `font-weight: 510;` to `.objective-head`, `.agent-heading span`, and `.terminal-log span`.

## Behaviors under test

This is a pure CSS/label lens; no new unit tests are required. The verification plan is:

- Lab test suite passes with zero new failures.
- Lab golden images remain byte-identical (typography changes are sub-pixel and should not alter screenshots).
- Lint passes on the two touched files.
- A quick grep confirms the six off-token values are gone: `0.22em`, `12.5px`, `10.5px`, `0.18em`, `Supervised` (as visible label), and the global `"case" 1` on `html`.

## Error handling / edge cases

- `font-feature-settings` is applied to elements that already declare it in only one place (the `html` rule). Moving it to a selector list is safe because no other rule in the file sets `font-feature-settings`.
- The secure-button label change must not affect the `title` tooltip or the screen-reader-only `role="status"` span, which intentionally use sentence-case explanations.
- Approval-panel size changes are small (<1px–1.5px); the panel's layout has enough slack that no wrapping or overflow is expected.

## Visual / canon impact

- Palette and texture canon are untouched.
- No new animations or layout shifts.
- The changes improve legibility and typographic consistency without altering the HUD's visual identity.

## Definition of done

- [ ] `globals.css` changes applied and lint-clean.
- [ ] `SuperbrainHUD.tsx` secure-button label updated to `SUPERVISED`.
- [ ] Lab tests pass (`npm test`).
- [ ] Golden images unchanged.
- [ ] Lab commit with a clear message referencing this spec.
- [ ] Product port deferred; noted in RESUME.

## Next step

Invoke the `writing-plans` skill to produce a step-by-step implementation plan for this spec.
