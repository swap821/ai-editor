import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { useMemo, useRef, useEffect } from 'react';
import { useFrame } from '@react-three/fiber';
import { createSeededRandom } from '@/lib/seededRandom';
import { makeBrainMaterial } from '@/lib/brainMaterial';
import { subscribeCognition } from '@/lib/cognitionBus';
import type { QualityTier } from '@/components/QualityTierProvider';
import type { BurstRef, CognitionUniforms } from './SuperbrainScene.LEGACY';
import {
  CORD_Z,
  SEGMENT_COUNT,
  SEGMENT_ANCHORS,
} from '@/lib/spineAnatomy';
import VertebraeRepoMapOverlay from './VertebraeRepoMapOverlay';

// ============================================================================
// THE LIVING NERVOUS SYSTEM — MESH, wearing the BRAIN'S EXACT material
//
// Operator's key insight: the loved aesthetic IS the brain's MESH SHADER (the
// organic 3D-Voronoi neural web + region/palette vertex-colours + luminance-
// ladder emission + fresnel glow, pulsing on uTime/uHold/uArrival/uBreath).
// The old cord/vertebrae looked DIFFERENT because they were a SEPARATE PARTICLE
// (THREE.Points) system with its own shader.
//
// THE FIX: rebuild the cord + vertebrae + roots + cauda spray as MESH geometry
// (TubeGeometry / TorusGeometry) and apply the BRAIN'S EXACT material to ALL of
// it via the shared makeBrainMaterial({ bodyMode: 'nerve', ... }) factory — so
// the nervous system reads as ONE continuous organism with the brain: the
// brain's living flesh extending downward.
//
// THE CONTINUITY CONTRACT (the single load-bearing decision): every nerve mesh
// is authored directly in the SAME brain-group-local frame the cortex occupies
// (cord spine y ≈ -0.60…-3.10; the brain occupies y ≈ -0.222…+0.633). The nerve
// group is a SIBLING of the brain group at the SAME transform/sway. We bake an
// `objectPos` attribute = the raw group-local vertex position and the brain's
// vertex shader samples `vLocalPos = objectPos * 2.0` at `scale = 0.6` — the
// brain's EXACT lines — so the Voronoi cell grid is ONE unbroken 3D field. The
// web literally flows out of the brainstem into the cord because both meshes
// sample the SAME lattice; they are not "matched", they are the same shader.
//
// Geometry merges into FOUR draw calls (cord+bulge / vertebrae / roots / spray),
// all sharing ONE nerve material instance.
// ============================================================================

// ── BRAIN-PALETTE ARC RAMP (keep the brain's vivid hues EXACTLY) ─────────────
// The body is the cortex palette read head→tail. The brain is born violet at
// the stem (cerebellum #6a35ff), so the cord starts there and the web's colours
// sweep through the cortex palette downward. Every hue below is a brain region
// colour (SuperbrainScene REGION_* constants) — no new hues invented.
const ARC_RAMP: ReadonlyArray<{ at: number; color: THREE.Color }> = [
  { at: 0.0, color: new THREE.Color('#6a35ff') }, // brainstem — cerebellum deep violet (where the cord is born; matches the brain's ventral/stem colour → no seam hue-jump)
  { at: 0.18, color: new THREE.Color('#19d4f0') }, // upper cord (cervical) — parietal crown cyan flowing down
  { at: 0.45, color: new THREE.Color('#36f07a') }, // mid cord (thoracic) — temporal green
  { at: 0.62, color: new THREE.Color('#a8e62b') }, // mid-lower — temporal lime
  { at: 0.8, color: new THREE.Color('#9b3bff') }, // lower cord (lumbar) — occipital violet
  { at: 0.92, color: new THREE.Color('#ff7a26') }, // spray core — frontal-edge burnt orange
  { at: 1.0, color: new THREE.Color('#e62bd4') }, // spray tips — occipital-hot magenta flourish
];

/** Luminance floor (mirrors SuperbrainScene REGION_LUMINANCE_FLOOR) so the cord
 *  never drops to black where two ramp stops blend dark. */
const NERVE_LUMINANCE_FLOOR = 0.12;

// ── FLOW (the downward nerve impulse; advanced module-side so the brain shader
//    / SuperbrainScene stay untouched — additive, reversible) ────────────────
const FLOW_PERIOD_S = 3.5;   // seconds for one impulse to sweep brain→spray
const FLOW_BURST_KICK = 2.4; // extra flow advance (body-lengths) on a cognition burst — a command races down the cord
const INTAKE_FLOW_PERIOD_S = 0.86; // a short brainstem→cortex packet, visibly faster than the full reply descent

/** Module-level uniform leaves (the bundle mounts once); frame-loop-mutable.
 *  uFlow lives here so the brain shader / SuperbrainScene stay UNTOUCHED. */
const NERVE_FLOW_UNIFORM = { value: 0 };
const NERVE_REDUCEMOTION_UNIFORM = { value: 0 };
// Flow-band GAIN: 0 at REST (the cord glows steady — no per-second traveling
// strobe), rising only on real cognition activity (a burst) so the impulse
// visibly races down the spine when the being is actually thinking, then decays.
const NERVE_FLOWGAIN_UNIFORM = { value: 0 };
const NERVE_INTAKE_UNIFORM = { value: 0 };
const NERVE_INTAKEGAIN_UNIFORM = { value: 0 };
const NERVE_REPLYWARM_UNIFORM = { value: 0 };

// ── GROWTH (the spine SLOWLY GENERATES downward, vertebra by vertebra) ────────
// uGrow sweeps 0→1 in body-arc; each mesh part is born (inflates from its birth
// point + lights up) as the front passes its arc. The brain forms first (short
// delay), then the cord descends from the brainstem and each vertebra blooms.
const GROW_DELAY_S = 1.1;     // let the brain coalesce/ignite before the spine starts
const GROW_DURATION_S = 6.5;  // slow, cinematic full-spine generation (brainstem → spray)
const NERVE_GROW_UNIFORM = { value: 0 }; // 0 = unborn (spine hidden); animates to 1 = fully grown
let nerveGrowElapsed = 0;     // module-level clock for the one-shot birth (survives re-render)

// ============================================================================
// ANATOMY TUNABLES — the operator tunes the being's central nervous system
// live in the browser by editing these. Coordinate frame: group-local (the
// parent group sways with the brain). +Y is up; the cord descends in -Y.
// ============================================================================

// --- The spinal CORD (central descending trunk) ---
// ANCHOR: the cord TOP emerges from the brain GLB's brainstem-stub bottom,
// seamless + continuous (stub-bottom ≈ -0.670 in nervous-local; nudged +0.02 to
// overlap INTO the stem so the float's low swing never opens a gap).
const CORD_TOP_Y = -0.60;        // cord-born Y — emerges from the brainstem-stub bottom
const CORD_STEM_EXIT_Y = -0.95;  // first descending control point — the stem-to-cord transition zone
const CORD_BOTTOM_Y = -3.1;      // conus-tip Y — bottom of the cord (spray origin)
const CORD_SIGMA = 0.18;         // cord trunk RADIUS (world-u) — a substantial, ~uniform thick tube
const CORD_SIGMA_TOP_EASE = 1.18;// at the very top (arc<0.16) ease the radius to this × CORD_SIGMA so it tucks INTO the brainstem stub instead of ballooning at the seam
const CORD_RADIAL_SEGMENTS = 32; // smooth round tube
const CORD_TUBE_SEGMENTS = 96;   // arc subdivisions along the cord (smoothness)
const STEM_TOP_R = 0.42;         // brainstem girth at the TOP, buried up inside the brain's basal cavity — wide enough to FILL the opening so brain→brainstem reads as one mass (no dark hollow)
const STEM_TOP_RISE = 0.55;      // how far ABOVE CORD_TOP_Y the brainstem reaches UP into the brain (so its wide top is hidden inside the cortex and it visibly emerges FROM the opening)
const STEM_RADIAL_SEGMENTS = 32;
const STEM_TUBE_SEGMENTS = 80;

// --- VERTEBRAL SEGMENTS (addressable anchors — later phase seats a 3D tab at each) ---
const VERTEBRA_RINGS = true;     // draw a chunky torus band at each anchor (the "vertebra" / tab-seat marker)
const VERTEBRA_RING_TOP_R = 0.19;    // torus MAJOR radius at the top anchor (just outside cord)
const VERTEBRA_RING_BOTTOM_R = 0.23; // torus MAJOR radius at the bottom anchor (grows downward)
const VERTEBRA_RING_TUBE = 0.045;    // torus MINOR (tube) radius — the chunky segment girth, distinctly thicker than the web detail so vertebrae stay crisp
const VERTEBRA_RADIAL_SEGMENTS = 20; // torus minor resolution (round)
const VERTEBRA_TUBULAR_SEGMENTS = 64;// torus major resolution (smooth ring)
const VERTEBRA_GIRTH: number = 2;   // # of stacked rings per vertebra (a short vertical band of girth, not a single flat hoop)
const VERTEBRA_GIRTH_SPACING = 0.028;// vertical spacing (world-u) between the stacked rings of one vertebra
const SPINOUS_LEN_TOP = 0.22;
const SPINOUS_LEN_BOT = 0.30;
const SPINOUS_R = 0.025;
const TRANSVERSE_LEN_TOP = 0.20;
const TRANSVERSE_LEN_BOT = 0.28;
const TRANSVERSE_R = 0.018;
const DISC_TUBE = 0.018;
const DISC_R_SCALE = 1.12;
const PROC_TUBE_SEGMENTS = 14;
const PROC_RADIAL_SEGMENTS = 8;

// --- Bilateral NERVE ROOTS (paired, fanning longer/wider toward the base) ---
const ROOT_PAIRS_PER_SEGMENT: number = 2; // root PAIRS (left+right) per vertebral anchor
const ROOT_LENGTH_TOP = 0.45;        // root reach at the top segment (short cervical)
const ROOT_LENGTH_GROWTH = 1.9;      // root reach at the bottom segment (long lumbar); growth uses f*f for an accelerating fan
const ROOT_SPREAD_BASE = 0.30;       // lateral (outward) reach at the top segment
const ROOT_SPREAD_GROWTH = 1.4;      // lateral reach at the bottom segment (the silhouette widens downward)
const ROOT_DROOP_TOP = 0.20;         // downward sag of a root at the top (near-horizontal cervical)
const ROOT_DROOP_GROWTH = 1.6;       // downward sag at the bottom (the weeping-willow hang)
const ROOT_RADIUS_TOP = 0.018;       // root tube RADIUS at the top segment (thin thread)
const ROOT_RADIUS_BOTTOM = 0.05;     // root tube RADIUS at the bottom segment (fuller)
const ROOT_FLARE = 0.7;              // radius gain toward the weeping tip: r(t)=base*(0.6+ROOT_FLARE*t)
const ROOT_RADIAL_SEGMENTS = 12;     // roots are thin + numerous → low radial count (still reads round)
const ROOT_TUBE_SEGMENTS = 28;       // arc subdivisions along a root

// --- Cauda-equina SPRAY (the terminal downward willow flourish) ---
const SPRAY_COUNT: number = 16;      // # of strands fanned across the spray
const SPRAY_FAN_WIDTH = 1.05;        // half-width the spray fans to at its tips
const SPRAY_LENGTH_CENTER = 1.4;     // how far the CENTER spray fibre hangs below the conus (longest)
const SPRAY_LENGTH_EDGE = 1.0;       // how far the OUTER spray fibres hang (shorter → teardrop, not broom)
const SPRAY_RADIUS_TOP = 0.04;       // spray tube RADIUS at the conus (the willow's neck)
const SPRAY_RADIUS_TIP = 0.03;       // spray tube RADIUS at the tips (softest, broadest fan)
const SPRAY_RADIAL_SEGMENTS = 12;    // spray is thin → low radial count
const SPRAY_TUBE_SEGMENTS = 48;      // arc subdivisions along a spray filament

// ── ARC-RAMP COLOUR SAMPLER (brain palette, region down the body arc) ────────
const _tmpA = new THREE.Color();
const _tmpB = new THREE.Color();
const _hsl = { h: 0, s: 0, l: 0 };
function arcColor(
  random: () => number,
  arc: number,
  jitterHue = 0.06,
  target = new THREE.Color()
): THREE.Color {
  const a = THREE.MathUtils.clamp(arc, 0, 1);
  let lo = ARC_RAMP[0];
  let hi = ARC_RAMP[ARC_RAMP.length - 1];
  for (let k = 0; k < ARC_RAMP.length - 1; k++) {
    if (a >= ARC_RAMP[k].at && a <= ARC_RAMP[k + 1].at) {
      lo = ARC_RAMP[k];
      hi = ARC_RAMP[k + 1];
      break;
    }
  }
  const span = Math.max(hi.at - lo.at, 1e-4);
  const w = THREE.MathUtils.smoothstep((a - lo.at) / span, 0, 1);
  target.copy(_tmpA.copy(lo.color).lerp(_tmpB.copy(hi.color), w));
  // Small seeded per-vertex hue jitter so boundaries are organic, not banded.
  if (jitterHue > 0) {
    target.getHSL(_hsl);
    target.setHSL(
      (_hsl.h + (random() - 0.5) * jitterHue + 1) % 1,
      THREE.MathUtils.clamp(_hsl.s + (random() - 0.5) * 0.08, 0, 1),
      THREE.MathUtils.clamp(_hsl.l + (random() - 0.5) * 0.06, 0, 1)
    );
  }
  // Luminance floor — keep the dark ramp blends off pure black.
  const lum = target.r * 0.2126 + target.g * 0.7152 + target.b * 0.0722;
  if (lum > 1e-4 && lum < NERVE_LUMINANCE_FLOOR) {
    target.multiplyScalar(NERVE_LUMINANCE_FLOOR / lum);
  } else if (lum <= 1e-4) {
    target.copy(ARC_RAMP[0].color);
  }
  return target;
}

/**
 * Bake the nerve attributes onto a freshly-built geometry IN PLACE:
 *   • `objectPos` (vec3) = the raw group-local vertex position (continuity
 *      contract — the brain shader reads vLocalPos = objectPos * 2.0).
 *   • `color` (vec3) = the brain-palette arc-ramp colour for this vertex.
 *   • `aArc` (float) = position along the body 0..1 (drives the flow band).
 * `arcFn(localY, vertexIndex)` maps a vertex to its body-arc; for tubes built
 * along a descending curve we derive arc from Y, for vertebrae/roots we pass a
 * constant segment arc, and for the spray we span the strand's own length.
 */
function bakeNerveAttributes(
  geo: THREE.BufferGeometry,
  random: () => number,
  arcAt: (vx: number, vy: number, vz: number, i: number) => number,
  hueJitter = 0.04
) {
  const pos = geo.getAttribute('position');
  const count = pos.count;
  const objectPos = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const arcs = new Float32Array(count);
  const c = new THREE.Color();
  for (let i = 0; i < count; i++) {
    const x = pos.getX(i);
    const y = pos.getY(i);
    const z = pos.getZ(i);
    // objectPos === the vertex position in the shared brain-group-local frame.
    objectPos[i * 3] = x;
    objectPos[i * 3 + 1] = y;
    objectPos[i * 3 + 2] = z;
    const arc = THREE.MathUtils.clamp(arcAt(x, y, z, i), 0, 1);
    arcs[i] = arc;
    arcColor(random, arc, hueJitter, c);
    colors[i * 3] = c.r;
    colors[i * 3 + 1] = c.g;
    colors[i * 3 + 2] = c.b;
  }
  geo.setAttribute('objectPos', new THREE.BufferAttribute(objectPos, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geo.setAttribute('aArc', new THREE.BufferAttribute(arcs, 1));
}

/** A radius-varying tube: TubeGeometry sweeps a CONSTANT radius, so we build it
 *  at radius 1 then scale each ring's cross-section by `radiusAt(t)` in-place.
 *  CatmullRom over the control points; `closed=false`, capped only where noted.
 *  Reproduces the cord/root/spray taper profiles exactly. */
function makeTaperedTube(
  points: THREE.Vector3[],
  tubularSegments: number,
  radialSegments: number,
  radiusAt: (t: number) => number,
  // GROWTH birth point each vertex collapses to before it is "born":
  //   'centerline' → its own ring centre (the tube materialises IN PLACE, thin→
  //                  full, downward) — used for the cord.
  //   Vector3      → a single origin (roots grow OUT from their cord attachment;
  //                  spray grows OUT from the conus).
  birthFrom: 'centerline' | THREE.Vector3 = 'centerline'
): THREE.TubeGeometry {
  const curve = new THREE.CatmullRomCurve3(points);
  const geo = new THREE.TubeGeometry(curve, tubularSegments, 1, radialSegments, false);
  const pos = geo.getAttribute('position') as THREE.BufferAttribute;
  const ringVerts = radialSegments + 1; // TubeGeometry emits (radial+1) verts per ring, (tubular+1) rings
  const birth = new Float32Array(pos.count * 3);
  // TubeGeometry places ring i at curve.getPoint(i/tubular) (uniform-t, NOT
  // arc-length) with a unit-circle cross-section, so |vert - center| == 1.
  // Scaling that offset by radiusAt(t) sets the ring radius — must use the SAME
  // getPoint(t) the geometry used or the offset won't be a clean unit vector.
  const center = new THREE.Vector3();
  const vert = new THREE.Vector3();
  const off = new THREE.Vector3();
  for (let i = 0; i <= tubularSegments; i++) {
    const t = tubularSegments === 0 ? 0 : i / tubularSegments;
    curve.getPoint(t, center);
    const r = radiusAt(t);
    for (let j = 0; j < ringVerts; j++) {
      const idx = i * ringVerts + j;
      vert.fromBufferAttribute(pos, idx);
      off.subVectors(vert, center).multiplyScalar(r);
      pos.setXYZ(idx, center.x + off.x, center.y + off.y, center.z + off.z);
      if (birthFrom === 'centerline') {
        birth[idx * 3] = center.x;
        birth[idx * 3 + 1] = center.y;
        birth[idx * 3 + 2] = center.z;
      } else {
        birth[idx * 3] = birthFrom.x;
        birth[idx * 3 + 1] = birthFrom.y;
        birth[idx * 3 + 2] = birthFrom.z;
      }
    }
  }
  pos.needsUpdate = true;
  geo.setAttribute('aBirth', new THREE.BufferAttribute(birth, 3));
  geo.computeVertexNormals();
  return geo;
}

/** Bake a CONSTANT birth point onto every vertex (used for the vertebra tori:
 *  the ring collapses to its spine anchor, then blooms OUT of the cord as the
 *  growth front reaches it). */
function bakeBirthConstant(geo: THREE.BufferGeometry, point: THREE.Vector3) {
  const count = geo.getAttribute('position').count;
  const birth = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    birth[i * 3] = point.x;
    birth[i * 3 + 1] = point.y;
    birth[i * 3 + 2] = point.z;
  }
  geo.setAttribute('aBirth', new THREE.BufferAttribute(birth, 3));
}

const NERVE_ATTRIBUTE_NAMES = [
  'position',
  'normal',
  'uv',
  'objectPos',
  'color',
  'aArc',
  'aBirth',
] as const;

function assertNerveAttributeSet(geo: THREE.BufferGeometry, label: string) {
  const attrs = Object.keys(geo.attributes).sort();
  const expected = [...NERVE_ATTRIBUTE_NAMES].sort();
  const missing = expected.filter((name) => !attrs.includes(name));
  const extra = attrs.filter((name) => !expected.includes(name as (typeof NERVE_ATTRIBUTE_NAMES)[number]));
  console.assert(
    missing.length === 0 && extra.length === 0,
    `Nerve geometry attribute mismatch in ${label}`,
    { missing, extra, attrs }
  );
}

export default function NervousSystem({
  burst,
  uniforms,
  tier = 'high',
  reducedMotion: _reducedMotion = false,
}: {
  burst: BurstRef;
  uniforms: CognitionUniforms;
  tier?: QualityTier;
  reducedMotion?: boolean;
}) {
  const groupRef = useRef<THREE.Group>(null);

  // Perfect synchronization with the brain's physical sway (sibling group, same
  // transform → cancels relative drift; the CNS moves as one body).
  useFrame((state) => {
    if (!groupRef.current) return;
    const time = state.clock.elapsedTime;
    groupRef.current.position.x = Math.sin(time * 0.16) * 0.24 + Math.cos(time * 0.09) * 0.1;
    groupRef.current.position.y = 0.12 + Math.cos(time * 0.2) * 0.14 + Math.sin(time * 0.14) * 0.07;
    groupRef.current.position.z = -1.2;
  });

  // The BRAIN'S EXACT material — Voronoi neural-web + region/palette vertex
  // colours + luminance ladder + fresnel glow, pulsing on the SAME shared
  // uTime/uHold/uArrival/uIgnite leaves the cortex uses + uBreath, plus the
  // nerve-only downward flow band. bodyMode:'nerve' uses the SAME 0.6 cell size
  // (continuity) but a cheaper single-octave + 8-cell Voronoi (PERF). Tier-keyed.
  const material = useMemo(
    () =>
      makeBrainMaterial({
        tier,
        uniforms,
        bodyMode: 'nerve',
        // FINE cell size: the cord is a thin smooth tube (no gyri/sulci), so it
        // needs a much higher Voronoi frequency than the big folded cortex to
        // read as the same living flesh (seeds uNerveScale; live-tunable via
        // window.__NERVE). LOCKED at 24 after a browser sweep (12=leopard-coarse,
        // 18=good, 26=finest; 24 = brain-dense stipple without thin-tube shimmer).
        webScale: 24,
        webOctaves: 'tier', // high tier gets brain-parity two-octave texture; lower tiers stay single-octave
        breathUniform: uniforms.uBreath,
        flowUniform: NERVE_FLOW_UNIFORM,
        reduceMotionUniform: NERVE_REDUCEMOTION_UNIFORM,
        growUniform: NERVE_GROW_UNIFORM,
        flowGainUniform: NERVE_FLOWGAIN_UNIFORM,
        intakeFlowUniform: NERVE_INTAKE_UNIFORM,
        intakeGainUniform: NERVE_INTAKEGAIN_UNIFORM,
        replyWarmUniform: NERVE_REPLYWARM_UNIFORM,
      }),
    [uniforms, tier]
  );

  useEffect(() => {
    NERVE_INTAKEGAIN_UNIFORM.value = 0;
    NERVE_REPLYWARM_UNIFORM.value = 0;
    NERVE_INTAKE_UNIFORM.value = 0;
    return () => {
      NERVE_INTAKEGAIN_UNIFORM.value = 0;
      NERVE_REPLYWARM_UNIFORM.value = 0;
      NERVE_INTAKE_UNIFORM.value = 0;
    };
  }, []);

  useEffect(
    () =>
      subscribeCognition((event) => {
        if (event.type !== 'voice-speaking') return;
        const phase = String(event.data?.phase ?? '');
        const intensity = THREE.MathUtils.clamp(event.intensity ?? 0.72, 0.25, 1);
        if (phase === 'question') {
          NERVE_INTAKE_UNIFORM.value = 0;
          NERVE_INTAKEGAIN_UNIFORM.value = Math.max(NERVE_INTAKEGAIN_UNIFORM.value, intensity);
          return;
        }
        if (event.source === 'reply' && phase === 'reply-start') {
          NERVE_FLOW_UNIFORM.value = Math.floor(NERVE_FLOW_UNIFORM.value);
          NERVE_FLOWGAIN_UNIFORM.value = Math.max(NERVE_FLOWGAIN_UNIFORM.value, intensity);
          NERVE_REPLYWARM_UNIFORM.value = 1;
          return;
        }
        if (event.source === 'reply' && phase === 'reply') {
          NERVE_FLOWGAIN_UNIFORM.value = Math.max(NERVE_FLOWGAIN_UNIFORM.value, intensity);
          NERVE_REPLYWARM_UNIFORM.value = Math.max(NERVE_REPLYWARM_UNIFORM.value, 0.85);
          return;
        }
        if (event.source === 'reply' && phase === 'reply-complete') {
          NERVE_FLOWGAIN_UNIFORM.value = Math.max(NERVE_FLOWGAIN_UNIFORM.value, intensity * 0.75);
          NERVE_REPLYWARM_UNIFORM.value = Math.max(NERVE_REPLYWARM_UNIFORM.value, 0.6);
        }
      }),
    []
  );

  useEffect(() => {
    const mat = material;
    return () => {
      mat.dispose();
    };
  }, [material]);

  // Advance the per-frame uniform leaves (flow sweep, reduced motion). The brain
  // shader / SuperbrainScene are untouched — uFlow lives here.
  useFrame((state, delta) => {
    NERVE_REDUCEMOTION_UNIFORM.value =
      typeof window !== 'undefined' && window.matchMedia
        ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
          ? 1
          : 0
        : 0;
    // Steady descent of the impulse + an extra burst-driven kick (a command
    // visibly travels down the body). Frozen amplitude under reduced motion is
    // handled in-shader; freeze the advance too so it isn't stuck mid-band.
    if (NERVE_REDUCEMOTION_UNIFORM.value < 0.5) {
      // Posture flow: the impulse descent rides uFlow — rest crawls (~0.6x),
      // streaming races (~1.8x) — so the cord's signal speed reads the live state.
      const flowK = 0.4 + uniforms.uFlow.value * 1.4;
      NERVE_FLOW_UNIFORM.value +=
        (delta / FLOW_PERIOD_S) * flowK + burst.current.intensity * FLOW_BURST_KICK * delta;
      if (NERVE_INTAKEGAIN_UNIFORM.value > 0.01) {
        NERVE_INTAKE_UNIFORM.value += delta / INTAKE_FLOW_PERIOD_S;
      }
    }
    // Steady at rest: the impulse band is only visible when the being is actually
    // thinking. Quick attack to the burst level, gentle ~1.4s release so a command
    // lingers as it travels, then the cord returns to a calm steady glow.
    NERVE_FLOWGAIN_UNIFORM.value = Math.max(
      THREE.MathUtils.clamp(burst.current.intensity, 0, 1),
      // Posture floor: think/stream show a faint STEADY traveling band even without
      // a discrete cognition burst; rest (flow 0.16) stays exactly calm (floor 0).
      Math.max(0, uniforms.uFlow.value - 0.16) * 0.42,
      NERVE_FLOWGAIN_UNIFORM.value - delta * 0.7
    );
    NERVE_INTAKEGAIN_UNIFORM.value = Math.max(0, NERVE_INTAKEGAIN_UNIFORM.value - delta * 1.35);
    NERVE_REPLYWARM_UNIFORM.value = Math.max(0, NERVE_REPLYWARM_UNIFORM.value - delta * 0.58);

    // GROWTH: the spine generates once on the being's birth — advances after the
    // brain has had a moment to coalesce, easing 0→1 over GROW_DURATION_S.
    nerveGrowElapsed += delta;
    const growT = Math.max(0, (nerveGrowElapsed - GROW_DELAY_S) / GROW_DURATION_S);
    NERVE_GROW_UNIFORM.value = Math.min(1, growT);
  });

  // ── Build the four merged mesh structures (static; curves are deterministic).
  //    All authored in brain-group-local space; objectPos/aArc/color baked per
  //    mesh; seed 0x57495245 preserved so the (light) jitter is stable. ────────
  const geometries = useMemo(() => {
    const random = createSeededRandom(0x57495245);

    // ── 1) BRAINSTEM BULGE + CORD → merged (1 draw call) ──────────────────────
    // The bulge bridges the brain mass (brain-bottom girth) into the cord girth
    // so they read as ONE body and tuck into the stem stub with no seam.
    // The brainstem rises UP INTO the brain's basal cavity (its wide top buried
    // inside the cortex) and necks down to the cord girth right as it clears the
    // brain underside — so the being reads as ONE continuous trunk emerging from
    // the opening, not a thin cord hung below a hollow.
    const stemPath = [
      new THREE.Vector3(0, CORD_TOP_Y + STEM_TOP_RISE, CORD_Z + 0.03),   // buried up inside the brain mass (fills the opening)
      new THREE.Vector3(0, CORD_TOP_Y + STEM_TOP_RISE * 0.45, CORD_Z + 0.01),
      new THREE.Vector3(0, CORD_TOP_Y - 0.06, CORD_Z - 0.02),            // at the brain underside — still broad
      new THREE.Vector3(0, CORD_TOP_Y - 0.50, CORD_Z - 0.05),           // necks into the thick cord just below the brain
    ];
    const stemGeo = makeTaperedTube(
      stemPath,
      STEM_TUBE_SEGMENTS,
      STEM_RADIAL_SEGMENTS,
      // stay broad through the upper half (filling the cavity), then neck to the
      // cord girth by the time it exits the brain underside.
      (t) => THREE.MathUtils.lerp(STEM_TOP_R, CORD_SIGMA, THREE.MathUtils.smoothstep(t, 0.42, 0.82))
    );
    const stemYTop = CORD_TOP_Y + STEM_TOP_RISE;
    const stemYBot = CORD_TOP_Y - 0.50;
    bakeNerveAttributes(stemGeo, random, (_x, y) => {
      // map the stem's Y into the very top of the body arc (stem-violet band)
      const f = THREE.MathUtils.clamp((stemYTop - y) / Math.max(stemYTop - stemYBot, 1e-4), 0, 1);
      return f * 0.04; // arc 0..0.04 — cerebellum stem violet, matches the brain base
    });

    const cordSpine = [
      new THREE.Vector3(0.0, CORD_TOP_Y, CORD_Z),              // born AT the brainstem-stub bottom (seamless)
      new THREE.Vector3(0.0, CORD_STEM_EXIT_Y, CORD_Z - 0.06), // the stem-to-cord transition zone
      new THREE.Vector3(0.0, -1.5, CORD_Z - 0.04),             // upper cord — slight forward bow
      new THREE.Vector3(0.0, -2.15, CORD_Z + 0.02),            // mid cord
      new THREE.Vector3(0.0, -2.8, CORD_Z - 0.02),             // lower cord
      new THREE.Vector3(0.0, CORD_BOTTOM_Y, CORD_Z),           // conus tip — spray origin
    ];
    const cordGeo = makeTaperedTube(
      cordSpine,
      CORD_TUBE_SEGMENTS,
      CORD_RADIAL_SEGMENTS,
      (t) => {
        // ease NARROWER into the stub (t<0.12) so the cord tucks cleanly into the
        // brainstem bulge instead of ballooning at the seam; uniform thick trunk
        // through the middle; soften to the conus tip (t>0.85). The exact profile
        // the operator liked. CORD_SIGMA_TOP_EASE>1 widens the seam toward the
        // stem girth; we invert it to a <1 narrowing so it slots INSIDE the bulge.
        const topEase = 1.0 / CORD_SIGMA_TOP_EASE; // ~0.85 → slightly narrower at the very top
        if (t < 0.12) return CORD_SIGMA * THREE.MathUtils.lerp(topEase, 1.0, t / 0.12);
        if (t > 0.85) return CORD_SIGMA * THREE.MathUtils.lerp(1.0, 0.6, (t - 0.85) / 0.15);
        return CORD_SIGMA;
      }
    );
    // cord spans body arc 0..0.82 (spray takes 0.82..1) — arc from Y down the cord.
    bakeNerveAttributes(cordGeo, random, (_x, y) => {
      const f = THREE.MathUtils.clamp((CORD_TOP_Y - y) / Math.max(CORD_TOP_Y - CORD_BOTTOM_Y, 1e-4), 0, 1);
      return f * 0.82;
    });

    const cordBundle = mergeGeometries([stemGeo, cordGeo], false);
    stemGeo.dispose();
    cordGeo.dispose();

    // ── 2) VERTEBRAE — stacked centrum rings + discs + processes → merged (1 call) ──
    const vertebraGeos: THREE.BufferGeometry[] = [];
    const pushVertebraGeo = (geo: THREE.BufferGeometry, label: string) => {
      assertNerveAttributeSet(geo, label);
      vertebraGeos.push(geo);
    };
    if (VERTEBRA_RINGS) {
      SEGMENT_ANCHORS.forEach((anchor, i) => {
        const f = SEGMENT_COUNT === 1 ? 0 : i / (SEGMENT_COUNT - 1);
        const segArc = 0.05 + f * 0.7;
        const ringR = THREE.MathUtils.lerp(VERTEBRA_RING_TOP_R, VERTEBRA_RING_BOTTOM_R, f);
        const bodyR = ringR * (1.0 + 0.35 * THREE.MathUtils.smoothstep(f, 0.55, 1.0));
        const vertebraBirth = new THREE.Vector3(anchor.x, anchor.y, anchor.z);
        const stackSpan = (VERTEBRA_GIRTH - 1) * VERTEBRA_GIRTH_SPACING;
        for (let g = 0; g < VERTEBRA_GIRTH; g++) {
          const gy =
            VERTEBRA_GIRTH === 1
              ? anchor.y
              : anchor.y + (g / (VERTEBRA_GIRTH - 1) - 0.5) * stackSpan;
          const torus = new THREE.TorusGeometry(
            bodyR,
            VERTEBRA_RING_TUBE,
            VERTEBRA_RADIAL_SEGMENTS,
            VERTEBRA_TUBULAR_SEGMENTS
          );
          // Lie flat (XZ plane) encircling the vertical cord, then seat on the anchor.
          torus.rotateX(Math.PI / 2);
          torus.translate(anchor.x, gy, anchor.z);
          // GROWTH: the vertebra collapses to its spine anchor, then blooms OUT of
          // the cord as the front reaches its segment — "generated from the spine".
          bakeBirthConstant(torus, vertebraBirth);
          // light, legible jitter only (a touch of organic life, not chaos)
          bakeNerveAttributes(torus, random, () => segArc + (random() - 0.5) * 0.01, 0.04);
          pushVertebraGeo(torus, `vertebra-${i}-centrum-${g}`);
        }

        if (i < SEGMENT_ANCHORS.length - 1) {
          const discY = (anchor.y + SEGMENT_ANCHORS[i + 1].y) * 0.5;
          const disc = new THREE.TorusGeometry(
            bodyR * DISC_R_SCALE,
            DISC_TUBE,
            PROC_RADIAL_SEGMENTS,
            VERTEBRA_TUBULAR_SEGMENTS
          );
          disc.rotateX(Math.PI / 2);
          disc.translate(anchor.x, discY, anchor.z);
          bakeBirthConstant(disc, vertebraBirth);
          bakeNerveAttributes(disc, random, () => segArc + (random() - 0.5) * 0.01, 0.04);
          pushVertebraGeo(disc, `vertebra-${i}-disc`);
        }

        const spLen = THREE.MathUtils.lerp(SPINOUS_LEN_TOP, SPINOUS_LEN_BOT, f);
        const tilt =
          THREE.MathUtils.lerp(0.15, 0.85, THREE.MathUtils.smoothstep(f, 0.15, 0.55)) *
          (1.0 - 0.5 * THREE.MathUtils.smoothstep(f, 0.75, 1.0));
        const p0 = new THREE.Vector3(anchor.x, anchor.y, anchor.z - bodyR * 0.2);
        const p1 = new THREE.Vector3(
          anchor.x,
          anchor.y - spLen * tilt * 0.4,
          anchor.z - bodyR - spLen * 0.45
        );
        const p2 = new THREE.Vector3(
          anchor.x,
          anchor.y - spLen * tilt,
          anchor.z - bodyR - spLen * 0.95
        );
        const spinous = makeTaperedTube(
          [p0, p1, p2],
          PROC_TUBE_SEGMENTS,
          PROC_RADIAL_SEGMENTS,
          (t) => SPINOUS_R * (1.0 - 0.55 * t),
          vertebraBirth
        );
        bakeNerveAttributes(spinous, random, () => segArc + (random() - 0.5) * 0.012, 0.05);
        pushVertebraGeo(spinous, `vertebra-${i}-spinous`);

        const tpLen = THREE.MathUtils.lerp(TRANSVERSE_LEN_TOP, TRANSVERSE_LEN_BOT, f);
        const fwd =
          0.06 *
          THREE.MathUtils.smoothstep(f, 0.2, 0.55) *
          (1.0 - THREE.MathUtils.smoothstep(f, 0.7, 1.0));
        for (const side of [-1, 1] as const) {
          const q0 = new THREE.Vector3(anchor.x, anchor.y, anchor.z);
          const q1 = new THREE.Vector3(
            anchor.x + side * tpLen * 0.5,
            anchor.y + 0.01,
            anchor.z + fwd * 0.5
          );
          const q2 = new THREE.Vector3(
            anchor.x + side * tpLen,
            anchor.y + 0.005,
            anchor.z + fwd
          );
          const transverse = makeTaperedTube(
            [q0, q1, q2],
            PROC_TUBE_SEGMENTS,
            PROC_RADIAL_SEGMENTS,
            (t) => TRANSVERSE_R * (0.7 + 0.5 * t),
            vertebraBirth
          );
          bakeNerveAttributes(
            transverse,
            random,
            () => segArc + (random() - 0.5) * 0.012,
            0.05
          );
          pushVertebraGeo(transverse, `vertebra-${i}-transverse-${side}`);
        }
      });
    }
    const vertebraeBundle =
      vertebraGeos.length > 0 ? mergeGeometries(vertebraGeos, false) : null;
    console.assert(
      vertebraGeos.length === 0 || vertebraeBundle !== null,
      'Vertebrae merge failed; sub-part attributes must match exactly'
    );
    vertebraGeos.forEach((g) => g.dispose());

    // ── 3) BILATERAL NERVE ROOTS — 48 tubes → merged (1 call) ─────────────────
    const rootGeos: THREE.BufferGeometry[] = [];
    SEGMENT_ANCHORS.forEach((anchor, i) => {
      const f = SEGMENT_COUNT === 1 ? 0 : i / (SEGMENT_COUNT - 1);
      const segArc = 0.05 + f * 0.7;
      const len = THREE.MathUtils.lerp(ROOT_LENGTH_TOP, ROOT_LENGTH_GROWTH, f * f); // f*f = accelerating fan
      const outX = THREE.MathUtils.lerp(ROOT_SPREAD_BASE, ROOT_SPREAD_GROWTH, f);
      const droop = THREE.MathUtils.lerp(ROOT_DROOP_TOP, ROOT_DROOP_GROWTH, f);
      const rootR = THREE.MathUtils.lerp(ROOT_RADIUS_TOP, ROOT_RADIUS_BOTTOM, f);

      for (let p = 0; p < ROOT_PAIRS_PER_SEGMENT; p++) {
        const pairBias =
          ROOT_PAIRS_PER_SEGMENT === 1 ? 0 : (p / (ROOT_PAIRS_PER_SEGMENT - 1) - 0.5) * 0.16;
        for (const side of [-1, 1] as const) {
          // Light, seeded organic jitter (legible near-symmetric fan, no chaos) —
          // same math the prior structure used so the SHAPE is preserved.
          const jLen = len * (0.9 + random() * 0.18);
          const jOut = outX * (0.92 + random() * 0.16);
          const jDroop = droop * (0.9 + random() * 0.24);
          const jZmid = (random() - 0.5) * 0.1;
          const jZtip = (random() - 0.5) * 0.18;
          const wander = (random() - 0.5) * 0.07;
          const yJit = (random() - 0.5) * 0.03;
          const rootPath = [
            new THREE.Vector3(anchor.x, anchor.y + pairBias + yJit, anchor.z), // emerge ON the cord
            new THREE.Vector3(
              side * jOut * 0.45 * jLen + wander * 0.3,
              anchor.y - jDroop * 0.25,
              anchor.z + 0.02 + jZmid * 0.5
            ),
            new THREE.Vector3(
              side * jOut * 0.85 * jLen + wander,
              anchor.y - jDroop * 0.62,
              anchor.z - 0.02 + jZmid
            ),
            new THREE.Vector3(
              side * jOut * 1.0 * jLen + wander * 1.3,
              anchor.y - jDroop * (0.97 + random() * 0.12),
              anchor.z + 0.04 + jZtip
            ), // weeping tip
          ];
          const rootGeo = makeTaperedTube(
            rootPath,
            ROOT_TUBE_SEGMENTS,
            ROOT_RADIAL_SEGMENTS,
            (t) => rootR * (0.6 + ROOT_FLARE * t), // flares toward the weeping tip
            rootPath[0].clone() // GROWTH: the root unfurls OUT from its cord attachment
          );
          const rootArc = segArc + (random() - 0.5) * 0.04; // minor hue spread so the fan isn't flat
          bakeNerveAttributes(rootGeo, random, () => rootArc, 0.05);
          rootGeos.push(rootGeo);
        }
      }
    });
    const rootsBundle = rootGeos.length > 0 ? mergeGeometries(rootGeos, false) : null;
    rootGeos.forEach((g) => g.dispose());

    // ── 4) CAUDA-EQUINA SPRAY — 16 tubes → merged (1 call) ────────────────────
    const conus = new THREE.Vector3(0, CORD_BOTTOM_Y, CORD_Z);
    const sprayGeos: THREE.BufferGeometry[] = [];
    for (let s = 0; s < SPRAY_COUNT; s++) {
      const fx = SPRAY_COUNT === 1 ? 0 : (s / (SPRAY_COUNT - 1) - 0.5) * 2; // -1..1 across the fan
      const tipX = fx * SPRAY_FAN_WIDTH + (random() - 0.5) * 0.2;
      const tipZ = CORD_Z + (random() - 0.5) * 0.55;
      const tipY =
        CORD_BOTTOM_Y -
        THREE.MathUtils.lerp(SPRAY_LENGTH_CENTER, SPRAY_LENGTH_EDGE, Math.abs(fx)) +
        (random() - 0.5) * 0.35;
      const sprayPath = [
        conus.clone(),
        new THREE.Vector3(
          fx * 0.15 + (random() - 0.5) * 0.1,
          CORD_BOTTOM_Y - 0.4,
          CORD_Z + 0.02 + (random() - 0.5) * 0.2
        ),
        new THREE.Vector3(
          fx * 0.5 + (random() - 0.5) * 0.16,
          CORD_BOTTOM_Y - 0.9,
          CORD_Z + (random() - 0.5) * 0.32
        ),
        new THREE.Vector3(tipX, tipY, tipZ), // scattered weeping tip
      ];
      const sprayGeo = makeTaperedTube(
        sprayPath,
        SPRAY_TUBE_SEGMENTS,
        SPRAY_RADIAL_SEGMENTS,
        (t) => THREE.MathUtils.lerp(SPRAY_RADIUS_TOP, SPRAY_RADIUS_TIP, t),
        conus.clone() // GROWTH: the spray unfurls OUT from the conus tip (born last)
      );
      // spray spans body arc 0.82..1.0 along its own length (top→tip)
      const yTop = CORD_BOTTOM_Y;
      const yTip = tipY;
      bakeNerveAttributes(
        sprayGeo,
        random,
        (_x, y) => {
          const t = THREE.MathUtils.clamp((yTop - y) / Math.max(yTop - yTip, 1e-4), 0, 1);
          return 0.82 + t * 0.18;
        },
        0.05
      );
      sprayGeos.push(sprayGeo);
    }
    const sprayBundle = sprayGeos.length > 0 ? mergeGeometries(sprayGeos, false) : null;
    sprayGeos.forEach((g) => g.dispose());

    return { cordBundle, vertebraeBundle, rootsBundle, sprayBundle };
  }, []);

  useEffect(() => {
    const { cordBundle, vertebraeBundle, rootsBundle, sprayBundle } = geometries;
    return () => {
      cordBundle?.dispose();
      vertebraeBundle?.dispose();
      rootsBundle?.dispose();
      sprayBundle?.dispose();
    };
  }, [geometries]);

  const { cordBundle, vertebraeBundle, rootsBundle, sprayBundle } = geometries;

  // FOUR draw calls, all wearing the ONE shared nerve material instance →
  // visually one continuous organism with the brain.
  return (
    <group ref={groupRef}>
      {cordBundle && (
        <mesh geometry={cordBundle} material={material} frustumCulled={false} renderOrder={2} />
      )}
      {vertebraeBundle && (
        <mesh geometry={vertebraeBundle} material={material} frustumCulled={false} renderOrder={2} />
      )}
      {rootsBundle && (
        <mesh geometry={rootsBundle} material={material} frustumCulled={false} renderOrder={2} />
      )}
      {sprayBundle && (
        <mesh geometry={sprayBundle} material={material} frustumCulled={false} renderOrder={2} />
      )}
      <VertebraeRepoMapOverlay />
    </group>
  );
}
