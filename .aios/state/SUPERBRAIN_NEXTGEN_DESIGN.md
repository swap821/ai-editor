# SUPERBRAIN — Next-Gen 3D Design Research & Direction

> Deep-research deliverable (2026-06-15). Operator directive: "renovate/redesign a
> 3D motion 'absolute cutting-edge GOAT next-gen north-star' working frontend, per
> the backend." Method: 3 parallel research lenses (backend data surface · the
> 2025-26 cutting edge · an audit of the canon scene) synthesized with the design
> skills. This is a **proposal (GREEN)** — no canon was touched producing it.

---

## 0. The non-negotiables (these govern every idea below)

1. **North star (his soul-line):** *an autonomous AI-OS superbrain travelling constant
   into the deep-vast knowledgeable infinite space.* Complete dark room, the glowing
   brain in perpetual motion, Jarvis-grade, goosebumps. Every choice anchors here.
2. **Enhance, never replace.** The 3D brain + cosmic space is the operator's cherished,
   canon-FROZEN core ([[fidelity-is-sacred-ui-laws]], [[superbrain-core-theme]]). Every
   item here is an **additive overlay or a tuning**, never a rebuild.
3. **FIDELITY process for any 3D change:** canon tag → lab edit → goldens → **before/after
   screenshots in HIS browser** for sign-off → `npm run port`. No auto-degrade ever.
   `components/canvas/**` is guard-frozen; work is authored in the lab and ported.
4. **Data-true.** No fabricated activity. Every visual either binds to a REAL backend
   signal or is honest ambient motion. The brain goes dormant when there's no data.
5. **Smooth on a 16GB box.** Adaptive DPR + quality tiers stay sacred; awe must never
   cost the frame.

---

## 1. Honest finding: the canon is already award-ADJACENT

The audit (see `.aios/state/` research notes) found a **15-layer living organism**, not a
demo. What already ships at expert tier:

- **Scene graph:** brain GLB (region-baked vertex colors) · cortex shell (custom physical
  shader, Voronoi web, rim fresnel, filament bloom) · neural casing (iridescent fresnel) ·
  neural aura (membrane + nucleus shells, synaptic sparks) · cortical signals (surface-sampled
  fireflies, thought-wave blink) · accretion core (820-particle infall) · nervous system
  (115 tubes merged → 1 draw call, data-packet trains) · memory galaxy (real skill-trail
  stars) · cognitive grasp (knowledge-transfer choreography) · knowledge horizon (IQ
  domain-warp nebula dome) · cosmic background (4500 converging glyph-stars) · region pins.
- **Cinematic pipeline (PostFX):** Bloom (knee-thresholded so only rim/filaments bloom) →
  Chromatic Aberration → log-contrast → **AgX tonemap** → teal/amber split-tone → vignette →
  film grain. This is already a real grade.
- **A phase-locked "breath":** one shared uniform block makes every layer breathe as ONE
  body; thought-waves fire at anatomically consistent lobes.
- **Honest data-reactivity:** reacts to `directive`, `approval-required/resolved`,
  `knowledge-acquired` (incl. VERIFICATION GREEN/RED synapse-storm), `agent-dispatch`,
  `telemetry`, internal Poisson bursts. Real trail awareness; dormant when offline.
- **Quality tiers:** high/medium/low gate DPR, aura shells, Voronoi octaves, firefly/star
  counts, bloom/CA/grain; demote-only, structure-locked, FIDELITY-governed (never auto).

**Implication:** the path to "GOAT next-gen" is NOT a new scene. It is (A) three or four
*cinematic-physics* upgrades the canon doesn't yet have, (B) deeper binding to backend
signals it doesn't yet visualize, and (C) camera choreography. Executed the way every
Awwwards winner wins: **3-4 effects done flawlessly, restrained palette, buttery camera** —
not by stacking everything.

---

## 2. The data-true foundation (what the brain can truthfully react to)

The backend exposes a deep real-time surface. Mapping it to "already visualized" vs "untapped":

**Already bound (keep):** `directive`, `agent-dispatch` (tool→lobe wave), `knowledge-acquired`
(+ VERIFY GREEN/RED), `approval-required/resolved` (amber hold), `telemetry` (memory galaxy),
internal bursts.

**Untapped backend signals → candidate NEW (additive) brain reactions:**

| Backend signal (real) | Source | Proposed brain reaction (additive, honest) |
|---|---|---|
| `route` privacy local/cloud + provider/model | SSE `route` | The **voyage tint**: local = the canon teal stays; a policy-permitted *cloud* turn shifts a faint violet rim + one distant cloud-amber star, so leaving the machine is *visible*. (Badge already exists; this is the ambient echo.) |
| `earned_autonomy` grant | SSE `earned_autonomy` | A distinct **self-act pulse** — a wave that fires from the frontal lobe with NO approval-hold amber (the brain acting on earned trust), color-coded apart from a human-approved act. |
| swarm / role-pass castes | SSE `step.role` | The **mesh forming**: transient satellite nodes around the brain (planner→coder→reviewer / decomposer→workers→synthesizer), dissolving after the turn. Today only narrated in the terminal. |
| audit-chain health | `/api/v1/audit/verify` | **Spine integrity**: the spinal nerve bundle runs clean cyan when the hash chain is valid; a break stains the spine (the tamper alarm made visceral, not just a tab). |
| verification coverage / success-rate | `/development/metrics` | A slow **vitality** read: overall aura clarity / accretion vigor scales with measured verified-success rate (evidence, not vibes). |
| memory growth (facts/skills/curriculum) | `/development/*` | Memory-galaxy **star birth**: a real new trail flares a nascent star into a persistent one (the operator *makes* a star). |

These deepen the "Jarvis is alive and responding to ME" feeling **with truth**, which is
exactly the difference between a screensaver and the AI-OS.

---

## 3. The WOW elevation plan — the 8 highest-impact upgrades

Ranked by goosebumps-per-effort, each mapped to a specific canon layer as an **additive**
change. (Refs: Maxime Heckel volumetrics/GPGPU, pmndrs postprocessing/drei, Codrops TSL,
Chipsa WebGPU case studies — full URLs in §7.)

1. **Volumetric god-rays (raymarched, blue-noise dithered)** — THE goosebumps beam. Light
   shafts streaming off the cortex through the nebula. Today there is flat bloom only.
   Custom `Effect` (depth-reconstructed, Henyey-Greenstein scatter, 250→50 steps via blue
   noise + temporal jitter). *Layer:* new pass in `PostFX` after Bloom. *Tier:* high only.

2. **GPGPU curl-noise synaptic dust (FBO ping-pong → WebGPU/TSL later)** — hundreds of
   thousands of motes in divergence-free curl flow: the mind *churning*, never static.
   Today particles are CPU-attribute point sprites. *Layer:* a new field between aura and
   cosmic background; `useFBO` + simulation shader. *Tier:* count scales per tier.

3. **Selective/emissive bloom refinement** — the cortex glows *from within* against pure
   black; ensure bloom selects only emissive cortex + synapses (the canon already
   knee-thresholds; tighten to selection-based for crisper void). *Layer:* `PostFX`.

4. **Raymarched FBM nebula depth** — give the deep space true volumetric parallax fog
   instead of a pure dome, so the brain visibly *voyages through* it. *Layer:* augment
   `KnowledgeHorizon` (additive volumetric shell behind the brain). *Tier:* high; dome
   fallback on low.

5. **Fresnel rim + fake subsurface scattering on the GLB** — light bleeds *through* the
   cortex (translucent living flesh, not plastic). Rim fresnel already exists; add a
   thickness/wrap SSS term. *Layer:* cortex `onBeforeCompile`. *Tier:* all (cheap).

6. **Camera choreography + constant voyaging** — `maath` `damp3` glide + `<Float>` idle +
   optional GSAP-style shot keyframes (region-focus on the active lobe, deferential lock
   on approval-hold, hero flare on VERIFY GREEN). Today the camera is passive orbital.
   *Layer:* the camera controller in the scene. *Feel:* nothing ever static.

7. **Data-reactive pulse tied to REAL signals (§2)** — the brain breathes/fires on actual
   AI-OS activity (and optionally TTS amplitude from the new voice loop). This is what
   makes it *Jarvis*. *Layer:* extend the cognition→uniform mapping (non-frozen bus side).

8. **Mode/data-reactive color grading** — the static split-tone becomes a living grade:
   cooler/introspective on observe, warm/energetic on synthesize, amber-locked on hold,
   a momentary contrast+vibrance spike on VERIFY GREEN. *Layer:* `PostFX` GradePost uniforms.

**Supporting cast (do these or it falls apart):** N8AO in the cortex folds (real flesh
contact shadows), DOF bokeh on the starfield, subtle CA + vignette (already present),
adaptive-DPR + PerformanceMonitor quality gating, KTX2 textures + shader preload to kill
first-frame jank.

---

## 4. The voice synergy (already half-built)

The Jarvis voice loop just landed (talk → `/api/v1/chat` → speak-back, both faces). The
**`voice-speaking` → brain pulse** is the natural #1 data-reactive moment (the brain visibly
speaks). It is deferred precisely because the pulse reaction lives in the frozen `canvas/`
scene — so it belongs in the FIRST canon session of this plan (§6, Phase 1), where it rides
in alongside the god-rays prototype under one screenshot review.

---

## 5. Tech strategy — ship WebGL2, prototype WebGPU/TSL in parallel

- **Ship on WebGL2.** The mature `@react-three/postprocessing` + the existing GLB/texture
  pipeline is rock-solid today; all 8 upgrades are achievable now.
- **Prototype the particle organism in WebGPU + TSL compute (in parallel).** That is where
  the ceiling lifts from ~50k FBO particles to **1M+** compute particles — the "living dust"
  at a scale WebGL can't touch. TSL is renderer-agnostic (compiles to WGSL *and* GLSL) with
  automatic WebGL2 fallback; browser coverage ~95% in 2026. Adopt as default only when the
  particle/draw-call wall is hit. Keep it a lab spike, not the shipping path, until proven.

---

## 6. Phased, FIDELITY-safe roadmap

Every phase is **lab-first → port**, gated by canon tag + goldens + **before/after
screenshots in his browser**. Nothing auto-degrades; his GLB + textures are never touched.

- **Phase 0 — Canon tag + baseline goldens.** Tag `pre-nextgen-canon-v1`; capture current
  goldens at all tiers as the rollback + comparison baseline. (cheap, do first)
- **Phase 1 — The single goosebumps beam + the voice pulse.** Volumetric god-rays (#1) +
  `voice-speaking` brain pulse (§4). One coherent "the brain speaks and the room lights up"
  moment. Highest awe, one review.
- **Phase 2 — Living matter.** Fresnel/SSS (#5) + GPGPU curl-noise dust (#2, WebGL FBO) +
  selective-bloom refinement (#3). The brain becomes translucent flesh in churning dust.
- **Phase 3 — The voyage.** Raymarched nebula depth (#4) + camera choreography & constant
  voyaging (#6). The brain visibly travels the infinite.
- **Phase 4 — Truth made visible.** Deeper data-binding (§2: route-privacy tint, earned-act
  pulse, swarm mesh, spine integrity, star-birth) + mode/data-reactive grade (#8).
- **Phase 5 (parallel spike, optional).** WebGPU/TSL 1M-particle compute prototype in the
  lab; promote only if it clears the FIDELITY bar in his browser and beats the WebGL field.

Each phase ends with: goldens refreshed (documentary), before/after in his browser, port,
gates green (canon-freeze + css-canon + build + vitest + pytest).

---

## 7. Reference hubs (kept for the build)

- Maxime Heckel (volumetrics, GPGPU, raymarching, TSL field-guide): https://blog.maximeheckel.com
- pmndrs postprocessing: https://react-postprocessing.docs.pmnd.rs · drei: https://drei.docs.pmnd.rs
- R3F perf: https://r3f.docs.pmnd.rs/advanced/scaling-performance
- Codrops TSL/WebGPU: https://tympanus.net/codrops/tag/tsl/ · https://tympanus.net/codrops/tag/webgpu/
- WebGPU migration (2026): https://www.utsubo.com/blog/webgpu-threejs-migration-guide
- N8AO: http://n8programs.com/n8ao/ · Awwwards three.js: https://www.awwwards.com/awwwards/collections/three-js/
- Shipping-grade case studies (Chipsa): https://medium.com/@Chipsa/the-evolution-of-webgl-at-chipsa-c68dca54d538

---

## 8. Risks & guardrails

- **Performance:** every effect is tier-gated + behind PerformanceMonitor; high-cost passes
  (volumetrics, GPGPU) high-tier only with graceful fallback. The frame is sacred.
- **Palette discipline:** one accent (canon teal) + state tokens only; the cloud-route violet
  is the single deliberate exception and it encodes truth (data left the machine).
- **FIDELITY:** no auto-degrade; his assets untouched; before/after in HIS browser per phase.
- **Data honesty:** every new reaction binds to a real signal or is honest ambient motion;
  dormant when there's no data.
- **Scope:** this is elevation of a cherished core, not a redesign. Each phase is independently
  shippable and independently reversible (canon tag).

---

## 9. Recommended first move

**Phase 0 + Phase 1** together: tag the canon, capture goldens, then prototype the **volumetric
god-rays + the voice-speaking brain pulse** in the lab and bring you before/after screenshots in
your browser. That is the single biggest "goosebumps in a dark room, and it speaks" leap, in one
review — and it finishes the voice arc you just started. Everything else stacks cleanly after.
