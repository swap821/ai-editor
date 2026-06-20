# GAGOS — Communication Surface + Home Decor (in-world)

- **Date:** 2026-06-20
- **Branch:** `feat/living-being-p1`
- **Status:** Approved design (operator sign-off 2026-06-20), pending spec review → implementation plan
- **Substrate:** the point-field being (`?being=points`), product frontend
- **Supersedes nothing** — this elevates the conversation + first-impression layer that the
  completed point-field organism (P0–P6) currently lacks.

## 1. Problem

The point-field organism itself is operator-approved ("working perfectly"). What drags the
experience down to "demo" is the **UI bolted onto it**, confirmed by frame-by-frame review of
the operator's 29-second recording (`20260620-0716-04`):

1. **The reply reads as a debug print.** `BrainstemIntake.jsx:713` renders the being's reply as a
   `<Billboard>` of `<Text>` floating at local `(0.82, 1.02, 0.22)` — up-and-right, **over the
   brain** — with `outlineBlur={0.14}` (the visible smear) and a 220-char string wrapped at
   `maxWidth={1.7}` (the jumble). No backing surface, low contrast, lines break mid-word. It
   competes with the point cloud and loses.
2. **The input is a placeholder.** The brainstem intake reads as a tiny teal-outlined capsule
   with a stub chrome bar parked on the cord — a widget, not part of the organism.
3. **There is no "home."** The experience drops straight onto a floating organism on pure black —
   no identity, no arrival, no first-moment that says *product*.

## 2. Goal

Make the **conversation surface** and the **first-impression framing** feel as finished as the
being — entirely **in-world / diegetic** (operator's choice: no DOM, no 2D chrome), materialized
from the anatomy, with the GAGOS identity and live system state always present.

## 3. Operator decisions (the forks already chosen)

- **Communication model:** *fully diegetic / in-world* — reply on a slab from a vertebra; input is
  a glowing organ on the brainstem; no 2D layer for the conversation.
- **Home / rest:** *both, restrained* — identity wordmark **and** a restrained voyaging mood, while
  keeping the clean knowledgeable void he fought for.
- **Status mark:** *in-world 3D readout* — GAGOS + active LLM + "supervised" rendered as luminous
  3D text in the **top-left**, no DOM.
- **`supervised`** = the being runs human-in-the-loop / under operator approval (operator did not
  correct this reading).

## 4. Hard laws honored (from [[living-being-materialization-laws]] + [[fidelity-is-sacred-ui-laws]])

- Everything materializes from the being's **own anatomy**; reply text = luminous 3D text on a dark
  slab; **never cover the brain or the spine**; **no Monaco / HTML / IDE chrome**.
- **Palette + textures are SACRED** — reuse spectral-v1 tones (`bodyPosture.ts`, the brain palette)
  for every new luminous element; invent no new colors. Final color tuning happens in the operator's
  `:5173` browser.
- **Test on `:5173` only** (backend CORS allows `:5173/:4173/:3000`).
- Scene additions under `superbrain/*` **mirror to the lab** (`GAG demo/gag-orchestrator/src/`);
  `workbench/BrainstemIntake.jsx` is **product-only** (not mirrored).
- **No push; commit only on the operator's explicit go**, with explicit pathspecs.

## 5. Design

### A. GAGOS identity + status (top-left, 3D, camera-anchored)

A small luminous text cluster **parented to the camera** so it holds the top-left corner through
every orbit, rendered **inside the main scene** so it passes through the existing Bloom (it glows
like the rest of the being). drei `<Hud>` is rejected: it renders a separate scene and would miss
the bloom.

- **`GAGOS`** — the brain's name, the largest line.
- **active LLM** — live system state, e.g. `◉ Opus 4.8 · cloud` or `Llama 3.1 · local`, with the
  leading dot in that model's accent. Sourced from the router: the `route` cognition event already
  carries `model` / `provider` / `privacy` (see `formatRouteLabel` in `BrainstemIntake.jsx`); the
  plan locates/threads the **persistent** active-brain value (the router's active-brain badge state)
  so the line shows the current brain at rest, not only mid-turn.
- **`supervised`** — a quiet status line (human-in-the-loop). May later switch wording on
  `approval-required` / `approval-resolved` cognition events, but v1 is a static "supervised".
- **Behavior:** dims ~30% while the being is speaking so it never competes with the reply.
- **Type quality:** drei `<Text>` (troika SDF — crisp by construction); thin outline for contrast
  against the void, **no blur**.

### B. Home / resting decor (restrained voyaging)

- **Slow voyaging drift** — a very slow camera (or scene) parallax so the being reads as
  *travelling* through deep space ([[superbrain-core-theme]]). No particles added. On a dial.
- **Soft vignette** — the `<Vignette>` pass **already exists** in `PostFX.tsx` wired from
  `POST_FX.vignette`; add a points-mode variant (à la `bloomPoints`) tuned to frame the being
  without crushing the corner readout.
- **Faint horizon glow** — one subtle distant luminous band, low in the scene, for depth. Strictly
  dialed so the clean void survives; default low.
- **Living invitation** — at rest the brainstem intake organ gently pulses, plus a soft "speak to
  me" 3D cue near the stem that **recedes the instant a turn starts** and stays gone during
  conversation.

### C. Input — diegetic intake organ (replaces the teal capsule)

- Remove the placeholder capsule read. The intake becomes a **single glowing organ at the
  brainstem** that clearly belongs to the body: palette-tinted (posture-driven, as the input surface
  already is via `deriveBodyPosture`), brightening on listen/type, sitting **off** the cord (not on
  it). The existing ring/core/conduit chrome stays hidden in points mode (already gated at
  `BrainstemIntake.jsx:628`).
- The operator's words appear as **crisp** 3D text at the organ — proper size, thin outline,
  **outlineBlur removed**, sane `maxWidth` so short lines don't wrap to mush.

### D. Reply — diegetic slab from a vertebra

- The being's reply **materializes on the existing content-surface slab** rather than as floating
  billboard text. Reuse the proven path:
  - `MaterializedTab` `kind === 'content'` already renders luminous 3D `<Text>` on an extruded slab
    that **unfurls from a vertebra seat** and **retracts** (`UNFURL_DURATION_MS`,
    `beginRetractingMaterializedTab`).
  - Seat via `getContentSurfacePlacement(seatIndex)` + `selectNextAvailableVertebraSeat` — the slab
    sits **to the side**, fed from a vertebra, **never over the brain, never on the spine**.
  - Add a tabStore writer for the reply that mirrors `upsertInputSurface` (e.g.
    `upsertReplySurface(text, placement)`), and retract it on turn-complete / dwell timeout (reuse
    `REPLY_DWELL_MS`).
- **Typography fix is the point:** dark slab gives contrast; single warm palette tone; correct
  width / line-height; no blur. This is a layout + surface fix, not a text-engine change — troika
  text was always crisp; the old presentation wasn't.
- The floating reply `<Billboard>` (`BrainstemIntake.jsx:712–729`) is **removed**.

## 6. Architecture / files

| Concern | File(s) | Change |
| --- | --- | --- |
| GAGOS top-left readout | new `superbrain/components/canvas/IdentityReadout.tsx` (mirrored) | camera-anchored 3D text group: name + active LLM + supervised; bloom-visible; dims while speaking |
| Active-brain source | `superbrain/lib/cognitionBus` + router active-brain state | expose persistent current model/provider/privacy for the readout (not only per-turn `route` events) |
| Voyaging drift | `superbrain/components/canvas/SuperbrainScene.tsx` (mirrored) | slow camera/scene parallax in points mode, dialed |
| Vignette + horizon | `PostFX.tsx`, `lib/constants.ts` (mirrored); optional new horizon element | points-mode vignette variant; subtle horizon band, dialed |
| Invitation cue | `workbench/BrainstemIntake.jsx` (product-only) | resting pulse + "speak to me" 3D cue that recedes on turn start |
| Intake organ | `workbench/BrainstemIntake.jsx` (product-only) | replace capsule read with a single palette-tinted organ; crisp prompt text (no blur) |
| Reply slab | `workbench/BrainstemIntake.jsx` (product-only) + `superbrain/lib/tabStore.ts` (mirrored) | route reply through content-surface slab; add `upsertReplySurface`; remove floating reply billboard |

**Isolation:** each unit is independently testable — `IdentityReadout` (props: name, model line,
supervised, speaking flag), the reply writer (pure tabStore function with a unit test like the
existing surface tests), the vignette/horizon (constant-driven, dialed). No unit needs another's
internals to be understood.

## 7. Non-goals (YAGNI)

- No 2D DOM HUD anywhere (operator chose fully in-world).
- No change to the point-field being itself (geometry, palette, perf tiers are done and approved).
- No mesh-mode (`?being=mesh`) changes — this targets the points being.
- No new color palette, no texture/GLB changes (sacred).
- No conversation-history panel / multi-turn transcript — single live reply slab only, v1.
- No default-flip (`?being=points` → default) — that remains a separate, later operator decision.

## 8. Testing / fidelity

- **Unit:** reply-surface tabStore writer (mirror existing surface tests); `IdentityReadout`
  active-LLM line formatting. Keep `npm test` green (currently 284 passing).
- **Typecheck + lint** clean.
- **Live fidelity (the real gate):** operator at `:5173/?ui=superbrain&being=points` —
  (1) GAGOS + live model + supervised legible top-left through full orbit;
  (2) ask the being something → reply slides out on a vertebra slab, **readable**, never over
  brain/spine, retracts cleanly;
  (3) input organ reads as part of the body; prompt text crisp, no smear;
  (4) at rest: identity + invitation + restrained voyaging mood, void still clean;
  (5) FPS holds (driven via kimi-webbridge rAF probe) at the P6 budget.

## 9. Defaults chosen where the operator didn't specify (tune at :5173)

- Reply slab seat = `DEFAULT_VERTEBRA_SEAT_INDEX` (2), side feed per `CONTENT_TARGET_OFFSET`.
- Identity readout colors = spectral-v1 violet/cyan tones; warm reply tone reuses the current
  `#ffe3a8` family (palette-consistent).
- Voyaging drift amplitude/period, horizon glow intensity, vignette darkness = conservative
  starting values behind dev dials; operator sets the final look in his browser.
- `supervised` is static text in v1 (no live approval-state wording yet).
