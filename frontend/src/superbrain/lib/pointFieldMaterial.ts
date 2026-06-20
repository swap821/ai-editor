// frontend/src/superbrain/lib/pointFieldMaterial.ts
import * as THREE from 'three';

export interface PointFieldUniformOverrides {
  uTime?: { value: number };
  uPostureColor?: { value: THREE.Color };
  uPostureTint?: { value: number };
}

const VERTEX = /* glsl */ `
  uniform float uPixelRatio; // device pixel ratio — DPR-correct on-screen size
  uniform float uRefDist;    // reference camera distance (~ brain distance) for weak depth
  uniform float uSize;       // base point size in CSS px
  uniform float uAttenK;     // 0 = flat poster (constant size), ~0.3 = weak depth
  uniform float uTime;       // shared scene clock — drives breathe/flow
  uniform float uGrow;       // 0 = no breath, 1 = full breath gain
  uniform float uFlowSpeed;  // body-axis flow-band sweep speed
  uniform float uArrival;    // 0 = scattered inrush origin, 1 = condensed in place
  uniform float uReabsorb;   // 0 = present, 1 = dissolved up/away
  attribute float aSize;
  attribute vec3 aColor;
  attribute vec3 aNormal;    // surface normal — breathe displaces along it
  attribute float aPhase;    // 0..2π per-point desync (shimmer + twinkle seed)
  attribute float aBand;     // normalized body-axis coord (flow band)
  attribute vec3 aScatter;   // unit scatter dir (arrival origin / reabsorb exit)
  attribute float aBirth;    // 0..1 per-point stagger
  varying vec3 vColor;
  varying float vViewZ;
  varying float vBand;
  varying float vSeed;
  varying float vAlpha;
  void main() {
    vColor = aColor;
    vSeed = aPhase;
    vec3 p = position;
    // BREATHE: coherent whole-body inhale/exhale along the surface normal
    // (shared phase), plus a tiny per-point shimmer so the surface lives.
    float breath = 0.5 + 0.5 * sin(uTime * 2.5);
    p += aNormal * (uGrow * 0.014 * length(position) * breath);
    p += aNormal * 0.002 * sin(uTime * 1.7 + aPhase);
    // FLOW BAND: a soft gaussian highlight sweeping the body axis (subtle on the
    // brain; reads strongly down the spine).
    float center = fract(uTime * uFlowSpeed);
    float band = exp(-pow((aBand - center) / 0.12, 2.0));
    vBand = band;
    // ARRIVAL inrush: stream in from a scattered origin and condense (staggered
    // by aBirth, ease-out so points decelerate as they settle).
    vec3 origin = p + aScatter * 2.0;
    float ta = clamp((uArrival - aBirth * 0.4) / 0.6, 0.0, 1.0);
    p = mix(origin, p, 1.0 - pow(1.0 - ta, 3.0));
    // REABSORPTION: rise + scatter away, fade + shrink (staggered, inverse order).
    vec3 exitP = p + vec3(0.0, 4.0, 0.0) + aScatter * 1.5;
    float tr = clamp((uReabsorb - (1.0 - aBirth) * 0.4) / 0.6, 0.0, 1.0);
    p = mix(p, exitP, pow(tr, 2.0));
    vAlpha = 1.0 - tr;
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    vViewZ = -mv.z;
    // Weak, reference-normalized depth scaling: atten ~ 1 at the brain so points
    // stay a near-constant pixel size (the flat-poster read); never the runaway
    // drawingBufferHeight/z factor that balloons every point to the 64px clamp.
    float atten = mix(1.0, uRefDist / -mv.z, clamp(uAttenK, 0.0, 1.0));
    gl_PointSize = min(uSize * aSize * uPixelRatio * atten * (1.0 + band * 0.2) * vAlpha, 64.0);
    gl_Position = projectionMatrix * mv;
  }
`;

// P1 fragment: soft radial halo + tight bright core + additive-safe depth fog.
// Emits color values above 1.0 so the existing PostFX Bloom (threshold 1.0) catches it.
const FRAGMENT = /* glsl */ `
  precision highp float;
  varying vec3 vColor;
  varying float vViewZ;
  varying float vBand;
  varying float vSeed;
  uniform vec3 uPostureColor;
  uniform float uPostureTint;
  uniform float uGlowMul;
  uniform float uFogDensity;
  uniform float uTime;
  uniform float uBodyOpacity; // 1 = solid; <1 dims the cloud so inner memory-nodes show through
  void main() {
    // Soft round sprite — rebuilt from the known-good base (1-d*2 stays in [0,1],
    // so pow() never goes NaN; the old smoothstep/fog path was producing NaN that
    // silently blanked the whole field).
    float d = length(gl_PointCoord - 0.5);
    if (d > 0.5) discard;
    float t = clamp(1.0 - d * 2.0, 0.0, 1.0);
    float glow = pow(t, 2.4);                 // wide soft halo
    float core = pow(t, 9.0);                  // tight bright core
    float intensity = glow * 0.7 + core * 0.6;
    // gentle desynced twinkle
    intensity *= 0.82 + 0.18 * sin(uTime * 0.7 + vSeed);
    vec3 c = mix(vColor, vColor * uPostureColor, clamp(uPostureTint, 0.0, 0.8));
    c += vColor * vBand * 0.4;                  // flow band brightens as it sweeps
    c *= uGlowMul;
    gl_FragColor = vec4(c * intensity * uBodyOpacity, intensity);
  }
`;

export function createPointFieldMaterial(overrides: PointFieldUniformOverrides = {}): THREE.ShaderMaterial {
  const material = new THREE.ShaderMaterial({
    vertexShader: VERTEX,
    fragmentShader: FRAGMENT,
    uniforms: {
      uTime: overrides.uTime ?? { value: 0 },
      uPixelRatio: { value: 1.5 }, // set per-frame from the renderer DPR
      uRefDist: { value: 15.0 },   // ~ camera→brain distance (points-mode poster camera z)
      uSize: { value: 3.2 },       // finer puncta (poster's dense fine-dot read; pairs with higher counts)
      uAttenK: { value: 0.2 },     // weak depth; 0 = fully flat
      uFogDensity: { value: 0.02 },// subtle recession only (thin depth slab)
      uGlowMul: { value: 2.4 },    // >1 so the existing PostFX Bloom (threshold 1.0) catches it
      uBodyOpacity: { value: 1.0 },// damped to ~0.5 while orchestrating so inner memory-nodes show
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
    depthTest: false,
    toneMapped: false,
    blending: THREE.AdditiveBlending,
  });
  material.customProgramCacheKey = () => 'pointfield_v8';
  return material;
}
