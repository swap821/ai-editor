# The Organism's Body — Making the Awakened Mind Visible

**Status:** Design direction, awaiting operator eye · **Date:** 2026-07-02 · **Author:** Claude
**Context:** The four-layer aliveness campaign landed today (`f404147`, `83a3e76`, `6d53357`):
chemotaxis, reflex, emotion, and narrative are default-on, hot-path, gate-verified. The
wonder organs stay caged, pinned by `tests/test_aliveness_defaults.py`.

---

## 1. Thesis — the gap is indexing, not features

The backend became genuinely alive today. The body (GAGOS points-being) is already a
masterpiece of motion — posture, metabolism, conduction, imprints, reflexes — but its
motion is still a *generic thinking pantomime*: the same beats fire whether the mind is
scenting a memory, hesitating, growing, or minting knowledge.

**Aliveness on screen is motion that can only be explained by what the mind is actually
doing.** The beautiful part: the nervous system already delivers the signal. Since fusion
C1, every SSE frame carries additive `phase` (chemotaxis/reflex/emotion/narrative/wonder),
`cognition_type`, and `seq` fields. Ground truth (verified today):

- `cognitionBus.ts` speaks the same 11-type vocabulary as the backend's `events.py` — but
  `CognitionEvent` has **no `phase` field**. The body drops the signal on the floor.
- `aiosAdapter.ts` has **no handler for `confidence.gated`** — the organism's brand-new
  hesitation beat (emotion layer, wired at `main.py:3301`) is inaudible to the body.
- The adapter already has `startAiosPolling` and a facts-graph fetcher — the pending-facts
  surface needs **zero backend changes** to ship its first version.

## 2. The phase chord — a canon-safe color grammar

Map the layers to the sacred tetrad. No new colors; the palette canon is untouched:

| Phase | Hue | Bodily meaning |
|---|---|---|
| chemotaxis | cyan `#7bf5fb` | scenting, recall, orientation |
| reflex | orange `#ff7e40` | gates, action, verification |
| emotion | purple `#b06eff` | weather, confidence, hesitation |
| narrative | green `#54f0a0` | growth, memory, identity |
| **wonder** | **all four in unison** | **a reserved chord — never played until wonder wakes** |

The chord makes the inner life *readable at a glance* with zero UI chrome, and reserves a
first-time visual event for the day the operator opens the wonder phase.

## 3. The six body slices (B1–B6) — small, lab-first, operator-gated

Same discipline as today's backend campaign: one slice, TDD where logic lives, the
operator's `:5173` eye as the aesthetic gate, `npm run port` to product.

### B1 — Listen (plumbing; invisible; unlocks everything)
Add optional `phase?: string` and `seq?: number` to `CognitionEvent` (additive — no
consumer breaks). Forward the SSE frames' additive fields through every adapter
`publishCognition` site. Add the missing `confidence.gated` SSE handler → publish an
approval-required-flavored event with `phase: 'emotion'` and the gate payload
(confidence, threshold, question). Tests mirror `aiosAdapter.sse.test.ts`.

### B2 — Weather (the emotion layer made ambient)
Per-turn confidence (the alignment frame carries it) drives point-field micro-tension
through existing `pointFieldMaterial` dials: high confidence = calm laminar drift; low =
fine-grained jitter. The turn's active phase tints conduction beads and nerve pulses via
the chord (`attentionConduction` / `turnMetabolism` already carry these beats). Subtle;
reduced-motion guarded; intensity dials left to the operator's eye.

### B3 — Hesitation (the honest pause)
On `confidence.gated`: the being pulls back slightly (`bodyPosture`), the field dims a
step, and the clarifying question materializes at the brainstem chat box — existing
anatomy, existing ask plumbing. The approval gate says "I need permission"; this says
"I'm not sure — help me." Together they are the supervised mind's two humilities, and
they are the product's thesis rendered as body language.

### B4 — The memory halo (flagship: supervised memory formation made tactile)
Pending fact proposals (`GET /api/v1/memory/facts/pending`, shipped today) orbit the
cortex as luminous green motes. Approaching one reveals its triple as luminous 3D text
(troika, per the materialization laws — no Monaco, no panels). The operator touches a
mote: **absorb** (POST approve → the mote spirals inward and settles into the node
lattice — knowledge minted through the contradiction check) or **release** (POST reject →
it drifts off and dims into the void). Contradiction (409) = the mote flares and holds,
awaiting reconcile.

The operator literally feeds the mind's beliefs by hand. First version rides
`startAiosPolling`; a later backend `facts.proposed` SSE beat (deferred seam, noted in
RESUME) removes the polling latency. Laws honored: materializes from cortex anatomy,
never covers the spine, palette-safe (narrative green).

### B5 — Growth (mastery hardening)
Curriculum level mastery and STRONG-verified skill promotion harden a lattice node: a
settle of brightness and size, one conduction flourish along its nerve. **Weak greens
produce nothing** — the body never celebrates hollow evidence; verification-strength
honesty becomes body language. Needs one small additive SSE beat (or telemetry polling
extension) — build-time choice.

### B6 — Dormant wonder (anticipation as anatomy)
The council region of the anatomy exists but sleeps: faint breathing luminance, no hue.
It is an honest, always-on status display of the caged organs. The day the operator
flips the wonder flags, the region wakes and the tetrad chord plays once — a first-time
event the body has been quietly promising.

## 4. Sequencing rationale

B1 is pure plumbing and unlocks all others. B2+B3 are the cheapest wow-per-line and make
today's emotion layer visible. B4 is the flagship — the only slice adding product
interaction, and the visible face of today's `fact_proposals` backend. B5–B6 complete
the growth and wonder stories. Every slice is independently shippable and reversible.

## 5. Laws compliance (checked at design time)

- Everything materializes from the being's own anatomy; the spine is never covered.
- Palette = the poster tetrad only; textures untouched; `check_css_canon` stays green.
- Lab first (unrestricted build space), the operator's `:5173` look gates every port;
  product `frontend/src/superbrain/*` is never hand-edited.
- `reducedMotion.ts` guards every new beat. Zero mandatory backend changes for B1–B4.
- Honest limit: no headless visual verification exists — the final aesthetic call on
  every slice is the operator's browser, by law.
