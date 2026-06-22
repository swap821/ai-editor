# Step 1 — Framing + Chrome Pass (Brain+Panels → One Organism)

## Context

Operator scorecard: the point-field brain is strong (8/10) but the whole reads as
"UI panels around a being" (living-organism feeling 5/10). The biggest, cheapest
"it's UI" tells are: mobile/portrait framing (3/10 — being floats small in black),
floating status pills (detached HUD), and weak active-vs-waiting hierarchy. This
step fixes the framing + chrome — the fastest path to making it *feel* like one
organism — before the harder anatomical-surface / dock work.

**Constraint:** improve visual grammar, add no features. Sacred palette untouched
(geometry / framing / luminance / motion only). Each piece is independently
shippable + provable via `window.__demo()`.

## Pieces (impact-first; separate commits/PRs)

### 1A. Responsive organism camera framing  *(build first — highest impact)*

Today the camera (`PerspectiveCamera` fov 26 @ z≈15 + `CameraDrift` damping
position + `lookAt`) is NOT viewport-aware, so portrait/mobile gets desktop framing
→ the being is small with a giant black void.

- **Pure contract** `deriveOrganismCameraFrame({ phase, aspect, activeSurfaceCount })`
  → `{ distance, fov, targetY, lift }`. Lives in
  `frontend/src/superbrain/lib/organismCameraFrame.ts` with tests.
  - Rest: being centred, occupies ~35–45% of frame height.
  - Orchestration (activeSurfaceCount ≥ 1): pull so the spine + active surface fill
    ~60–70% of useful width.
  - **Portrait (aspect < 1):** smaller distance (pull in) + raise `targetY` so the
    organism climbs up out of the dead zone; widen fov modestly so the tall frame
    fills.
- **Renderer:** `CameraDrift` consumes the derived frame for its damp targets +
  `lookAt` height (it already damps position; we make the TARGETS frame-aware). No
  new camera component; reuse CameraDrift.
- **Proof:** `window.__getOrganismCameraFrame()`; capture desktop + portrait — no
  giant dead zone in either.

### 1B. Status off the chrome → body marks  *(+ keep the trust cue)*

The `gagos-status` pills (model/offline + supervised) are detached HUD.

- Remove the boxed PILL chrome. Re-home ambient status to the body: supervised =
  a calm green/cyan pulse near the brainstem intake; auto = a small orbiting signal
  near the active vertebra (reuse existing posture/signal channels — no new colour).
- **KEEP a minimal readable cue for `offline`/`supervised`** — it is a trust +
  data-privacy signal (local vs cloud), where ambiguity is costly. A tiny,
  un-boxed text line (not a pill), or an unmistakable body-mark + screen-reader
  text. Decorative status → pure body language; the trust bit stays legible.
- Acceptance: no boxed pill cluster; supervised/offline still unambiguously
  knowable; sacred palette held.

### 1C. Active vs waiting hierarchy

Multi-surface currently competes. Strengthen (mostly scale/opacity/depth on the
existing surfaces, via the existing conductor/pose contracts):
- Active: center-forward, largest, brightest, readable, strongest root grip.
- Waiting: smaller, dimmer, pushed back in depth, slow breathe, still connected.
- Acceptance: the focused work is instantly obvious.

## Architecture discipline

Per piece: pure contract → focused tests → wire renderer (consumes derived state)
→ `window.__get*` proof hook → live capture (desktop + portrait via `__demo()`)
→ then done. Gates each: typecheck + test + build; CI green; live-verified.

## Out of scope (later steps of the arc)

NeuralCommandDock (Step 2); anatomical surface membranes + living roots (Step 3).
Input-purity-as-stem-only is superseded by the operator's NeuralCommandDock hybrid
decision (Step 2). Mobile *content* readability beyond framing rides with 1A/1C.

## Success definition

Desktop + portrait both frame the being with no dead void; status reads from the
body (with the trust cue kept legible); the active work is instantly obvious. The
scene moves from "brain + floating chrome" toward "one organism" — measurably on
the operator's mobile/framing/organism-feeling scores.
