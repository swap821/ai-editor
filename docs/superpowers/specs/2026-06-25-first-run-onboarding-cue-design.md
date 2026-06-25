# First-run onboarding cue — design spec

**Date:** 2026-06-25  
**Scope:** P3-3 from `RENOVATION_PLAN.md` — a single, dismissible, canon-styled hint for a new operator.  
**Constraint:** No change to the cherished 3D superbrain scene; only the command chrome in `GagosChrome` is touched.

---

## Goal

A brand-new operator opening the product sees a gorgeous voyaging brain and one input with no sense of what to type first, where the organs are, or how to open the forge. A single first-run hint converts wow-factor into orientation without adding friction or persistent UI chrome.

## Approach (chosen)

**Approach A — native placeholder + dismissible chip**

- Show a ghost example directive as the command input's native `placeholder` whenever the conversation has no messages.
- Render a small, canon-styled chip beside/below the input that names `▣ ORGANS` and the forge shortcut.
- The placeholder clears naturally on focus/typing (browser-native behavior).
- The chip stays until the user clicks its dismiss `X`.
- Dismissal is remembered across restarts via `localStorage`.

### Why not B or C

- **B (ghost overlay text inside the input)** keeps the example visible while typing, but it fights the real input value for screen space and is harder to make accessible.
- **C (hint row below the input)** is clearer but consumes more real estate and feels heavier than a single first-run nudge.

## Persistence

- Key: `aios-onboarding-hint-dismissed`
- Values: `"true"` when dismissed; absent otherwise.
- Dismissal is per-browser/profile. A future "Reset hint" control can delete the key.
- The hint is also suppressed automatically once the operator has sent at least one message or a turn exists in the current session, so returning users who already interacted never see it.

## UI details

- **Placeholder text:** `"Try: 'scaffold a FastAPI /health endpoint'"`
  - Single-line, fits in the input, uses sentence case, ends without punctuation.
- **Chip text:** `"▣ ORGANS  ·  forge (Ctrl+\`)"`
  - Uses the existing `▣` organ glyph from the canon HUD.
  - Keyboard shortcut is read from the existing `toggleWorkbench` hotkey if available; otherwise falls back to `Ctrl+\``.
- **Dismiss button:** small `×` with `aria-label="Dismiss onboarding hint"`.
- **Reduced motion:** chip fade-in respects `prefers-reduced-motion` via the existing global media block.

## Accessibility

- The chip container has `role="note"` and `aria-label="Onboarding hint"`.
- Dismiss `×` is a real `<button>` with visible `:focus-visible` ring.
- Placeholder is exposed natively by the browser for screen readers.
- No keyboard trap: `Tab` moves through the chip's dismiss button and back to the input normally.

## Files touched

- `frontend/src/workbench/GagosChrome.jsx` — render hint when `messages.length === 0` and not dismissed.
- `frontend/src/workbench/GagosChrome.css` — chip styling using canon tokens.
- `frontend/src/workbench/GagosChrome.onboarding.test.tsx` (new) — presence, dismissal, and localStorage behavior.

## Testing plan

1. `npm run typecheck` — no new type errors.
2. `npm test -- --run GagosChrome.onboarding` —
   - chip and placeholder render on first run;
   - clicking dismiss removes chip and writes localStorage;
   - reloading state hides chip;
   - sending a message hides the placeholder.
3. `npm run build` — exit 0.
4. Manual check in the operator's browser that the palette matches canon (`tools/check_css_canon.py`).

## Out of scope

- Multi-step tutorial.
- Onboarding milestone state machine.
- Changes to `SuperbrainHUD.tsx`, the 3D scene, or organ surface materials.
- Mobile-responsive rework of the command bar (already addressed by P1-7).
