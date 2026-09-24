# GAGOS physical embodiment — accessibility and operator-surface evidence

Date: 2026-09-24  
Branch: `codex/frontend-physical-embodiment`  
Viewport: 1280×720  
Surface: disposable local Vite preview, then the dev-only physical gallery

## Root product surface

The loaded root exposed these named controls in the accessibility tree:

- `Skip to the chat`
- `Account identity status. Open the account panel.`
- `Guided` and `Expert / Mirror`, with `aria-pressed` state
- `Talk to GAGOS` textbox
- `Hold to speak to GAGOS`
- `Mute GAGOS voice`
- disabled `Send` while the request field is empty
- `Emergency stop`
- `Inspect emergency stop`: `Details`
- `Try again`

The skip control was activated through the page and moved focus to the
`Talk to GAGOS` input. Expert / Mirror changed its pressed state and exposed
the operational mirror controls. Emergency-stop details opened with an
expanded disclosure and exposed `Refresh`, the `Reason` textbox, and
`Close details`. This is keyboard/DOM interaction evidence, not a claim that
a human screen-reader session has been completed.

The browser reported no console errors. It did report the existing
`THREE.Clock` deprecation and repeated `GL_CLOSE_PATH_NV` ReadPixels GPU-stall
warnings; those warnings are recorded rather than hidden and keep hardware
performance acceptance open.

The inspected loaded-scene artifact is
[gagos-physical-accessibility-1280x720.png](gagos-physical-accessibility-1280x720.png).

## Deterministic physical gallery

The dev-only gallery exposed an accessible `Quality` combobox with Low,
Medium, and High options; a `Reduced motion` checkbox; and 21 named fixture
buttons. The selected `Resting / ready` fixture was announced as pressed. The
browser changed the combobox to High and checked Reduced motion; the resulting
DOM state reported `quality=high` and `reduced=true`.

The visual state was captured and inspected at
[gagos-physical-gallery-accessibility-1280x720.png](gagos-physical-gallery-accessibility-1280x720.png).
The capture shows the selected resting organism, inspector values, the quality
control, the reduced-motion control, and the full named fixture matrix.

After the gallery accessibility seam was strengthened, a fresh
`127.0.0.1:5187/?physical-gallery=1` inspection exposed a
`role=status` / `aria-live=polite` / `aria-atomic=true` announcement.
Selecting `Bounded worker burst with terminal receipts` changed the announcement
to `Selected Bounded worker burst with terminal receipts. Quality High. Full
motion enabled.`; checking Reduced motion changed it to `Selected Bounded worker
burst with terminal receipts. Quality High. Reduced motion enabled.`. This
proves the gallery's DOM live-region update, not a human screen-reader session.

## Boundaries

This evidence is limited to one local browser viewport and a DOM/accessibility
tree inspection. It does not establish full screen-reader semantics, touch
gesture success, operator visual approval, three-person human validation,
product-hardware performance, a persistent WebGL resource trend, or a live
backend-driven worker cycle. The gallery is a development inspection route and
is not the production root.
