# Voice Into the Body — Design Spec (2026-06-22)

Re-home the being's VOICE (reply + status) into its own anatomy, keeping only a thin
input affordance. The transformation from *"a 3D being **with** a 2D HUD around it"*
toward *"the interface **is** the organism."* (Operator scope: **minimal hybrid**.)

## North star + product law

Reference: the VARIANT-H poster (`GAG demo/reference/demoplan.png`) — *"One being. Many
postures. Everything grows from the being."* THE PRODUCT LAW (operator-authored): every
visible element must be one of —
1. part of the being's anatomy, 2. grown out of it, 3. state moving through it, 4. memory
left inside it. If an element fails this law, remove it or re-home it into the body.

## The motivating loophole

The live build still surfaces the being's voice through **2D DOM chrome** (`GagosChrome`),
which violates the product law + the spec's hard bans:
- GAGOS **reply** streams into a 2D DOM thread bubble (`GagosChrome.jsx:360-367`) — not as
  in-scene body-speech. (Confirmed: no in-scene reply text exists today.)
- **Status** is read off top-right DOM pills (auto / resting / supervised), not the body.
- Detached **wordmark** + **prompt chips** = overlay clutter.

The body already carries posture colour/pulse (#15 reply-brighten, posture system) and the
input is usable — so the gap is specifically the **voice (reply + status)** still living in
the DOM.

## Scope (minimal hybrid — operator decision 2026-06-22)

This RESOLVES the standing tension (the 2D chrome was previously an operator-approved
hybrid; the new spec bans it). The agreed middle path:

- **KEEP:** one thin, single-owned **input** affordance (typing usability).
- **RE-HOME into the body:** **reply** (→ in-scene luminous body-speech) and **status**
  (→ body colour/pulse + a minimal cue).
- **DROP:** status pills, wordmark, prompt chips.

NON-GOALS (explicitly out of scope): full removal of the input into the brainstem;
voice/mic redesign; backend changes; touching the sacred palette/textures.

## Decomposition (3 sub-projects, sequenced)

### SP1 — Reply as in-scene luminous body-speech  *(build first; highest embodiment)*

- **Pure contract** `deriveBodySpeech({ replyText, phase, sinceStartMs, reducedMotion })`
  → `{ visibleText, glow (0..1), fade (0..1), active }`. Decides what text shows, how
  bright, and the settle/fade — renderer never invents it. Lives in
  `frontend/src/superbrain/lib/bodySpeech.ts` with focused tests.
- **Renderer** `BodySpeech` (new, `components/canvas/`) — luminous drei `<Text>` emanating
  at the upper stem / cortex base, camera-billboarded, streaming the reply; brightens on
  `streaming`, settles + fades on `complete`. **Reply-text source:** subscribe to the
  cognition-bus `voice-speaking` events the chat already publishes (`GagosChrome.jsx:368`
  emits `source:'gagos', data:{phase:'reply', reply:chunk}`, plus `reply-complete`) and
  accumulate the chunks — no new data wiring. Luminance/anatomy only; reuses the sacred
  palette (posture/theme hues).
- **DOM thread → secondary:** GAGOS reply text is no longer duplicated into the DOM thread;
  the body-speech is the primary reply. The thread keeps only the user's typed echo
  (minimal scrollback) for usability. (Minimal hybrid.)
- **Proof hook:** `window.__getBodySpeech()`.
- **Acceptance:** type a chat turn → the reply appears as glowing text emanating from the
  being (not a DOM bubble); cortex brightens + spine-rise still play; reply settles/fades;
  reduced-motion shows the final text without travel.

### SP2 — Status off the body (retire the pills)

- The body already encodes phase via posture colour/pulse. Retire the top-right DOM pills
  (auto / resting / supervised). Add a **minimal** in-scene/least-chrome state cue (a small
  legend) + keep only a minimal model/latency readout (operator's prior ask). Drop the
  wordmark + prompt chips clutter.
- Proof hook: reuse posture/lifecycle hooks; acceptance: state is readable from the being;
  no top-right pill cluster.

### SP3 — Minimal input (single-owned)

- Keep one thin input affordance; ensure single visible input ownership (no DOM-bar +
  brainstem-intake duplication); declutter. Acceptance: one input path; intent reaches the
  being; no duplicate input surface.

## Architecture discipline (per the operator's spec)

For every sub-project, in order: **(1)** pure contract/store, **(2)** focused tests,
**(3)** wire the renderer (renderer consumes derived state, invents nothing), **(4)** expose
a `window.__get*` proof hook, **(5)** capture live screenshots on the operator's RTX via
kimi-webbridge, **(6)** only then call it done. Gates each step: `npm run typecheck` +
`npm test` (≥209 green) + `npm run build`; CI green; live-verified before merge.

## Risks / guardrails

- **Sacred palette/textures untouched** — body-speech text + status cues use existing
  posture/theme hues only (luminance/geometry).
- **No new flat panels** — body-speech is in-scene 3D text, not a DOM overlay; status cue is
  minimal/in-body.
- **Reduced-motion** parity for the body-speech (no vestibular travel; show final text).
- **Reversibility** — `GagosChrome` changes are additive/guarded so the DOM thread can be
  restored if the embodied reply doesn't read on the operator's GPU.
- **Context** — each SP is independently shippable + verifiable; build/verify/merge one at a
  time (do not stack unverified).

## Success definition

Typing a turn: the reply rises and **glows from the being** (body-speech), status is read
from the body, and only a thin input remains — the being's voice lives in its anatomy, with
the chrome reduced to a minimal usable input. Verified live on the operator's GPU.
