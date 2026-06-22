I now have a complete, file-grounded picture of the live stack. Here is the design spike, returned as plain text.

---

# GAGOS WebGPU + TSL Look-Spike — "The Million-Mote Mind"

A FLAGGED (`?gpu=webgpu`), browser-native answer to "use Unreal for samples." It elevates the GAGOS point-field toward AAA fidelity by moving the being's flesh from ~90k baked-attribute CPU points to **200k–1M GPU-compute particles** in divergence-free curl flow — while leaving the default WebGL path byte-for-byte untouched and keeping the sacred poster tetrad (cyan `#7bf5fb`, purple `#b06eff`, green `#54f0a0`, orange `#ff7e40`, zero blue).

I judged this against `GAG demo/reference/demoplan.png`: the poster's being is **discrete spectral puncta on near-black**, a multicolored brain canopy crowning a flow-lit spine, soft luminous halos, each posture its own hue, the field churning but never strobing. The spike must read as that — only denser, deeper, and with motion the CPU substrate physically cannot produce.

---

## 1. CONCRETE PLAN — flag gating + graceful fallback

### Flag (mirror the existing `beingMode.ts` pattern exactly)
A new `lib/gpuMode.ts` sibling to `beingMode.ts`:
```ts
export type GpuMode = 'webgl' | 'webgpu';
export function readGpuMode(search?: string): GpuMode {
  const raw = search ?? (typeof window !== 'undefined' ? window.location.search : '');
  const value = new URLSearchParams(raw).get('gpu');
  // Opt-IN only. Default stays 'webgl'. Capability-gate even when requested.
  if (value !== 'webgpu') return 'webgl';
  const ok = typeof navigator !== 'undefined' && 'gpu' in navigator;
  return ok ? 'webgpu' : 'webgl'; // silent, safe fallback to the shipping path
}
```
- **Default `/` (no params) NEVER changes** — `readGpuMode()` returns `'webgl'`, the current `BrainPointField` + WebGL `<Canvas>` render exactly as today. This satisfies the hard law that clean root boots the shipping being.
- `?gpu=webgpu` is opt-in AND capability-gated: if `navigator.gpu` is absent (or `requestAdapter()` later resolves null), it falls back to `'webgl'` with a one-line `console.info`. No black screen, no thrown error — the WebGLErrorBoundary stays the last line of defense.
- Composable with the existing flag: `?gpu=webgpu&being=points` is the spike; `?being=mesh` still forces the legacy GLB mesh on either renderer.

### Where it mounts / what it replaces ONLY under the flag
The swap is surgical — it touches **two** mount points and adds new lab files; it edits **nothing** in the WebGL render path:

1. **Renderer** (`WorkspaceCanvas.tsx`): r3f v9 + three r0.184 support `three/webgpu`'s `WebGPURenderer`. Under the flag, pass a custom renderer factory to `<Canvas>`:
   ```tsx
   // ONLY when gpuMode === 'webgpu':
   import * as THREE from 'three/webgpu';
   <Canvas
     gl={(props) => {
       const r = new THREE.WebGPURenderer({ ...props, antialias: false, alpha: false, powerPreference: 'high-performance' });
       return r.init().then(() => r); // r3f v9 awaits async renderer init
     }}
     /* camera/dpr unchanged */
   >
   ```
   The default branch keeps today's `gl={{ antialias:false, alpha:false, ... }}` WebGLRenderer verbatim. A `WebGPURenderer` *also* runs WebGL2 as a backend, so the same renderer can be the fallback — but we gate by `navigator.gpu` so the proven WebGL path is never disturbed for default users.

2. **Being substrate** (`SuperbrainScene.tsx`, the `mode==='points'` branch): swap the component, not the scene graph.
   ```tsx
   {gpuMode === 'webgpu'
     ? <GpuBrainPointField source={brainClone} uniforms={SCENE_UNIFORMS} count={gpuCount} spineCount={...} />
     : <BrainPointField        source={brainClone} uniforms={SCENE_UNIFORMS} count={...} spineCount={...} />}
   ```
   `GpuBrainPointField` consumes the **same `CognitionUniforms` leaf object** (`uTime, uPosture, uPostureTint, uArrival, uIgnite, ...`) and the **same posture system** (`bodyPosture.ts`, `organismPhaseBus`, `conversationPhaseBus`, `lifecycleTargets`). The lifecycle/data-binding contract is 1:1; only the simulation+draw substrate changes.

3. **PostFX**: keep it. The WebGPU material emits `>1` exactly like the WebGL one, so the existing AgX-tonemapped Bloom (`PostFX.tsx`, threshold 1.0) catches it unchanged. (Note for the build: `@react-three/postprocessing` is WebGL-only today; under WebGPU, Phase 1 uses three's WebGPU `PostProcessing` + `bloom()` TSL node as the equivalent pass — same knee threshold 1.0, same AgX-equivalent tonemap, half-res. This is the one pipeline piece that is reimplemented, not reused, and it stays behind the flag.)

**Net replaced under the flag:** the renderer instance, the `<points>` substrate component, and the post pass. **Net untouched:** `pointFieldSampler.ts`, `pointFieldMaterial.ts`, `bodyPosture.ts`, every bus, the lifecycle engine, the chrome, the camera, the cosmos, the spine fusion math. Lab-first per the standing mirror discipline; the spike lives in the gitignored lab until it clears the operator's `:5173` FIDELITY bar.

---

## 2. CORE TECHNIQUE — GPU compute particles, posture-hued

**Seeding (reuse, don't reinvent):** run the existing `samplePointField()` once at load to bake **anchor buffers** — `aBase` (world position on the brain+spine anatomy), `aColor` (region/spine RGB — the sacred palette, untouched), `aNormal`, `aBand` (body-axis 0=roots→1=cortex), `aScatter`, `aBirth`. These are the *home positions*. We just scale the count from ~90k to 200k–1M (the CPU sampler is fine for static seeding; only animation moves to the GPU). Anchors upload once to GPU storage buffers.

**Simulation (the new part):** a compute pass each frame integrates a **live position** per particle, pulled toward its `aBase` home by a spring, perturbed by **divergence-free curl-noise** (swirls, never clumps), with lifecycle posture fed as compute uniforms:
- `position = home(aBase) + curlNoise(aBase·freq + time·drift) · uCurlAmp` — displacement of a *fixed* anchor (NOT integration of previous position; that drifts/clumps — pitfall #10 from the spec, and it's why we keep `aBase` authoritative).
- A soft **spring** (`vel += (home - pos)·k`) lets the field *breathe* and *recover* its shape, so it always re-forms the brain silhouette after any gesture — critical for reading as the poster.
- **Lifecycle as compute uniforms** (1:1 with the current shader): `uArrival` (home `= aBase + aScatter·R`, staggered by `aBirth`, ease-out condense), `uReabsorb` (rise +Y + scatter + curl-amp ramp), `uGrow` (breath gain), `uFlowSpeed` (spine flow-band center), `uCurlAmp` (idle churn), `uIgnite/uAwaken/uStatePulse/uReabsorbGlow` (luminance-only flashes, cortex/spine weighted by `aBand`). Posture color `uPostureColor`+`uPostureTint` feed the render material, never the geometry — hue stays sacred.

**Count tiers (RTX-3050-aware — memory notes 256k breaks WebGL, 90k is the working WebGL ceiling):** WebGPU compute lifts that wall by ~10×.
| Tier | Particles | Notes |
|---|---|---|
| Spike-default (RTX 3050) | 250,000 | safe headroom, visibly denser than 90k WebGL |
| High desktop | 500,000 | the "churning mind" look lands here |
| Showcase / capture | 1,000,000 | the poster's fine-puncta density, for the FIDELITY screenshot |
| Fallback (no WebGPU) | → WebGL 90k | the shipping path |

**Keeping the poster hues:** `aColor` is the baked region/spine palette (linear-sRGB) — never recomputed on GPU. The render node applies only the existing posture *wash* (`mix(c, c·uPostureColor·1.6, tint)`), the flow-band brighten, and luminance-only ignite/awaken/state/reabsorb boosts — identical math to `pointFieldMaterial.ts` lines 104–127. So 1M GPU particles wear the exact same sacred tetrad as the 90k WebGL field.

---

## 3. KEY TSL / WGSL CODE (enough to scaffold)

Using **three.js TSL** (`three/tsl`) so it compiles to WGSL on WebGPU and GLSL on the WebGL2 fallback — the renderer-agnostic path the nextgen doc mandates. Storage buffers hold `posLive` (rw) and `velLive` (rw); anchors are read-only instanced attributes.

### 3a. Setup — buffers + compute node (`lib/gpuPointFieldTSL.ts`)
```ts
import * as THREE from 'three/webgpu';
import {
  Fn, instanceIndex, storage, uniform, attribute, vec3, vec4, float,
  positionLocal, time, mix, clamp, pow, sin, exp, length, smoothstep, mul, add, sub
} from 'three/tsl';
import { curlNoise3 } from './curlNoiseTSL';   // §3c

export function buildGpuPointField(count: number, anchors /* from samplePointField */) {
  // ---- GPU storage (live state) ----
  const posLive = storage(new THREE.StorageInstancedBufferAttribute(anchors.positions.slice(), 3), 'vec3', count);
  const velLive = storage(new THREE.StorageInstancedBufferAttribute(new Float32Array(count*3), 3), 'vec3', count);

  // ---- read-only anchor attributes (the baked home + sacred color) ----
  const aBase    = storage(new THREE.StorageInstancedBufferAttribute(anchors.positions, 3), 'vec3', count).toReadOnly();
  const aScatter = storage(new THREE.StorageInstancedBufferAttribute(anchors.scatter,   3), 'vec3', count).toReadOnly();
  const aBirth   = storage(new THREE.StorageInstancedBufferAttribute(anchors.births,    1), 'float', count).toReadOnly();
  const aBand    = storage(new THREE.StorageInstancedBufferAttribute(anchors.bands,     1), 'float', count).toReadOnly();

  // ---- lifecycle uniforms (mirror CognitionUniforms 1:1, driven via .value each frame) ----
  const U = {
    uCurlAmp:   uniform(0.0),  uCurlFreq: uniform(0.40), uDrift: uniform(0.06),
    uGrow:      uniform(0.0),  uArrival:  uniform(0.0),  uReabsorb: uniform(0.0),
    uSpring:    uniform(6.0),  uDamp:     uniform(0.90), uDt:       uniform(0.016),
  };

  // ---- COMPUTE: spring-to-home + curl churn + arrival/reabsorb (closed-form home) ----
  const computeStep = Fn(() => {
    const i = instanceIndex;
    const base = aBase.element(i);

    // arrival: home flies in from a scattered origin, staggered by birth, ease-out
    const arrOrigin = base.add(aScatter.element(i).mul(2.0));
    const ta = clamp(U.uArrival.sub(aBirth.element(i).mul(0.4)).div(0.6), 0.0, 1.0);
    let home = mix(arrOrigin, base, float(1.0).sub(pow(float(1.0).sub(ta), 3.0)));

    // reabsorption: home rises + scatters away (inverse stagger)
    const exitP = home.add(vec3(0.0, 4.0, 0.0)).add(aScatter.element(i).mul(1.5));
    const tr = clamp(U.uReabsorb.sub(float(1.0).sub(aBirth.element(i)).mul(0.4)).div(0.6), 0.0, 1.0);
    home = mix(home, exitP, pow(tr, 2.0));

    // breathe along radius (whole-body coherent inhale)
    const breath = float(0.5).add(sin(time.mul(2.5)).mul(0.5));
    home = home.add(base.normalize().mul(U.uGrow.mul(0.014).mul(length(base)).mul(breath)));

    // divergence-free curl flow (displacement field, NOT integration of pos)
    const flow = curlNoise3(base.mul(U.uCurlFreq).add(time.mul(U.uDrift))).mul(U.uCurlAmp);
    const target = home.add(flow);

    // critically-damped spring so the silhouette always re-forms
    const p = posLive.element(i); const v = velLive.element(i);
    const acc = target.sub(p).mul(U.uSpring);
    const vNew = v.add(acc.mul(U.uDt)).mul(U.uDamp);
    velLive.element(i).assign(vNew);
    posLive.element(i).assign(p.add(vNew.mul(U.uDt)));
  })().compute(count);

  return { posLive, aBand, U, computeStep };
}
```

### 3b. Render material — SpriteNodeMaterial, sacred palette, emits >1 for bloom
```ts
import { SpriteNodeMaterial } from 'three/webgpu';

export function buildGpuPointMaterial(posLive, anchors, count, postureU) {
  // sacred baked color + band ride along as read-only attributes
  const aColor = storage(new THREE.StorageInstancedBufferAttribute(anchors.colors, 3), 'vec3', count).toReadOnly();
  const aBand  = storage(new THREE.StorageInstancedBufferAttribute(anchors.bands, 1), 'float', count).toReadOnly();
  const { uPostureColor, uPostureTint, uGlowMul, uIgnite, uAwaken, uStatePulse } = postureU;

  const mat = new SpriteNodeMaterial({ transparent: true, depthWrite: false, depthTest: false });
  mat.blending = THREE.AdditiveBlending;

  // POSITION: read the compute-simulated live position
  mat.positionNode = posLive.toAttribute();

  // soft round procedural sprite (no texture) — same halo+core profile as WebGL frag
  const uvc = uv().sub(0.5); const d = length(uvc);
  const t = clamp(float(1.0).sub(d.mul(2.0)), 0.0, 1.0);
  const intensity = pow(t, 2.4).mul(0.62).add(pow(t, 9.0).mul(0.85));

  // COLOR: sacred region color + posture WASH only (hue preserved; identical to pointFieldMaterial L104-127)
  const band = aBand.toAttribute();
  let c = mix(aColor.toAttribute(), aColor.toAttribute().mul(uPostureColor).mul(1.6), clamp(uPostureTint, 0.0, 0.8));
  // luminance-only flashes weighted to cortex(band high)/spine(band low) — NEVER touch hue
  const ignite = clamp(uIgnite, 0.0, 1.0).mul(smoothstep(0.45, 1.0, band));
  const awaken = clamp(uAwaken, 0.0, 1.0).mul(smoothstep(0.40, 1.0, band)).mul(0.5);
  const spineMask = float(1.0).sub(smoothstep(0.35, 0.55, band));
  const state = clamp(uStatePulse, 0.0, 1.0).mul(spineMask).mul(0.6);
  c = c.mul(uGlowMul).mul(float(1.0).add(ignite.mul(2.5)).add(awaken).add(state.mul(0.8)));

  mat.colorNode = vec4(c.mul(intensity), intensity);  // emits >1 → Bloom (threshold 1.0) flares it
  mat.scaleNode = aSize.toAttribute().mul(uSize);      // per-particle size, weak/no attenuation = poster flatness
  return mat;
}
```

### 3c. Curl-noise drop-in (`lib/curlNoiseTSL.ts`)
Divergence-free curl of a gradient-noise potential field (analytic finite-difference curl). TSL `Fn` so it inlines into the compute graph:
```ts
import { Fn, vec3, float, cross } from 'three/tsl';
import { mx_noise_float } from 'three/tsl'; // three ships the MaterialX noise nodes

export const curlNoise3 = Fn(([p]) => {
  const e = float(0.1);
  const dx = vec3(e, 0, 0), dy = vec3(0, e, 0), dz = vec3(0, 0, e);
  // potential field = 3 decorrelated noise samples
  const pot = (q) => vec3(mx_noise_float(q), mx_noise_float(q.add(31.4)), mx_noise_float(q.sub(57.7)));
  const dpdy = pot(p.add(dy)).sub(pot(p.sub(dy)));
  const dpdz = pot(p.add(dz)).sub(pot(p.sub(dz)));
  const dpdx = pot(p.add(dx)).sub(pot(p.sub(dx)));
  // curl = (∂Pz/∂y − ∂Py/∂z, ∂Px/∂z − ∂Pz/∂x, ∂Py/∂x − ∂Px/∂y)
  const curl = vec3(
    dpdy.z.sub(dpdz.y), dpdz.x.sub(dpdx.z), dpdx.y.sub(dpdy.x)
  ).div(e.mul(2.0));
  return curl;
});
```

### 3d. Per-frame driver (`GpuBrainPointField.tsx`, inside `useFrame`)
Same scalar-only damping as today's `BrainPointField` — runs the compute pass, mutates a handful of uniform `.value`s from `lifecycleTargets(phase)`. Zero per-particle CPU.
```ts
useFrame((state, delta) => {
  const phase = conversationToOrganismPhase(getConversationPhase()) ?? getOrganismPhase();
  const tgt = lifecycleTargets(phase);
  U.uDt.value = Math.min(delta, 1/30);
  U.uGrow.value     = THREE.MathUtils.damp(U.uGrow.value, tgt.grow, 2, delta);
  U.uArrival.value  = THREE.MathUtils.damp(U.uArrival.value, tgt.arrival, 1.6, delta);
  U.uReabsorb.value = THREE.MathUtils.damp(U.uReabsorb.value, tgt.reabsorb, 1.6, delta);
  U.uCurlAmp.value  = THREE.MathUtils.damp(U.uCurlAmp.value, 0.012 + tgt.flow*0.02, 3, delta);
  postureU.uPostureColor.value.copy(uniforms.uPosture.value); // sacred hue passthrough
  postureU.uPostureTint.value = uniforms.uPostureTint.value;
  gl.computeAsync(computeStep);  // dispatch the sim for this frame
});
```

---

## 4. RISKS + tiny A/B test plan

**Risks (with mitigations):**
1. **`@react-three/postprocessing` is WebGL-only.** Under WebGPU you must reimplement the Bloom+AgX pass as three's WebGPU `PostProcessing` + `bloom()` TSL node. *Mitigation:* match the WebGL pass numerically (threshold 1.0, half-res, same exposure), keep it behind the flag, A/B the glow side-by-side. This is the single largest build cost.
2. **r0.184 WebGPU/TSL is young.** API churn between three minor versions; storage-buffer + `SpriteNodeMaterial` ergonomics can shift. *Mitigation:* pin `three`, keep the spike in the lab, don't promote until it clears FIDELITY. The TSL→GLSL compile gives a built-in WebGL2 fallback for the *material* even if compute is the only WebGPU-exclusive piece.
3. **WebGPU adapter absent / driver-blocklisted** (older browsers, some Linux/Intel). *Mitigation:* the capability gate in `readGpuMode()` falls back to WebGL silently; default users never hit it.
4. **VRAM at 1M particles** (pos+vel+anchors ≈ 8 buffers × 1M × 12B ≈ 100MB+). RTX 3050 is 4GB-class; memory notes already flag 256k breaking *WebGL*. *Mitigation:* tier the count (250k spike-default), reserve 1M for the capture/showcase machine, add a `PerformanceMonitor`-style demote.
5. **Palette regression risk** — any GPU recolor would violate the sacred tetrad. *Mitigation:* `aColor` is read-only and never recomputed; only luminance/wash math touches it, asserted identical to `pointFieldMaterial.ts`. This is the non-negotiable judged against the poster.
6. **Bloom blowout to white** at high density (additive overlap). *Mitigation:* same AgX roll-off + threshold-1.0 knee as today; if dense cortex reads white, lower exposure/intensity before touching colors (per the spec's composition check).

**Tiny A/B test plan (vs current build):**
- **Toggle:** open `:5173/?being=points` (control, WebGL 90k) and `:5173/?being=points&gpu=webgpu` (spike) in two tabs — identical scene, identical posture system, only the substrate differs. CORS is fine on :5173 (the test-port law).
- **Static parity:** at rest, front-on poster pose — confirm the spike's silhouette, hue distribution, and halo softness match the control (judged against `demoplan.png` panel 2). Sacred-palette check: no rogue blue/indigo introduced.
- **Lifecycle parity:** fire one chat turn through both. Verify arrival inrush, awaken cortex-heat, materialization, spine state-pulse (panel 5 flow-down), reabsorption up-spine — all read in the spike exactly as the control. The bus contract is shared, so any divergence is a render bug, not a behavior bug.
- **Perf capture:** r3f `<Perf>` / `stats` overlay both tabs; record FPS at 250k/500k/1M (spike) vs 90k (control) on the RTX 3050. Pass bar: spike holds ≥60fps at 250k, the control's quality at strictly higher density.
- **Screenshot A/B for the operator's FIDELITY call** — before/after in HIS browser, his real GPU (software captures are approximate). Promote only on his sign-off, per the standing law.

---

## 5. THREE PATTERN SAMPLES worth prototyping (distinct gorgeous looks)

All three reuse the same compute+render scaffold and the same sacred tetrad — they differ in the *flow field* and *density distribution*, each a distinct AAA "look" to put in front of the operator. Each is judged against a specific poster panel.

**Sample A — "The Churning Cortex" (panel 2/6 — alive at rest).**
1M particles, **strong spring + low curl-amp**, so the brain silhouette is rock-solid but its *surface* boils with fine divergence-free swirl — the cortex visibly *thinks*. Density biased to the canopy (70% budget, matching the sampler). The poster's signature: dense multicolored puncta that shimmer without losing the head shape. The flow-band sweep (cyan, panel 6) reads as a luminous wave climbing the spine. This is the closest 1:1 to the poster's resting being — the safest, most likely-to-ship look.

**Sample B — "Synaptic Streamlines" (panel 5/6 — orchestration, the nerves carrying state).**
Curl-amp ramps with `uFlowSpeed`; particles are pulled along **anisotropic curl tubes oriented down the body axis** (bias the curl gradient toward `−Y` on the spine band, `aBand<0.55`). The result: visible *current* — thousands of motes streaming brain→roots into the focused work, exactly the poster's "data flows DOWN the spine" legend. Posture cyan stream. Reads as conduction, not churn — the most *Jarvis-alive* of the three when a code turn is running.

**Sample C — "The Coalescence" (panel 1/7 — arrival & reabsorption, the voyage).**
Foregrounds the lifecycle transitions: at `uArrival`, 1M motes stream inward from a scattered shell (origin `aBase + aScatter·R`, staggered by `aBirth`) and **condense into the being** with an ease-out, a single cortex-weighted ignition flash firing as they settle ("first ignition of awareness"). At `uReabsorb`, the inverse — the field rises +Y, scatters, curl-amp grows, fades up the spine into the brain ("energy returns up the spine. Back to rest. Always voyaging."). This is the GPU substrate's showpiece: 1M-particle coalescence is physically impossible on the 90k WebGL path, so it's the clearest "this is why WebGPU" demo for the FIDELITY review.

---

**Files grounding this spike (all read, absolute paths):**
- Poster ground truth: `C:\Users\kumar\ai-editor\GAG demo\reference\demoplan.png`
- Nextgen direction (Phase 5 = exactly this WebGPU/TSL spike): `C:\Users\kumar\ai-editor\.aios\state\SUPERBRAIN_NEXTGEN_DESIGN.md`
- Point-field substrate spec (the WebGL path this translates 1:1): `C:\Users\kumar\ai-editor\docs\superpowers\specs\2026-06-20-pointfield-3d-living-being-design.md`
- Material to mirror (uniforms, blending, shaders): `C:\Users\kumar\ai-editor\frontend\src\superbrain\lib\pointFieldMaterial.ts`
- Sacred posture tetrad: `C:\Users\kumar\ai-editor\frontend\src\superbrain\lib\bodyPosture.ts`
- Substrate mount + lifecycle driver: `C:\Users\kumar\ai-editor\frontend\src\superbrain\components\canvas\BrainPointField.tsx`
- Anchor seeding (reused for GPU): `C:\Users\kumar\ai-editor\frontend\src\superbrain\lib\pointFieldSampler.ts`
- Flag pattern to mirror: `C:\Users\kumar\ai-editor\frontend\src\superbrain\lib\beingMode.ts`
- Renderer/Canvas gate point: `C:\Users\kumar\ai-editor\frontend\src\superbrain\components\canvas\WorkspaceCanvas.tsx` (lines 216–247)
- Post pass to match: `C:\Users\kumar\ai-editor\frontend\src\superbrain\components\canvas\PostFX.tsx`

NOTE: This is a read-only design deliverable. No files were created, modified, or deleted; the default WebGL path is untouched by design. Lab proposal for `?gpu=webgpu`. New lab files proposed: `lib/gpuMode.ts`, `lib/gpuPointFieldTSL.ts`, `lib/curlNoiseTSL.ts`, `components/canvas/GpuBrainPointField.tsx`, plus a flag branch in `WorkspaceCanvas.tsx` + `SuperbrainScene.tsx`. Three.js r0.184 + r3f v9 already support `three/webgpu` + TSL — no dependency add required for the spike.
