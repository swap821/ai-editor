// frontend/src/superbrain/lib/gpuPointFieldTSL.ts
//
// "The Million-Mote Mind" — the WebGPU/TSL compute-particle substrate (flagged spike).
// Builds: (1) a compute pass that integrates a live position per particle — pulled to
// its baked anchor "home" by a critically-damped spring, perturbed by divergence-free
// curl flow, with arrival/reabsorption as closed-form home displacement; and (2) a
// SpriteNodeMaterial that wears the SACRED baked region color + the same posture wash
// and luminance flashes as pointFieldMaterial.ts (hue never recomputed on the GPU).
//
// The geometry math scales to 250k–1M particles; the WebGL path (BrainPointField) is
// untouched. NOTE: not yet verified on a real WebGPU device — fidelity/perf is the
// operator's RTX call (see .aios/state/GAGOS_WEBGPU_SPIKE.md §4 A/B plan).
import * as THREE from 'three/webgpu';
import {
  Fn, instanceIndex, storage, uniform, uv,
  vec3, vec4, float, mix, clamp, pow, sin, length, smoothstep, time,
} from 'three/tsl';
import { curlNoise3 } from './curlNoiseTSL';

/** Baked anchor arrays (from samplePointField + spine fusion) the GPU sim reads. */
export interface GpuAnchors {
  positions: Float32Array; // itemSize 3 — the "home" silhouette
  colors: Float32Array;    // itemSize 3 — sacred region/spine RGB (never recomputed)
  scatter: Float32Array;   // itemSize 3 — unit dir for arrival/dissolve
  births: Float32Array;    // itemSize 1 — 0..1 stagger
  bands: Float32Array;     // itemSize 1 — body-axis 0=roots → 1=cortex
  sizes: Float32Array;     // itemSize 1 — per-particle size
  count: number;
}

export interface GpuPointField {
  /** the renderable object (instanced sprites) — mount via <primitive>. */
  mesh: THREE.Sprite;
  /** the compute node to dispatch each frame via renderer.computeAsync(). */
  computeStep: unknown;
  /** lifecycle (geometry) uniforms — damped each frame from lifecycleTargets(). */
  U: Record<string, { value: number }>;
  /** render (posture/luminance) uniforms — driven from the scene CognitionUniforms. */
  P: {
    uPostureColor: { value: THREE.Color };
    uPostureTint: { value: number };
    uGlowMul: { value: number };
    uSize: { value: number };
    uIgnite: { value: number };
    uAwaken: { value: number };
    uStatePulse: { value: number };
  };
}

export function buildGpuPointField(anchors: GpuAnchors): GpuPointField {
  const count = anchors.count;
  const sab = (arr: Float32Array, size: number) =>
    new THREE.StorageInstancedBufferAttribute(arr, size);

  // ── GPU storage: live (read/write) state ──────────────────────────────────
  const posLive = storage(sab(anchors.positions.slice(), 3), 'vec3', count);
  const velLive = storage(sab(new Float32Array(count * 3), 3), 'vec3', count);

  // ── read-only baked anchors (home + sacred color + band) ──────────────────
  const aBase = storage(sab(anchors.positions, 3), 'vec3', count).toReadOnly();
  const aScatter = storage(sab(anchors.scatter, 3), 'vec3', count).toReadOnly();
  const aBirth = storage(sab(anchors.births, 1), 'float', count).toReadOnly();
  const aBand = storage(sab(anchors.bands, 1), 'float', count).toReadOnly();
  const aColor = storage(sab(anchors.colors, 3), 'vec3', count).toReadOnly();
  const aSize = storage(sab(anchors.sizes, 1), 'float', count).toReadOnly();

  // ── lifecycle (geometry) uniforms — mirror CognitionUniforms 1:1 ──────────
  const U = {
    uCurlAmp: uniform(0.012), uCurlFreq: uniform(0.4), uDrift: uniform(0.06),
    uGrow: uniform(0), uArrival: uniform(0), uReabsorb: uniform(0),
    uSpring: uniform(6), uDamp: uniform(0.9), uDt: uniform(0.016),
  };

  // ── render (posture/luminance) uniforms — sacred hue passthrough ──────────
  const P = {
    uPostureColor: uniform(new THREE.Color(0.62, 0.47, 1.0)),
    uPostureTint: uniform(0),
    uGlowMul: uniform(2.55),
    uSize: uniform(2.8),
    uIgnite: uniform(0),
    uAwaken: uniform(0),
    uStatePulse: uniform(0),
  };

  // ── COMPUTE: spring-to-home + curl churn + arrival/reabsorb ───────────────
  const computeStep = Fn(() => {
    const i = instanceIndex;
    const base = aBase.element(i);

    // arrival: home flies in from a scattered shell, staggered by birth, ease-out
    const arrOrigin = base.add(aScatter.element(i).mul(2.0));
    const ta = clamp(U.uArrival.sub(aBirth.element(i).mul(0.4)).div(0.6), 0.0, 1.0);
    let home = mix(arrOrigin, base, float(1.0).sub(pow(float(1.0).sub(ta), 3.0)));

    // reabsorption: home rises +Y and scatters away (inverse stagger)
    const exitP = home.add(vec3(0.0, 4.0, 0.0)).add(aScatter.element(i).mul(1.5));
    const tr = clamp(U.uReabsorb.sub(float(1.0).sub(aBirth.element(i)).mul(0.4)).div(0.6), 0.0, 1.0);
    home = mix(home, exitP, pow(tr, 2.0));

    // whole-body coherent breathe along the radius
    const breath = float(0.5).add(sin(time.mul(2.5)).mul(0.5));
    home = home.add(base.normalize().mul(U.uGrow.mul(0.014).mul(length(base)).mul(breath)));

    // divergence-free curl flow (displacement of the fixed anchor — never integrate pos)
    const flow = curlNoise3(base.mul(U.uCurlFreq).add(time.mul(U.uDrift))).mul(U.uCurlAmp);
    const target = home.add(flow);

    // critically-damped spring so the silhouette always re-forms
    const p = posLive.element(i);
    const v = velLive.element(i);
    const acc = target.sub(p).mul(U.uSpring);
    const vNew = v.add(acc.mul(U.uDt)).mul(U.uDamp);
    velLive.element(i).assign(vNew);
    posLive.element(i).assign(p.add(vNew.mul(U.uDt)));
  })().compute(count);

  // ── RENDER: SpriteNodeMaterial, sacred palette, emits >1 for bloom ────────
  const mat = new THREE.SpriteNodeMaterial({ transparent: true, depthWrite: false, depthTest: false });
  mat.blending = THREE.AdditiveBlending;
  // position from the compute-simulated live buffer
  mat.positionNode = posLive.toAttribute();

  // soft round procedural sprite (halo + core) — same profile as the WebGL fragment
  const uvc = uv().sub(0.5);
  const dist = length(uvc);
  const t = clamp(float(1.0).sub(dist.mul(2.0)), 0.0, 1.0);
  const intensity = pow(t, 2.4).mul(0.62).add(pow(t, 9.0).mul(0.85));

  // COLOR: sacred region color + posture WASH only (hue preserved — identical math
  // to pointFieldMaterial.ts L104–127). Luminance-only flashes weighted by band.
  const band = aBand.toAttribute();
  const baseColor = aColor.toAttribute();
  let c = mix(baseColor, baseColor.mul(P.uPostureColor).mul(1.6), clamp(P.uPostureTint, 0.0, 0.8));
  const ignite = clamp(P.uIgnite, 0.0, 1.0).mul(smoothstep(0.45, 1.0, band));
  const awaken = clamp(P.uAwaken, 0.0, 1.0).mul(smoothstep(0.4, 1.0, band)).mul(0.5);
  const spineMask = float(1.0).sub(smoothstep(0.35, 0.55, band));
  const state = clamp(P.uStatePulse, 0.0, 1.0).mul(spineMask).mul(0.6);
  c = c.mul(P.uGlowMul).mul(float(1.0).add(ignite.mul(2.5)).add(awaken).add(state.mul(0.8)));

  mat.colorNode = vec4(c.mul(intensity), intensity); // >1 → AgX Bloom flares it
  // per-particle world size (weak attenuation = poster flatness); RTX-tune via P.uSize
  mat.scaleNode = aSize.toAttribute().mul(P.uSize).mul(0.06);

  const mesh = new THREE.Sprite(mat);
  (mesh as unknown as { count: number }).count = count; // instanced via instanceIndex
  mesh.frustumCulled = false;
  mesh.renderOrder = 3;

  return { mesh, computeStep, U, P };
}
