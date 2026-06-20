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
  attribute float aSize;
  attribute vec3 aColor;
  attribute vec3 aNormal;    // surface normal — breathe displaces along it
  attribute float aPhase;    // 0..2π per-point desync (shimmer + twinkle seed)
  attribute float aBand;     // normalized body-axis coord (flow band)
  varying vec3 vColor;
  varying float vViewZ;
  varying float vBand;
  varying float vSeed;
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
    // brain; reads strongly once the spine is points in P5).
    float center = fract(uTime * uFlowSpeed);
    float band = exp(-pow((aBand - center) / 0.12, 2.0));
    vBand = band;
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    vViewZ = -mv.z;
    // Weak, reference-normalized depth scaling: atten ~ 1 at the brain so points
    // stay a near-constant pixel size (the flat-poster read); never the runaway
    // drawingBufferHeight/z factor that balloons every point to the 64px clamp.
    float atten = mix(1.0, uRefDist / -mv.z, clamp(uAttenK, 0.0, 1.0));
    gl_PointSize = min(uSize * aSize * uPixelRatio * atten * (1.0 + band * 0.2), 64.0);
    gl_Position = projectionMatrix * mv;
  }
`;

// P1 fragment: soft radial halo + tight bright core + additive-safe depth fog.
// Emits color values above 1.0 so the existing PostFX Bloom (threshold 1.0) catches it.
const FRAGMENT = /* glsl */ `
  precision mediump float;
  varying vec3 vColor;
  varying float vViewZ;
  varying float vBand;
  varying float vSeed;
  uniform vec3 uPostureColor;
  uniform float uPostureTint;
  uniform float uGlowMul;
  uniform float uFogDensity;
  uniform float uTime;
  void main() {
    float d = length(gl_PointCoord - 0.5);
    float halo = pow(1.0 - clamp(d / 0.5, 0.0, 1.0), 2.5);
    float core = smoothstep(0.16, 0.0, d);
    float i = halo * 0.65 + core * 0.9;
    // gentle per-point twinkle (breathe, don't strobe) — desynced by aPhase
    i *= 0.8 + 0.2 * sin(uTime * 0.7 + vSeed);
    float fog = 1.0 - exp(-uFogDensity * uFogDensity * vViewZ * vViewZ);
    i *= (1.0 - fog);
    if (i <= 0.003) discard;
    vec3 c = mix(vColor, vColor * uPostureColor, clamp(uPostureTint, 0.0, 0.8));
    c += vColor * vBand * 0.3;   // flow band brightens as it sweeps (subtle)
    c *= uGlowMul;
    gl_FragColor = vec4(c * i, i);
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
      uSize: { value: 3.0 },       // small puncta in CSS px (poster fine-dot read)
      uAttenK: { value: 0.2 },     // weak depth; 0 = fully flat
      uFogDensity: { value: 0.05 },
      uGlowMul: { value: 1.6 },    // >1 so the existing PostFX Bloom (threshold 1.0) catches it
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
  material.customProgramCacheKey = () => 'pointfield_v4';
  return material;
}
