# Point-Field 3D Living-Being Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the live 3D superbrain from a *lit mesh* to a single ~60k-point *additive glow field* so it reads as the 2D `demoplan.png` poster ("point-field organism"), while keeping all behavior, lifecycle, data-binding, and the spectral-v1 posture system unchanged.

**Architecture:** Sample `brain.glb` (+ spine/root meshes) into one `THREE.Points` with a custom premultiplied-additive `ShaderMaterial`; all animation in the vertex shader from baked static attributes + a handful of scalar uniforms; the existing `CognitionUniforms` posture system binds per-point; the existing `PostFX` Bloom→AgX pipeline supplies the glow (points just emit >1 and set `toneMapped:false`); a poster-flat camera (low FOV) and depth-fog-as-alpha give the flat 2D read. The whole point-field is gated behind `?being=points` with the existing mesh being kept as the default fallback until operator FIDELITY sign-off.

**Tech Stack:** React 19, React Three Fiber 9, three 0.184, @react-three/drei 10, @react-three/postprocessing 3, Vitest 4, TypeScript 5.9. `MeshSurfaceSampler` from `three/examples/jsm/math/MeshSurfaceSampler.js`.

**Spec:** `docs/superpowers/specs/2026-06-20-pointfield-3d-living-being-design.md`

---

## Ground truth (verified — the engineer can rely on these)

- `frontend/public/models/brain.glb` = single mesh, **2605 verts**, attrs `POSITION/NORMAL/TANGENT/TEXCOORD_0`, **no `COLOR_0`, 0 materials**. Region color comes from a **processed clone** passed as the `source`/`object` prop (smooth-normaled + region-vertex-colored upstream), NOT the raw GLB. `sample()` silently leaves color untouched if the geometry has no `color` attribute.
- The proven sampler pattern is `frontend/src/superbrain/components/canvas/CorticalSignals.tsx` (~320 motes): Set-dedup of geometries, mulberry32 seeded PRNG, budget-by-triangle-count, per-sample `position.applyMatrix4(mesh.matrixWorld)` + `normalMatrix.getNormalMatrix(mesh.matrixWorld)`, hoisted scratch temporaries, `additive / depthWrite:false / toneMapped:false`.
- Shared uniforms live in `SuperbrainScene.tsx`: `interface CognitionUniforms` (incl. `uTime`, `uPosture`, `uPostureTint`, `uFlow`, `uPostureCommit`, `uArrival`), one module-level instance `SCENE_UNIFORMS`, mutated once per frame. The brain `source` clone is `brainAsset.object`, passed to `CorticalSignals`/`NeuralAura` today.
- Post-processing is `frontend/src/superbrain/components/canvas/PostFX.tsx`: `<EffectComposer>` → `<Bloom luminanceThreshold={1.0} luminanceSmoothing={0.9} mipmapBlur>` → AgX `<ToneMapping>` → grades/vignette/noise. The composer **forces `renderer.toneMapping = NoToneMapping`**, so anything with `toneMapped:false` emitting >1 blooms; anything ≤1 (the starfield) does not. Tuning values are in `frontend/src/superbrain/lib/constants.ts` `POST_FX`.
- Camera is set in `frontend/src/superbrain/components/canvas/WorkspaceCanvas.tsx` (`camera={{ position:[0,0.25,8.5], fov: CAMERA.fov(=45) }}`); `CameraDrift` in `SuperbrainScene.tsx` animates `state.camera` every frame.
- Spine/vertebrae/roots are **mesh** geometry built in `NervousSystem.tsx` from `lib/spineAnatomy.ts` constants (Tube/Torus). `SEGMENT_ANCHORS` is exported.
- Quality tiers: `QualityTier = 'low'|'medium'|'high'` from `components/QualityTierProvider.tsx`; DPR per tier in `WorkspaceCanvas.tsx` `TIER_DPR`.
- Module feature flags are plain consts (`const SHOW_MEMORY_GALAXY = true`, `const NODE_BRAIN = false`).

## Conventions (apply to EVERY task)

- **Build location:** edit in the **product tree** `frontend/src/superbrain/*`. After each task, **mirror identical files into the gitignored lab** (`GAG demo/gag-orchestrator/...` byte-synced source). New product-only files have no lab counterpart unless they live under `superbrain/`.
- **Test port is :5173 only** (backend CORS allows :5173/:4173/:3000 — any other port silently "Failed to fetch"). FIDELITY is judged in the operator's real browser, not software-GL captures.
- **Quality gates (must be green before any commit), run from repo root:**
  - `npm --prefix frontend run lint`
  - `npm --prefix frontend run typecheck`
  - `npm --prefix frontend run test`
  - `npm --prefix frontend run build`
- **Single test file:** `npm --prefix frontend run test -- <relative/path.test.ts>` (forwards to `vitest run <path>`).
- **Commit discipline:** the operator's standing rule is **commit only when he says go.** Each task lists a ready-to-run commit command; do NOT run it until the operator approves that batch. End commit messages with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.
- **FIDELITY gate:** visual phases (P1–P6) cannot be unit-tested for "look." Their gate is: all four quality gates green **and** operator sign-off at :5173. Pure-logic units (sampler, flag, material factory, lifecycle math) ARE unit-tested (TDD below).
- **Sacred:** never change the spectral-v1 palette (`bodyPosture.ts`) or `brain.glb`/texture assets. Never touch `aios/security/*`. No `git push` without explicit OK.
- **Fallback safety:** the mesh being stays the **default**; the point-field is opt-in via `?being=points` for the whole build, so a broken intermediate never replaces the working scene. Default flips to `points` only in the final task, after sign-off.

---

## File structure

**New files (product tree; mirror `superbrain/*` to lab):**
- `frontend/src/superbrain/lib/pointFieldSampler.ts` — pure: sources → all baked Float32 attribute arrays. No rendering.
- `frontend/src/superbrain/lib/pointFieldSampler.test.ts` — unit tests.
- `frontend/src/superbrain/lib/beingMode.ts` — pure `?being=` flag reader.
- `frontend/src/superbrain/lib/beingMode.test.ts` — unit tests.
- `frontend/src/superbrain/lib/pointFieldLifecycle.ts` — pure: organism phase → {grow, flow, arrival, reabsorb} targets.
- `frontend/src/superbrain/lib/pointFieldLifecycle.test.ts` — unit tests.
- `frontend/src/superbrain/lib/curlNoise.glsl.ts` — divergence-free curl GLSL chunk (string export).
- `frontend/src/superbrain/lib/pointFieldMaterial.ts` — `ShaderMaterial` factory (vertex+fragment, premultiplied additive, uniforms, cache key).
- `frontend/src/superbrain/lib/pointFieldMaterial.test.ts` — factory unit test.
- `frontend/src/superbrain/components/canvas/BrainPointField.tsx` — mounts `<points>`, drives uniforms via ref, owns the lifecycle scalar damping.

**Modified files:**
- `frontend/src/superbrain/components/canvas/SuperbrainScene.tsx` — `BEING_MODE` flag; mount `BrainPointField` (and gate the mesh being) by flag; add point-field uniforms to `CognitionUniforms`/`createCognitionUniforms`; poster camera; point-count tiers.
- `frontend/src/superbrain/components/canvas/WorkspaceCanvas.tsx` — (P6) DPR clamp / PerformanceMonitor for points mode if needed.
- `frontend/src/superbrain/lib/constants.ts` — (P3) optional `POINT_FIELD` tuning block.

---

# PHASE P0 — Sampler scale-up + flag (pure logic, TDD)

**Gate:** static point cloud renders at `:5173/?being=points`, one draw call (`renderer.info.render.calls` ≈ 1 for the cloud), deterministic layout; mesh being unchanged at default.

### Task 1: Pure point-field sampler

**Files:**
- Create: `frontend/src/superbrain/lib/pointFieldSampler.ts`
- Test: `frontend/src/superbrain/lib/pointFieldSampler.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/superbrain/lib/pointFieldSampler.test.ts
import { describe, it, expect } from 'vitest';
import * as THREE from 'three';
import { samplePointField, type PointFieldSource } from './pointFieldSampler';

function coloredBox(): THREE.Object3D {
  const geo = new THREE.BoxGeometry(2, 2, 2, 4, 4, 4);
  const n = geo.getAttribute('position').count;
  const colors = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) { colors[i * 3] = 0.5; colors[i * 3 + 1] = 0.25; colors[i * 3 + 2] = 0.9; }
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  const mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial());
  const root = new THREE.Group();
  root.add(mesh);
  return root;
}

describe('samplePointField', () => {
  const sources: PointFieldSource[] = [{ object: coloredBox(), share: 1, axisMin: -1, axisMax: 1 }];

  it('produces every attribute array at the requested count', () => {
    const d = samplePointField(sources, 5000, 0xa11ce);
    expect(d.count).toBe(5000);
    expect(d.positions).toHaveLength(5000 * 3);
    expect(d.colors).toHaveLength(5000 * 3);
    expect(d.normals).toHaveLength(5000 * 3);
    expect(d.sizes).toHaveLength(5000);
    expect(d.phases).toHaveLength(5000);
    expect(d.speeds).toHaveLength(5000);
    expect(d.scatter).toHaveLength(5000 * 3);
    expect(d.births).toHaveLength(5000);
    expect(d.bands).toHaveLength(5000);
  });

  it('reads the baked region color (the COLOR_0 trap)', () => {
    const d = samplePointField(sources, 1000, 1);
    // not all-zero — color attribute was honored
    const sum = d.colors.reduce((a, b) => a + b, 0);
    expect(sum).toBeGreaterThan(0);
    expect(d.colors[0]).toBeCloseTo(0.5, 1);
    expect(d.colors[2]).toBeCloseTo(0.9, 1);
  });

  it('is deterministic for a fixed seed', () => {
    const a = samplePointField(sources, 800, 42);
    const b = samplePointField(sources, 800, 42);
    expect(Array.from(a.positions)).toEqual(Array.from(b.positions));
    const c = samplePointField(sources, 800, 43);
    expect(Array.from(a.positions)).not.toEqual(Array.from(c.positions));
  });

  it('bakes attributes into expected ranges', () => {
    const d = samplePointField(sources, 2000, 7);
    for (let i = 0; i < d.count; i++) {
      expect(d.sizes[i]).toBeGreaterThanOrEqual(0.6);
      expect(d.sizes[i]).toBeLessThanOrEqual(1.4);
      expect(d.speeds[i]).toBeGreaterThanOrEqual(0.6);
      expect(d.speeds[i]).toBeLessThanOrEqual(1.4);
      expect(d.phases[i]).toBeGreaterThanOrEqual(0);
      expect(d.phases[i]).toBeLessThanOrEqual(Math.PI * 2 + 1e-6);
      expect(d.births[i]).toBeGreaterThanOrEqual(0);
      expect(d.births[i]).toBeLessThanOrEqual(1);
      expect(d.bands[i]).toBeGreaterThanOrEqual(0);
      expect(d.bands[i]).toBeLessThanOrEqual(1);
    }
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- src/superbrain/lib/pointFieldSampler.test.ts`
Expected: FAIL — `samplePointField` is not defined.

- [ ] **Step 3: Write the implementation**

```ts
// frontend/src/superbrain/lib/pointFieldSampler.ts
import * as THREE from 'three';
import { MeshSurfaceSampler } from 'three/examples/jsm/math/MeshSurfaceSampler.js';

const TAU = Math.PI * 2;

/** One sampling source: a processed (region-colored) clone + its budget share +
 *  the world-Y range used to normalize aBand (0 at axisMin → 1 at axisMax). */
export interface PointFieldSource {
  object: THREE.Object3D;
  /** fraction of the total budget for this source (the array should sum ~1). */
  share: number;
  /** group-local Y that maps to aBand=0 (e.g. cloud top). */
  axisMin: number;
  /** group-local Y that maps to aBand=1 (e.g. root base). */
  axisMax: number;
}

export interface PointFieldData {
  positions: Float32Array; // itemSize 3 (aBase, world-transformed + jitter)
  colors: Float32Array;    // itemSize 3 (region RGB, linear-sRGB)
  normals: Float32Array;   // itemSize 3 (surface normal)
  sizes: Float32Array;     // itemSize 1 (~[0.6,1.4])
  phases: Float32Array;    // itemSize 1 (0..2π)
  speeds: Float32Array;    // itemSize 1 (~[0.6,1.4])
  scatter: Float32Array;   // itemSize 3 (unit dir, arrival/dissolve)
  births: Float32Array;    // itemSize 1 (0..1 stagger)
  bands: Float32Array;     // itemSize 1 (normalized body-axis coord)
  count: number;
}

/** Project-standard mulberry32 (matches CorticalSignals/NodeLattice). */
function createSeededRandom(seed: number) {
  let state = seed >>> 0;
  return () => {
    state += 0x6d2b79f5;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

/** Tiny hand-drawn jitter so points don't read as mechanically scanned (% of model scale). */
const JITTER = 0.012;

type SeedableSampler = MeshSurfaceSampler & { randomFunction: () => number };

/**
 * Sample one or more region-colored source clones into a single set of baked
 * point-field attribute arrays. Pure: deterministic given (sources, count, seed).
 */
export function samplePointField(
  sources: PointFieldSource[],
  totalCount: number,
  seed: number,
): PointFieldData {
  const positions = new Float32Array(totalCount * 3);
  const colors = new Float32Array(totalCount * 3);
  const normals = new Float32Array(totalCount * 3);
  const sizes = new Float32Array(totalCount);
  const phases = new Float32Array(totalCount);
  const speeds = new Float32Array(totalCount);
  const scatter = new Float32Array(totalCount * 3);
  const births = new Float32Array(totalCount);
  const bands = new Float32Array(totalCount);

  const random = createSeededRandom(seed);
  const position = new THREE.Vector3();
  const normal = new THREE.Vector3();
  const color = new THREE.Color();
  const dir = new THREE.Vector3();
  const normalMatrix = new THREE.Matrix3();

  const triangleCount = (mesh: THREE.Mesh) => {
    const index = mesh.geometry.getIndex();
    return (index ? index.count : mesh.geometry.getAttribute('position').count) / 3;
  };

  let writeIndex = 0;
  const shareTotal = sources.reduce((s, src) => s + src.share, 0) || 1;

  sources.forEach((src, srcIndex) => {
    src.object.updateMatrixWorld(true);
    const isLastSource = srcIndex === sources.length - 1;
    // budget for this source (last source absorbs rounding so the array fills)
    const srcTarget = isLastSource
      ? totalCount
      : writeIndex + Math.round((totalCount * src.share) / shareTotal);

    const seen = new Set<THREE.BufferGeometry>();
    const meshes: THREE.Mesh[] = [];
    src.object.traverse((object) => {
      if (!(object instanceof THREE.Mesh)) return;
      if (seen.has(object.geometry)) return;
      seen.add(object.geometry);
      meshes.push(object);
    });
    if (meshes.length === 0) return;

    const triTotal = meshes.reduce((sum, m) => sum + triangleCount(m), 0) || 1;
    const axisRange = src.axisMax - src.axisMin || 1;

    let triSeen = 0;
    meshes.forEach((mesh, meshIndex) => {
      triSeen += triangleCount(mesh);
      const meshTarget = meshIndex === meshes.length - 1
        ? srcTarget
        : writeIndex + Math.round((srcTarget - writeIndex) * (triSeen / triTotal) - (writeIndex - writeIndex));
      const target = Math.min(meshTarget, srcTarget);

      const hasColor = !!mesh.geometry.getAttribute('color');
      const sampler = new MeshSurfaceSampler(mesh) as SeedableSampler;
      sampler.randomFunction = random;
      sampler.build();
      normalMatrix.getNormalMatrix(mesh.matrixWorld);

      for (; writeIndex < target && writeIndex < totalCount; writeIndex++) {
        sampler.sample(position, normal, hasColor ? color : undefined);
        position.applyMatrix4(mesh.matrixWorld);
        normal.applyMatrix3(normalMatrix).normalize();

        // hand-drawn jitter
        position.x += (random() - 0.5) * JITTER;
        position.y += (random() - 0.5) * JITTER;
        position.z += (random() - 0.5) * JITTER;

        positions[writeIndex * 3] = position.x;
        positions[writeIndex * 3 + 1] = position.y;
        positions[writeIndex * 3 + 2] = position.z;

        colors[writeIndex * 3] = hasColor ? color.r : 0.6;
        colors[writeIndex * 3 + 1] = hasColor ? color.g : 0.5;
        colors[writeIndex * 3 + 2] = hasColor ? color.b : 0.95;

        normals[writeIndex * 3] = normal.x;
        normals[writeIndex * 3 + 1] = normal.y;
        normals[writeIndex * 3 + 2] = normal.z;

        sizes[writeIndex] = 0.6 + random() * 0.8;
        phases[writeIndex] = random() * TAU;
        speeds[writeIndex] = 0.6 + random() * 0.8;
        births[writeIndex] = random();

        // random unit scatter dir
        dir.set(random() * 2 - 1, random() * 2 - 1, random() * 2 - 1);
        if (dir.lengthSq() < 1e-6) dir.set(0, 1, 0);
        dir.normalize();
        scatter[writeIndex * 3] = dir.x;
        scatter[writeIndex * 3 + 1] = dir.y;
        scatter[writeIndex * 3 + 2] = dir.z;

        // body-axis band: 0 at axisMin → 1 at axisMax, clamped
        bands[writeIndex] = THREE.MathUtils.clamp((position.y - src.axisMin) / axisRange, 0, 1);
      }
    });
  });

  return { positions, colors, normals, sizes, phases, speeds, scatter, births, bands, count: totalCount };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend run test -- src/superbrain/lib/pointFieldSampler.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 5: Mirror to lab + run all gates**

Copy `pointFieldSampler.ts` + `pointFieldSampler.test.ts` into the lab's mirror of `superbrain/lib/`. Then:
Run: `npm --prefix frontend run lint && npm --prefix frontend run typecheck && npm --prefix frontend run test && npm --prefix frontend run build`
Expected: all green.

- [ ] **Step 6: Commit (on operator go)**

```bash
git add frontend/src/superbrain/lib/pointFieldSampler.ts frontend/src/superbrain/lib/pointFieldSampler.test.ts
git commit -m "feat(pointfield): pure brain->point-field sampler (P0)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `?being=` fallback flag

**Files:**
- Create: `frontend/src/superbrain/lib/beingMode.ts`
- Test: `frontend/src/superbrain/lib/beingMode.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/superbrain/lib/beingMode.test.ts
import { describe, it, expect } from 'vitest';
import { readBeingMode } from './beingMode';

describe('readBeingMode', () => {
  it('returns points only for ?being=points', () => {
    expect(readBeingMode('?being=points')).toBe('points');
  });
  it('defaults to mesh when absent', () => {
    expect(readBeingMode('')).toBe('mesh');
  });
  it('returns mesh for ?being=mesh', () => {
    expect(readBeingMode('?being=mesh')).toBe('mesh');
  });
  it('falls back to mesh for unknown values', () => {
    expect(readBeingMode('?being=banana')).toBe('mesh');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- src/superbrain/lib/beingMode.test.ts`
Expected: FAIL — `readBeingMode` not defined.

- [ ] **Step 3: Write the implementation**

```ts
// frontend/src/superbrain/lib/beingMode.ts
export type BeingMode = 'points' | 'mesh';

/**
 * Which being substrate to render. Default 'mesh' (the working scene) for the
 * whole build; opt into the point-field with ?being=points. The default flips
 * to 'points' only after operator FIDELITY sign-off (final task).
 */
export function readBeingMode(search?: string): BeingMode {
  const raw = search ?? (typeof window !== 'undefined' ? window.location.search : '');
  const value = new URLSearchParams(raw).get('being');
  return value === 'points' ? 'points' : 'mesh';
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend run test -- src/superbrain/lib/beingMode.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 5: Mirror to lab + gates**

Mirror both files to lab. Run the four gates (lint/typecheck/test/build). Expected: green.

- [ ] **Step 6: Commit (on operator go)**

```bash
git add frontend/src/superbrain/lib/beingMode.ts frontend/src/superbrain/lib/beingMode.test.ts
git commit -m "feat(pointfield): ?being=points fallback flag (P0)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Point-field material factory (initial — plain dots)

This task ships the material with a SIMPLE round-dot fragment so P0 can render a visible static cloud. P1 swaps in the full glow/flatness math.

**Files:**
- Create: `frontend/src/superbrain/lib/pointFieldMaterial.ts`
- Test: `frontend/src/superbrain/lib/pointFieldMaterial.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/superbrain/lib/pointFieldMaterial.test.ts
import { describe, it, expect } from 'vitest';
import * as THREE from 'three';
import { createPointFieldMaterial } from './pointFieldMaterial';

describe('createPointFieldMaterial', () => {
  it('is additive, depth-write-off, transparent, tone-map-off', () => {
    const m = createPointFieldMaterial();
    expect(m).toBeInstanceOf(THREE.ShaderMaterial);
    expect(m.depthWrite).toBe(false);
    expect(m.transparent).toBe(true);
    expect(m.toneMapped).toBe(false);
    expect(m.blending).toBe(THREE.CustomBlending);
    expect(m.premultipliedAlpha).toBe(true);
  });

  it('exposes the tunable + posture uniforms', () => {
    const m = createPointFieldMaterial();
    for (const key of ['uTime','uScale','uSize','uAttenK','uFogDensity','uGlowMul',
                        'uGrow','uFlow','uFlowSpeed','uCurlAmp','uArrival','uReabsorb',
                        'uPostureColor','uPostureTint']) {
      expect(m.uniforms[key]).toBeDefined();
    }
  });

  it('accepts shared posture leaf uniforms by reference', () => {
    const shared = { uTime: { value: 3 }, uPosture: { value: new THREE.Color(1, 0, 0) }, uPostureTint: { value: 0.5 } };
    const m = createPointFieldMaterial({
      uTime: shared.uTime, uPostureColor: shared.uPosture, uPostureTint: shared.uPostureTint,
    });
    expect(m.uniforms.uTime).toBe(shared.uTime);
    expect(m.uniforms.uPostureColor).toBe(shared.uPosture);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- src/superbrain/lib/pointFieldMaterial.test.ts`
Expected: FAIL — `createPointFieldMaterial` not defined.

- [ ] **Step 3: Write the implementation**

```ts
// frontend/src/superbrain/lib/pointFieldMaterial.ts
import * as THREE from 'three';

export interface PointFieldUniformOverrides {
  uTime?: { value: number };
  uPostureColor?: { value: THREE.Color };
  uPostureTint?: { value: number };
}

const VERTEX = /* glsl */ `
  uniform float uScale;     // drawingBufferHeight * 0.5 (recompute on resize/DPR)
  uniform float uSize;
  uniform float uAttenK;    // 0 = flat poster, ~0.25 = weak depth
  attribute float aSize;
  attribute vec3 aColor;
  varying vec3 vColor;
  void main() {
    vColor = aColor;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    float atten = mix(1.0, uScale / -mv.z, uAttenK);
    gl_PointSize = min(uSize * aSize * atten, 64.0);
    gl_Position = projectionMatrix * mv;
  }
`;

// P0 fragment: simple soft round dot (premultiplied). P1 replaces this.
const FRAGMENT = /* glsl */ `
  precision mediump float;
  varying vec3 vColor;
  uniform vec3 uPostureColor;
  uniform float uPostureTint;
  uniform float uGlowMul;
  void main() {
    float d = length(gl_PointCoord - 0.5);
    float i = pow(1.0 - clamp(d / 0.5, 0.0, 1.0), 2.5);
    if (i <= 0.003) discard;
    vec3 c = mix(vColor, vColor * uPostureColor, clamp(uPostureTint, 0.0, 0.8)) * uGlowMul;
    gl_FragColor = vec4(c * i, i);
  }
`;

export function createPointFieldMaterial(overrides: PointFieldUniformOverrides = {}): THREE.ShaderMaterial {
  const material = new THREE.ShaderMaterial({
    vertexShader: VERTEX,
    fragmentShader: FRAGMENT,
    uniforms: {
      uTime: overrides.uTime ?? { value: 0 },
      uScale: { value: 540 },
      uSize: { value: 9 },
      uAttenK: { value: 0.25 },
      uFogDensity: { value: 0.0 },
      uGlowMul: { value: 1.0 },     // P0 plain; P1 raises >1 for bloom
      uGrow: { value: 0 },
      uFlow: { value: 0.16 },
      uFlowSpeed: { value: 0.16 },
      uCurlAmp: { value: 0 },
      uArrival: { value: 0 },
      uReabsorb: { value: 0 },
      uPostureColor: overrides.uPostureColor ?? { value: new THREE.Color(150 / 255, 120 / 255, 255 / 255) },
      uPostureTint: overrides.uPostureTint ?? { value: 0 },
    },
    transparent: true,
    depthWrite: false,
    depthTest: true,
    toneMapped: false,
    blending: THREE.CustomBlending,
    blendEquation: THREE.AddEquation,
    blendSrc: THREE.OneFactor,
    blendDst: THREE.OneFactor,
    premultipliedAlpha: true,
  });
  material.customProgramCacheKey = () => 'pointfield_v1';
  return material;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend run test -- src/superbrain/lib/pointFieldMaterial.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Mirror to lab + gates** — mirror both files; run the four gates. Expected: green.

- [ ] **Step 6: Commit (on operator go)**

```bash
git add frontend/src/superbrain/lib/pointFieldMaterial.ts frontend/src/superbrain/lib/pointFieldMaterial.test.ts
git commit -m "feat(pointfield): premultiplied-additive material factory (P0)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: BrainPointField component (static cloud)

**Files:**
- Create: `frontend/src/superbrain/components/canvas/BrainPointField.tsx`

- [ ] **Step 1: Write the component**

```tsx
// frontend/src/superbrain/components/canvas/BrainPointField.tsx
'use client';

import { useEffect, useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import { samplePointField, type PointFieldSource } from '@/superbrain/lib/pointFieldSampler';
import { createPointFieldMaterial } from '@/superbrain/lib/pointFieldMaterial';
import type { CognitionUniforms } from './SuperbrainScene';

/** The being's flesh as a single additive point cloud (poster substrate). */
export default function BrainPointField({
  source,
  uniforms,
  count = 60000,
}: {
  /** processed brain clone (region-colored), same prop CorticalSignals takes. */
  source: THREE.Object3D;
  uniforms: CognitionUniforms;
  count?: number;
}) {
  const materialRef = useRef<THREE.ShaderMaterial>(null);
  const gl = useThree((s) => s.gl);

  const geometry = useMemo(() => {
    // brain.glb occupies group-local y ≈ -0.222 .. +0.633; band normalizes over it.
    const sources: PointFieldSource[] = [{ object: source, share: 1, axisMin: -0.6, axisMax: 0.7 }];
    const d = samplePointField(sources, count, 0x50494e54);
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(d.positions, 3));
    g.setAttribute('aColor', new THREE.BufferAttribute(d.colors, 3));
    g.setAttribute('aNormal', new THREE.BufferAttribute(d.normals, 3));
    g.setAttribute('aSize', new THREE.BufferAttribute(d.sizes, 1));
    g.setAttribute('aPhase', new THREE.BufferAttribute(d.phases, 1));
    g.setAttribute('aSpeed', new THREE.BufferAttribute(d.speeds, 1));
    g.setAttribute('aScatter', new THREE.BufferAttribute(d.scatter, 3));
    g.setAttribute('aBirth', new THREE.BufferAttribute(d.births, 1));
    g.setAttribute('aBand', new THREE.BufferAttribute(d.bands, 1));
    return g;
  }, [source, count]);

  const material = useMemo(
    () => createPointFieldMaterial({
      uTime: uniforms.uTime,
      uPostureColor: uniforms.uPosture,
      uPostureTint: uniforms.uPostureTint,
    }),
    [uniforms],
  );

  // uScale must track the real drawing-buffer height (size attenuation correctness).
  const setScale = () => {
    const v = new THREE.Vector2();
    gl.getDrawingBufferSize(v);
    material.uniforms.uScale.value = v.height * 0.5;
  };
  useEffect(() => {
    setScale();
    window.addEventListener('resize', setScale);
    return () => {
      window.removeEventListener('resize', setScale);
      geometry.dispose();
      material.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geometry, material, gl]);

  useFrame(() => {
    // uTime already shared; keep uScale fresh against DPR changes.
    setScale();
  });

  return (
    <points geometry={geometry} frustumCulled={false} renderOrder={3}>
      <primitive object={material} ref={materialRef} attach="material" />
    </points>
  );
}
```

> **Note on the `@/superbrain/...` import alias:** confirm the alias by opening any sibling that imports from `lib/` (e.g. `CorticalSignals.tsx` imports `./SuperbrainScene`; `PostFX.tsx` imports `@/lib/constants`). Match whichever alias the neighboring files use — if they use `@/superbrain/lib/...`, keep the above; if they use a relative `../../lib/...`, switch to that. Do not invent a new alias.

- [ ] **Step 2: Mirror to lab + gates**

Mirror the file. Run lint/typecheck/test/build. Expected: green (component compiles; not yet mounted).

- [ ] **Step 3: Commit (on operator go)**

```bash
git add frontend/src/superbrain/components/canvas/BrainPointField.tsx
git commit -m "feat(pointfield): BrainPointField component (static cloud, P0)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Wire into the scene behind `?being=points`

**Files:**
- Modify: `frontend/src/superbrain/components/canvas/SuperbrainScene.tsx`

- [ ] **Step 1: Add the flag + import (top of file, near other module consts)**

```ts
import { readBeingMode } from '@/superbrain/lib/beingMode';
import BrainPointField from './BrainPointField';

/** Substrate: 'mesh' (default, the working being) or 'points' (?being=points). */
const BEING_MODE = readBeingMode();
```

- [ ] **Step 2: Gate the mesh being and mount the point-field**

In `BrainModel`'s returned group (around `SuperbrainScene.tsx:860`), wrap the mesh primitives so they only render in mesh mode, and add the point-field for points mode. Locate:

```tsx
        {surface === 'organ' ? (
          <Suspense fallback={<primitive object={brainAsset.object} />}>
            <OrganSurface />
          </Suspense>
        ) : (
          <primitive object={brainAsset.object} />
        )}
        <primitive object={neuralSkin.object} scale={1.004} />
```

Replace with:

```tsx
        {BEING_MODE === 'mesh' && (surface === 'organ' ? (
          <Suspense fallback={<primitive object={brainAsset.object} />}>
            <OrganSurface />
          </Suspense>
        ) : (
          <primitive object={brainAsset.object} />
        ))}
        {BEING_MODE === 'mesh' && <primitive object={neuralSkin.object} scale={1.004} />}
        {BEING_MODE === 'points' && (
          <BrainPointField
            source={brainAsset.object}
            uniforms={uniforms}
            count={tier === 'high' ? 80000 : tier === 'medium' ? 60000 : 40000}
          />
        )}
```

> Leave `NeuralAura`, `CorticalSignals`, `NodeLattice` as-is for P0 (they ride the mesh; in points mode they layer harmlessly or can be gated in P5). The aim of P0 is: the point cloud is visible and correct.

- [ ] **Step 3: Manual gate at :5173**

Start the dev server (operator runs `! npm --prefix frontend run dev` if not already up). Open `http://localhost:5173/?ui=superbrain&being=points`.
Expected: a static multicolored point cloud in the brain's shape (plain dots, no fancy glow yet); default `http://localhost:5173/?ui=superbrain` is the unchanged mesh being. In the console, `__THREE__`-free check: the cloud is ONE `<points>` (draw calls for the cloud ≈ 1).

- [ ] **Step 4: Mirror to lab + gates**

Mirror `SuperbrainScene.tsx`. Run the four gates. Expected: green.

- [ ] **Step 5: Commit (on operator go)**

```bash
git add frontend/src/superbrain/components/canvas/SuperbrainScene.tsx
git commit -m "feat(pointfield): mount BrainPointField behind ?being=points (P0)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

**P0 GATE (operator):** confirm at `:5173/?ui=superbrain&being=points` that the static cloud reads as the brain shape with the region palette, and the default mesh scene is untouched. Sign off before P1.

---

# PHASE P1 — Glow look (FIDELITY-gated)

**Gate (operator at :5173):** soft colored puncta, dark bg, no grey wash, colored (not white) dense clusters, flat poster read.

### Task 6: Full glow + flatness fragment/vertex + bloom emission

**Files:**
- Modify: `frontend/src/superbrain/lib/pointFieldMaterial.ts`
- Modify: `frontend/src/superbrain/lib/pointFieldMaterial.test.ts` (cache key bump assertion only)

- [ ] **Step 1: Replace the fragment with the glow+core+fog, raise glow for bloom**

In `pointFieldMaterial.ts`, replace `FRAGMENT` and add the fog varying in `VERTEX`:

```glsl
// VERTEX — add depth varying for fog, keep size attenuation
  varying float vViewZ;
  // ... inside main(), after computing mv:
  vViewZ = -mv.z;
```

```glsl
// FRAGMENT — soft radial glow + tight core + posture wash + alpha-fade fog
  precision mediump float;
  varying vec3 vColor;
  varying float vViewZ;
  uniform vec3 uPostureColor;
  uniform float uPostureTint;
  uniform float uGlowMul;
  uniform float uFogDensity;
  void main() {
    float d = length(gl_PointCoord - 0.5);
    float halo = pow(1.0 - clamp(d / 0.5, 0.0, 1.0), 2.5);
    float core = smoothstep(0.16, 0.0, d);
    float i = halo * 0.65 + core * 0.9;
    // additive-safe depth fog: fade ALPHA, never mix to fog color
    float fog = 1.0 - exp(-uFogDensity * uFogDensity * vViewZ * vViewZ);
    i *= (1.0 - fog);
    if (i <= 0.003) discard;
    vec3 c = mix(vColor, vColor * uPostureColor, clamp(uPostureTint, 0.0, 0.8));
    c *= uGlowMul;                       // >1 so the EXISTING PostFX Bloom (threshold 1.0) catches it
    gl_FragColor = vec4(c * i, i);       // premultiplied
  }
```

Set the defaults that make it bloom: in the uniforms, change `uGlowMul` default to `{ value: 2.0 }` and `uFogDensity` to `{ value: 0.06 }`. Bump `material.customProgramCacheKey = () => 'pointfield_v2';`.

- [ ] **Step 2: Update the cache-key + glow assertion in the test**

```ts
  it('emits above 1.0 for bloom and has a versioned cache key', () => {
    const m = createPointFieldMaterial();
    expect(m.uniforms.uGlowMul.value).toBeGreaterThan(1.0);
    expect(m.customProgramCacheKey()).toContain('v2');
  });
```

- [ ] **Step 3: Run tests**

Run: `npm --prefix frontend run test -- src/superbrain/lib/pointFieldMaterial.test.ts`
Expected: PASS.

- [ ] **Step 4: Manual FIDELITY at :5173** — `?being=points`: dots now have soft halos and bloom (via existing PostFX); dense regions stay colored, not white. If clusters read white, lower `uGlowMul` default toward 1.6 or `POST_FX.bloom.intensity` (do NOT change the mesh-mode value without operator OK — see P3).

- [ ] **Step 5: Mirror + gates + commit (on operator go)**

```bash
git add frontend/src/superbrain/lib/pointFieldMaterial.ts frontend/src/superbrain/lib/pointFieldMaterial.test.ts
git commit -m "feat(pointfield): glow + core + alpha-fog fragment, HDR emission for bloom (P1)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Poster-flat camera (flag-gated low FOV)

**Files:**
- Modify: `frontend/src/superbrain/components/canvas/SuperbrainScene.tsx`

- [ ] **Step 1: Add a flag-gated poster camera**

Import drei's camera at the top:

```ts
import { PerspectiveCamera } from '@react-three/drei';
```

In the scene's returned JSX (the top-level fragment in `SuperbrainScene`, near where `<CameraDrift/>` is mounted ~`SuperbrainScene.tsx:1537`), add — ONLY for points mode — a low-FOV camera dollied back, and suppress `CameraDrift` so it doesn't fight the static poster framing:

```tsx
      {BEING_MODE === 'points' ? (
        <PerspectiveCamera makeDefault position={[0, -1.0, 16]} fov={26} near={0.1} far={100} />
      ) : (
        <CameraDrift activity={activeBoost} burst={burstRef} push={cameraPushRef} idleRef={idleRef} />
      )}
```

Find the existing `<CameraDrift .../>` line and replace it with the conditional above (keep all the same props).

> **Why position y=-1.0, z=16:** the brain sits around y≈0..0.6 and the spine descends to y≈-2.85; framing the whole organism vertically means looking slightly down the body. FOV 26 + z16 ≈ near-orthographic poster flatness. These are starting values — expose them for operator tuning in Task 8/P6.

- [ ] **Step 2: Manual FIDELITY at :5173** — `?being=points`: the cloud reads flat/front-on like the poster; orbit (if controls present) still works. Default mesh mode camera is unchanged (still uses `CameraDrift`).

- [ ] **Step 3: Mirror + gates + commit (on operator go)**

```bash
git add frontend/src/superbrain/components/canvas/SuperbrainScene.tsx
git commit -m "feat(pointfield): poster-flat low-FOV camera in points mode (P1)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

**P1 GATE (operator):** sign off the glow + flatness look before P2.

---

# PHASE P2 — Color binding (FIDELITY-gated)

**Gate:** regional palette + posture wash both read; no single color dominates the bloom.

### Task 8: Per-color bloom compensation + posture wash verification + dev dials

The region color already flows (Task 1 reads the clone's `color` attribute). This task adds the per-color bloom compensation (blue/violet bloom weaker under the luminance weighting) and exposes the operator dials.

**Files:**
- Modify: `frontend/src/superbrain/lib/pointFieldMaterial.ts`
- Modify: `frontend/src/superbrain/components/canvas/BrainPointField.tsx`

- [ ] **Step 1: Per-color glow compensation in the fragment**

In `pointFieldMaterial.ts` FRAGMENT, replace the `c *= uGlowMul;` line with a luminance-aware boost so blue/violet bloom as much as green:

```glsl
    // bloom luminance under-weights blue (0.0722) vs green (0.7152). Boost the
    // glow inversely to perceived luminance so the spectral palette blooms evenly.
    float lum = dot(c, vec3(0.2126, 0.7152, 0.0722));
    float comp = mix(1.6, 1.0, clamp(lum, 0.0, 1.0)); // dim colors get a bigger push
    c *= uGlowMul * comp;
```

Bump cache key to `'pointfield_v3'` and update the test's `toContain('v2')` → `toContain('v3')`.

- [ ] **Step 2: Expose `window.__POINTFIELD` dev dials**

In `BrainPointField.tsx`, after `material` is created, add (dev-only, mirroring the `window.__POSTURE` pattern in `SuperbrainScene.tsx`):

```tsx
  useEffect(() => {
    if (typeof window === 'undefined' || process.env.NODE_ENV === 'production') return;
    (window as unknown as { __POINTFIELD?: Record<string, number> }).__POINTFIELD = new Proxy(
      {},
      {
        get: (_t, key: string) => material.uniforms[key]?.value,
        set: (_t, key: string, value: number) => {
          if (material.uniforms[key]) material.uniforms[key].value = value;
          return true;
        },
      },
    );
  }, [material]);
```

So the operator can run `window.__POINTFIELD.uSize = 12`, `window.__POINTFIELD.uAttenK = 0.1`, `window.__POINTFIELD.uGlowMul = 1.8`, `window.__POINTFIELD.uFogDensity = 0.04` live.

- [ ] **Step 3: Run material tests** — `npm --prefix frontend run test -- src/superbrain/lib/pointFieldMaterial.test.ts`. Expected: PASS.

- [ ] **Step 4: Manual FIDELITY at :5173** — confirm greens don't scream while blues whisper; trigger a posture change (talk to the being so it goes think→stream) and confirm the whole cloud washes toward the posture hue, just like the mesh does today.

- [ ] **Step 5: Mirror + gates + commit (on operator go)**

```bash
git add frontend/src/superbrain/lib/pointFieldMaterial.ts frontend/src/superbrain/lib/pointFieldMaterial.test.ts frontend/src/superbrain/components/canvas/BrainPointField.tsx
git commit -m "feat(pointfield): per-color bloom compensation + posture wash + dev dials (P2)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

**P2 GATE (operator):** sign off color before P3.

---

# PHASE P3 — Post-FX tuning (FIDELITY-gated)

**Gate:** cinematic glow matches the poster; the starfield stays crisp (not bloomed).

### Task 9: Confirm/relax bloom for the point-field

The point-field already blooms through the existing `PostFX` (threshold 1.0). This task only adjusts tuning **if** the operator finds the mesh-tuned bloom wrong for points — and does so without regressing mesh mode.

**Files:**
- Modify: `frontend/src/superbrain/lib/constants.ts` (only if needed)
- Modify: `frontend/src/superbrain/components/canvas/PostFX.tsx` (only if a points-specific value is needed)

- [ ] **Step 1: Evaluate at :5173** — with `?being=points`, judge bloom intensity/radius. If it reads right with the existing `POST_FX.bloom` (intensity 2.5, threshold 1.0), **do nothing** — note that in the commit and skip to P4.

- [ ] **Step 2 (only if needed): Add a points-mode bloom value**

If points need a gentler bloom, add to `constants.ts` `POST_FX`:

```ts
  // Point-field rides the same Bloom; a lower intensity keeps puncta from
  // fusing into a white blob. Applied only in ?being=points (PostFX reads it).
  bloomPoints: { intensity: 1.0, luminanceThreshold: 1.0, luminanceSmoothing: 0.3 },
```

Then in `PostFX.tsx`, read the being mode and pick the block:

```tsx
import { readBeingMode } from '@/superbrain/lib/beingMode';
// ...
  const being = readBeingMode();
  const bloom = being === 'points' ? POST_FX.bloomPoints : POST_FX.bloom;
// in <Bloom ... intensity={bloom.intensity} luminanceThreshold={bloom.luminanceThreshold} luminanceSmoothing={bloom.luminanceSmoothing} />
```

> This is additive and flag-scoped: mesh mode keeps `POST_FX.bloom` byte-for-byte.

- [ ] **Step 3: Mirror + gates + commit (on operator go)**

```bash
git add frontend/src/superbrain/lib/constants.ts frontend/src/superbrain/components/canvas/PostFX.tsx
git commit -m "feat(pointfield): points-mode bloom tuning (P3)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

**P3 GATE (operator):** sign off the cinematic glow.

---

# PHASE P4 — Animation (vertex shader; FIDELITY + 60fps gate)

**Gate:** the field reads "alive" (breathe + idle drift + spine flow band + twinkle); 60fps held desktop.

### Task 10: Curl noise chunk + breathe/curl/flow vertex + twinkle fragment

**Files:**
- Create: `frontend/src/superbrain/lib/curlNoise.glsl.ts`
- Modify: `frontend/src/superbrain/lib/pointFieldMaterial.ts`
- Modify: `frontend/src/superbrain/components/canvas/BrainPointField.tsx`

- [ ] **Step 1: Add the curl-noise GLSL chunk**

```ts
// frontend/src/superbrain/lib/curlNoise.glsl.ts
// Divergence-free curl noise (cabbibo/glsl-curl-noise + Ashima simplex),
// applied as a DISPLACEMENT of a fixed input so it stays stateless/bounded.
export const CURL_NOISE_GLSL = /* glsl */ `
  vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
  vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
  vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
  vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
  float snoise(vec3 v){
    const vec2 C=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
    vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
    vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.0-g; vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
    vec3 x1=x0-i1+C.xxx; vec3 x2=x0-i2+C.yyy; vec3 x3=x0-D.yyy;
    i=mod289(i);
    vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
    float n_=0.142857142857; vec3 ns=n_*D.wyz-D.xzx;
    vec4 j=p-49.0*floor(p*ns.z*ns.z);
    vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.0*x_);
    vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy; vec4 h=1.0-abs(x)-abs(y);
    vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
    vec4 s0=floor(b0)*2.0+1.0; vec4 s1=floor(b1)*2.0+1.0; vec4 sh=-step(h,vec4(0.0));
    vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
    vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y); vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
    vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
    p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
    vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0); m=m*m;
    return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
  }
  vec3 snoiseVec3(vec3 x){return vec3(snoise(vec3(x)),snoise(vec3(x.y-19.1,x.z+33.4,x.x+47.2)),snoise(vec3(x.z+74.2,x.x-124.5,x.y+99.4)));}
  vec3 curlNoise(vec3 p){
    const float e=0.1; vec3 dx=vec3(e,0.0,0.0); vec3 dy=vec3(0.0,e,0.0); vec3 dz=vec3(0.0,0.0,e);
    vec3 p_x0=snoiseVec3(p-dx); vec3 p_x1=snoiseVec3(p+dx);
    vec3 p_y0=snoiseVec3(p-dy); vec3 p_y1=snoiseVec3(p+dy);
    vec3 p_z0=snoiseVec3(p-dz); vec3 p_z1=snoiseVec3(p+dz);
    float x=p_y1.z-p_y0.z-p_z1.y+p_z0.y;
    float y=p_z1.x-p_z0.x-p_x1.z+p_x0.z;
    float z=p_x1.y-p_x0.y-p_y1.x+p_y0.x;
    return normalize(vec3(x,y,z)/(2.0*e));
  }
`;
```

- [ ] **Step 2: Rewrite the vertex shader to animate from attributes + uniforms**

In `pointFieldMaterial.ts`, import the chunk and rebuild `VERTEX`:

```ts
import { CURL_NOISE_GLSL } from './curlNoise.glsl';
```

```glsl
// VERTEX
  ${CURL_NOISE_GLSL}
  uniform float uScale, uSize, uAttenK, uTime, uGrow, uFlowSpeed, uCurlAmp;
  attribute float aSize, aPhase, aSpeed, aBand;
  attribute vec3 aNormal;
  attribute vec3 aColor;
  varying vec3 vColor;
  varying float vViewZ;
  varying float vBand;
  void main() {
    vColor = aColor;
    vec3 p = position;
    float r = length(position);
    // breathe along normal (whole-body coherent + per-point shimmer)
    float breath = 0.5 + 0.5 * sin(uTime * 2.5);
    p += aNormal * (uGrow * 0.025 * r * breath);
    p += aNormal * 0.004 * sin(uTime * 1.7 + aPhase);
    // curl idle drift (stateless displacement of fixed base)
    p += curlNoise(position * 0.4 + uTime * 0.06) * uCurlAmp;
    // flow band sweep along the body axis
    float center = fract(uTime * uFlowSpeed);
    float band = exp(-pow((aBand - center) / 0.12, 2.0));
    vBand = band;
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    vViewZ = -mv.z;
    float atten = mix(1.0, uScale / -mv.z, uAttenK);
    gl_PointSize = min(uSize * aSize * atten * (1.0 + band * 1.2), 64.0);
    gl_Position = projectionMatrix * mv;
  }
```

- [ ] **Step 3: Add band emissive + twinkle to the fragment**

In FRAGMENT, add `varying float vBand;` and `uniform float uTime;`, and after computing `c`:

```glsl
    c += vColor * vBand * 0.8;                              // flow band brightens
    i *= 0.65 + 0.35 * sin(uTime * 0.6 + 0.0);             // global gentle twinkle
```

> Use a per-point seed for twinkle by adding `varying float vSeed;` set from `aPhase` in the vertex (`vSeed = aPhase;`) and use `sin(uTime*0.6 + vSeed)` — desynced shimmer rather than a global pulse. Bump cache key to `'pointfield_v4'` and update the test.

- [ ] **Step 4: Drive the new uniforms + reduced motion in the component**

In `BrainPointField.tsx` `useFrame`, set the breathing/flow/curl gains and honor reduced motion:

```tsx
import { shouldReduceMotion } from '@/superbrain/lib/...'; // reuse the existing helper used in SuperbrainScene
// ...
  const reduce = useMemo(() => shouldReduceMotion(), []);
  useFrame((state) => {
    setScale();
    const u = material.uniforms;
    u.uGrow.value = reduce ? 0 : 1;
    u.uCurlAmp.value = reduce ? 0 : 0.012;        // ~1.2% of body radius
    u.uFlowSpeed.value = uniforms.uFlow.value * 0.25; // flow band rides posture flow
    // uTime is the shared leaf; if reduced motion, freeze it for this material only:
    if (reduce) u.uTime.value = 0;
  });
```

> Confirm the exact import path/name of `shouldReduceMotion` (it's already imported in `SuperbrainScene.tsx`). Reuse it; do not duplicate.

- [ ] **Step 5: Run material tests** — update the cache-key assertion to `v4`; `npm --prefix frontend run test -- src/superbrain/lib/pointFieldMaterial.test.ts`. Expected: PASS.

- [ ] **Step 6: Manual FIDELITY + perf at :5173** — the cloud breathes, drifts, a soft band sweeps the spine axis, points shimmer; confirm ~60fps (operator's GPU). If fps drops, lower `count` via tier or `uSize`.

- [ ] **Step 7: Mirror + gates + commit (on operator go)**

```bash
git add frontend/src/superbrain/lib/curlNoise.glsl.ts frontend/src/superbrain/lib/pointFieldMaterial.ts frontend/src/superbrain/lib/pointFieldMaterial.test.ts frontend/src/superbrain/components/canvas/BrainPointField.tsx
git commit -m "feat(pointfield): vertex-shader breathe/curl/flow + twinkle, reduced-motion (P4)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

**P4 GATE (operator):** sign off "alive" + 60fps.

---

# PHASE P5 — Lifecycle gestures + spine/roots

**Gate:** arrival inrush → alive → (materialize/conduct postures) → reabsorption dissolve reads as the poster's 7 phases; spine + roots are part of the cloud.

### Task 11: Lifecycle target math (pure, TDD)

**Files:**
- Create: `frontend/src/superbrain/lib/pointFieldLifecycle.ts`
- Test: `frontend/src/superbrain/lib/pointFieldLifecycle.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/superbrain/lib/pointFieldLifecycle.test.ts
import { describe, it, expect } from 'vitest';
import { lifecycleTargets } from './pointFieldLifecycle';

describe('lifecycleTargets', () => {
  it('arrival/booting ramps the inrush, not yet grown', () => {
    const t = lifecycleTargets('arrival');
    expect(t.arrival).toBe(1);   // arrival uniform driven to 1 = condensed
    expect(t.reabsorb).toBe(0);
  });
  it('rest is fully grown, calm flow, no inrush/dissolve', () => {
    const t = lifecycleTargets('rest');
    expect(t.grow).toBe(1);
    expect(t.arrival).toBe(1);
    expect(t.reabsorb).toBe(0);
    expect(t.flow).toBeLessThan(0.3);
  });
  it('working/streaming flows fastest', () => {
    expect(lifecycleTargets('working').flow).toBeGreaterThan(lifecycleTargets('rest').flow);
  });
  it('reabsorbing drives the dissolve', () => {
    expect(lifecycleTargets('reabsorbing').reabsorb).toBe(1);
  });
  it('falls back to rest for unknown phases', () => {
    // @ts-expect-error testing the guard
    expect(lifecycleTargets('nonsense')).toEqual(lifecycleTargets('rest'));
  });
});
```

- [ ] **Step 2: Run to verify fail** — `npm --prefix frontend run test -- src/superbrain/lib/pointFieldLifecycle.test.ts`. Expected: FAIL.

- [ ] **Step 3: Implement**

```ts
// frontend/src/superbrain/lib/pointFieldLifecycle.ts
import type { OrganismLifecyclePhase } from './organismLifecycle';

export interface LifecycleTargets {
  grow: number;     // 0 = unborn, 1 = fully grown (breath gain)
  flow: number;     // 0..1 flow-band speed gain
  arrival: number;  // 0 = scattered origin, 1 = condensed at base
  reabsorb: number; // 0 = present, 1 = dissolved up the spine
}

const REST: LifecycleTargets = { grow: 1, flow: 0.16, arrival: 1, reabsorb: 0 };

const TABLE: Record<OrganismLifecyclePhase, LifecycleTargets> = {
  booting: { grow: 0, flow: 0.16, arrival: 0, reabsorb: 0 },
  arrival: { grow: 0.4, flow: 0.4, arrival: 1, reabsorb: 0 },
  rest: REST,
  attentive: { grow: 1, flow: 0.5, arrival: 1, reabsorb: 0 },
  intake: { grow: 1, flow: 0.55, arrival: 1, reabsorb: 0 },
  materializing: { grow: 1, flow: 0.9, arrival: 1, reabsorb: 0 },
  working: { grow: 1, flow: 1.0, arrival: 1, reabsorb: 0 },
  conducting: { grow: 1, flow: 1.0, arrival: 1, reabsorb: 0 },
  approval_hold: { grow: 1, flow: 0.34, arrival: 1, reabsorb: 0 },
  error_repair: { grow: 1, flow: 0.22, arrival: 1, reabsorb: 0 },
  completion_settle: { grow: 1, flow: 0.3, arrival: 1, reabsorb: 0 },
  reabsorbing: { grow: 1, flow: 0.3, arrival: 1, reabsorb: 1 },
};

export function lifecycleTargets(phase: OrganismLifecyclePhase): LifecycleTargets {
  return TABLE[phase] ?? REST;
}
```

> Verify the phase string union in `lib/organismLifecycle.ts` matches these keys exactly (the `PHASE_TO_POSTURE` map in `bodyPosture.ts` uses the same 12 phases — booting/arrival/rest/attentive/intake/materializing/working/conducting/approval_hold/error_repair/completion_settle/reabsorbing).

- [ ] **Step 4: Run to verify pass** — Expected: PASS (5 tests).

- [ ] **Step 5: Mirror + gates + commit (on operator go)**

```bash
git add frontend/src/superbrain/lib/pointFieldLifecycle.ts frontend/src/superbrain/lib/pointFieldLifecycle.test.ts
git commit -m "feat(pointfield): pure lifecycle->target math (P5)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: Arrival/reabsorption morph in the shader + drive from organism phase

**Files:**
- Modify: `frontend/src/superbrain/lib/pointFieldMaterial.ts`
- Modify: `frontend/src/superbrain/components/canvas/BrainPointField.tsx`

- [ ] **Step 1: Add the arrival/reabsorb morph to the vertex shader**

In `pointFieldMaterial.ts` VERTEX, add `attribute vec3 aScatter; attribute float aBirth; uniform float uArrival, uReabsorb;` and a `varying float vAlpha;`, then morph `p` BEFORE the modelView transform:

```glsl
    // ARRIVAL inrush: from scattered origin → base, staggered ease-out condense
    vec3 origin = position + aScatter * 6.0;
    float ta = clamp((uArrival - aBirth * 0.4) / 0.6, 0.0, 1.0);
    p = mix(origin, p, 1.0 - pow(1.0 - ta, 3.0));
    // REABSORPTION: rise + scatter, fade + shrink, staggered
    vec3 exitP = p + vec3(0.0, 4.0, 0.0) + aScatter * 1.5;
    float tr = clamp((uReabsorb - (1.0 - aBirth) * 0.4) / 0.6, 0.0, 1.0);
    p = mix(p, exitP, pow(tr, 2.0));
    vAlpha = 1.0 - tr;
```

Multiply final `gl_PointSize` by `(1.0 - tr)` and in the FRAGMENT multiply `i *= vAlpha;`. Bump cache key `'pointfield_v5'`, update the test.

- [ ] **Step 2: Drive uArrival/uReabsorb/uGrow/uFlow from the organism phase**

In `BrainPointField.tsx`, read the live phase from the existing bus and damp the material uniforms toward the lifecycle targets:

```tsx
import { getOrganismPhase } from '@/superbrain/lib/organismPhaseBus';
import { lifecycleTargets } from '@/superbrain/lib/pointFieldLifecycle';
import * as THREE from 'three';
// ...
  useFrame((state, delta) => {
    setScale();
    const u = material.uniforms;
    const t = lifecycleTargets(getOrganismPhase());
    u.uGrow.value = reduce ? t.grow : THREE.MathUtils.damp(u.uGrow.value, t.grow, 2, delta);
    u.uArrival.value = reduce ? t.arrival : THREE.MathUtils.damp(u.uArrival.value, t.arrival, 1.5, delta);
    u.uReabsorb.value = reduce ? t.reabsorb : THREE.MathUtils.damp(u.uReabsorb.value, t.reabsorb, 1.5, delta);
    u.uFlowSpeed.value = THREE.MathUtils.damp(u.uFlowSpeed.value, 0.1 + t.flow * 0.2, 3, delta);
    u.uCurlAmp.value = reduce ? 0 : 0.012;
  });
```

> `getOrganismPhase`/`organismPhaseBus` already exists (MaterializationLayer writes it via `setOrganismPhase`). Confirm the exact exported name.

- [ ] **Step 3: Manual FIDELITY at :5173** — reload (arrival inrush plays: points stream in + condense), talk to it (postures shift), and trigger completion (reabsorption: points rise + dissolve up). Reduced-motion: set OS reduce-motion and confirm it snaps (no big translate) but stays lit.

- [ ] **Step 4: Mirror + gates + commit (on operator go)**

```bash
git add frontend/src/superbrain/lib/pointFieldMaterial.ts frontend/src/superbrain/lib/pointFieldMaterial.test.ts frontend/src/superbrain/components/canvas/BrainPointField.tsx
git commit -m "feat(pointfield): arrival inrush + reabsorption dissolve, phase-driven (P5)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: Add spine + roots to the cloud

**Files:**
- Modify: `frontend/src/superbrain/lib/spineAnatomy.ts` (export a geometry builder)
- Modify: `frontend/src/superbrain/components/canvas/NervousSystem.tsx` (use the shared builder — refactor, no behavior change)
- Modify: `frontend/src/superbrain/components/canvas/BrainPointField.tsx` (sample the spine geometries as extra sources)

- [ ] **Step 1: Extract the spine geometry construction into a reusable builder**

`NervousSystem.tsx` builds the cord/vertebrae/roots/spray as merged Tube/Torus geometries. Move that construction into a pure exported function in `spineAnatomy.ts`:

```ts
// frontend/src/superbrain/lib/spineAnatomy.ts  (append)
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';

/** Build the spine point-sources: returns merged BufferGeometries for the cord
 *  trunk and the vertebrae+roots+spray, in group-local space. Pure (no scene). */
export function buildSpineGeometries(): { trunk: THREE.BufferGeometry; roots: THREE.BufferGeometry } {
  // ... move the EXACT Tube/Torus construction currently inline in NervousSystem
  // here (cord + brainstem stub → trunk; vertebra rings + root tubes + cauda
  // spray → roots). Return the two merged geometries.
}
```

> This is a mechanical extraction: cut the geometry-building code from `NervousSystem.tsx` into this function and have `NervousSystem` call it. Run the mesh-mode scene (`?being=mesh`, default) after the refactor and confirm the spine looks byte-identical (no behavior change) — that is the refactor's gate.

- [ ] **Step 2: Sample the spine geometries as extra point-field sources**

In `BrainPointField.tsx`, wrap each spine geometry in a throwaway `Mesh`/`Group` and add as sources with their own band ranges:

```tsx
import { buildSpineGeometries } from '@/superbrain/lib/spineAnatomy';
// inside the geometry useMemo, before sampling:
  const spine = buildSpineGeometries();
  const trunkObj = new THREE.Group(); trunkObj.add(new THREE.Mesh(spine.trunk));
  const rootsObj = new THREE.Group(); rootsObj.add(new THREE.Mesh(spine.roots));
  const sources: PointFieldSource[] = [
    { object: source, share: 0.70, axisMin: -0.6, axisMax: 0.7 },   // cortex canopy
    { object: trunkObj, share: 0.20, axisMin: -2.85, axisMax: -0.6 }, // spine trunk
    { object: rootsObj, share: 0.10, axisMin: -2.85, axisMax: -0.9 }, // roots/base
  ];
  const d = samplePointField(sources, count, 0x50494e54);
```

> The spine geometries have no `color` attribute, so the sampler falls back to its default violet (Task 1). If the operator wants the spine to carry the `spineAnatomy` per-segment palette, bake a `color` attribute onto the merged geometries in `buildSpineGeometries` from the existing `STEM_COLORS`/segment stops (a follow-on; the fallback color is acceptable for the first pass — note this in the commit).

- [ ] **Step 3: Manual FIDELITY at :5173** — the full organism now reads: brain canopy → spine trunk → root base, all points, with the flow band sweeping the whole vertical axis. Confirm mesh mode (default) still shows the original mesh spine unchanged.

- [ ] **Step 4: Mirror + gates + commit (on operator go)**

```bash
git add frontend/src/superbrain/lib/spineAnatomy.ts frontend/src/superbrain/components/canvas/NervousSystem.tsx frontend/src/superbrain/components/canvas/BrainPointField.tsx
git commit -m "feat(pointfield): spine + roots sampled into the cloud (P5)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

**P5 GATE (operator):** sign off the full 7-phase organism read.

---

# PHASE P6 — Perf tiers + mobile + default flip

**Gate:** 60fps desktop @ 80k/DPR2; 30fps real mid mobile @ 30k/DPR1.5; degrade ladder works; default flips to points after sign-off.

### Task 14: Point-count tiers, DPR clamp, regress-on-orbit, mobile

**Files:**
- Modify: `frontend/src/superbrain/components/canvas/SuperbrainScene.tsx` (counts already tier-mapped in Task 5 — confirm + add a mobile tier check)
- Modify: `frontend/src/superbrain/components/canvas/WorkspaceCanvas.tsx` (DPR already `TIER_DPR`; confirm cap ≤2, ≤1.5 mobile)
- Modify: `frontend/src/superbrain/components/canvas/BrainPointField.tsx` (regress point size/dpr on orbit if a PerformanceMonitor is present)

- [ ] **Step 1: Confirm tier counts + DPR** — counts: high 80k / medium 60k / low/mobile 40k→30k. Verify `TIER_DPR` caps DPR at 2 (desktop) and 1.5 (mobile). If a mobile detection exists in `QualityTierProvider`, reuse it; otherwise add `dpr={[1, 2]}` is already set — confirm.

- [ ] **Step 2: Regress during orbit** — additive fill is heaviest while orbiting. If the scene mounts drei `<PerformanceMonitor>` already (check `WorkspaceCanvas`/`TierGovernor`), hook its `onDecline`/`regress` to lower `uSize` and/or DPR for the cloud; restore ~200ms after. If none exists, add a minimal `regress()` on OrbitControls `onStart`/`onEnd`.

- [ ] **Step 3: Measure at :5173 on the operator's machine + a real mid mobile** — record fps at each tier; tune `count`/`uSize`/bloom res to hit the targets. Log any cap you apply (e.g. "mobile capped at 30k/DPR1.5") in the commit — never silently truncate.

- [ ] **Step 4: Bake operator-tuned defaults** — fold the operator's final `window.__POINTFIELD` values (uSize, uAttenK, uFogDensity, uGlowMul, fov) into the material/material-factory/camera defaults so a fresh load matches his FIDELITY pass.

- [ ] **Step 5: Flip the default (ONLY after full sign-off)** — in `beingMode.ts`, change the default so the point-field is the being and `?being=mesh` is the fallback:

```ts
  return value === 'mesh' ? 'mesh' : 'points';
```

Update `beingMode.test.ts` accordingly (default now `points`; `?being=mesh` → `mesh`). Run the test.

- [ ] **Step 6: Mirror + gates + commit (on operator go)**

```bash
git add frontend/src/superbrain/components/canvas/SuperbrainScene.tsx frontend/src/superbrain/components/canvas/WorkspaceCanvas.tsx frontend/src/superbrain/components/canvas/BrainPointField.tsx frontend/src/superbrain/lib/beingMode.ts frontend/src/superbrain/lib/beingMode.test.ts
git commit -m "feat(pointfield): perf tiers + mobile + default flip to points (P6)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

**P6 GATE (operator):** final sign-off — the point-field IS the being; perf targets met.

---

## Self-review (done by the plan author)

- **Spec coverage:** §1 substrate (Tasks 4–6), §5 rendering foundation (Tasks 1,3,6), §6 color (Tasks 1,8,13), §7 glow/bloom (Tasks 6,9), §8 animation (Tasks 10,12), §9 camera/flatness (Tasks 6,7), §10 7-phase gestures (Tasks 11,12,13), §11 integration/fallback (Tasks 2,5; default flip Task 14), §12 modules (all new files mapped), §13 pitfalls (uScale recompute T4; depthWrite:false T3; toneMapped+>1 T6; COLOR_0 trap tested T1; matrixWorld T1; fog-as-alpha T6; no per-frame CPU T1/T10; pointSize clamp T3; curl-as-displacement T10), §14 phase order (P0–P6 = Tasks 1–14), §15 testing (unit T1,2,3,11; FIDELITY gates each phase), §16 dials (T8 `__POINTFIELD`), §17 sacred (conventions). All covered.
- **Placeholder scan:** the only deferred specifics are explicitly operator-tuned values (camera position, glow strength, perf counts) which are dialed live at :5173 by design, and the Step-1 extraction in Task 13 (mechanical cut/paste of existing code that must stay byte-identical). No silent TODOs.
- **Type consistency:** `PointFieldSource`/`PointFieldData` (T1) consumed unchanged in T4/T13; `createPointFieldMaterial` overrides shape (T3) used in T4; `lifecycleTargets`/`LifecycleTargets` (T11) used in T12; uniform names (`uGlowMul`,`uFogDensity`,`uArrival`,`uReabsorb`,`uGrow`,`uFlowSpeed`,`uCurlAmp`,`uAttenK`,`uScale`,`uSize`) consistent across T3/T6/T8/T10/T12.

**Two items the implementer MUST verify against the live tree before coding (flagged inline, not assumed):**
1. The import-alias style for `lib/` and components (`@/superbrain/...` vs relative) — match the neighbors.
2. The exact exported names `shouldReduceMotion`, `getOrganismPhase`/`setOrganismPhase`, and the `OrganismLifecyclePhase` union — reuse, don't duplicate.
