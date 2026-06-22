# ATMOSPHERE + MEMORY/RECALL — DEPTH BUILD PLAN

**The two remaining canon lenses, elevated to premium + data-true.** Chief-Architect synthesis of
4 depth lenses + the adversarial Corrections Ledger, every claim re-verified against the live lab
tree on **2026-06-15** by direct file reads. Research/plan only — **NO code edited, NO builds run.**

- **Scope.** Two lenses, LOWER priority than the alive-being core (NodeLattice P2 + NervousSystem
  `uFlowDir`): **PART A — CORTEX/ATMOSPHERE** (cortex shell + casing, CorticalSignals, NeuralAura,
  AccretionCore, CosmicBackground, KnowledgeHorizon, PostFX) and **PART B — MEMORY/RECALL**
  (MemoryGalaxy, CognitiveGrasp, RegionPins). These are an **ELEVATION, not a rebuild** — the canon
  is already award-adjacent; the job is to close honest data-truth gaps and polish ambient atmosphere,
  proportionately.
- **North star** ([alive-being-brain-vision]): an ALIVE BEING — idle brain voyaging in deep space;
  talk to it → it wakes and works via its nervous system. Everything shown is something the AI-OS
  actually IS or DOES — **DATA-TRUE, or honestly ambient atmosphere; never decoration.** Honest
  dormancy: render NOTHING for an empty data source.
- **The final aesthetic call is the OPERATOR'S BROWSER. WebGL cannot be verified headlessly.** Every
  visual change is lab-first → his browser sign-off → canon tag + goldens. Before/after screenshots
  for every visual change.
- **Frozen invariants** (do not violate): `/models/brain.glb` + textures UNTOUCHED; the 8 cortex
  region color constants (`SuperbrainScene.tsx:238-245`) are the FROZEN canon palette — NOT a gradient;
  10 cognition-bus types is the contract; `superseded_by` is absent from the frontend `TrailRow`.

---

# PART A — CORTEX / ATMOSPHERE

## A.1 VERIFICATION LEDGER (what is TRUE, with file:line; what lenses got wrong; ambient vs data-bound)

### A.1.1 Confirmed TRUE this session (re-read against the live tree)

**Cortex shell (BrainModel).**
- `onBeforeCompile` injects EXACTLY two live uniforms into the cortex shader: `uTime` and `uHold`
  (`SuperbrainScene.tsx:653-654`). The comment at `:649-652` states it "reads ONLY uTime ... and
  uHold." `uBurst` and `uModeTint` are computed in SCENE_UNIFORMS (`:1185`, `:1195-1201`) but are
  **NOT** in the cortex shader. ✔ Confirmed.
- 8 region color constants at `:238-245` (`#ff3b28 #ff7a26 #19d4f0 #36f07a #a8e62b #9b3bff #e62bd4
  #6a35ff`). NOT a gradient — a per-vertex multi-region weighted bake with `pow(w, 2.6)` sharpening
  + `fbm3` boundary wobble + `CAVITY_DARKEN=0.52` AO (`:419-445`). ✔ Confirmed.
- `customProgramCacheKey: () => 'superbrain_v6_${tier}'` (`:808`). Any new cortex uniform MUST bump
  this string or THREE silently reuses the old compiled program. ✔ Confirmed.
- Cortex fragment layers (`:773`, `:785`, `:789`, `:793-798`): regional Voronoi glow `pow(cDetail,1.5)*4.0`;
  `pulseMix = mix(mix(0.7,1.5,pulse),1.25,uHold)`; fresnel rim `safeColor*fresnel*2.5*pulseMix`;
  hold amber lerp toward `vec3(1.0,0.62,0.22)` at `uHold*0.85`. ✔ Confirmed.
- Voronoi: 27-cell loop (`:689-705`); HIGH = 2 octaves (`:715`), MEDIUM/LOW = 1 octave (`:718-719`);
  animation FROZEN on low (`vec3 anim = vec3(0.5)` at `:696-697`). The single heaviest fragment cost,
  evaluated once and shared between bump + emission (`:735`, `:765`). ✔ Confirmed.

**Casing (neuralSkin) — a SEPARATE `ShaderMaterial`, scale 1.004.**
- Its own `uniforms: { uTime, uHold }` (`:825`) — does NOT share SCENE_UNIFORMS, does NOT read
  `uBurst`. ✔ Confirmed. Iridescence `0.5+0.5*cos(6.28318*(fres*1.5+uTime*0.1+vec3(0,0.33,0.67)))`
  (`:598`), cyan→amber `mix(vec3(0,0.8,1.0),vec3(1.0,0.62,0.22),uHold)` (`:595`). ✔ Confirmed.

**Wave scheduler (the cortex's real-event surface).**
- `WAVE_REGION_ANCHORS` = EXACTLY 4 anchors (`:469-476`): SIGNAL/TITAN→occipital, ARCHIVE/MYTHOS/MEMORY
  →temporal, CAUSAL/GRAPH/DELTA→frontal, SEMANTIC/LATTICE→parietal. No cerebellum, no router anchor.
  ✔ Confirmed. `uWaveOrigins`/`uWaveTimes` are 3-slot.
- `waveLabelForTool` (`:490-496`): `plan|orchestr|skill|recall|memory|lesson`→CAUSAL;
  `read|search|list|web|fetch|grep|inspect`→ARCHIVE; `create|edit|write|exec|verify|run|build`→LATTICE;
  else→SIGNAL. The `web|fetch|grep|inspect` arm is live GLSL routing code that only fires if such a
  tool is dispatched — and the real backend has no web tool, so it is dead-but-inert. `self_analyze`/
  `propose_fixes` fall to SIGNAL (not listed). ✔ Confirmed.
- Real cortex-firing events (`:1031-1106`): `approval-required`→hold; `approval-resolved approved`→
  CAUSAL wave; `directive`→burst 0.6; `agent-dispatch` (`detail.startsWith('tool engaged: ')`)→
  `waveLabelForTool` wave + burst 0.45; `knowledge-acquired VERIFICATION GREEN|SKILL MASTERED`→
  synapse storm over `.slice(0,3)` of anchors + burst 1; other `burst`/`knowledge-acquired`→one wave.
  Idle waves every 3-8 s (`:1208 → time + 3 + random()*5`), gated by `holding < 0.5` (`:1206`); idle
  cascade 6-9 s (`:1225-1227`). Burst decay 3.5/s (`:1167`). ✔ All confirmed.

**CorticalSignals (surface fireflies).**
- Component default `FIREFLY_COUNT = 320` (`:17`) but the scene OVERRIDES via `count` prop:
  `tier==='high' ? 180 : tier==='medium' ? 110 : 50` (`SuperbrainScene.tsx:918`). **Live high-tier = 180.**
  ✔ Confirmed. Shader: `flash = pow(0.5+0.5*sin(uTime*aSpeed*4.0+aPhase), 8.0)` (`:87`); wave bias
  `prox = clamp(thoughtWave(position,uTime,3.0)*1.6,0,1)` (`:91`), `flash *= 0.3+0.7*prox` (`:92`),
  `flash *= 0.7+uActivity*0.5` (`:93`). Uniforms = shared `uTime`/`uWaveOrigins`/`uWaveTimes` leaves +
  LOCAL `uActivity` (`:225-234`). No `uHold`/`uBurst`. Seed `0x53594e41` (`:163`). `NORMAL_LIFT=0.004`
  (`:18`). ✔ Confirmed.

**NeuralAura (membrane + nucleus + 50 sparks).**
- `MEMBRANE_SCALE=1.025` BackSide, `CORE_SCALE=0.85` FrontSide. Membrane alpha capped at 0.25:
  `a = min(a*(0.85+0.30*uBreath+uBurst*0.45), 0.25)` (`:97`); peak additive output `1.4*0.25=0.35`
  (`:99-100`), below the 1.0 bloom knee. Both shell materials read shared `uBreath`+`uBurst` only
  (`:264`, `:275`). `SPARK_COUNT=50` module const (`:51`), `SPARK_ORBIT_RADIUS=0.48` (`:50`); spark
  uniforms = shared `uTime` + LOCAL `uActivity` + `uColor` (`:249-256`). Mode colors observe `#40e8ff`
  / synthesize `#aef2ff` / orchestrate `#8f7bff` (`:54-58`); hold amber `#ffb454` (`:61`) lerped when
  `uniforms.uHold.value > 0.01` (`:345-348`). Nucleus dropped when `shellBudget < 2` (gate
  `shellBudget >= 2` at `:373`). Scene passes `shells={tier==='high'?2:1}` (`:908`), NO `sparkCount`
  prop → 50 sparks at every tier. **No `voice-speaking` subscriber exists in the file.** ✔ All confirmed.

**AccretionCore (820-particle infall disk).**
- `PARTICLE_COUNT=820` (`:9`), `INNER_RADIUS=1.55`/`OUTER_RADIUS=4.85` (`:10-11`), disk position
  `[0, 0.12, -1.18]` (`:217`). Subscriber fires on `event.type==='knowledge-acquired'` ONLY (`:169`),
  reads `event.intensity` only (NOT label/detail): `pulseRef = clamp(0.6+(intensity??1)*0.4,0,1)`
  (`:170`). `uPulse = 1+pulseRef*PULSE_GAIN(0.5)` (`:206`), decay `PULSE_DECAY_RATE=3.6` (`:199`).
  `uBurst` from the `BurstRef` prop (`:192,205`) — NOT SCENE_UNIFORMS. 4 static tints (`:53-56`);
  `pickTint` distribution = cyan 60% / rose 18% / violet 12% / amber 10% (thresholds 0.6/0.78/0.9 at
  `:125-130`). No tier gate on particle count. ✔ All confirmed.

**CosmicBackground (glyph-star streamfield).**
- `STAR_COUNTS: high=2800, medium=1400, low=600` (`:68-72`). `STARFIELD_TIME_UNIFORM` module-level
  (`:65`). Hold dilation `STARFIELD_TIME_UNIFORM.value += delta*(1 - 0.7*hold.blend)` (`:136`) → 30%
  speed at full hold. Hold subscriber: `approval-required`→target 1; `approval-resolved|directive|
  synthesis`→target 0 (`:121-127`); damp 2.5 (`:135`). Starfield uniforms = `uTime` + `uAtlas` ONLY
  (`:108-111`) — NO `uActivity`. Scene passes only `tier`. Seed `0x564f5941` (`:84`). ✔ All confirmed.

**PostFX (the whole-frame grade — internals NOW verified against the live tree).**
- Pass order = JSX order (`:154-209`): Bloom (`tier!=='low'`, `:164`) → ChromaticAberration
  (`tier==='high'`, `:174`) → GradePre → ToneMapping(AGX) → GradePost → Vignette → Noise
  (`tier==='high'`, `:202`). ✔ Confirmed.
- `GradePreEffect` (`:60-67`): one uniform `uContrast` from `POST_FX.grade.contrast = 1.06`.
  `GradePostEffect` (`:122-139`): `uShadowTint=Vector3(0.42,0.52,0.55)`, `uHighTint=Vector3(0.52,0.5,
  0.44)`, `uBalance=-0.08`, `uVibrance=0.21` (from `constants.ts:202-209`). Both via `wrapEffect`
  (`:141-142`). **PostFX is FULLY STATIC at runtime** — no `useRef`/`useFrame`/`subscribeCognition`;
  the only `useMemo` is for `aberrationOffset`. ✔ Confirmed.
- `POST_FX.toneMappingExposure = 1.45` (`constants.ts:190`). ✔ Confirmed.

### A.1.2 What the lenses got WRONG (corrections that override prior research)

1. **❌ Lens 1 AccretionCore tints "60% cyan, 12% rose, 12% violet, 16% amber."** WRONG. Correct
   (verified `pickTint` thresholds `:125-130`): cyan 60% / rose 18% / violet 12% / amber 10%.
2. **❌ Lens 1 framing that `uBurst` already drives "NeuralAura, AccretionCore, and NervousSystem"
   via SCENE_UNIFORMS.** AccretionCore reads `uBurst` from a `BurstRef` PROP (`:192,205`), NOT from
   SCENE_UNIFORMS. NeuralAura shells DO read the shared `uBurst` leaf (`:264,275`). The architecture
   distinction is load-bearing for any builder.
3. **❌ Lens 2 "PostFX `toneMappingExposure = 1.6`."** WRONG. Live value is **1.45**
   (`constants.ts:190`). The PostFX.tsx HEADER COMMENT (`:15`) does say "1.6" — it is **stale**; the
   real consumed constant is 1.45. (Flag this stale comment for a cheap doc fix.)
4. **❌ Any proposal to mutate `.uniforms.get(...)` directly on the `<GradePre/>`/`<GradePost/>` JSX
   components.** `wrapEffect` does NOT forward a ref to the Effect instance. A live-grade requires a
   refactor FIRST (a `forwardRef`/`useMemo`-held instance) — see A.3 / PFX1. Confirmed at `:141-142`.
5. **❌ Cortex "gradient."** Confirmed NOT a gradient (multi-region bake). Never propose one.
6. **CONFIRMED-CORRECT items the lenses flagged that survive scrutiny:** `CAUSAL DECISION` DOES match
   `/CAUSAL|GRAPH|DELTA/i` (`:474`); idle waves ARE 3-8 s; membrane cap IS 0.25; `voice-speaking` IS a
   real bus type (`cognitionBus.ts:41`) with ZERO canvas consumers.

### A.1.3 Ambient vs data-bound (the honest classification)

| Layer | Data-bound (REAL) | Ambient (correctly atmosphere) | Absent / gap |
|---|---|---|---|
| **Cortex shell** | `uHold` amber (real approval pause); `uTime` alive pulse | region palette (static skin), Voronoi web, cavity AO, fresnel rim cycle | `uBurst` not injected; no provider/route signal |
| **Casing** | `uHold` cyan→amber | iridescence cycle | no `uCloudRoute` |
| **CorticalSignals** | wave-biased blink (real bus events via scheduler); `uActivity` fire rate | static positions, per-mote phase/speed/size, baked `aColor` | no per-lobe flash-color reveal |
| **NeuralAura** | mode color, `uHold` amber, `uBreath`/`uBurst` shared leaves, `uActivity`→spark size | orbit geometry, 50-spark count, `aTint` 65/35 split, rose SSS hue | no `voice-speaking`; sparks never tier-gated |
| **AccretionCore** | `knowledge-acquired`→`uPulse` (intensity-graduated); `uBurst`; `uActivity` | 4 tint colors (random assign), infall geometry, tilt | tint ignores `event.label`; no tier gate |
| **CosmicBackground** | `approval-required`→voyage dilation (the macro behavioral signal) | glyph types, field, gravitational pull | no `uActivity`-proportional drift |
| **KnowledgeHorizon** | `uActivity` ~3% nebula opacity; `uPointer` parallax; `uReducedMotion` | entire nebula/stars/dust/volumetric | none worth closing — correctly ambient |
| **PostFX** | NOTHING (100% static today) | the whole cinematic grade | no live grade on hold/verify/mode |

---

## A.2 PER-LAYER ASSESSMENT + HONEST PREMIUM UPGRADE

Granularity rule (the cohesion spine): the **cortex shell + PostFX operate at BEHAVIORAL-STATE level**
(hold / verify-success / mode / route) — never per-tool (that would strobe unreadably). Per-tool /
per-hub detail belongs to the interior **NodeLattice** and per-lobe firing to **CorticalSignals waves**.
This keeps every layer DISTINCT yet COHESIVE: shell (states) ≠ lattice (compute) ≠ nerves (direction)
≠ galaxy (skill-field). All read as one organism because they share the same SCENE_UNIFORMS leaves and
the same `AdditiveBlending + depthWrite:false + near-black` identity, with the bloom knee (1.0) as the
single mechanism that keeps the atmosphere recessive and only the brain's fired elements glowing.

### A.2.1 Cortex shell — ambient skin; deepen the broadest state, never clutter
- **Real-vs-decoration:** correctly the always-on SKIN. Its only honest gap is that the brain visibly
  responds to approvals (`uHold`) but is BLIND to its own cognition bursts (`uBurst` computed but not
  injected, `:653-654` vs `:1185`).
- **Premium upgrade C1 (canon-AMBER) — inject `uBurst` as a mild whole-shell emissive lift.** Add
  `shader.uniforms.uBurst = uniforms.uBurst` at `:653-654`; after the hold tint (`:798`) add a small
  burst term to the EXISTING emission (no palette change — the region colors brighten briefly, ~0.3 s).
  Semantics: a verified-correct moment (VERIFICATION GREEN / synapse storm) flushes the whole cortex
  more radiant. `uBurst` already exp-decays at 3.5/s — no new logic. **MUST bump `customProgramCacheKey`
  to `superbrain_v7_${tier}` (`:808`)** or the new uniform is silently dropped. Honest dormancy: idle
  `uBurst=0` → zero contribution → exact canonical appearance.
- **Premium upgrade C3 (canon-RED) — `uCloudRoute` on the CASING iridescence.** A module-level
  `CASING_CLOUD_UNIFORM={value:0}` (the casing is a SEPARATE material — it CANNOT come through
  SCENE_UNIFORMS) + a subscriber on `route` events reading `event.data.privacy`; blend a faint warm
  bias into the iridescence phase at `:598` ("knowledge leaving the machine" on the outer skin when
  cloud-routed). Lowest-priority visual edit; explicit sign-off + before/after.
- **Non-visual correctness (Green) — C2:** add `self_analy|propose_fix` to the CAUSAL arm of
  `waveLabelForTool` (`:492`) so introspection tools light the frontal lobe instead of falling to
  SIGNAL. Leave the dead `web|fetch|grep|inspect` arm inert (removing it is noise; it costs nothing).

### A.2.2 CorticalSignals — the cleanest data-binding in the scene
- **Real-vs-decoration:** wave-biased blinking is genuinely data-true (real tool dispatch → anchor →
  the temporal/frontal/parietal/occipital fireflies near that lobe fire brighter). Strongest honest
  layer on the cortex.
- **Premium upgrade S1 (canon-AMBER, low priority) — per-lobe wave-flash color reveal.** Bake a SECOND
  static attribute `aWaveColor` during the surface-sampling `useMemo` (the nearest of the 8 region
  constants by the same `az`/`h` coords `applyRegionVertexColors` uses). At REST show `aColor` (identical
  to today); on a wave hit, `mix(vColor, vWaveColor, vAlpha*prox*0.6)`. Makes "which lobe a tool
  activated" legible without any new data source. No new uniform, no palette change at rest.
- **DO NOT** inflate the firefly count back to 320 — the deliberate calm (180/110/50) lets the interior
  lattice read as the star (comment `:911`).

### A.2.3 NeuralAura — most data-true atmosphere; one constitutive add
- **Real-vs-decoration:** mode color + hold amber make it the organism's mood ring at the broadest
  affective level — correct granularity. Gap: the brain literally vocalizes but the breath-film does
  not respond.
- **Premium upgrade A1 (Green) — `voice-speaking` membrane swell.** Module-level `VOICE_PULSE={value:0}`
  + a `subscribeCognition` for `voice-speaking` (real type, zero current consumers): on the event,
  `VOICE_PULSE.value = max(VOICE_PULSE.value, event.intensity ?? 0.5)`; decay ~6/s in `useFrame`; add
  a small `uVoicePulse` term to the membrane alpha-cap lift at `:97` (lift the cap from 0.25 to ~0.30
  ONLY while speaking). Three distinct honest signals stay separate: burst (sharp verify), breath (slow
  systole), voice (short, word-boundary cadence). Honest dormancy: silence → decays to 0 → baseline.
- **Premium upgrade A2 (Green, low priority) — spark-count tier gate.** Accept a `sparkCount` prop
  (high 50 / med 30 / low 15); memoize the spark geometry on it. Consistency only; 50 is fine on 16 GB.

### A.2.4 AccretionCore — the knowledge stomach; deepen the existing single binding
- **Real-vs-decoration:** `knowledge-acquired`→pulse is the cleanest single binding; the 4 tints carry
  no meaning (random `pickTint`), yet the adapter already labels every event with its knowledge TYPE.
- **Premium upgrade AC1 (Green) — label-to-tint bias.** In the EXISTING subscriber (`:169`), parse
  `event.label` to resolve a target tint and drive a new `uTintBias` (vec4 weight per slot, decays with
  `pulseRef` over ~1.2 s). Mapping (labels already emitted by the adapter): `VERIFICATION GREEN`→cyan;
  `trail #N reinforced`/`SKILL MASTERED`→amber (earned); `CAPABILITY EARNED`/`AUTONOMOUS ACTION`→rose;
  `CODE EMITTED`/`SYNTHESIS COMPLETE`→violet. Disk shape/motion unchanged; only the predominant feeding
  hue shifts during the window. Zero new backend data. **Keep `knowledge-acquired` the ONLY binding —
  do NOT add `agent-dispatch` (that conflates intake with action).**
- **OPEN QUESTION:** `VERIFICATION RED` would map to rose — accurate ("ingested error") but may read
  as "disk broken." Confirm or remap (see open questions).

### A.2.5 CosmicBackground — the voyage field; hold dilation already perfect
- **Real-vs-decoration:** the hold dilation ("the cosmos holds its breath" for a real pending decision)
  is the single most important macro behavioral signal in the whole scene. Gap: drift speed is constant
  regardless of cognitive intensity (no `uActivity` threaded).
- **Premium upgrade CB1 (Green) — activity-proportional drift.** Thread `activity` as a prop and change
  `:136` to `+= delta*(1 - 0.7*hold.blend)*(0.85 + activity*0.3)` — the voyage accelerates ~30% when
  synthesizing. One multiply; no shader change; honest dormancy (idle → canonical speed). Do NOT do the
  optional "absorbed-star domain color" (CB2) — the AccretionCore already owns "what was ingested";
  double-encoding it on the field risks blur.

### A.2.6 KnowledgeHorizon — the photographic dome; accept + minimally polish as atmosphere
- **Real-vs-decoration:** correctly near-fully ambient — it is the deep-space CONTEXT the brain voyages
  through, not a reaction surface. The 3% `uActivity` opacity lift (`:286`) is the right ceiling; the
  Hubble-SHO palette is the operator's authored cosmos.
- **Premium upgrade (Green, optional, coherence-only) — drift speed ∝ activity.** `driftForward =
  time*(0.0006 + uActivity*0.0004)*(1-uReducedMotion)` (`uActivity` is already a uniform here). Only do
  it ALONGSIDE CB1 so the dome and the field accelerate together. **Keep the palette static; add no bus
  subscriber; add nothing per-fragment** (this dome is the heaviest fragment cost in the scene — high-
  tier 4-octave volumetric).

### A.2.7 PostFX — the whole-frame emotional register; highest wow-per-effort
- **Real-vs-decoration:** 100% static today. The architecture is clean for a live grade — but
  `wrapEffect` blocks direct mutation.
- **Premium upgrade PFX1 (canon-AMBER) — live grade on hold / verify / mode.** **Architecture
  prerequisite (mandatory):** replace the bare `wrapEffect(GradePostEffect)` with a `useMemo`-held
  instance exposed via `useRef` (or a `forwardRef` wrapper) so its `uniforms` Map is mutable from a
  `useFrame`. Then drive THREE behavioral grades, easing, never strobing, all within a SMALL envelope
  around the authored `POST_FX.grade` values:
  - **Hold** (read `SCENE_UNIFORMS.uHold > 0.1`): ease `uHighTint` toward warm amber-gold (the "golden
    pause" while the operator decides); ease back on resolve.
  - **VERIFICATION GREEN / verify-burst:** spike `uVibrance` from 0.21 to ~0.55 for ~0.8 s, `exp`-decay
    — the single most-saturated frame the operator ever sees (the "VERIFY PASS" moment, whole-frame).
  - **Mode:** observe→slightly cooler `uShadowTint`/`uHighTint`, synthesize→neutral-warm, orchestrate→
    slightly more saturated; ease over ~2 s (rare changes → a prop-rebuild path is acceptable for mode).
  - Keep `uContrast` (GradePre) static — it is a scene-referred HDR op; making it dynamic risks clipping.
  - No new pass; uniform-mutation only; idle rests at `POST_FX.grade` defaults (honest dormancy).
  - **DO NOT** fire on `agent-dispatch` (per-tool) — strobe.

---

## A.3 PART A — PHASED, IMPORTANCE-RANKED BUILD PLAN

All phases LOWER priority than the alive-being core (lattice/nerves). Each ends at HIS browser sign-off.
Lab-first → `npm run port` → his browser → canon tag + goldens. ⚡ = FIDELITY-safe quick win; ⚠ = blind/
riskiest step (judgeable only in his browser).

**Phase A0 — FIDELITY baseline (gate, no code) ⚡.** Confirm canon tag exists; capture before-goldens
of `?ui=superbrain` in HIS browser. Data shown: none. Lab-only.

**Phase A1 — Atmospheric data-truth bundle (the proportionate core of this lens) ⚡.** All additive,
no backend, no palette change, lab-first:
- AC1 (AccretionCore label→tint) — knowledge TYPE on ingestion. Green.
- A1 (NeuralAura `voice-speaking` swell) — speech cadence made physical. Green.
- CB1 (CosmicBackground activity-drift) + the matching KnowledgeHorizon drift tie — voyage accelerates
  when thinking. Green.
- C2 (`waveLabelForTool` `self_analy|propose_fix`→CAUSAL) — correct lobe on introspection. Green.
- A2 (spark tier gate) — consistency. Green.
**Data shown:** ingestion type, speech, cognitive intensity, introspection anatomy. **Gate:** each
reads as intended, none strobes. **Riskiest:** none (all additive, dormancy-clean). Lab-first.

**Phase A2 — The whole frame breathes: PostFX live grade (PFX1) ⚠.** Do the `wrapEffect`→`useMemo`/
ref refactor FIRST, then wire hold/verify/mode. Highest wow-per-effort for the operator's eye.
**Data shown:** golden-amber pause on hold; peak-saturation frame on VERIFY GREEN; mode grade.
**Gate:** grades read as intended, never flicker. **Riskiest/blind:** the refactor + WebGL-only
verification; canon-AMBER (stays within the `POST_FX.grade` envelope). Lab-first.

**Phase A3 — Per-lobe synapse legibility: CorticalSignals wave-flash color (S1) (canon-AMBER, low pri).**
**Data shown:** the anatomical lobe color flashes when its tool's wave passes. **Gate:** base appearance
identical at rest; flash reads as lobe identity. Lab-first.

**Phase A4 — Cortex burst flush: `uBurst` injection (C1) ⚠ canon-AMBER.** Inject `uBurst` + bump
`customProgramCacheKey` to `v7`. **Data shown:** whole-cortex shimmer on verified success. **Gate:**
his browser — flush reads as a flush, not a strobe; idle is byte-identical to canon. **Riskiest:**
forgetting the cache-key bump (silent no-op); a cortex shader edit needs explicit sign-off. Lab-first.

**Phase A5 — Cloud-voyage accent: casing `uCloudRoute` (C3) ⚠ canon-RED, lowest priority.** Separate
casing uniform + `route` subscriber. **Data shown:** faint warm iridescence bias when cloud-routed.
**Gate:** explicit operator sign-off + before/after + goldens (changes casing visual character).
Backend-status: relies on the already-real `route` event — NOT backend-blocked. Lab-first.

**Honest-dormancy / backend-blocked:** no Part-A item is backend-blocked — every binding uses an event
the bus already carries. All atmosphere layers are correctly always-on (they represent "the brain
exists / voyages"); the live signals all rest at neutral at idle.

---

# PART B — MEMORY / RECALL

## B.1 VERIFICATION LEDGER (TRUE with file:line; lens errors; ambient vs data-bound)

### B.1.1 Confirmed TRUE this session

**MemoryGalaxy (the exterior macro skill-field).**
- `MAX_STARS=128` (`:23`), one `THREE.Points` draw call. 9 attributes (`:101-105`): `aRadius aAngle
  aSpeed aHeight aWobble aSize aStrength aQuarantine aFlash`. `aFlash` pre-seeded to `-10` (`:110`) so
  the galaxy stays calm at mount. ✔ Confirmed.
- `aHeight = -1.4 + hash01(id,4)*4.6` (`:145`) — PURELY hash-based; `trail.freshness` is UNUSED here.
  `aSize = 2.4 + min(walks,12)*0.55` where `walks = success_count+reuse_success_count` (`:147-148`).
  `aStrength = clamp(trail.strength,0,1)` (`:149`). NO `aStatus` attribute, NO candidate dimming. ✔.
- Flash subscriber (`:165-179`): on `telemetry`→`sync()`; on `knowledge-acquired`|`burst`, match
  `/trail #(\d+)/` against **`event.detail`** only (`:172`). ✔.
- Honest dormancy `if (starCount === 0) return null` (`:188`) — gold standard. ✔.
- `TrailRow` (`aiosAdapter.ts:498-509`): `skill_id, goal_pattern, status, quarantined, success_count,
  reuse_success_count, failure_count, reuse_failure_count, strength, freshness`. **NO `superseded_by`,
  NO `updated_at`.** ✔ Confirmed.

**MASTERY-FLASH BUG (confirmed).** The `SKILL MASTERED — TRAIL #N` event puts the trail number in
`event.label` and sets `event.detail = trailLabel(goal_pattern).toLowerCase()` (`aiosAdapter.ts:686-687`).
The galaxy regex checks `event.detail` only (`:172`) → **mastery flashes are silently missed.** The
`trail #N reinforced` path DOES work (`detail` carries it, `aiosAdapter.ts:668`). ✔ Confirmed bug.

**CognitiveGrasp (the retrieval ACT).**
- `SLOT_SECONDS=6` (`:11`); `absoluteSlot = floor(elapsed/6)`, `activeTarget = absoluteSlot % 4`
  (`:308-310`). `trailForSlot(slot) = trails[slot % trails.length]` (`:35-39`) — real trail per slot,
  wearing real `strength`/`freshness`/`walks`/`quarantined` (`:617-621`). ABSORB at phase 0.82-0.92
  (`:20-23`, `:389-409`) publishes a `burst` (NOT `knowledge-acquired`) carrying the real
  `trailLabel(goal_pattern)` (`:398-407`). 4 authored deep-space targets at z -5.1..-7.2 (`:100-135`).
  Honest dormancy `if (!hasTrails) return null` (`:754`), poll every 5 s (`:738-742`). **It imports
  `publishCognition` but NOT `subscribeCognition` — ZERO bus subscription; timing is pure wall-clock.**
  ✔ Confirmed.

**RegionPins (4 real metric channels).**
- 4 `Html` chips RESEARCH/MEMORY/TOOLS/SIGNALS (`:43-74`); anchors EXACTLY match `WAVE_REGION_ANCHORS`
  (RESEARCH frontal `(0,0.26,0.48)`, MEMORY temporal `(0.34,0.16,0.11)`, TOOLS parietal `(0,0.61,0.11)`,
  SIGNALS occipital `(0.05,0.31,-0.38)`). `useMetric`/`useMetricHistory` from `metricsStore`. ✔.
- Metric channels (`aiosAdapter.ts:654-659`): `research=verified_success_rate*100`,
  `tools=verification_coverage*100`, `memory=avg verified trail strength*100`, `signals=avg freshness*100`.
  So the "TOOLS" pin actually shows verification coverage — **semantically mislabeled.** ✔.

**metricsStore BUMP-ROUTING BUG (confirmed).** `metricsStore.ts:112-114`:
`const label = (event.label ?? '').toLowerCase(); const matched = METRIC_KEYS.find(key =>
label.includes(key)); const key = matched ?? METRIC_KEYS[rotation++ % length]`. `METRIC_KEYS =
['research','memory','tools','signals']`. Real labels (`VERIFICATION GREEN`, `SKILL MASTERED — TRAIL #N`,
`TRAIL WEAKENED`, `CAPABILITY EARNED`, …) contain NONE of those strings → bumps ALWAYS fall to
round-robin → **pins bump on real events but route to the WRONG channel** (semantically random). The
20 s `telemetry` poll still sets the correct base values. ✔ Confirmed bug.

### B.1.2 What the lenses got WRONG

1. **❌ Lens 3 "TrailRow carries `updated_at`" (used to justify CPU-side freshness).** WRONG — there is
   no `updated_at` in the interface (`:498-509`). But `freshness` IS a real field (`:508`) — so the
   MG2 freshness-altitude upgrade is still valid; just bind to `trail.freshness` directly, NOT a
   computed `updated_at`.
2. **❌ Lens 2 "`aStatus` ... whether it is currently used in the shader is unverified."** Now verified:
   there is NO `aStatus` attribute at all (`:101-105`) and no status dimming. The MG1 upgrade is
   genuinely absent (buildable).
3. **❌ Any `superseded_by` ghost-star / lineage rendering.** BLOCKED — the FK is absent from the
   frontend `TrailRow` (`:498-509`); only the aggregate `TrailMapResponse.summary.superseded` count
   exists (`:513`). Render nothing until the backend adds the per-row FK.
4. **CONFIRMED-CORRECT lens flags:** mastery-flash bug, CognitiveGrasp wall-clock-only, metricsStore
   bump bug, TOOLS mislabel — all four survive scrutiny and are buildable fixes.

### B.1.3 Ambient vs data-bound

| Layer | Data-bound (REAL) | Ambient (correctly atmosphere) | Gap |
|---|---|---|---|
| **MemoryGalaxy** | every star = a real `TrailRow`; size=walks, brightness=strength, red=quarantine, flash=reinforce/recall | orbit radius/angle/speed/wobble (deterministic-by-id; stable across sessions) | mastery-flash missed; no candidate dimming; freshness unused; lineage blocked |
| **CognitiveGrasp** | trail DATA per slot; absorb burst label + intensity (∝ real strength) | 4 authored target positions; the slot animation choreography | TIMING is wall-clock, not the real recall event |
| **RegionPins** | 4 real backend metric channels; real poll-history sparkline | offline demo drift | bump routing broken (round-robin); TOOLS mislabel |

---

## B.2 PER-LAYER ASSESSMENT + HONEST PREMIUM UPGRADE

Cohesion: MemoryGalaxy is the **exterior macro skill-field** (the constellation of ALL trails, the
accumulated past) — DISTINCT from the interior NodeLattice (micro, current-turn compute) and from
CognitiveGrasp (the retrieval ACT). They never overlap spatially (galaxy radius 7.5-13; grasp targets
at z -5.1..-7.2; lattice inside the cortex). RegionPins are the only DOM-in-3D semantic labels and
must stay minimal.

### B.2.1 MemoryGalaxy — near-fully data-true; three honest deepenings + one blocked
- **MG3 (Green, bug fix, DO FIRST) — mastery-flash regex.** Add a second branch matching
  `/TRAIL #(\d+)/i` against `event.label` (alongside the existing `event.detail` match) so the
  `SKILL MASTERED — TRAIL #N` event flashes its star. One regex; zero visual change at rest.
- **MG1 (Green) — candidate dimming.** Add `aStatus` (or fold into `aStrength`): in `sync()`,
  `aStrength_effective = clamp(strength,0,1) * (status==='verified' ? 1.0 : ~0.45)`. Verified trails
  are the bright constellation; candidates the dim halo. `status` is already in the row.
- **MG2 (Green) — freshness → altitude.** Replace the purely-hashed `aHeight` (`:145`) with a freshness
  blend, e.g. `hash01(id,4)*2.0 + trail.freshness*2.5 - 1.4`: fresh trails orbit high (the active crown),
  stale trails drift low (the forgotten past). `freshness` is a real `TrailRow` field (`:508`).
- **MG4 — superseded ghost stars: BLOCKED** (no `superseded_by` in the row). Render nothing until the
  backend adds the FK (operator decision; see open questions).

### B.2.2 CognitiveGrasp — the retrieval act; close the clock-vs-event gap (the single most important
Memory/Recall upgrade)
- **CG1 (Green) — event-driven slot acceleration.** Add a `subscribeCognition` (currently absent) for
  `knowledge-acquired` events whose `detail` matches `/trail #(\d+)/`; when a known trail is recalled,
  target/accelerate the next slot toward THAT trail (a module-level `pendingRecall` ref checked at slot
  start). Keep the 6 s wall-clock cycle as idle fallback. Effect: when the brain ACTUALLY recalls
  trail #7 during a `query_skills`, the next emission targets trail #7 — the animation answers the real
  recall, not the clock. No geometry/material change.
- **CG2 (low priority) — region-direction tie.** Loosely associate the 4 targets with the 4 anatomical
  regions so recall returns from where the knowledge was encoded. Authored-position work; only after CG1.

### B.2.3 RegionPins — real metrics; two correctness repairs + optional extras
- **RP2 (Green, bug fix, highest correctness-per-effort) — bump routing.** In `metricsStore.ts:113`,
  replace `label.includes(key)` (which never matches) with real-label routing, e.g.
  `verification`→`tools`; `trail`/`skill`/`mastered`→`memory`; `capability`/`autonomous`→`research`;
  else→`signals`. Pins then tick on the correct channel for real events instead of waiting 20 s and
  routing randomly. Store logic only; zero visual change at rest.
- **RP1 (Green) — rename "TOOLS" → "VERIFY"** (`RegionPins.tsx:59`) to match its real metric
  (`verification_coverage`). Honest label; no data change.
- **RP3 (optional, canon-AMBER) — 5th AUTONOMY pin** from `getAutonomy()`/`earnedAutonomy.earned`,
  rendered ONLY when telemetry is non-null (honest dormancy). Operator call — the 4-pin layout is
  intentional; the cerebellum has no wave anchor (would be an authored position).
- **RP4 (optional, canon-AMBER) — alarm tint** on the SIGNALS pin when `chainValid === false`. One
  conditional class.

---

## B.3 PART B — PHASED, IMPORTANCE-RANKED BUILD PLAN

Lower priority than the alive-being core; proportionate (these are mostly one-line fixes + small additive
attributes). Each ends at HIS browser sign-off; lab-first.

**Phase B0 — FIDELITY baseline ⚡.** (Shared with A0.) Confirm canon tag; before-goldens.

**Phase B1 — Correctness bundle (trivial, zero/near-zero visual risk) ⚡ ★ DO FIRST.**
- MG3 (mastery-flash regex) — galaxy now flashes on mastery. Green.
- RP2 (metricsStore bump routing) — pins tick on the correct channel on real events. Green.
- RP1 (TOOLS→VERIFY) — honest label. Green.
**Data shown:** mastery moments; live correctly-routed metric ticks; honest channel name. **Gate:** his
browser — mastery flash fires; pins move on a real event. **Riskiest:** none. Lab-first.

**Phase B2 — Galaxy skill-maturity (additive attributes, no palette change) ⚡.**
- MG1 (candidate dimming) + MG2 (freshness altitude).
**Data shown:** verified vs candidate maturity; recent vs forgotten as orbital altitude. **Gate:** his
browser — verified stars read brighter; fresh skills orbit high. **Riskiest:** low (one attribute each).
Lab-first.

**Phase B3 — Recall becomes honest: CognitiveGrasp event-driven (CG1).** Add the subscriber + slot
acceleration; keep wall-clock fallback. **Data shown:** the grasp answers the ACTUAL recall event.
**Gate:** his browser — a real `trail #N` recall redirects the next emission; idle still cycles.
**Riskiest:** slot/ref timing discipline (medium). Lab-first.

**Phase B4 — Optional extras (operator call).** RP3 (AUTONOMY pin), RP4 (chain alarm tint), CG2
(region-direction tie). Each canon-AMBER (new/conditional UI). Gate per item.

**Backend-blocked / honest-dormant (render nothing until backend provides):**
- **MG4 superseded ghost stars** — needs `superseded_by` added to the per-row `TrailRow` payload
  (`aiosAdapter.ts:498-509`). Until then render nothing for lineage.

---

# C. CROSS-CUTTING RISKS · PERF · FIDELITY CLASSIFICATION

## C.1 FIDELITY class per change (gate required)
| Change | Class | Gate |
|---|---|---|
| AC1, A1, A2, CB1, horizon-drift, C2 | Green | lab-first, his browser |
| MG3, MG1, MG2, RP1, RP2, CG1 | Green | lab-first, his browser |
| S1 (firefly wave-flash), C1 (cortex `uBurst`), PFX1 (live grade), RP3, RP4, CG2 | canon-AMBER | lab-first + his browser sign-off + goldens |
| C3 (casing `uCloudRoute`) | canon-RED | explicit operator sign-off + before/after + new canon tag |

## C.2 Perf budget (16 GB; Ollama can evict the GPU)
The whole two-lens roadmap adds, at most: ~3 new scalar/vec uniforms (cortex `uBurst`, AccretionCore
`uTintBias`, NeuralAura `uVoicePulse`, PostFX live-mutation of EXISTING uniforms), 1-2 baked static
attributes (CorticalSignals `aWaveColor`, MemoryGalaxy `aStatus`), a few subscribers, and one extra
regex per bus event. **No new draw calls, no new geometry, no new PostFX pass.** Marginal GPU cost is
sub-1% on any tier. Heaviest EXISTING costs are untouched and stay tier-gated: KnowledgeHorizon high-
tier 4-octave volumetric and the cortex 2-octave Voronoi — add nothing per-fragment to them.

## C.3 Distinct-yet-cohesive (the layering must be preserved)
Shell = behavioral states · CorticalSignals = per-lobe surface firing · NeuralAura = mood/breath/voice ·
AccretionCore = ingestion type · CosmicBackground = the voyage · KnowledgeHorizon = the photographic
context (recessive, below the bloom knee) · PostFX = whole-frame register · MemoryGalaxy = exterior
skill-field · CognitiveGrasp = the retrieval act · RegionPins = semantic labels. The bloom knee (1.0)
keeps the atmosphere recessive; never raise atmosphere output across it.

## C.4 Cross-effort risks
- **Headless-blind WebGL.** Every visual phase ends at HIS browser; before/after; canon tag + goldens.
- **`customProgramCacheKey` not bumped** on the cortex `uBurst` inject → silent no-op. Mitigation: bump
  to `v7` is part of C1; verify the burst flush actually appears.
- **`wrapEffect` mutation trap** (PFX1). The refactor to a ref-held instance is MANDATORY and is the
  blind step — verify the grade actually moves before wiring all three states.
- **Fabrication drift.** Never re-introduce: the cortex gradient, `uBurst` in cortex "already wired,"
  Lens-1 tint percentages, `toneMappingExposure 1.6`, a frontend `superseded_by`/`updated_at`.
- **Stale doc.** `PostFX.tsx:15` comment says exposure "1.6"; the real constant is 1.45 — cheap fix.

---

# D. TOP RECOMMENDATIONS + OPEN QUESTIONS

### TOP RECOMMENDATION — PART A (Cortex/Atmosphere)
**Build the Phase A1 atmospheric data-truth bundle next** (AC1 + A1 + CB1/horizon-drift + C2 + A2). It
is the proportionate, FIDELITY-SAFE core of this lens: all additive, no backend, no palette change, each
closing a genuine honest gap (ingestion TYPE, speech cadence, cognitive intensity, introspection
anatomy) the bus ALREADY carries. It elevates the atmosphere to data-true without touching the frozen
cortex. **Then PFX1 (PostFX live grade)** as the single highest wow-per-effort step once its `wrapEffect`
refactor is done — the golden pause + the peak-saturation VERIFY frame are the two whole-organism
moments that matter. Defer the canon-AMBER/RED cortex edits (C1, S1, C3) until the safe wins are signed off.

### TOP RECOMMENDATION — PART B (Memory/Recall)
**Build the Phase B1 correctness bundle next** (MG3 mastery-flash regex + RP2 metricsStore bump routing
+ RP1 TOOLS→VERIFY). These are near-zero-risk one-line/one-attribute fixes with the highest
correctness-per-effort in either lens — they make ALREADY-data-true elements actually fire on real
events (the galaxy on mastery; the pins on the right channel). **Then CG1 (CognitiveGrasp event-driven
recall)** — the single upgrade that crosses the retrieval act from "simulated every 6 s" to "answers
the actual recall," the most meaningful Memory/Recall deepening.

### OPEN QUESTIONS FOR THE OPERATOR
1. **AccretionCore `VERIFICATION RED` → rose (AC1):** accurate ("ingested error") but may read as "the
   disk is broken." Keep it, or remap RED to a quieter treatment?
2. **PostFX live-grade implementation (PFX1):** approve the `wrapEffect`→ref/`useMemo` refactor (the
   only non-trivial part)? Per-frame mutation for vibrance/hold; prop-rebuild acceptable for mode.
3. **Cortex `uBurst` flush (C1):** approve a canon-AMBER cortex shader edit (whole-shell shimmer on
   verified success), with the mandatory `customProgramCacheKey` → `superbrain_v7_${tier}` bump?
4. **Casing `uCloudRoute` (C3):** want the local-vs-cloud voyage accent on the casing iridescence (the
   only canon-RED edit here), or leave the shell free of route signaling?
5. **MemoryGalaxy superseded lineage (MG4):** approve adding `superseded_by` to the per-row trail
   payload so the galaxy can render lineage? (Until then it renders nothing.)
6. **RegionPins AUTONOMY pin (RP3):** add a 5th authored pin from `earnedAutonomy.earned`, or keep the
   intentional 4-pin anatomical layout?
7. **CorticalSignals wave-flash color (S1):** worth the canon-AMBER attribute add for per-lobe legibility,
   or is the current wave-biased brightness enough?

---

**The final aesthetic call is, and remains, the OPERATOR'S BROWSER. Nothing here is "done" until it is
signed off there. WebGL cannot be verified headlessly. These two lenses are an ELEVATION, not a rebuild —
keep them proportionate to their LOWER priority beneath the alive-being core.**
