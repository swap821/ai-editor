# Point-Field 3D Living-Being — Aesthetic Conversion Design Spec

**Date:** 2026-06-20
**Status:** Proposed (approved in brainstorm: Approach A; research-backed). Awaiting operator review of this written spec.
**Owner:** operator (kumarswapnil82)
**Builds on (does NOT supersede):**
- `2026-06-16-living-being-frontend-design.md` — the lifecycle, the laws ("everything grows from the being"), the 7 states. **Still authoritative for behavior.**
- `2026-06-18-living-being-frontend-100-roadmap.md` — the 100%-complete roadmap.

This spec changes **only the aesthetic substrate** — *how the being is rendered* — so the live 3D organism reads as the 2D `demoplan.png` poster ("VARIANT H: POINT-FIELD ORGANISM"). It does not change the behavior, the data-binding, or the lifecycle. The being still arrives, talks, materializes tabs from its nerves, conducts from its spine, and reabsorbs.

---

## 1. The gap, in one sentence

The poster's being is a **field of glowing colored points** (a particle organism). Our being today is a **lit mesh** (`brain.glb` with shaders). That single substrate difference — *mesh vs. point-field* — is the dominant reason the live scene does not read as the poster, even though palette, composition, and lifecycle already match. **This spec converts the substrate to points.**

> **The goal:** a real-time, orbit-able, backend-data-true 3D being that — framed front-on — is visually indistinguishable in *aesthetic* from the 2D poster: soft spectral puncta on deep space, luminous halos, a brain canopy over a spine trunk over a root base, each posture its own hue.

We are honest about the medium: a live 3D scene is not literally pixel-identical to a flat illustration. But the poster *is itself* a point-field, so converting our substrate to a point-field — with the research-verified flatness/glow levers — closes the gap to "same aesthetic," which is exactly what the operator asked for.

## 2. The one law this inherits (unchanged)

> **Everything you see is either *part of* the being or *grew out of* it. Nothing flat floats on top.**

The point-field is the being's flesh. Tabs, nerves, spine, roots — all are points or grow from points. Palette + textures remain **sacred** (operator's bible); everything else in the lab is free to rebuild.

## 3. Approved approach — Point-Field Organism (Approach A)

Sample `brain.glb` (and the spine/root anatomy) into a **single ~60k-point cloud** rendered as additive glowing puncta with a custom `ShaderMaterial`. Reuse the existing posture-color system (`uPostureColor`/`uPostureTint`/`uPostureCommit`/`uFlow`) as a per-point data binding. Frame with a near-orthographic poster camera, orbit-able. All animation lives in the vertex shader. The existing mesh being is kept behind a fallback flag during the phased build.

**Why this over the alternatives** (settled in brainstorm):
- *Mesh + heavier shaders* — cannot produce the discrete-puncta read; it will always look like a lit surface, not a particle organism. Rejected.
- *2D canvas overlay of the poster* — violates the one law (flat thing on top), kills orbit/depth/data-binding. Rejected.
- *Point-field (this)* — IS the poster's medium, keeps live 3D + depth + data-true behavior. **Chosen.**

## 4. Anatomy as points (what gets sampled)

The poster is one vertical organism: **brain canopy → spine trunk → root base ring.** All three are the being's own anatomy and all three are point-fields from the same draw call where possible.

- **Cortex / canopy** — sample the processed `brain.glb` clone surface (area-weighted) → the dense multicolored cloud at the top. The bulk of the budget (~70%).
- **Spine / brainstem trunk** — sample the **existing spine mesh** (cord + brainstem stub, `TubeGeometry`) descending dead-center → the trunk. ~20%.
- **Roots / vertebrae / cauda-equina base** — sample the existing vertebra rings (`TorusGeometry`) + bilateral nerve roots + cauda spray (`TubeGeometry`) fanning to the faint base ring → ~10%. These also seat tabs in orchestration (per the 2026-06-16 spec).

**Source of the spine geometry:** it is built today in `NervousSystem.tsx` + `lib/spineAnatomy.ts` as merged **mesh** (Tube/Torus, four draw calls) — deliberately rebuilt from an earlier `THREE.Points` system so it could share the brain's mesh material and keep the Voronoi web unbroken. Under the point-field direction this is intentionally reversed: the poster shows the spine as a point-field too, so we **sample those same mesh geometries** (they are real `BufferGeometry`, so `MeshSurfaceSampler` works on them) into the cloud. The "one unbroken field" goal is *better* served by points — brain + spine become literally one continuous point cloud.

All baked into **one `THREE.Points`** (one draw call) with a per-point `aBand`/region tag so the shader can treat canopy/trunk/roots differently (flow direction, density, where the arrival inrush originates). The brain's region color baking handles the canopy; the spine inherits the existing `spineAnatomy.ts` per-segment palette stops, baked into `aColor` the same way.

## 5. Rendering foundation (research-verified)

**Primitive:** ONE `THREE.Points` + custom `ShaderMaterial`. Not `InstancedMesh` (80k point sprites = 80k verts vs 320k quad verts; instancing measurably slower for tiny glowing dots). Not thousands of drei `<Point>` children (React overhead + ~50k CPU wall).

**Point-count tiers** (sampled once at load, baked to static attributes):

| Tier | Points | DPR cap |
|---|---|---|
| High desktop | 80,000 | 2.0 |
| Default desktop | 60,000 | 2.0 |
| Mid / low GPU | 40,000 | 1.5 |
| Mobile | 30,000 | 1.5 |

**Static geometry attributes** (set once, `needsUpdate` once, never per-frame):
`position` (aBase, world-transformed), `aColor` (region RGB, linear-sRGB), `aNormal` (breathe-along-normal), `aSize` (~[0.6,1.4] variance), `aPhase` (0..2π twinkle desync), `aSpeed` (~[0.6,1.4]), `aScatter` (normalized random dir for arrival/dissolve), `aBirth` (0..1 stagger), `aBand` (normalized body-axis coord for flow + region tag).

**Vertex shader** — weak size attenuation for poster flatness:
```glsl
uniform float uScale;          // = drawingBufferSize.height * 0.5  (RECOMPUTE on resize/DPR!)
uniform float uSize, uAttenK;  // uAttenK ~0.25 (0 = fully flat poster)
attribute float aSize;
varying vec3 vColor;
void main() {
  vColor = aColor;
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  float atten = mix(1.0, uScale / -mv.z, uAttenK);
  gl_PointSize = min(uSize * aSize * atten, 64.0);  // clamp < hw cap
  gl_Position = projectionMatrix * mv;
}
```

**Fragment shader** — procedural soft radial sprite (no texture), premultiplied:
```glsl
precision mediump float;   // ~2x faster than highp on mobile
varying vec3 vColor;
void main() {
  float d = length(gl_PointCoord - 0.5);
  float halo = pow(1.0 - clamp(d / 0.5, 0.0, 1.0), 2.5); // wide colored glow
  float core = smoothstep(0.16, 0.0, d);                  // tight bright core
  float i = halo * 0.65 + core * 0.9;
  if (i <= 0.003) discard;       // skip ~0 rim fragments -> cuts fill-rate
  gl_FragColor = vec4(vColor * i, i);   // rgb PRE-multiplied by i
}
```
`pow(...,2.5)` mimics `ctx.createRadialGradient`; the tight `smoothstep` core is the near-white puncta center; additive overlap builds hot cores in dense regions exactly like canvas `'lighter'`.

**Material — premultiplied additive (kills dark fringe):**
```js
new THREE.ShaderMaterial({
  blending: THREE.CustomBlending, blendEquation: THREE.AddEquation,
  blendSrc: THREE.OneFactor, blendDst: THREE.OneFactor,  // blendFunc(ONE, ONE)
  premultipliedAlpha: true, transparent: true,
  depthWrite: false,   // NON-NEGOTIABLE for additive (else self-occlude/flicker on orbit)
  depthTest: true,     // keep TRUE so opaque scene geometry can occlude
  toneMapped: false,   // emit >1 so bloom sees it (see §7)
})
```
Fallback if not premultiplying: `THREE.AdditiveBlending` + `gl_FragColor = vec4(vColor, i)` (acceptable, slight fringe). Additive is order-independent → **never sort the points.**

## 6. Color binding (regional palette + posture wash)

The raw GLB has **no `COLOR_0`** — `sample()` silently leaves color untouched. So:

**A. Regional palette (baked):** the upstream pipeline already paints region vertex colors onto the brain clone (`CorticalSignals.tsx` reads them today). **Bake a `color` attribute (3 floats, linear-sRGB) onto the 2605-vert clone BEFORE `sampler.build()`** (by lobe/hemisphere zones from vertex position, matching today's regions). Then per sample, `sample(pos, normal, col)` returns barycentric-interpolated region color → write straight into `aColor`. **Do NOT** `convertSRGBToLinear()` an already-linear sampled color (double-convert muddies the palette).

**B. Posture wash (dynamic, already in repo):** keep `uPostureColor`/`uPostureTint`. Layer in the fragment over the regional color:
```glsl
vec3 c = vColor;
c = mix(c, c * uPostureColor * uGlowMul, clamp(uPostureTint, 0.0, 0.8));
```
Driven per-frame by mutating the shared uniform leaf (the `CorticalSignals`/`SCENE_UNIFORMS` pattern). `uGlowMul` pushes the being's points >1 for bloom.

This preserves the entire spectral-v1 posture system (`bodyPosture.ts`) unchanged — it just binds to points instead of mesh.

## 7. Glow match — bloom + tone mapping

The luminous halos are the poster's signature. Pipeline (@react-three/postprocessing, **one Bloom + one late ToneMapping**):

1. **Renderer NO tone map** when postprocessing is active: `<Canvas gl={{ toneMapping: THREE.NoToneMapping }}>` + `outputColorSpace = SRGBColorSpace`. (ACES on the renderer clamps to [0,1] before bloom → nothing glows.)
2. **Points emit >1:** `toneMapped:false` + `rgb = regionColor * uGlowMul`, `uGlowMul ≈ 1.5–3.0`. **Starfield strictly <1.0** so a threshold of 1.0 auto-excludes it.
3. **`<Bloom mipmapBlur>`** starting values: `luminanceThreshold={1.0}` · `luminanceSmoothing={0.2–0.3}` · `intensity={0.8–1.2}` · `radius={0.6}` · `kernelSize={KernelSize.LARGE}` · resolution = half canvas. Selective **by luminance threshold, NOT layers** (one pass, no `BLOOM_SCENE` two-composer technique).
4. **`<ToneMapping mode={ACES_FILMIC} />` LAST** (after Bloom), exposure ~0.8–1.0. ACES rolls off stacked highlights so dense regions stay **colored, not white** — but ACES desaturates, so **bump palette saturation/value +10–20%** to compensate.
5. **Per-color bloom compensation:** bloom luminance `L = 0.2126R + 0.7152G + 0.0722B` — blue/violet barely bloom. Bake `uGlowMul` higher for blue/violet, lower for green, so the palette blooms evenly.
6. **`multisampling={0}`** — MSAA is pointless for glow.

## 8. Animation (all in the vertex shader, zero per-frame CPU loop)

**Architecture: stateless attribute-driven (THREE.BAS model), NOT GPGPU/FBO.** Every effect is a closed-form function of `(aBase, uTime, uProgress)` — no position-depends-on-previous → FBO buys nothing. Per-frame JS = mutating a few scalar uniforms via **ref, never setState** (<0.5ms/frame).

Per-frame uniforms: `uTime, uGrow, uFlow, uArrival, uReabsorb, uFlowSpeed, uCurlAmp` (+ `uScale` on resize).

Vertex recipe (composited; all use `aSpeed`/`aPhase` for desync):
```glsl
// BREATHE — along normal, shared low-freq phase for whole-body coherence
float breath = 0.5 + 0.5 * sin(uTime * 2.5);
vec3 p = aBase + aNormal * (uGrow * 0.025 * length(aBase) * breath); // 1–4% radius
p += aNormal * 0.004 * sin(uTime * 1.7 + aPhase);                    // subtle shimmer
// CURL idle drift — DISPLACEMENT of fixed aBase (stateless, bounded)
p += curlNoise(aBase * 0.4 + uTime * 0.06) * uCurlAmp;              // ~0.5–1.5% radius
// FLOW BAND sweep along body axis (spine pulse)
float center = fract(uTime * uFlowSpeed);                           // ~0.1–0.25
float band = exp(-pow((aBand - center) / 0.12, 2.0));
// -> gl_PointSize *= (1.0 + band*1.5); pass vBand to frag for emissive boost
// ARRIVAL inrush (uArrival 0->1, ~2.5–3.5s) — staggered ease-out condense
vec3 origin = aBase + aScatter * 6.0;
float ta = clamp((uArrival - aBirth * 0.4) / 0.6, 0.0, 1.0);
p = mix(origin, aBase, 1.0 - pow(1.0 - ta, 3.0));
// REABSORB (uReabsorb 0->1) — rise + scatter, fade + shrink, growing curl
vec3 exit = aBase + vec3(0.0, 4.0, 0.0) + aScatter * 1.5;
float tr = clamp((uReabsorb - (1.0 - aBirth) * 0.4) / 0.6, 0.0, 1.0);
p = mix(p, exit, pow(tr, 2.0));   // vAlpha = 1.0 - tr; gl_PointSize *= (1.0 - tr);
```
Use cabbibo `glsl-curl-noise` (divergence-free → swirls without clumping). **Clamp stagger so the last point still finishes:** `stagger + duration ≤ 1`.

Twinkle (fragment alpha): `alpha *= 0.65 + 0.35 * sin(uTime*0.6 + aPhase)` — speed ≤1.0, amplitude ≤0.4 (breathe, don't strobe).

Lifecycle JS stays scalar-only (`idle → arriving → alive → reabsorbing`): tween `uArrival`, run `uGrow/uFlow` during alive, tween `uReabsorb`. **No per-point JS ever.**

**Reduced motion** (`matchMedia('(prefers-reduced-motion: reduce)')`): don't blank — crawl/stop `uTime`, snap `uArrival=uReabsorb` to final, replace big translates with opacity/color crossfade. Keep the lit field visible; expose a manual toggle.

## 9. Camera & poster flatness

Three levers make a live 3D cloud read as a flat poster:
- **Low FOV:** `PerspectiveCamera` **FOV 22–28**, dollied well back to fill frame → near-orthographic flatness while orbit-able. Expose FOV as a tunable; offer a pure `OrthographicCamera` toggle for max 2D fidelity. (Default FOV 75 is a silent flatness-killer.)
- **Weak size attenuation:** `uAttenK ~0.25` (§5). Constant-ish on-screen dot size is THE biggest "flat dot field" cue; `uAttenK=0` = fully flat.
- **Depth fog as ALPHA fade (additive-safe), NOT color mix:**
```glsl
float depth = -mvPosition.z;
float fog = 1.0 - exp(-uFogDensity * uFogDensity * depth * depth);
i *= (1.0 - fog);   // far points recede like a poster value gradient
```
- **Composition:** front-on, vertical (brain top, roots bottom), organism centered — exactly the poster framing. Orbit allowed but **default pose is the poster pose.**
- **Orbit:** standard OrbitControls; regress DPR during orbit (heaviest fill), restore ~200ms after release.
- **Hand-drawn feel:** tiny per-point positional jitter baked into `aBase` so points don't read as mechanically scanned.

## 10. Per-scene 3D interpretation (the 7 poster phases)

Each poster phase is the **same point organism** in a different posture. The lifecycle behavior is unchanged (2026-06-16 spec); this maps each to its point-field gesture and posture color. Phases bind to the existing `organismLifecycle` phases via `PHASE_TO_POSTURE`.

1. **ARRIVAL** *(booting/arrival → think)* — the knowledge-field (starfield points) **streams inward and condenses** into the cortex: the `uArrival` inrush (`origin = aBase + aScatter*6`, staggered by `aBirth`, ease-out). First ignition = a brief `uGlowMul` pulse. "Born from the data it travels through."
2. **REST + FIRST CONTACT** *(rest → rest, violet)* — the field settles; whole-body **breathe** (`uGrow`) + slow **curl** drift + faint spine flow band. Posture violet `[150,120,255]`, `tint 0.0` (cleanest). The brainstem trunk reads steady at the base. Typed light condenses at the intake; reply pulses up the spine flow band.
3. **AWAKENING / CONVERSATION** *(attentive/intake → think, magenta)* — cortex **brightens** (raise `uGlowMul` + posture `tint 0.46`); nerves light from the core; flow band quickens. Attentive lean toward pointer (existing `CURSOR_ATTENTION`). Posture magenta `[196,78,255]`.
4. **MATERIALIZATION** *(materializing → stream, cyan)* — a **nerve grows out** from the cortex (a thin sub-stream of points extruding from `aBase` along a path) and a **tab unfurls at its tip.** The umbilical = a flowing point-line (flow band gated to that nerve). The tab content stays per the 2026-06-16 spec (luminous 3D text). Posture cyan `[54,214,255]`, `tint 0.70`.
5. **ORCHESTRATION** *(conducting → stream)* — the **spine trunk extends**, vertebrae become addressable seats; multiple tabs anchor to vertebrae (focus tab forward/bright, others dim at depth). The spine **flow band** carries state down to the focus tab. Same cyan stream posture.
6. **WORKING + SHOWING WORK** *(working → stream)* — live data flows through the nerve flow bands in real time; the work tab shows real content; "status is the pulse, color, and motion of the body." Flow band fastest here.
7. **REABSORPTION** *(completion_settle/reabsorbing → complete, green)* — tabs **dissolve into particles**, nerves retract, **energy travels up the spine** (`uReabsorb`: rise + scatter + fade + shrink + growing curl). Settle back to rest. Posture green `[62,240,160]`. "Back to rest. Always voyaging."

Error at any phase → red `[255,92,72]`, `tint 0.82` (existing `error_repair`).

## 11. Integration with the existing repo

- **Posture system unchanged** — `bodyPosture.ts`, `organismLifecycle.ts`, `organismPhaseBus.ts`, `PHASE_TO_POSTURE` all reused as-is. Points consume the same uniforms the mesh does today.
- **Reuse the proven sampler** — generalize `CorticalSignals.tsx` (geometry dedup by Set, budget-by-triangle, seeded mulberry32 PRNG, per-sample `applyMatrix4(matrixWorld)` + normal-matrix, hoisted temporaries) into a standalone `BrainPointField`. Same pattern, scaled 320 → 60k, plus the lifecycle attributes.
- **Fallback flag** — the existing mesh being stays behind `?being=mesh` (or a scene flag) during the phased build, so we can A/B and never lose a working scene. Default flips to `points` only after operator FIDELITY sign-off.
- **Materialization layer** — `MaterializationLayer.tsx` / `MaterializedTab.tsx` keep their behavior; the nerve birth now originates from a point on the cloud rather than a mesh vertex (cosmetic source change).
- **Lab ↔ product mirror** — build in the gitignored lab first; mirror `src/superbrain/*` edits to the product tree (the standing discipline). Test on **:5173** (CORS-allowed) only.

## 12. Module boundaries (new/changed files)

- `lib/pointFieldSampler.ts` (NEW) — pure: `(sources[], totalCount, seed) → { positions, colors, normals, sizes, phases, speeds, scatter, births, bands }` Float32 arrays, where `sources` = the brain clone + the spine/vertebrae/root mesh geometries, each with its own budget share and region tag. Unit-testable (deterministic given seed). No three rendering.
- `lib/pointFieldMaterial.ts` (NEW) — the `ShaderMaterial` factory (vertex+fragment GLSL above, uniforms, premultiplied-additive config, `customProgramCacheKey`). Mirrors `brainMaterial.ts`'s structure.
- `components/canvas/BrainPointField.tsx` (NEW) — mounts `<points>` with baked geometry, drives per-frame uniforms via ref, owns the lifecycle scalar state machine reading `organismPhaseBus`.
- `components/canvas/PointFieldPost.tsx` (NEW) — the `<EffectComposer>` (Bloom + late ACES ToneMapping), perf-tier aware.
- `SuperbrainScene.tsx` (CHANGED) — mount `BrainPointField` behind the fallback flag; feed it `SCENE_UNIFORMS`; set camera FOV/dolly to the poster framing.
- `curlNoise.glsl.ts` (NEW) — the cabbibo divergence-free curl drop-in as a GLSL chunk string.

Each unit has one purpose, a clear interface, independent testability — per the design-for-isolation principle.

## 13. Top pitfalls (guardrails baked into the plan)

1. **Stale `uScale`** → points wrong-size after resize/DPR. Recompute `uScale = drawingBufferHeight*0.5` on every resize + DPR change.
2. **`depthWrite:true` on additive** → self-occlude/flicker on orbit. Always `depthWrite:false`; never sort.
3. **Tone-map clamp kills bloom** — `NoToneMapping` renderer + `toneMapped:false` + emit >1 + late `<ToneMapping>`.
4. **Over-bloom / white blowout** — per-point peak modest (~0.2–0.5), threshold 1.0, moderate intensity, let ACES roll off; never threshold 0.
5. **`sample()` returns NO color** when geometry lacks `COLOR_0` — bake `color` onto the clone before `build()`; assert `geometry.attributes.color` exists.
6. **Local-space sampler positions** — `applyMatrix4(mesh.matrixWorld)` per sample (repo already does).
7. **Fog as color-mix on additive** brightens far points — fade ALPHA only.
8. **Per-point CPU work** (per-frame buffer rewrites, `needsUpdate` every frame, `setState` in `useFrame`) — bake static, animate in-shader, mutate via ref.
9. **Oversized `gl_PointSize`** → hard square clip — `min(gl_PointSize, 64.0)`.
10. **Curl as integration** (`pos += curl*dt`) drifts/clumps — apply as displacement of fixed `aBase`.

## 14. Phase order (research-recommended; each gated by operator FIDELITY at :5173)

- **P0 — Sampler scale-up:** `pointFieldSampler.ts` + `BrainPointField` static cloud at 60k, all attributes baked once. **Gate:** static field renders, 1 draw call, deterministic layout.
- **P1 — Glow look:** premultiplied-additive material + radial sprite + weak attenuation + alpha-fade fog + `NoToneMapping`. **Gate:** soft colored puncta, dark bg, no grey wash, colored (not white) clusters, flat poster read.
- **P2 — Color binding:** bake region `color` attr → `aColor`; re-layer posture wash + per-color `uGlowMul`. **Gate:** regional palette + posture wash both read; no color dominates bloom.
- **P3 — Post-FX:** `<EffectComposer>` half-res Bloom (mipmapBlur) + late ACES, `multisampling=0`. **Gate:** cinematic glow matches the poster.
- **P4 — Animation:** breathe + curl idle + flow band (vertex) + twinkle (fragment) + reduced-motion crossfade. **Gate:** "alive" read, 60fps held.
- **P5 — Lifecycle gestures:** scalar state machine → arrival inrush + reabsorption dissolve + the per-scene gestures (§10), spine + roots sampled in. **Gate:** arrival→alive→materialize→conduct→dissolve chain reads as the poster's 7 phases.
- **P6 — Perf tiers + mobile:** `dpr={[1,2]}`, `PerformanceMonitor` degrade ladder, point-count tiers, regress-on-orbit. **Gate:** 60fps desktop @ 80k/DPR2, 30fps real mid mobile @ 30k/DPR1.5.

## 15. Testing & FIDELITY gates

- **Unit:** `pointFieldSampler.test.ts` — deterministic counts, all attributes present, color attribute non-empty (the COLOR_0 trap), positions world-space, seed reproducibility.
- **Gate quality bar** — all frontend gates green (lint/types/vitest/build) before each phase hand-off.
- **FIDELITY is the operator's browser, his real GPU** — every phase ends with a before/after capture and his sign-off (per `fidelity-is-sacred-ui-laws`). Software-GL puppeteer captures are approximate only.
- **Composition check:** orbit to the poster's framing, verify the cues — constant-ish dot size (flat), dark bg (no grey wash), colored (not white) dense clusters (tone mapping working), soft halos (bloom), gentle shimmer (twinkle). If clusters read white → lower exposure/bloom before touching colors.

## 16. Operator-tunable dials (his GPU, dialed live in dev)

Exposed on `window.__POINTFIELD` (alongside existing `window.__POSTURE`): `count`, `uSize`, `uAttenK`, `fov`, `uFogDensity`, `uGlowMul` (+per-color), bloom `intensity`/`radius`/`threshold`, `uFlowSpeed`, `uCurlAmp`, breathe amplitude. Bake the operator's chosen values as defaults + canon goldens once he signs off.

## 17. Sacred / out of scope

- **Palette + textures are sacred** — the spectral-v1 colors (`bodyPosture.ts`) and `brain.glb`/texture assets are untouched; we sample them, we don't repaint them.
- **No behavior/lifecycle change** — this is a substrate swap; the 2026-06-16 spec governs behavior.
- **Security frozen core** (`aios/security/*`) untouched.
- **No git push / nothing outward-facing** without explicit operator OK; commit only when asked.
- **Backend unchanged** — the being stays data-true on the existing endpoints.

---

**One body. Many postures. The interface is alive — now rendered as the point-field it was always drawn to be.**
