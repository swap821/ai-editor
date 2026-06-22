// frontend/src/superbrain/lib/spinePointField.ts
import * as THREE from 'three';
import type { PointFieldData } from './pointFieldSampler';
import {
  SEGMENT_BOTTOM_Y,
  CORD_Z,
  SEGMENT_COUNT,
  SEGMENT_ANCHORS,
} from './spineAnatomy';

// CORD_TOP_Y is the brainstem-exit Y. Raised to -0.42 so the cord's top overlaps
// the brain's brainstem stub — the spine visibly comes OUT of the brain (one body),
// no gap. Exported so tests and callers can match without re-defining it.
export const CORD_TOP_Y = -0.42;

// Inline helpers — avoid THREE.MathUtils which may not resolve in jsdom
function clamp(v: number, lo: number, hi: number): number {
  return v < lo ? lo : v > hi ? hi : v;
}
function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}
function smoothstep(edge0: number, edge1: number, x: number): number {
  const t = clamp((x - edge0) / (edge1 - edge0), 0, 1);
  return t * t * (3 - 2 * t);
}

// ── Body-axis constants (exported so the brain side can match) ────────────────
/** World-Y that maps to aBand = 0 (root base). */
export const BODY_AXIS_MIN = -2.85;
/** World-Y that maps to aBand = 1 (brain top). */
export const BODY_AXIS_MAX = 0.7;

// ── Internal region constants ─────────────────────────────────────────────────
const TAU = Math.PI * 2;
const ROOT_FILAMENTS = 11; // poster phase 2: a WIDE luminous root splay (was 6)
const INTAKE_RING_COUNT = 5; // concentric "you speak here" base ripple rings

// ── Project-standard mulberry32 PRNG (byte-identical to pointFieldSampler.ts) ─
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

// ── Color: the BRAIN's own region palette ──────────────────────────────────────
// The spine is one body with the brain — its flesh extruded down the cord — so it
// wears the brain's exact region colours (same hexes baked into the cortex, in the
// same linear space via THREE.Color). The cord is BORN from the cerebellum/stem
// (deep violet) so the top stays violet for continuity, then the full multicolour
// palette spreads down toward the roots.
const STEM_VIOLET = new THREE.Color('#6a35ff'); // cerebellum / ventral stem — the join
const BRAIN_PALETTE: ReadonlyArray<THREE.Color> = [
  new THREE.Color('#6a35ff'), // cerebellum violet (weighted: appears twice)
  new THREE.Color('#9b3bff'), // occipital violet
  new THREE.Color('#e62bd4'), // occipital magenta
  new THREE.Color('#19d4f0'), // parietal cyan
  new THREE.Color('#36f07a'), // temporal green
  new THREE.Color('#a8e62b'), // temporal lime
  new THREE.Color('#ff7a26'), // frontal burnt orange
  new THREE.Color('#ff3b28'), // frontal red
];

/**
 * Colour a spine point from the BRAIN palette. bf ∈ [0,1] (0 = root base, 1 =
 * brainstem join); r ∈ [0,1] random pick. Near the join (bf>0.8) it stays the
 * stem violet so the cord visibly continues out of the brain; lower down it
 * takes the full brain palette so the organism reads as one multicoloured body.
 */
function paletteColor(bf: number, r: number, out: [number, number, number]): void {
  const join = smoothstep(0.78, 0.98, clamp(bf, 0, 1)); // 0 low → 1 at the brain join
  const pick = BRAIN_PALETTE[Math.min(BRAIN_PALETTE.length - 1, Math.floor(r * BRAIN_PALETTE.length))];
  out[0] = lerp(pick.r, STEM_VIOLET.r, join);
  out[1] = lerp(pick.g, STEM_VIOLET.g, join);
  out[2] = lerp(pick.b, STEM_VIOLET.b, join);
}

// ── Main generator ────────────────────────────────────────────────────────────
/**
 * Build the spine + roots as a pure point-field — deterministic given
 * (count, seed). Returns a PointFieldData in the same shape as samplePointField.
 */
export function buildSpinePoints(count: number, seed: number): PointFieldData {
  // Allocate all attribute arrays
  const positions = new Float32Array(count * 3);
  const colors    = new Float32Array(count * 3);
  const normals   = new Float32Array(count * 3);
  const sizes     = new Float32Array(count);
  const phases    = new Float32Array(count);
  const speeds    = new Float32Array(count);
  const scatter   = new Float32Array(count * 3);
  const births    = new Float32Array(count);
  const bands     = new Float32Array(count);

  const random = createSeededRandom(seed);

  // Region budgets (ringN added for the poster's brainstem-intake base ripple)
  const cordN  = Math.round(count * 0.38);
  const vertN  = Math.round(count * 0.12);
  const ringN  = Math.round(count * 0.10);
  const rootN  = count - cordN - vertN - ringN;

  const col: [number, number, number] = [0, 0, 0];
  const dir = new THREE.Vector3();

  let wi = 0; // write index

  // ── 1. CORD TRUNK ─────────────────────────────────────────────────────────
  for (let i = 0; i < cordN; i++, wi++) {
    const f    = random();                                    // 0=top, 1=bottom
    const y    = lerp(CORD_TOP_Y, SEGMENT_BOTTOM_Y, f);
    const cz   = CORD_Z + Math.sin(f * Math.PI) * 0.04;     // gentle forward bow
    const rad  = lerp(0.16, 0.09, f);
    const ang  = random() * TAU;
    const rr   = rad * Math.sqrt(random());                  // uniform disc
    const x    = Math.cos(ang) * rr;
    const pz   = cz + Math.sin(ang) * rr;

    positions[wi * 3]     = x;
    positions[wi * 3 + 1] = y;
    positions[wi * 3 + 2] = pz;

    normals[wi * 3]     = Math.cos(ang);
    normals[wi * 3 + 1] = 0;
    normals[wi * 3 + 2] = Math.sin(ang);

    const bf = clamp(
      (y - SEGMENT_BOTTOM_Y) / (CORD_TOP_Y - SEGMENT_BOTTOM_Y), 0, 1,
    );
    paletteColor(bf, random(), col);
    colors[wi * 3]     = col[0];
    colors[wi * 3 + 1] = col[1];
    colors[wi * 3 + 2] = col[2];

    sizes[wi]  = 0.6 + random() * 0.8;
    phases[wi] = random() * TAU;
    speeds[wi] = 0.6 + random() * 0.8;
    births[wi] = random();

    dir.set(random() * 2 - 1, random() * 2 - 1, random() * 2 - 1);
    if (dir.lengthSq() < 1e-6) dir.set(0, 1, 0);
    dir.normalize();
    scatter[wi * 3]     = dir.x;
    scatter[wi * 3 + 1] = dir.y;
    scatter[wi * 3 + 2] = dir.z;

    bands[wi] = clamp(
      (y - BODY_AXIS_MIN) / (BODY_AXIS_MAX - BODY_AXIS_MIN), 0, 1,
    );
  }

  // ── 2. VERTEBRAE RINGS ────────────────────────────────────────────────────
  for (let i = 0; i < vertN; i++, wi++) {
    const aIdx = Math.floor(random() * SEGMENT_COUNT);
    const a    = SEGMENT_ANCHORS[aIdx];
    const vr   = 0.20 + random() * 0.03;
    const ang  = random() * TAU;
    const x    = a.x + Math.cos(ang) * vr;
    const y    = a.y + (random() - 0.5) * 0.05;
    const pz   = a.z + Math.sin(ang) * vr;

    positions[wi * 3]     = x;
    positions[wi * 3 + 1] = y;
    positions[wi * 3 + 2] = pz;

    normals[wi * 3]     = Math.cos(ang);
    normals[wi * 3 + 1] = 0;
    normals[wi * 3 + 2] = Math.sin(ang);

    const bf = clamp(
      (y - SEGMENT_BOTTOM_Y) / (CORD_TOP_Y - SEGMENT_BOTTOM_Y), 0, 1,
    );
    paletteColor(bf, random(), col);
    colors[wi * 3]     = col[0];
    colors[wi * 3 + 1] = col[1];
    colors[wi * 3 + 2] = col[2];

    sizes[wi]  = 0.6 + random() * 0.8;
    phases[wi] = random() * TAU;
    speeds[wi] = 0.6 + random() * 0.8;
    births[wi] = random();

    dir.set(random() * 2 - 1, random() * 2 - 1, random() * 2 - 1);
    if (dir.lengthSq() < 1e-6) dir.set(0, 1, 0);
    dir.normalize();
    scatter[wi * 3]     = dir.x;
    scatter[wi * 3 + 1] = dir.y;
    scatter[wi * 3 + 2] = dir.z;

    bands[wi] = clamp(
      (y - BODY_AXIS_MIN) / (BODY_AXIS_MAX - BODY_AXIS_MIN), 0, 1,
    );
  }

  // ── 2b. INTAKE RINGS (poster phase 2 — "you speak here") ──────────────────
  // Concentric point rings on the horizontal plane at the base: the brainstem
  // intake ripple where the user's words enter. Flat disc centered on the cord
  // axis so it reads as ground ripples from every orbit angle. In the brain's
  // own palette at the root-base end (bf≈0, full multicolour — NOT the violet join).
  const ringBaseY = SEGMENT_BOTTOM_Y - 0.5;
  for (let i = 0; i < ringN; i++, wi++) {
    const ringIdx = Math.floor(random() * INTAKE_RING_COUNT);
    const ringR = 0.28 + (ringIdx / (INTAKE_RING_COUNT - 1)) * 1.05; // 0.28 → 1.33
    const ang = random() * TAU;
    const rr = ringR + (random() - 0.5) * 0.025; // soft band, not a hard wire
    const x = Math.cos(ang) * rr;
    const y = ringBaseY + (random() - 0.5) * 0.02;
    const pz = CORD_Z + Math.sin(ang) * rr;

    positions[wi * 3]     = x;
    positions[wi * 3 + 1] = y;
    positions[wi * 3 + 2] = pz;

    // disc faces up so the breathe/flow normal displacement reads as a ripple
    normals[wi * 3]     = 0;
    normals[wi * 3 + 1] = 1;
    normals[wi * 3 + 2] = 0;

    paletteColor(0.05, random(), col);
    colors[wi * 3]     = col[0];
    colors[wi * 3 + 1] = col[1];
    colors[wi * 3 + 2] = col[2];

    sizes[wi]  = 0.6 + random() * 0.6; // keep within the [0.6,1.4] field-size bound
    phases[wi] = random() * TAU;
    speeds[wi] = 0.6 + random() * 0.8;
    births[wi] = random();

    dir.set(random() * 2 - 1, random() * 2 - 1, random() * 2 - 1);
    if (dir.lengthSq() < 1e-6) dir.set(0, 1, 0);
    dir.normalize();
    scatter[wi * 3]     = dir.x;
    scatter[wi * 3 + 1] = dir.y;
    scatter[wi * 3 + 2] = dir.z;

    bands[wi] = clamp((y - BODY_AXIS_MIN) / (BODY_AXIS_MAX - BODY_AXIS_MIN), 0, 1);
  }

  // ── 3. ROOTS / CAUDA SPRAY ───────────────────────────────────────────────
  for (let i = 0; i < rootN; i++, wi++) {
    const side     = random() < 0.5 ? -1 : 1;
    const fi       = Math.floor(random() * ROOT_FILAMENTS);
    const fiF      = fi / (ROOT_FILAMENTS - 1);
    // attach Y: higher fi (outer filament) attaches lower
    const baseY    = lerp(-1.9, SEGMENT_BOTTOM_Y, fiF);
    const t        = random();                               // 0=attach, 1=tip
    const angleOut = lerp(0.2, 1.4, fiF);                   // wider splay (poster's wide luminous roots)
    const len      = 1.1 + fi * 0.16;

    let x  = side * Math.sin(angleOut) * t * len;
    let y  = baseY - Math.cos(angleOut) * t * len * 0.55 - t * 0.25;
    let pz = CORD_Z + Math.sin(t * Math.PI) * 0.06;

    // tiny tube thickness jitter
    x  += (random() - 0.5) * 0.03;
    y  += (random() - 0.5) * 0.03;
    pz += (random() - 0.5) * 0.03;

    // Clamp y so roots never violate the test bound (SEGMENT_BOTTOM_Y - 0.6)
    const Y_FLOOR = SEGMENT_BOTTOM_Y - 0.6;
    if (y < Y_FLOOR) y = Y_FLOOR;

    positions[wi * 3]     = x;
    positions[wi * 3 + 1] = y;
    positions[wi * 3 + 2] = pz;

    // approx outward normal; normalise; guard zero-length
    const nx = side * Math.sin(angleOut);
    const ny = -0.3;
    const nz = 0.0;
    const nLen = Math.sqrt(nx * nx + ny * ny + nz * nz);
    if (nLen > 1e-6) {
      normals[wi * 3]     = nx / nLen;
      normals[wi * 3 + 1] = ny / nLen;
      normals[wi * 3 + 2] = nz / nLen;
    } else {
      normals[wi * 3]     = 0;
      normals[wi * 3 + 1] = 1;
      normals[wi * 3 + 2] = 0;
    }

    const bf = clamp(
      (y - SEGMENT_BOTTOM_Y) / (CORD_TOP_Y - SEGMENT_BOTTOM_Y), 0, 1,
    );
    paletteColor(bf, random(), col);
    colors[wi * 3]     = col[0];
    colors[wi * 3 + 1] = col[1];
    colors[wi * 3 + 2] = col[2];

    sizes[wi]  = 0.6 + random() * 0.8;
    phases[wi] = random() * TAU;
    speeds[wi] = 0.6 + random() * 0.8;
    births[wi] = random();

    dir.set(random() * 2 - 1, random() * 2 - 1, random() * 2 - 1);
    if (dir.lengthSq() < 1e-6) dir.set(0, 1, 0);
    dir.normalize();
    scatter[wi * 3]     = dir.x;
    scatter[wi * 3 + 1] = dir.y;
    scatter[wi * 3 + 2] = dir.z;

    bands[wi] = clamp(
      (y - BODY_AXIS_MIN) / (BODY_AXIS_MAX - BODY_AXIS_MIN), 0, 1,
    );
  }

  return { positions, colors, normals, sizes, phases, speeds, scatter, births, bands, count };
}
