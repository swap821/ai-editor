# NERVOUS_SYSTEM_REIMAGINATION.md

> Design-engineer research + judgment on giving the nervous system its **own visual
> identity** — SIGNAL TRANSMISSION, distinct from the brain's tissue/mass — while staying
> cohesive with the superbrain-voyaging-the-infinite soul.
> **RESEARCH ONLY (2026-06-15).** No code edited, no build. The visual call is the operator's
> browser (FIDELITY law). Supersedes nothing; complements `NERVOUS_SYSTEM_REDESIGN.md`
> (that doc solved *topology / control-bus wiring*; this doc solves *visual identity / material*).

---

## 0. The problem, restated precisely

The operator's verdict: the brain and its work-bus now read as the **same entity** — the
same teal, organic, volumetric glowing tissue. There is no perceptual line between "the mind"
and "the conduits that carry its commands." The fix is **a new visual category** for the nerves:
they must read as **signal-in-transit** (flow / conduit / directed energy / data-on-a-wire),
NOT as tissue/mass/soft-breathing-glow. **The cortex BREATHES; the nerves must TRANSMIT.**

This is an **identity** change (form / material / motion), explicitly **NOT a topology** change.
Every hard constraint below is preserved.

### Why they currently merge — verified in code, not asserted

The nerves read as tissue because of **four levers in `WIRE_FRAGMENT`** (`NervousSystem.tsx`):

| # | Lever | Line | What it does | Whose language it is |
|---|---|---|---|---|
| 1 | **Opaque teal body** | 66 (`vColor*0.75`), 89 (`alpha 0.95`) | a fat, solid, lit cable | MASS / tissue |
| 2 | **Fresnel rim → amber** | 62-66 (`pow(1-dotNV,3.5)`, `RIM_AMBER`) | a luminous *surface edge*; the comment literally calls it "the living-tissue fresnel edge" | MASS / surface |
| 3 | **Breath sinusoid** | 74 (`sin(uTime*2 - vUv.x*5)`) | the cable inhales/exhales in place | BODY / organism |
| 4 | **NormalBlending, opaque** | 206-207 (`NormalBlending`, `depthWrite:true`) | the cable occludes, reads as solid matter | MASS |

These four are **exactly** the cortex's own vocabulary. The cortex (`SuperbrainScene.tsx:514-520`)
is "color is LIGHT not paint": near-black base 0.08 → core glow 0.18 → SSS 0.3 → **fresnel rim
1.2-1.6** → filaments 2.2. The nerves borrow #1/#2/#3 from that ladder, so the eye files them
under the same heading. **Invert those four levers and the nerves leave the "tissue" category.**
All three submitted concepts correctly identify these four levers — that convergence is itself
strong evidence the levers are the right ones.

### The single most important technical fact (decisive for the judging)

**Bloom in this scene is GLOBAL and luminance-keyed, not selective/emissive.**
`constants.ts:193` → `bloom: { intensity: 2.5, luminanceThreshold: 1.0, luminanceSmoothing: 0.9 }`,
mounted once in `PostFX.tsx:165` as a single `<Bloom>` pass over the whole composited frame,
sampled **PRE-exposure in linear space** (knee = `smoothstep(1.0, 1.9, sceneLuma)`). The entire
world is hand-tuned to that 1.0 knee: cortex rim 1.2-1.6 blooms 13-74%, filaments ~2.2 bloom
fully, and **everything else is clamped ≤0.5 with deliberate 2× headroom** (see the luminance
discipline in `CognitiveGrasp.tsx:63-74` and `KnowledgeHorizon.tsx:277-284`).

Two consequences that the concepts get **partly wrong** and that the recommendation must fix:

1. **For a packet to read as "light-in-transit," it must cross the 1.0 linear knee.** Pure cyan
   `(0,1,1)` has Rec.709 luma `0.7152+0.0722 = 0.787` — *below* 1.0. At a 1.0× multiplier a cyan
   packet would **not bloom at all** (it'd be a flat bright line). So the high multiplier
   (`*3.5` in Concepts 1/2, `*3.5` in Concept 3) is **not optional flourish — it is the
   mechanism**: `cyan * 3.5` → luma ~2.75 → blooms fully, exactly like the filaments. This is
   correct and must be kept, exposed as a uniform for in-browser tuning.
2. **`react-postprocessing` `Bloom` does NOT read a material's `emissive` channel.** It thresholds
   final scene luminance. **Concept 3's step 5** — adding `emissive: 0x00ffff` +
   `emissiveIntensity` so "the PostFX bloom selector tells it which pixels are light" — is
   **factually incorrect** for this pipeline (it would do nothing useful and the `ShaderMaterial`
   has no `emissive` uniform anyway). The correct mechanism is purely "make the packet's output
   luminance > 1.0," which the multiplier already does. **This is a real error in Concept 3's
   technique and a reason it ranks third.**

### The second decisive fact — AdditiveBlending is *idiomatic here, not novel risk*

The nerves are the scene's **only** opaque, `NormalBlending`, `depthWrite:true` light element.
Every other glowing subsystem already uses **`AdditiveBlending` + `depthWrite:false` +
`toneMapped:false`**: `AccretionCore.tsx:236`, `CognitiveGrasp.tsx:501/516/528/546/564/669/684/696/720`,
`NeuralAura.tsx:269/280/395`, `MemoryGalaxy.tsx:120`, `CorticalSignals.tsx:264`,
`CosmicBackground.tsx:146`, and the cortex filament shell `SuperbrainScene.tsx:831`. So flipping
the nerves to additive doesn't introduce a foreign technique — **it makes the nerves consistent
with how this scene already renders "energy."** This materially de-risks Concepts 1 & 2 (their
core move is "go additive like everything else that is light") and is the strongest single
argument that the right answer is *already proven idiom in this codebase*.

---

## 1. Hard constraints (a concept that violates any of these cannot ship)

1. **Control-bus function preserved.** Tips still land at the canon ports — left `(-4.8,-1.7)`,
   right `(+4.8,-1.5)`, spinal `(0,-2.6,1.5)`; `tabX=4.82` framing untouched
   (`NervousSystem.tsx:191,224-225,307,324,340`). **Reimagine form/material/motion, NOT where
   nerves connect.** All three concepts respect this (shader-only / material-only). ✔
2. **Real cognition still drives it.** `uBurst` (← `WIRE_BURST_UNIFORM`/`burst.current.intensity`,
   lines 94,199,213) must still brighten on a real event; `uHold` (← `SCENE_UNIFORMS.uHold`) must
   still quiet on approval. Same uniforms, reinterpreted meaning. ✔ all three.
3. **Cohesive-but-distinct.** Same dark-cosmic world, same palette *family*, same premium bar —
   but a clearly different entity. Must avoid BOTH failure modes: the OLD rainbow wisps
   (disconnected) AND the current over-matched teal axons (merged).
4. **Perf (16GB, frame sacred).** Single merged draw call / instanced / shader; tier-scalable;
   **no per-frame allocations.** The 115-tube merged geometry (`mergeGeometries`, line 347) and
   its baked attributes must be reused untouched. WebGL2 / GLSL ES 1.0 (TSL/WebGPU = future note).
5. **Canon / FIDELITY.** Any *build* is lab-first (`GAG demo/gag-orchestrator/...`) + full gate
   (operator-browser sign-off, before/after goldens). A material change to the canon
   `NervousSystem.tsx` is a **lab edit + `npm run port`** and **does** trip the FIDELITY gate
   (re-tag + re-golden + his-browser parity) — it is NOT zero-cost. This is honestly the one tax
   all three concepts share, because the nerve shader lives in a ported canon file.

---

## 2. The three submitted concepts, distilled

All three are the **same core inversion**: dark carrier + bright discrete cyan packets + additive
+ no breath/rim. They differ mainly in framing, precision, and a few technical correctness points.

- **Concept 1 — "Signal Streams"** (conf 0.87). Conduit nearly vanishes; only bright cyan
  light-packets stream root→tip. Dark-teal sheath at 2-5% opacity, additive, no rim/breath. Motion
  = pure translation vs the brain's in-place pulse ("opposite motion vocabularies"). ~30-line frag
  rewrite. **Cleanest articulation of the *motion-language* contrast.** Slightly vague on exact
  packet math and bloom-knee crossing.

- **Concept 2 — "Fiber-Optic Control-Bus"** (conf 0.92). The most **precise and code-grounded**:
  names exact line edits (54,52-66,74,68-71,76-83,206), exact smoothstep retunes
  (`0.85,0.88 / 0.98,0.95`, `wake=0`), `wireColor=vColor*0.08`, `+signalColor*packet*3.5`, surge
  `(1+uBurst*2.5)`, hold `mix(1,0.2,uHold)`, `AdditiveBlending`. Idle/normal/burst/hold motion
  states fully specified ("packets **freeze mid-cable** on hold" — a genuinely better hold read
  than just dimming). Per-region tints kept as a *whispered* undertone. Risk table is the most
  honest (names additive stack-up + bloom threshold). **Most build-ready; fewest errors.**

- **Concept 3 — "Energy Transmission Conduits"** (conf 0.89). Same inversion, richest prose, keeps
  the LEFT/RIGHT/SPINAL triadic tints as the carrier base at 0.08-0.12. **But contains a real
  technical error**: step 5's `emissive:0x00ffff` + "bloom selector" does not work with this
  global luminance-keyed `Bloom` (and the `ShaderMaterial` has no emissive). Also leans hardest
  into `depthWrite:false` additive across the **dense 115-tube braid** without fully reckoning with
  additive stack-up where many tubes overlap near the root — its own risk #1, only partially
  mitigated. Strong concept, but needs Concept 2's corrections to be safe.

---

## 3. Scoring — the operator's five axes (1-5, 5 = best)

| Concept | (1) Distinct from tissue | (2) Cohesive w/ world+soul | (3) Reads as control-bus | (4) Feasible+perf+ports | (5) Fidelity/canon cost (5=cheapest) | **Weighted** |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| **2 · Fiber-Optic Control-Bus** | **5** | **5** | **5** | **5** | 4 | **★ 4.85** |
| 1 · Signal Streams | 5 | 4.5 | 4.5 | 5 | 4 | 4.6 |
| 3 · Energy Transmission Conduits | 5 | 4.5 | 4.5 | 4 | 4 | 4.4 |

Weighting: axes (1) distinct and (3) control-bus are the **core ask** (×1.5 each); (2) cohesion,
(4) feasibility ×1.0; (5) fidelity cost ×0.75 (it's a shared, known, non-blocking tax).

**Per-axis notes.**

- **(1) Distinct — all three score 5.** Inverting all four tissue levers (opaque→dark, rim→none,
  breath→flow, normal→additive) is *sufficient and correct*; this is the right surgery. The eye
  will instantly separate "breathing mass" from "discrete flowing packets." No concept is weak here
  — this axis is essentially solved by the shared inversion.
- **(2) Cohesion — 2 edges ahead.** All stay in the teal-cyan family, dark cosmos, same bloom. But
  Concept 2 is the most explicit that the dark conduit is a **desaturated sibling** of the brain
  teal and that cyan is the *one* signal color (no rainbow regression) — and it keeps the regional
  tints alive as a whisper. Concept 1 lets the conduit "nearly vanish" (risk: too disconnected from
  the brain at idle — a faint echo of the old rainbow-wisp "doesn't belong" failure if the carrier
  is invisible). Concept 3 keeps tints but its additive-everywhere lean risks over-bright braid near
  the root, slightly hurting the premium read.
- **(3) Control-bus legibility — 2 wins.** Its four named motion states (idle trickle / normal flow
  / burst doubles+whitens / **hold freezes packets mid-cable**) read unambiguously as an engineered
  bus with power states. "Freeze mid-cable on hold" is the strongest single idea in the whole set:
  a literally *stopped* signal is the clearest possible "the mind is waiting for approval." Concepts
  1 & 3 dim on hold (good, but less legible than a freeze).
- **(4) Feasibility/perf/ports — 2 highest.** All are shader/material-only, one draw call, zero new
  allocations, ports frozen. Concept 2 has the **fewest technical errors** and the most exact patch,
  so least in-browser thrash. Concept 3 loses a point for the non-functional `emissive` step (wasted
  work / misleading mechanism) and under-mitigated additive stack-up on the dense braid.
- **(5) Fidelity cost — tie at 4.** Identical for all: it's a material change to the **ported canon**
  `NervousSystem.tsx`, so lab-edit + `npm run port` + full FIDELITY gate (re-tag, re-golden,
  before/after in HIS browser). Not 5, because it is genuinely a canon visual change — but cheap,
  bounded, and revertible (one fragment + two material props).

---

## 4. RECOMMENDATION — **Concept 2 (Fiber-Optic Control-Bus), grafted with the best of 1 & 3**

Adopt **Concept 2 as the spine** (it is the most code-correct, most build-ready, and wins the two
core axes outright), and **graft three things**:

- **From Concept 1:** frame the design around the explicit *motion-vocabulary opposition* — "the
  cortex pulses **in place**, the bus **translates** root→tip; opposite motion is the instant tell."
  Make that the headline read, not just the color.
- **From Concept 3:** keep the **per-region carrier tints** (LEFT/RIGHT/SPINAL) alive as a *whispered*
  dark undertone so the bus stays family-bonded to the brain at idle and never re-becomes a
  disconnected wisp — but **drop Concept 3's `emissive` step entirely** (it does not work with this
  bloom pipeline; see §0).
- **Discard** the one wrong idea (emissive-driven selective bloom). The packet blooms because its
  output luminance crosses 1.0 — nothing else is needed.

**Identity in one line:** *dark fiber-optic conduits — desaturated teal siblings of the cortex —
carrying sparse, discrete, bright-cyan light-packets that race root→tip, additive, no rim, no
breath; the cortex breathes mass, the bus transmits flow.*

### Why this wins
- It is the **only** option with zero technical errors AND the clearest control-bus read.
- It exploits the **two decisive facts of this codebase**: (a) additive-glow is the scene's existing
  language for "energy," so the nerves finally render like everything else that is light; (b) the
  global 1.0 bloom knee means a high-multiplier cyan packet blooms *exactly like the cortex
  filaments* — same bloom signature, opposite material — which is the precise definition of
  "cohesive but distinct."
- The "freeze-on-hold" motion makes the approval pause **legible**, which is core to this product's
  whole supervised-autonomy thesis.

---

## 5. Concrete build outline (lab-first; ports + uBurst/uHold preserved)

All edits are to **`GAG demo/gag-orchestrator/src/components/canvas/NervousSystem.tsx`** (lab/canon),
then **`npm run port`** once, then the FIDELITY gate. **Geometry, control points, endpoints,
`tabX`, `addWireBundle`, the merged 115-tube draw call, and all baked attributes are UNTOUCHED.**

**Phase 0 — baseline (FIDELITY law).** Confirm canon tag; capture before-goldens of home
(`?ui=superbrain`) in HIS browser. No code yet.

**Phase 1 — `WIRE_FRAGMENT` rewrite (the identity flip, ~25 lines).**
1. **Kill tissue cue #2 (rim):** delete `RIM_AMBER` (line 54) and the fresnel block (lines 61-66).
   Replace the body with a **dark carrier**: `vec3 carrier = vColor * 0.08;` (vColor already carries
   the whispered LEFT/RIGHT/SPINAL tint — keep it, per the Concept-3 graft).
2. **Kill tissue cue #3 (breath):** delete the `breath` term (line 74) and its contribution (line 80).
3. **Sharpen the packet to discrete tokens:** retune the existing `fract` flow (line 69 stays as the
   transport) — tighten to a sparse hard bead with long dark gaps and **no wake**:
   `float packet = smoothstep(0.86,0.90,flow) * smoothstep(0.98,0.94,flow); // wake removed`.
   (Sparse + brief is also the additive-stack-up mitigation — 90%+ of each wire is dark at any frame.)
4. **Signal color + bloom-crossing multiplier (the mechanism, not flourish):**
   `vec3 signal = mix(vec3(0.0,1.0,1.0), vec3(1.0), uBurst); // cyan→white on real burst`
   `vec3 finalColor = carrier + signal * packet * uSignalGain; // uSignalGain default 3.5`.
   The `*3.5` pushes peak luma >1.0 so the packet **blooms like a filament** through the existing
   global `<Bloom>` — no emissive, no PostFX change.
5. **Preserve cognition semantics (reinterpreted):**
   surge → `finalColor *= (1.0 + uBurst * 2.5);` (uBurst still from `WIRE_BURST_UNIFORM`),
   hold → **freeze + quiet**: gate the flow's time term by `(1.0 - uHold)` so packets *stop
   mid-cable*, and `finalColor *= mix(1.0, 0.2, uHold);`. (uHold still from `SCENE_UNIFORMS.uHold`.)
   Keep the `vUv.x < 0.005 || > 0.995` discard (line 86) so tips still cut cleanly at the ports.
6. **Output:** additive expects premultiplied-ish bright-on-black; emit `gl_FragColor =
   vec4(finalColor, 1.0);` (alpha irrelevant under additive).

**Phase 2 — material props (2 lines, line 205-207):**
`blending: THREE.AdditiveBlending` (was Normal), `depthWrite: false` (was true),
add `toneMapped`-equivalent intent (the `ShaderMaterial` already bypasses tone-mapping via the
composer; match the scene's `toneMapped:false` energy convention). This makes the nerves render
**exactly like AccretionCore / NeuralAura / filaments** — proven idiom.

**Phase 3 — add two tuning uniforms (no per-frame alloc):** `uSignalGain {value:3.5}` and
optional `uIdleTrickle {value:0.15}` (a faint baseline packet so the bus reads "powered" at idle,
preventing the Concept-1 "carrier vanished, looks disconnected" risk). Tier-scaling = lower
`uSignalGain` to ~2.0 on the low tier, or thin packet density — single-uniform, zero recompile.

**Phase 4 — VALIDATE (FIDELITY law).** `npm run port`; before/after in HIS browser; confirm:
(a) nerves read unmistakably as flowing signal vs breathing cortex; (b) a real `tool engaged`
event (`aiosAdapter.ts:101-103`, intensity 0.8) visibly surges + whitens the packets; (c) an
approval pause freezes packets mid-cable; (d) frame budget holds with Monaco + preview + local
inference; (e) packets bloom but the dark carrier does **not** (verify the carrier luma stays
≪1.0 — at `vColor*0.08`, max teal luma ≈ 0.27×0.08 ≈ 0.02, far under the knee ✔). Re-tag canon,
add goldens.

**Rollback:** restore the one fragment + two material props. Fully revertible, localized.

### Risks (grafted + corrected)
- **Additive stack-up on the dense braid root** (Concept 3's risk #1, real): mitigated by the sparse
  hard packet (long dark gaps) + `uSignalGain` headroom; if the root over-brightens, tighten the
  smoothstep window or fade `uSignalGain` over the first 20% of `vUv.x` (root). Measure in-browser.
- **Packet must cross the 1.0 knee or it won't bloom** (the §0 fact): keep `uSignalGain ≥ ~2.5`;
  cyan×2.5 ≈ luma 1.97 > 1.0 ✔. Do NOT drop below ~1.3 or the "light-in-transit" read collapses
  into a flat line.
- **Do NOT add `emissive`** (Concept 3 error): it does nothing in this global-bloom pipeline.
- **Fidelity gate is mandatory** (canon material change in a ported file): before/after in HIS
  browser, re-tag, re-golden. Not skippable.

### Honest limits
- No headless GPU/WebGL verification is possible here; the bloom-crossing and stack-up numbers are
  reasoned from the code's documented luminance ladder, not measured. The final aesthetic + perf
  call is the operator's browser (FIDELITY law).
- WebGPU/TSL could later move the packet to a GPGPU particle stream for crisper discrete beads — a
  **future option only**, explicitly out of scope; WebGL2 GLSL ES 1.0 ships today with zero new deps.

---

## 6. One-paragraph summary for the operator

Keep the nerves' **topology** exactly as the redesign doc set it (ports at ±4.8 / spinal, real
uBurst/uHold), but flip their **material identity** from tissue to signal. The brain stays a
*breathing mass* (opaque, fresnel-rimmed, sinusoid, normal-blended); the nerves become a
*flowing fiber-optic control-bus* (near-black desaturated-teal conduit + sparse discrete
bright-cyan light-packets racing root→tip, additive like every other "energy" element in the
scene, no rim, no breath). On a real event the packets double and whiten; on an approval pause
they **freeze mid-cable** — the clearest possible "the mind is waiting." It's a ~25-line fragment
rewrite + two material flags in the canon `NervousSystem.tsx`, reusing the merged 115-tube geometry
untouched, then `npm run port` + the FIDELITY gate. The recommendation is **Concept 2 grafted with
Concept 1's motion-opposition framing and Concept 3's whispered regional tints — and explicitly
WITHOUT Concept 3's broken `emissive` bloom step** (the scene's bloom is global/luminance-keyed,
not emissive-driven, so packets bloom purely by crossing the 1.0 knee via the gain multiplier).
