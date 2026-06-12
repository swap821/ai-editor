'use client';

import { useEffect, useMemo, useRef, useState, type MutableRefObject } from 'react';
import { Float, useGLTF } from '@react-three/drei';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { CognitiveMode } from '@/components/ui/SuperbrainHUD';
import AccretionCore from './AccretionCore';
import CognitiveGrasp from './CognitiveGrasp';
import CorticalSignals, { THOUGHT_WAVE_GLSL } from './CorticalSignals';
import PostFX from './PostFX';
import { publishCognition, subscribeCognition } from '@/lib/cognitionBus';
import { createSeededRandom } from '@/lib/seededRandom';
import NeuralAura from './NeuralAura';
import NervousSystem from './NervousSystem';
import CosmicBackground from './CosmicBackground';
import KnowledgeHorizon from './KnowledgeHorizon';
import RegionPins from './RegionPins';
import type { QualityTier } from '@/components/QualityTierProvider';

/** THE VISION (operator's words — the design constitution, see VISION.md):
 *  "AN AGENTIC AI-OS SUPERBRAIN CONSTANTLY MOVING FORWARD (MOTION) IN THE
 *  DEEP VAST KNOWLEDGE SPACE." The voyage is not negotiable: the knowledge
 *  field FLYING PAST the camera carries the forward motion. Any sky change
 *  that removes that motion breaks the product. 'voyage' = the operator's
 *  original moving field alone; 'layered' = his field in front of his
 *  photographic dome (motion + depth) — operator's choice. */
const SKY_MODE: 'voyage' | 'layered' = 'voyage';

/** Anatomical region pins (RESEARCH/MEMORY/TOOLS/SIGNALS callouts bound to
 *  the same live channels as the intake rows). Additive layer — the
 *  operator's call (VISION.md): flip to false to remove without a trace. */
const SHOW_REGION_PINS = true;

interface SuperbrainSceneProps {
  mode: CognitiveMode;
  activity: number;
  /** Effective quality tier — governs particle counts, shells, and the
   *  cortex shader's octave/animation budget. */
  tier?: QualityTier;
}

const BRAIN_SCALE = 3.02;
const TAU = Math.PI * 2;

/* ---------- shared cognition burst state ---------- */
export interface BurstState {
  lastBurst: number;
  intensity: number;
}

export type BurstRef = MutableRefObject<BurstState>;

/* ---------- shared camera push impulse (directive surge) ---------- */
interface CameraPushState {
  /** 0..1 impulse; CameraDrift converts it into a -0.45 dolly-in and decays it. */
  value: number;
}

type CameraPushRef = MutableRefObject<CameraPushState>;

/* -------------------------------------------------------------------------- */
/*  Idle attract-mode — autonomous cognition                                   */
/*                                                                             */
/*  After 30 s with NO user input the brain visibly keeps thinking on its      */
/*  own: CameraDrift gains a slow extra orbital yaw + a ±2° pitch sine         */
/*  (eased in over 2.5 s), and every 6–9 s a "thought cascade" fires — an      */
/*  immediate cortex thought-wave plus a synthesis event on the cognition      */
/*  bus so the terminal logs the unprompted inference. ANY input eases the     */
/*  blend back out over ~0.6 s. The controller is module-level so the scene    */
/*  root (which advances it) and CameraDrift (which reads it) share state;     */
/*  the input listeners are attached in a useEffect with full cleanup.         */
/* -------------------------------------------------------------------------- */

const IDLE_DELAY_S = 30;
const IDLE_EASE_IN_S = 2.5;
const IDLE_EASE_OUT_S = 0.6;
/** Extra orbital yaw while idle (rad/s) — multiplied into the existing orbit. */
const IDLE_YAW_RATE = 0.02;
/** ±2° pitch sine while idle. */
const IDLE_PITCH_AMPLITUDE = THREE.MathUtils.degToRad(2);
/** Pitch sway angular frequency (rad/s) — one full sway ≈ 25 s. */
const IDLE_PITCH_FREQ = 0.25;

interface IdleControllerState {
  lastInputMs: number;
  progress: number;
  blend: number;
  yaw: number;
  cascadeIndex: number;
  nextCascadeAt: number;
  wasIdle: boolean;
}
type IdleControllerRef = MutableRefObject<IdleControllerState>;

/** Idle never engages while the user is focused in a text-entry element. */
function isTextEntryFocused(): boolean {
  const active = document.activeElement;
  return (
    active instanceof HTMLInputElement ||
    active instanceof HTMLTextAreaElement ||
    active instanceof HTMLSelectElement ||
    (active instanceof HTMLElement && active.isContentEditable)
  );
}

/* -------------------------------------------------------------------------- */
/*  Shared sentience uniforms                                                  */
/*                                                                             */
/*  ONE module-scope object whose {value} leaves are referenced by the cortex  */
/*  shader, the two NeuralAura shells and the CorticalSignals fireflies. The   */
/*  scene root writes each leaf once per frame, so breath / waves / burst are  */
/*  phase-locked across every layer — the organism moves as one body.          */
/* -------------------------------------------------------------------------- */

export interface CognitionUniforms {
  uTime: { value: number };
  /** Layered asymmetric breath, 0..1 (0.1 Hz systole + slower swells). */
  uBreath: { value: number };
  uRimGain: { value: number };
  uSssScale: { value: number };
  uCoreGain: { value: number };
  uBurst: { value: number };
  /** View-space direction toward the virtual backlight BEHIND the brain. */
  uBackLightDir: { value: THREE.Vector3 };
  uModeTint: { value: THREE.Color };
  uWaveOrigins: { value: THREE.Vector3[] };
  uWaveTimes: { value: number[] };
  /** 0..1 — the approval hold. The supervised mind is waiting for its
   *  operator: breath freezes, the organism turns amber, wires dim. */
  uHold: { value: number };
}

const createCognitionUniforms = (): CognitionUniforms => ({
  uTime: { value: 0 },
  uBreath: { value: 0.5 },
  uRimGain: { value: 1.4 },
  uSssScale: { value: 0.9 },
  uCoreGain: { value: 0.18 },
  uBurst: { value: 0 },
  uBackLightDir: { value: new THREE.Vector3(0, 0.1, -1).normalize() },
  uModeTint: { value: new THREE.Color('#10164a') },
  uWaveOrigins: {
    value: [new THREE.Vector3(0, 10, 0), new THREE.Vector3(0, 10, 0), new THREE.Vector3(0, 10, 0)],
  },
  // Dormant slots sit far in the past; the GLSL clamps ages so this is safe.
  uWaveTimes: { value: [-10, -10, -10] },
  uHold: { value: 0 },
});

/** YELLOW-zone amber — the approval hold's signature color. Accent only. */
const HOLD_TINT = new THREE.Color('#b96a14');

/** The ONE shared-uniform instance — genuinely module-level (the scene mounts
 *  exactly once), so frame-loop mutation is architecture, not a hook-rule
 *  violation. */
const SCENE_UNIFORMS = createCognitionUniforms();

/* -------------------------------------------------------------------------- */
/*  Travel convention: the brain voyages toward -Z (into deep knowledge        */
/*  space), so the knowledge field flows past it toward +Z. The brain's slow   */
/*  lateral drift is shared between BrainModel (position + bank) and           */
/*  CameraDrift (lookAt pursuit) so the framing follows the voyage.            */
/* -------------------------------------------------------------------------- */

function brainDriftX(time: number): number {
  return Math.sin(time * 0.16) * 0.24 + Math.cos(time * 0.09) * 0.1;
}

/** d/dt of brainDriftX — the ship banks into the turn (negative direction). */
function brainDriftVelocityX(time: number): number {
  return Math.cos(time * 0.16) * 0.0384 - Math.sin(time * 0.09) * 0.009;
}

/** Scales the drift velocity (|max| ~0.0474) to a ~0.03 rad bank amplitude. */
const BANK_GAIN = 0.633;
/** Constant forward lean — nose pitched into the voyage. */
const FORWARD_LEAN = 0.05;

/* ---------- mode-reactive core tint targets (lerped into uModeTint) ---------- */
const MODE_EMISSIVE: Record<CognitiveMode, THREE.Color> = {
  observe: new THREE.Color('#10164a'),
  synthesize: new THREE.Color('#35205f'),
  orchestrate: new THREE.Color('#5c183d'),
};

/* -------------------------------------------------------------------------- */
/*  Anatomical region vertex colors                                            */
/*                                                                             */
/*  Baked once per unique geometry into a "color" buffer attribute in          */
/*  brain-group-local space. clone(true) SHARES geometry between the brain,    */
/*  wireframe, aura and signal layers, so every layer can read the same        */
/*  attribute for free. The same pass bakes "objectPos" (group-local           */
/*  position) so the shaders can evaluate filaments and thought-waves in a     */
/*  stable object space regardless of the GLB's node transforms.               */
/* -------------------------------------------------------------------------- */

/**
 * Anterior (frontal / red-orange) end of the long horizontal axis (local Z).
 * With the group's rotation.y ≈ -0.78, local +Z maps to screen-LEFT, which is
 * where the red frontal lobe sits. Flip to -1 to mirror the whole anatomical
 * mapping in one line.
 */
const ANTERIOR_SIGN = +1;

/* Measured brain-group-local bounds of /models/brain.glb (root scale 0.01). */
const BRAIN_MIN = new THREE.Vector3(-0.379, -0.222, -0.439);
const BRAIN_MAX = new THREE.Vector3(0.382, 0.633, 0.553);

const REGION_FRONTAL_CORE = new THREE.Color('#ff3b28'); // deep red-orange
const REGION_FRONTAL_EDGE = new THREE.Color('#ff7a26'); // burnt orange blend
const REGION_PARIETAL = new THREE.Color('#19d4f0');     // electric cyan crown
const REGION_TEMPORAL = new THREE.Color('#36f07a');     // mid vivid green
const REGION_TEMPORAL_LIME = new THREE.Color('#a8e62b'); // lower-mid lime
const REGION_OCCIPITAL = new THREE.Color('#9b3bff');    // rear deep violet
const REGION_OCCIPITAL_HOT = new THREE.Color('#e62bd4'); // rear magenta
const REGION_CEREBELLUM = new THREE.Color('#6a35ff');   // ventral/stem deep violet

/** Minimum blended-region luminance BEFORE cavity darkening (keeps the
 *  underside violet instead of dropping to black). */
const REGION_LUMINANCE_FLOOR = 0.12;
/** Sulci (vertices below the mean shell radius) darken toward this factor.
 *  Softened from 0.30: the emission-led material model already keeps the
 *  base near-black, so heavy baked AO would just kill the rim/SSS tints. */
const CAVITY_DARKEN = 0.52;

/* ---------- 3-octave value noise (organic region boundaries) ---------- */

function hash3(ix: number, iy: number, iz: number): number {
  let n = Math.imul(ix, 374761393) ^ Math.imul(iy, 668265263) ^ Math.imul(iz, 1274126177);
  n = Math.imul(n ^ (n >>> 13), 1274126177);
  return ((n ^ (n >>> 16)) >>> 0) / 4294967296;
}

function valueNoise3(x: number, y: number, z: number): number {
  const ix = Math.floor(x);
  const iy = Math.floor(y);
  const iz = Math.floor(z);
  const fx = x - ix;
  const fy = y - iy;
  const fz = z - iz;
  const sx = fx * fx * (3 - 2 * fx);
  const sy = fy * fy * (3 - 2 * fy);
  const sz = fz * fz * (3 - 2 * fz);

  const c000 = hash3(ix, iy, iz);
  const c100 = hash3(ix + 1, iy, iz);
  const c010 = hash3(ix, iy + 1, iz);
  const c110 = hash3(ix + 1, iy + 1, iz);
  const c001 = hash3(ix, iy, iz + 1);
  const c101 = hash3(ix + 1, iy, iz + 1);
  const c011 = hash3(ix, iy + 1, iz + 1);
  const c111 = hash3(ix + 1, iy + 1, iz + 1);

  const x00 = c000 + (c100 - c000) * sx;
  const x10 = c010 + (c110 - c010) * sx;
  const x01 = c001 + (c101 - c001) * sx;
  const x11 = c011 + (c111 - c011) * sx;
  const y0 = x00 + (x10 - x00) * sy;
  const y1 = x01 + (x11 - x01) * sy;
  return y0 + (y1 - y0) * sz;
}

/** 3 octaves, output roughly centered on 0 (range about -0.5..0.5). */
function fbm3(x: number, y: number, z: number): number {
  const n =
    valueNoise3(x, y, z) * 0.5 +
    valueNoise3(x * 2.03 + 17.1, y * 2.03 + 9.7, z * 2.03 + 31.4) * 0.25 +
    valueNoise3(x * 4.07 + 47.2, y * 4.07 + 71.3, z * 4.07 + 5.9) * 0.125;
  return n / 0.875 - 0.5;
}

const smoothstep = (edge0: number, edge1: number, v: number) => {
  const t = THREE.MathUtils.clamp((v - edge0) / (edge1 - edge0), 0, 1);
  return t * t * (3 - 2 * t);
};

/**
 * Bakes anatomical region colors into a vertex "color" attribute for every
 * unique geometry under `root`, plus an "objectPos" attribute holding the
 * brain-group-local position. Positions are taken in clone-root space (the
 * clone is never added to the scene, so matrixWorld === group-local space).
 */
function applyRegionVertexColors(root: THREE.Object3D) {
  root.updateMatrixWorld(true);

  const center = new THREE.Vector3().addVectors(BRAIN_MIN, BRAIN_MAX).multiplyScalar(0.5);
  const halfExtents = new THREE.Vector3().subVectors(BRAIN_MAX, BRAIN_MIN).multiplyScalar(0.5);
  const halfZ = halfExtents.z;
  const spanY = BRAIN_MAX.y - BRAIN_MIN.y;
  const v = new THREE.Vector3();
  const out = new THREE.Color();
  const frontal = new THREE.Color();
  const temporal = new THREE.Color();
  const occipital = new THREE.Color();

  // Unique geometries (clone(true) SHARES them across the brain / wireframe /
  // aura layers). GLB-authored color attributes are intentionally overwritten:
  // some assets ship near-black ventral vertex colors that previously survived
  // the bake and rendered the stem zone black.
  const seen = new Set<THREE.BufferGeometry>();
  const entries: { geometry: THREE.BufferGeometry; matrixWorld: THREE.Matrix4 }[] = [];
  root.traverse((object) => {
    if (!(object instanceof THREE.Mesh)) return;
    const geometry = object.geometry as THREE.BufferGeometry;
    if (seen.has(geometry)) return;
    seen.add(geometry);
    entries.push({ geometry, matrixWorld: object.matrixWorld });
  });

  /* Pass 1 — ellipsoid-normalized shell radius per vertex. The global mean is
     the "smooth hull" reference: gyri crest above it, sulci dip below it. */
  const shellRadii: Float32Array[] = [];
  let radiusSum = 0;
  let vertexCount = 0;
  for (const { geometry, matrixWorld } of entries) {
    const position = geometry.getAttribute('position');
    const radii = new Float32Array(position.count);
    for (let i = 0; i < position.count; i++) {
      v.fromBufferAttribute(position, i).applyMatrix4(matrixWorld);
      const rx = (v.x - center.x) / halfExtents.x;
      const ry = (v.y - center.y) / halfExtents.y;
      const rz = (v.z - center.z) / halfExtents.z;
      const radius = Math.sqrt(rx * rx + ry * ry + rz * rz);
      radii[i] = radius;
      radiusSum += radius;
    }
    vertexCount += position.count;
    shellRadii.push(radii);
  }
  const meanRadius = vertexCount > 0 ? radiusSum / vertexCount : 1;

  /* Pass 2 — region colors + cavity darkening (sulci dark, gyri bright). */
  entries.forEach(({ geometry, matrixWorld }, entryIndex) => {
    const position = geometry.getAttribute('position');
    const radii = shellRadii[entryIndex];
    const colors = new Float32Array(position.count * 3);
    const objectPositions = new Float32Array(position.count * 3);

    for (let i = 0; i < position.count; i++) {
      v.fromBufferAttribute(position, i).applyMatrix4(matrixWorld);

      // Group-local position — the shaders' stable object space.
      objectPositions[i * 3] = v.x;
      objectPositions[i * 3 + 1] = v.y;
      objectPositions[i * 3 + 2] = v.z;

      // Normalized anatomical coordinates.
      const az = (ANTERIOR_SIGN * (v.z - center.z)) / halfZ;        // -1 rear .. +1 front
      const h = (v.y - BRAIN_MIN.y) / spanY;                        // 0 bottom .. 1 top

      // Organic boundary wobble — two decorrelated fbm samples.
      const n1 = fbm3(v.x * 7.0, v.y * 7.0, v.z * 7.0);
      const n2 = fbm3(v.x * 5.0 + 93.7, v.y * 5.0 + 11.3, v.z * 5.0 + 57.9);
      const azn = az + n1 * 0.34;
      const hn = h + n2 * 0.22;

      // Region weights (smooth, overlapping — blended, never hard-edged).
      const lowRear = smoothstep(0.12, 0.55, -azn) * smoothstep(0.42, 0.12, hn);
      // Height-damped so red owns the frontal FACE while the cyan crown keeps
      // the dome (red never climbs over the top).
      const wFrontal = smoothstep(0.22, 0.62, azn) * (1 - smoothstep(0.55, 0.85, hn) * 0.8);
      // Ventral / stem coverage: anything near the underside leans deep violet
      // (damped under the frontal lobe so the front underside stays warm).
      const ventral = smoothstep(0.3, 0.04, hn) * (1 - wFrontal * 0.6);
      const wCerebellum = lowRear * 1.4 + ventral * 1.1;
      // Occipital boosted 1.6x so violet/magenta wins the rear quarter (the
      // judges measured the rear silhouette reading green otherwise).
      const wOccipital = smoothstep(0.0, 0.45, -azn) * (1 - lowRear * 0.85) * 1.6;
      // Crown: no occipital damp + 1.4x so the top reads icy cyan, not pink.
      // Rear-damped: the cyan crown is a top sliver — the rear-top belongs to
      // the occipital violet.
      const wParietal = smoothstep(0.46, 0.78, hn) * (1 - wFrontal * 0.45)
        * (1 - smoothstep(0.1, 0.5, -azn) * 0.7) * 1.7;
      // Temporal green confined to the mid-lateral zone.
      const wTemporal = Math.max(
        (1 - smoothstep(0.05, 0.45, Math.abs(azn))) * smoothstep(0.78, 0.3, hn),
        0.02, // tiny floor keeps the total weight nonzero
      );

      // Intra-region gradients.
      frontal.lerpColors(REGION_FRONTAL_EDGE, REGION_FRONTAL_CORE, smoothstep(0.1, 0.65, azn));
      temporal.lerpColors(REGION_TEMPORAL, REGION_TEMPORAL_LIME, smoothstep(0.45, 0.18, hn));
      // Magenta sits LOW-rear, violet at the top — reversed so the hot pink
      // no longer bleeds into the cyan crown.
      occipital.lerpColors(REGION_OCCIPITAL, REGION_OCCIPITAL_HOT, smoothstep(0.75, 0.25, hn));

      // Sharpen region dominance: a linear blend of complementary hues makes
      // mud (red + cyan = washed pink). The exponent pushes each vertex toward
      // its strongest region while the fbm wobble keeps boundaries organic.
      const pFrontal = Math.pow(wFrontal, 2.6);
      const pParietal = Math.pow(wParietal, 2.6);
      const pTemporal = Math.pow(wTemporal, 2.6);
      const pOccipital = Math.pow(wOccipital, 2.6);
      const pCerebellum = Math.pow(wCerebellum, 2.6);

      const total = pFrontal + pParietal + pTemporal + pOccipital + pCerebellum;
      out.setRGB(
        (frontal.r * pFrontal + REGION_PARIETAL.r * pParietal + temporal.r * pTemporal +
          occipital.r * pOccipital + REGION_CEREBELLUM.r * pCerebellum) / total,
        (frontal.g * pFrontal + REGION_PARIETAL.g * pParietal + temporal.g * pTemporal +
          occipital.g * pOccipital + REGION_CEREBELLUM.g * pCerebellum) / total,
        (frontal.b * pFrontal + REGION_PARIETAL.b * pParietal + temporal.b * pTemporal +
          occipital.b * pOccipital + REGION_CEREBELLUM.b * pCerebellum) / total,
      );

      // Luminance floor BEFORE cavity darkening — no near-black region blends.
      const lum = out.r * 0.2126 + out.g * 0.7152 + out.b * 0.0722;
      if (lum < REGION_LUMINANCE_FLOOR) {
        if (lum < 1e-4) out.copy(REGION_CEREBELLUM);
        else out.multiplyScalar(REGION_LUMINANCE_FLOOR / lum);
      }

      // AO-like cavity darkening: vertices that dip below the mean shell
      // radius (sulci) fall toward CAVITY_DARKEN; gyral crests stay bright.
      const depth = smoothstep(meanRadius * 1.06, meanRadius * 0.84, radii[i]);
      const ao = 1 - depth * (1 - CAVITY_DARKEN);

      colors[i * 3] = out.r * ao;
      colors[i * 3 + 1] = out.g * ao;
      colors[i * 3 + 2] = out.b * ao;
    }

    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geometry.setAttribute('objectPos', new THREE.BufferAttribute(objectPositions, 3));
  });
}

/* -------------------------------------------------------------------------- */
/*  Thought-wave scheduling (CPU side)                                         */
/*                                                                             */
/*  Waves fire at Poisson-ish 3–8 s intervals AND on cognitionBus burst /      */
/*  knowledge-acquired events. Labeled knowledge lands near its anatomical     */
/*  region, so the SAME shard always lights the SAME cortex zone — causality   */
/*  is what upgrades "animated" to "sentient".                                 */
/* -------------------------------------------------------------------------- */

const WAVE_CENTER = new THREE.Vector3().addVectors(BRAIN_MIN, BRAIN_MAX).multiplyScalar(0.5);
const WAVE_HALF = new THREE.Vector3().subVectors(BRAIN_MAX, BRAIN_MIN).multiplyScalar(0.5);

const WAVE_REGION_ANCHORS: { pattern: RegExp; origin: THREE.Vector3 }[] = [
  // Signal-flavored intake lands occipital (rear violet), archives temporal,
  // causal/graph work frontal, lattices on the parietal crown.
  { pattern: /SIGNAL|TITAN/i, origin: new THREE.Vector3(0.05, 0.31, -0.38 * ANTERIOR_SIGN) },
  { pattern: /ARCHIVE|MYTHOS|MEMORY/i, origin: new THREE.Vector3(0.34, 0.16, 0.11 * ANTERIOR_SIGN) },
  { pattern: /CAUSAL|GRAPH|DELTA/i, origin: new THREE.Vector3(0, 0.26, 0.48 * ANTERIOR_SIGN) },
  { pattern: /SEMANTIC|LATTICE/i, origin: new THREE.Vector3(0, 0.61, 0.11) },
];

function randomWaveOrigin(random: () => number): THREE.Vector3 {
  const theta = random() * TAU;
  const phi = Math.acos(2 * random() - 1);
  return new THREE.Vector3(
    WAVE_CENTER.x + Math.sin(phi) * Math.cos(theta) * WAVE_HALF.x * 0.92,
    WAVE_CENTER.y + Math.cos(phi) * WAVE_HALF.y * 0.92,
    WAVE_CENTER.z + Math.sin(phi) * Math.sin(theta) * WAVE_HALF.z * 0.92,
  );
}

function waveOriginForLabel(label: string | undefined, random: () => number): THREE.Vector3 {
  if (label) {
    for (const anchor of WAVE_REGION_ANCHORS) {
      if (anchor.pattern.test(label)) {
        return new THREE.Vector3(
          anchor.origin.x + (random() - 0.5) * 0.1,
          anchor.origin.y + (random() - 0.5) * 0.1,
          anchor.origin.z + (random() - 0.5) * 0.1,
        );
      }
    }
  }
  return randomWaveOrigin(random);
}

/* -------------------------------------------------------------------------- */
/*  Cortex shader — color is LIGHT, not paint                                  */
/*                                                                             */
/*  The baked region vertex colors survive as an emission mask over a          */
/*  near-black base. Layers (luminance ladder): dark base 0.08 -> core glow    */
/*  ~0.18 (sub-bloom) -> SSS ~0.3 (sub-bloom) -> fresnel rim 1.2-1.6 (thin     */
/*  silhouette bloom only) -> filaments ~2.2 / wavefronts (hairline + front,   */
/*  the only hot pixels).                                                      */
/* -------------------------------------------------------------------------- */

const FLOW_NOISE_GLSL = /* glsl */ `
  float sbHash(vec3 p) {
    p = fract(p * 0.3183099 + vec3(0.71, 0.113, 0.419));
    p *= 17.0;
    return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
  }
  float sbNoise(vec3 p) {
    vec3 i = floor(p);
    vec3 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float n000 = sbHash(i);
    float n100 = sbHash(i + vec3(1.0, 0.0, 0.0));
    float n010 = sbHash(i + vec3(0.0, 1.0, 0.0));
    float n110 = sbHash(i + vec3(1.0, 1.0, 0.0));
    float n001 = sbHash(i + vec3(0.0, 0.0, 1.0));
    float n101 = sbHash(i + vec3(1.0, 0.0, 1.0));
    float n011 = sbHash(i + vec3(0.0, 1.0, 1.0));
    float n111 = sbHash(i + vec3(1.0, 1.0, 1.0));
    return mix(
      mix(mix(n000, n100, f.x), mix(n010, n110, f.x), f.y),
      mix(mix(n001, n101, f.x), mix(n011, n111, f.x), f.y),
      f.z
    );
  }
  float sbFbm(vec3 p) {
    return sbNoise(p) * 0.667 + sbNoise(p * 2.13 + vec3(31.7, 11.3, 71.9)) * 0.333;
  }
  float brainFold(vec3 p) {
    vec3 warp = vec3(sbNoise(p * 0.8), sbNoise(p * 0.8 + 13.0), sbNoise(p * 0.8 + 27.0)) * 1.5;
    float n = sbNoise(p * 1.5 + warp); 
    return 1.0 - abs(n * 2.0 - 1.0); 
  }
  vec3 voronoi(vec3 p) {
    vec3 i = floor(p); vec3 f = fract(p);
    vec2 res = vec2(8.0, 8.0);
    for(int x=-1; x<=1; x++) for(int y=-1; y<=1; y++) for(int z=-1; z<=1; z++) {
        vec3 b = vec3(float(x), float(y), float(z));
        vec3 r = b + vec3(sbHash(i + b)) - f;
        float d = length(r);
        if(d < res.x) { res.y = res.x; res.x = d; }
        else if(d < res.y) { res.y = d; }
    }
    return vec3(res, 0.0);
  }
`;

const CASING_VERTEX_SHADER = /* glsl */ `
  varying vec3 vNormalV;
  varying vec3 vViewDirV;

  void main() {
    vNormalV = normalize(normalMatrix * normal);
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    vViewDirV = -mvPosition.xyz;
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const CASING_FRAGMENT_SHADER = /* glsl */ `
  uniform float uTime;
  varying vec3 vNormalV;
  varying vec3 vViewDirV;

  void main() {
    vec3 N = normalize(vNormalV);
    vec3 V = normalize(vViewDirV);
    
    // Sharp fresnel edge
    float fres = pow(1.0 - clamp(dot(N, V), 0.0, 1.0), 3.0);
    
    // Vibrant neon rim glow
    vec3 glowColor = vec3(0.0, 0.8, 1.0); // Cyan base
    
    // Iridescence (magenta/purple shift on the edges)
    vec3 irid = 0.5 + 0.5 * cos(6.28318 * (fres * 1.5 + uTime * 0.1 + vec3(0.0, 0.33, 0.67)));
    
    vec3 emission = mix(glowColor, irid, 0.5) * fres * 3.0; // Intense glow
    
    float alpha = fres * 0.4;
    
    gl_FragColor = vec4(emission, alpha);
  }
`;

function BrainModel({
  activity,
  mode,
  burst,
  uniforms,
  tier = 'high',
}: {
  activity: number;
  mode: CognitiveMode;
  burst: BurstRef;
  uniforms: CognitionUniforms;
  tier?: QualityTier;
}) {
  const groupRef = useRef<THREE.Group>(null);
  const { scene } = useGLTF('/models/brain.glb');

  const brainAsset = useMemo(() => {
    const clone = scene.clone(true);
    const materials: THREE.Material[] = [];
    
    applyRegionVertexColors(clone);
    
      const mat = new THREE.MeshPhysicalMaterial({
        vertexColors: true,
        color: 0x010308, // Dark base
        roughness: 0.2,
        metalness: 0.1,
        emissive: 0x000000,
        
        // Deep glass polish (opaque but highly reflective)
        clearcoat: 1.0,
        clearcoatRoughness: 0.05,
      });

      mat.onBeforeCompile = (shader) => {
        // Link the shared sentience leaves into the brain shader
        shader.uniforms.uTime = uniforms.uTime;
        shader.uniforms.uHold = uniforms.uHold;

        // Pass local position to fragment shader for stable high-frequency noise
        shader.vertexShader = shader.vertexShader.replace(
          '#include <common>',
          `#include <common>
           varying vec3 vLocalPos;
          `
        );
        shader.vertexShader = shader.vertexShader.replace(
          '#include <begin_vertex>',
          `#include <begin_vertex>
           vLocalPos = position * 2.0; // Stabilized local scale
          `
        );

        shader.fragmentShader = shader.fragmentShader.replace(
          '#include <common>',
          `#include <common>
           uniform float uTime;
           uniform float uHold;
           varying vec3 vLocalPos;
           
           vec3 hash33(vec3 p) {
               p = vec3(dot(p, vec3(127.1, 311.7, 74.7)),
                        dot(p, vec3(269.5, 183.3, 246.1)),
                        dot(p, vec3(113.5, 271.9, 124.6)));
               return fract(sin(p) * 43758.5453123);
           }

           // Animated 3D Voronoi for flowing, living neural synapses
           float voronoi(vec3 x) {
               vec3 p = floor(x);
               vec3 f = fract(x);
               float res = 100.0;
               for(int k=-1; k<=1; k++) {
                   for(int j=-1; j<=1; j++) {
                       for(int i=-1; i<=1; i++) {
                           vec3 b = vec3(float(i), float(j), float(k));
                           vec3 h = hash33(p + b);
                           // Animate the cell points smoothly over time
                           // (frozen on the low tier: same web, zero per-frame churn)
                           ${tier === 'low'
                             ? 'vec3 anim = vec3(0.5);'
                             : 'vec3 anim = 0.5 + 0.5 * sin(uTime * 1.2 + 6.2831 * h);'}
                           vec3 r = vec3(b) - f + anim;
                           float d = dot(r, r);
                           if(d < res) res = d;
                       }
                   }
               }
               return sqrt(res);
           }

            // Continuous glowing neural web (edges of the Voronoi cells)
           float microDetail(vec3 pos) {
               float scale = 0.6; 
               // Do not invert! We want distance to center. 
               // Centers are 0.0 (dark), edges are ~0.8 (bright)
               float v1 = voronoi(pos * scale);
               ${tier === 'high'
                 ? `float v2 = voronoi(pos * scale * 2.0 + vec3(v1));
               // Combine into a multi-scale continuous web
               float webbing = v1 * 0.7 + v2 * 0.3;`
                 : `// Single-octave web below the high tier (half the loops)
               float webbing = v1;`}
               
               // Isolate the highest values to create thin, sharp, glowing interconnected lines
               return smoothstep(0.4, 0.8, webbing);
           }
          `
        );

        shader.fragmentShader = shader.fragmentShader.replace(
          '#include <normal_fragment_begin>',
          `#include <normal_fragment_begin>
           // PROCEDURAL BUMP MAPPING (Normal Perturbation)
           // Smooth, thick organic bump (lowered multiplier from 0.08 to 0.015 to prevent sandy artifacts)
           // Evaluated ONCE per fragment and shared with the emission pass
           // below (each microDetail call is two 27-cell animated Voronoi
           // loops — the single heaviest cost on screen).
           float gNeuralWeb = microDetail(vLocalPos);
           float h = gNeuralWeb * 0.015;
           vec3 vSigmaX = dFdx(vViewPosition);
           vec3 vSigmaY = dFdy(vViewPosition);
           vec3 vN = normal;
           vec3 R1 = cross(vSigmaY, vN);
           vec3 R2 = cross(vN, vSigmaX);
           float fDet = dot(vSigmaX, R1);
           float vGradX = dFdx(h);
           float vGradY = dFdy(h);
           vec3 vGrad = sign(fDet) * (vGradX * R1 + vGradY * R2);
           normal = normalize(abs(fDet) * vN - vGrad);
          `
        );

        shader.fragmentShader = shader.fragmentShader.replace(
          '#include <color_fragment>',
          `#include <color_fragment>
           // Make the diffuse base extremely dark so the emissive glow pops.
           // color_fragment already applies vColor to diffuseColor, but we want it
           // to be driven purely by emission.
           diffuseColor.rgb = vec3(0.01, 0.02, 0.04);
          `
        );

        shader.fragmentShader = shader.fragmentShader.replace(
          '#include <emissivemap_fragment>',
          `#include <emissivemap_fragment>
           
           // The neural synapse pattern, computed once in the bump pass above.
           float cDetail = gNeuralWeb;
           
           // Extract RGB safely regardless of whether vColor is vec3 or vec4
           vec3 safeColor = vColor.rgb;
           
           // 1. Core Regional Glow: Drive the emission intensely using the baked regional colors,
           // modulated by the Voronoi network so it looks incredibly detailed and organic!
           // Reduced pow() to make the web slightly thicker and increased multiplier for intense bloom!
           totalEmissiveRadiance += safeColor * pow(cDetail, 1.5) * 4.0;
           
           // 2. Vibrant Edge Rim Light: Smooth Fresnel that dynamically matches the region's color!
           vec3 viewDir = normalize(vViewPosition);
           vec3 geomNormal = normalize(vNormal); 
           float fresnel = pow(1.0 - max(dot(viewDir, geomNormal), 0.0), 2.5);
           
           // Organic breathing pulse — held steady and bright during an
           // approval hold (bated breath, not a flatline).
           float pulse = sin(uTime * 2.0) * 0.5 + 0.5;
           float pulseMix = mix(mix(0.7, 1.5, pulse), 1.25, uHold);

           // Add the dynamic rim light, heavily multiplying the local region color
           totalEmissiveRadiance += safeColor * fresnel * 2.0 * pulseMix;

           // Approval hold: the whole cortex tints toward YELLOW-zone amber —
           // structure preserved, hue deferring to the operator.
           vec3 holdTone = vec3(1.0, 0.62, 0.22);
           totalEmissiveRadiance = mix(
             totalEmissiveRadiance,
             totalEmissiveRadiance * holdTone + holdTone * 0.05,
             uHold * 0.85
           );
          `
        );
      };
      
      // The GLSL varies by tier, so the compiled-program cache key MUST too —
      // a constant key made THREE reuse the first-compiled (possibly
      // degraded) program for the whole session, no matter what FIDELITY
      // said. The operator's eyes caught what three rounds of instruments
      // missed.
      mat.customProgramCacheKey = () => `superbrain_v6_${tier}`;

      clone.traverse((object) => {
        if (object instanceof THREE.Mesh) {
          object.material = mat;
        }
      });

    return { object: clone, materials };
  }, [scene, uniforms, tier]);

  const neuralSkin = useMemo(() => {
    const clone = brainAsset.object.clone(true);
    const materials: THREE.ShaderMaterial[] = [];
    clone.traverse((object) => {
      if (!(object instanceof THREE.Mesh)) return;
      const mat = new THREE.ShaderMaterial({
        uniforms: { uTime: uniforms.uTime },
        vertexShader: CASING_VERTEX_SHADER,
        fragmentShader: CASING_FRAGMENT_SHADER,
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      object.material = mat;
      materials.push(mat);
      object.renderOrder = 2;
    });
    return { object: clone, materials };
  }, [brainAsset, uniforms, CASING_VERTEX_SHADER, CASING_FRAGMENT_SHADER]);

  useEffect(() => {
    return () => {
      brainAsset.materials.forEach(m => m.dispose());
      neuralSkin.materials.forEach(m => m.dispose());
    };
  }, [brainAsset, neuralSkin]);

  useFrame((state, delta) => {
    const time = state.clock.elapsedTime;
    const burstPow = burst.current.intensity;

    /* ── Brain group animation ── */
    if (groupRef.current) {
      // Asymmetric systolic breath (shared uniform — the same rhythm every
      // shader layer breathes with) + burst expansion kick.
      const scale = BRAIN_SCALE * (1 + uniforms.uBreath.value * 0.006)
        + activity * 0.05 + burstPow * 0.15;
      const damped = THREE.MathUtils.damp(groupRef.current.scale.x, scale, 2.4, delta);
      groupRef.current.scale.setScalar(damped);

      // Hold a cinematic three-quarter silhouette instead of spinning into
      // unreadable rear angles. Restores the classic, recognizable brain shape.
      groupRef.current.rotation.y = -0.78
        + Math.sin(time * 0.11) * 0.22
        + Math.sin(time * 0.31) * 0.04
        + burstPow * 0.025;
      // Constant forward lean: the mind is pitched INTO the voyage (-Z).
      groupRef.current.rotation.x = FORWARD_LEAN
        + Math.sin(time * 0.21) * 0.065 + Math.cos(time * 0.13) * 0.025;
      // Bank into the turn like a ship — roll follows the NEGATIVE direction
      // of the lateral drift velocity, amplitude ~0.03 rad.
      groupRef.current.rotation.z = Math.sin(time * 0.17) * 0.045 + Math.cos(time * 0.11) * 0.02
        - brainDriftVelocityX(time) * BANK_GAIN;

      // A slow exploratory drift keeps the intelligence moving through space.
      groupRef.current.position.x = brainDriftX(time);
      groupRef.current.position.y = 0.12 + Math.cos(time * 0.2) * 0.14 + Math.sin(time * 0.14) * 0.07;
    }
  });

  return (
    <group ref={groupRef} rotation={[0.04, -0.82, 0]} position={[0, -0.35, -1.2]}>
      
      <primitive object={brainAsset.object} />
      <primitive object={neuralSkin.object} scale={1.004} />
      
      {/* Physical 3D Shiny UI Nodes connected directly to Brain Surface with constellation lines.
          Tier budget: low drops the aura shells entirely; medium keeps the
          membrane but drops the interior nucleus glow. */}
      {tier !== 'low' && (
        <NeuralAura
          activity={activity}
          mode={mode}
          source={brainAsset.object}
          uniforms={uniforms}
          shells={tier === 'high' ? 2 : 1}
        />
      )}
      <CorticalSignals
        activity={activity}
        source={brainAsset.object}
        uniforms={uniforms}
        count={tier === 'high' ? 320 : tier === 'medium' ? 180 : 80}
      />
      {/* Anatomical callouts ride INSIDE the group: pinned to the lobes,
          breathing and banking with the organism. */}
      {SHOW_REGION_PINS && <RegionPins />}
    </group>
  );
}

function CameraDrift({
  activity,
  burst,
  push,
  idleRef,
}: {
  activity: number;
  burst: BurstRef;
  push: CameraPushRef;
  idleRef: IdleControllerRef;
}) {
  useFrame((state, delta) => {
    const time = state.clock.elapsedTime;
    const cycle = (time % 20) / 20;
    const focus = THREE.MathUtils.smoothstep(cycle, 0.38, 0.64) * (1 - THREE.MathUtils.smoothstep(cycle, 0.7, 0.9));

    // Slow orbital component (60s full orbit) — feel of circling the
    // intelligence. Idle attract-mode adds extra yaw (~0.02 rad/s, eased in
    // by the idle blend) INTO this same orbit angle — multiplied into the
    // existing math, never replacing it.
    const orbitAngle = time * 0.015 + idleRef.current.yaw;
    const orbitRadius = 0.35;

    // Cognition bursts ripple into a tiny high-frequency camera shake.
    // Applied AFTER damping — the 1.8λ low-pass would otherwise swallow it.
    const shake = burst.current.intensity;
    const shakeX = Math.sin(time * 43.7) * shake * 0.018;
    const shakeY = Math.cos(time * 38.3) * shake * 0.014;

    const targetX = state.pointer.x * 0.25
      + Math.sin(time * 0.12) * 0.12
      + focus * 0.22
      + Math.sin(orbitAngle) * orbitRadius;
    const targetY = 0.2
      + state.pointer.y * 0.15
      + Math.cos(time * 0.1) * 0.06
      + Math.cos(orbitAngle) * orbitRadius * 0.3;
    // Perpetual dolly wave (~0.04 Hz): the camera breathes along the travel
    // axis, so the voyage never reads as a tripod lockoff. The directive push
    // impulse (decayed by the scene root over ~2s) dollies in by up to 0.45 —
    // issuing a command feels like the engine surging.
    const dollyWave = Math.sin(time * Math.PI * 2 * 0.04) * 0.12;
    const targetZ = 7.5 - focus * 0.55 - activity * 0.14 // hero framing: zoomed out to 7.5 for soothing size
      + dollyWave
      - push.current.value * 0.45;

    state.camera.position.x = THREE.MathUtils.damp(state.camera.position.x, targetX, 1.8, delta) + shakeX;
    state.camera.position.y = THREE.MathUtils.damp(state.camera.position.y, targetY, 1.8, delta) + shakeY;
    state.camera.position.z = THREE.MathUtils.damp(state.camera.position.z, targetZ, 1.8, delta);
    // The lookAt leads the brain's lateral drift slightly — pursuit framing,
    // the camera chasing a mind in motion rather than panning a tripod.
    state.camera.lookAt(brainDriftX(time) * 0.35, 0.62, -1.2);

    // Idle attract-mode pitch: a ±2° sine composed AFTER the lookAt as a
    // pure local-X rotation, scaled by the idle blend — zero effect until
    // 30 s of no input, eased back out within ~0.6 s of any input.
    const idlePitch = Math.sin(time * IDLE_PITCH_FREQ) * IDLE_PITCH_AMPLITUDE * idleRef.current.blend;
    if (idlePitch !== 0) state.camera.rotateX(idlePitch);
  });

  return null;
}

export default function SuperbrainScene({ mode, activity, tier = 'high' }: SuperbrainSceneProps) {
  const activeBoost = mode === 'synthesize' ? 1 : mode === 'orchestrate' ? 0.78 : activity;
  const burstRef = useRef<BurstState>({ lastBurst: 0, intensity: 0 });
  const cameraPushRef = useRef<CameraPushState>({ value: 0 });
  const directivePendingRef = useRef(false);
  const uniforms = SCENE_UNIFORMS;
  
  const idleRef = useRef<IdleControllerState>({
    lastInputMs: Number.POSITIVE_INFINITY,
    progress: 0,
    blend: 0,
    yaw: 0,
    cascadeIndex: 0,
    nextCascadeAt: -1,
    wasIdle: false,
  });

  const waveRef = useRef({
    slot: 0,
    nextAuto: -1,
    random: createSeededRandom(0x5e4713a9),
    pending: [] as THREE.Vector3[],
  });

  // Approval hold: the supervised mind defers to its operator. Captured
  // breath is frozen, the organism turns amber, and the hold releases on the
  // operator's decision (approval-resolved) or when the conversation moves on.
  const holdRef = useRef({ active: false, breathAtHold: 0.5 });

  // Nervous system: a directive from the command bar surges the engine — an
  // immediate cognition burst plus a camera push impulse CameraDrift decays.
  // Burst / knowledge events additionally queue a thought-wave on the cortex,
  // anchored near the matching anatomical region when the event is labeled.
  useEffect(
    () =>
      subscribeCognition((event) => {
        if (event.type === 'approval-required') {
          const hold = holdRef.current;
          hold.active = true;
          hold.breathAtHold = uniforms.uBreath.value; // freeze mid-inhale
          // A slow, attentive dolly-in: the camera leans toward the held mind.
          cameraPushRef.current.value = Math.max(cameraPushRef.current.value, 0.8);
          return;
        }
        if (
          event.type === 'approval-resolved' ||
          event.type === 'directive' ||
          event.type === 'synthesis'
        ) {
          holdRef.current.active = false;
        }
        if (event.type === 'approval-resolved' && event.label === 'approved') {
          // The operator's decision executes: a thought-wave fires from the
          // frontal (planning) anchor. A rejection gets no wave — standing
          // down is the absence of one.
          const waves = waveRef.current;
          if (waves.pending.length < 3) {
            waves.pending.push(waveOriginForLabel('CAUSAL DECISION', waves.random));
          }
        }
        if (event.type === 'directive') {
          directivePendingRef.current = true;
          cameraPushRef.current.value = 1;
          return;
        }
        if (event.type !== 'burst' && event.type !== 'knowledge-acquired') return;
        const waves = waveRef.current;
        if (waves.pending.length >= 3) return;
        waves.pending.push(waveOriginForLabel(event.label, waves.random));
      }),
    [uniforms],
  );

  // Idle attract-mode input sensing: every user input stamps the controller;
  // the frame loop below converts "30 s with no input" into the idle blend.
  // The timestamp is set at MOUNT (not Infinity), so idle starts ONLY after
  // a full 30 s quiet period following mount — never during the e2e window.
  useEffect(() => {
    const idle = idleRef.current;
    idle.lastInputMs = performance.now();
    idle.progress = 0;
    idle.blend = 0;
    idle.wasIdle = false;
    idle.nextCascadeAt = -1;
    const reset = () => {
      idle.lastInputMs = performance.now();
    };
    const opts: AddEventListenerOptions = { passive: true };
    window.addEventListener('pointermove', reset, opts);
    window.addEventListener('pointerdown', reset, opts);
    window.addEventListener('keydown', reset, opts);
    window.addEventListener('wheel', reset, opts);
    return () => {
      window.removeEventListener('pointermove', reset);
      window.removeEventListener('pointerdown', reset);
      window.removeEventListener('keydown', reset);
      window.removeEventListener('wheel', reset);
      // Park the controller: Infinity means "cannot go idle" until remount.
      idle.lastInputMs = Number.POSITIVE_INFINITY;
      idle.progress = 0;
      idle.blend = 0;
      idle.wasIdle = false;
      idle.nextCascadeAt = -1;
    };
  }, []);

  useFrame((state, delta) => {
    const time = state.clock.elapsedTime;
    const current = burstRef.current;
    const hold = holdRef.current;

    // The hold blend eases in/out; while engaged the organism neither bursts,
    // free-associates, nor drifts into the idle attract mode.
    uniforms.uHold.value = THREE.MathUtils.damp(
      uniforms.uHold.value,
      hold.active ? 1 : 0,
      2.5,
      delta,
    );
    const holding = uniforms.uHold.value;
    if (hold.active) idleRef.current.lastInputMs = performance.now();

    if (holding < 0.5 &&
        (directivePendingRef.current || time - current.lastBurst > 8 + Math.sin(time * 0.13) * 2)) {
      directivePendingRef.current = false;
      current.lastBurst = time;
      current.intensity = 1;
      // The HUD reacts to the SAME pulse the 3D scene feels.
      publishCognition({ type: 'burst', intensity: 1, source: 'scene' });
    }
    current.intensity = THREE.MathUtils.damp(current.intensity, 0, 3.5, delta);
    // Decay the directive camera surge here (the ref is owned by this scope);
    // CameraDrift only reads it.
    cameraPushRef.current.value = THREE.MathUtils.damp(cameraPushRef.current.value, 0, 2, delta);

    /* ── shared sentience uniforms: one write per frame drives every layer ── */
    uniforms.uTime.value = time;

    // Asymmetric 0.1 Hz systole layered with slower swells at decreasing
    // amplitude — never a constant ~1 Hz pulse.
    const systole = Math.pow(0.5 + 0.5 * Math.sin(time * 0.628), 1.8);
    const swell = 0.5 + 0.5 * Math.sin(time * TAU * 0.043 + 1.7);
    const tide = 0.5 + 0.5 * Math.sin(time * TAU * 0.017 + 4.2);
    const breath = systole * 0.62 + swell * 0.26 + tide * 0.12;
    // The approval hold freezes the breath exactly where it was caught.
    uniforms.uBreath.value = THREE.MathUtils.lerp(breath, hold.breathAtHold, holding);
    uniforms.uRimGain.value = 1.4 * (0.85 + 0.3 * breath);   // ±15%
    uniforms.uSssScale.value = 0.9 * (0.8 + 0.4 * breath);   // ±20%
    uniforms.uBurst.value = current.intensity;

    // Virtual rose backlight BEHIND the brain (view space, ~opposite the
    // camera), slowly orbiting ±15° so the transmission cue wanders.
    uniforms.uBackLightDir.value
      .set(Math.sin(time * 0.07) * 0.27, 0.1 + Math.sin(time * 0.043) * 0.2, -1)
      .normalize();

    // Mode tint eases into the core glow (15% mix happens in the shader);
    // the approval hold pulls it toward YELLOW-zone amber on top.
    uniforms.uModeTint.value.lerp(
      MODE_EMISSIVE[mode] ?? MODE_EMISSIVE.observe,
      Math.min(1, delta * 2.5),
    );
    if (holding > 0.01) {
      uniforms.uModeTint.value.lerp(HOLD_TINT, Math.min(1, delta * 2.5) * holding);
    }

    /* ── thought-wave scheduler: Poisson-ish idle waves + event waves ── */
    const waves = waveRef.current;
    if (waves.nextAuto < 0) waves.nextAuto = time + 2 + waves.random() * 3;
    if (holding < 0.5 && time >= waves.nextAuto) {
      waves.pending.push(randomWaveOrigin(waves.random));
      waves.nextAuto = time + 3 + waves.random() * 5;
    }

    /* ── idle attract-mode: autonomous cognition after 30 s of no input ── */
    const idle = idleRef.current;
    const idleForS = (performance.now() - idle.lastInputMs) / 1000;
    const isIdle = idleForS >= IDLE_DELAY_S && !isTextEntryFocused();
    idle.progress = isIdle
      ? Math.min(1, idle.progress + delta / IDLE_EASE_IN_S)
      : Math.max(0, idle.progress - delta / IDLE_EASE_OUT_S);
    // smoothstep — CameraDrift multiplies this into its yaw/pitch math.
    idle.blend = idle.progress * idle.progress * (3 - 2 * idle.progress);
    idle.yaw += IDLE_YAW_RATE * idle.blend * delta;

    if (isIdle) {
      if (!idle.wasIdle || idle.nextCascadeAt < 0) {
        // Idle just began — schedule the first cascade 6–9 s out (seeded).
        idle.nextCascadeAt = time + 6 + waves.random() * 3;
      } else if (time >= idle.nextCascadeAt) {
        idle.nextCascadeAt = time + 6 + waves.random() * 3;
        // Thought cascade: fire a cortex wave NOW from a seeded rotating
        // anatomical anchor (never unseeded randomness — the pending queue
        // drains this same frame), and log the unprompted inference.
        idle.cascadeIndex = (idle.cascadeIndex + 1) % WAVE_REGION_ANCHORS.length;
        const anchor = WAVE_REGION_ANCHORS[idle.cascadeIndex].origin;
        if (waves.pending.length < 3) {
          waves.pending.push(
            new THREE.Vector3(
              anchor.x + (waves.random() - 0.5) * 0.1,
              anchor.y + (waves.random() - 0.5) * 0.1,
              anchor.z + (waves.random() - 0.5) * 0.1,
            ),
          );
        }
        publishCognition({
          type: 'synthesis',
          label: 'autonomous reflection',
          detail: 'unprompted inference cycle',
          intensity: 0.7,
          source: 'idle',
        });
      }
    }
    idle.wasIdle = isIdle;

    while (waves.pending.length > 0) {
      const origin = waves.pending.shift()!;
      uniforms.uWaveOrigins.value[waves.slot].copy(origin);
      uniforms.uWaveTimes.value[waves.slot] = time;
      waves.slot = (waves.slot + 1) % 3;
    }
  });

  return (
    <>
      <CameraDrift activity={activeBoost} burst={burstRef} push={cameraPushRef} idleRef={idleRef} />

      {/* Cinematic deep space background */}
      {/* The sky serves the VOYAGE: the operator's knowledge field flying
          past the camera IS the forward motion of the thesis. The optional
          photographic dome sits far behind it for depth — it may add to the
          voyage, never replace it. (Dome skipped on low tier: the
          full-screen fbm pass is the budget, and the brain is the show.) */}
      {SKY_MODE === 'layered' && tier !== 'low' && (
        <KnowledgeHorizon activity={activeBoost} />
      )}
      <CosmicBackground tier={tier} />

      {/* The recall stream: distant glints are REAL trails from the pheromone
          map (strength = core brightness, walks = cage size, freshness =
          spin, quarantine = red stain); each absorb fires a label-anchored
          cortical burst at the matching anatomical region. Dormant when no
          trails are known — nothing pretends to arrive. */}
      {tier !== 'low' && <CognitiveGrasp activity={activeBoost} />}

      {/* Post-processing lives ONLY in <PostFX/> (mounted below). A second
          EffectComposer here used to render the entire scene twice per frame
          with its bloom output overwritten by PostFX — pure GPU waste on a
          machine sharing memory bandwidth with a local LLM. */}

      {/* The cortex shader is self-lit and ignores scene lights — this rig
          exists for the OTHER scene objects (accretion core). */}
      <color attach="background" args={['#000000']} />
      <ambientLight intensity={0.14} color="#241145" />
      <directionalLight position={[-6, 7, 1]} intensity={0.41} color="#8fa8ff" />
      <directionalLight position={[7, -2, 0]} intensity={0.42} color="#bcd0ff" />
      <directionalLight position={[0, -3, -8]} intensity={0.39} color="#795cff" />
      <pointLight position={[-4.5, 2.8, -1]} intensity={1.0} distance={10} color="#5e8dff" />
      <pointLight position={[3.5, 4.0, 3]} intensity={0.7} distance={12} color="#c8a8ff" />
      <pointLight position={[4.2, -2.6, -5]} intensity={0.6 + activeBoost * 0.6} distance={8} color="#ff5c9a" />

      <Float speed={0.46 + activeBoost * 0.18} rotationIntensity={0.025} floatIntensity={0.1}>
        <BrainModel activity={activeBoost} mode={mode} burst={burstRef} uniforms={uniforms} tier={tier} />
        <AccretionCore activity={activeBoost} burst={burstRef} />
      </Float>
      
      {/* Kept OUTSIDE Float so the bottom wires stay rigidly attached to the static UI. 
          The top wires plug deep inside the brain, so they just slide 0.1 units inside the brain as it bobs. */}
      <NervousSystem burst={burstRef} uniforms={uniforms} />

      <PostFX />
    </>
  );
}

useGLTF.preload('/models/brain.glb');
