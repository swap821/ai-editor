import * as THREE from 'three';
import type { QualityTier } from '@/components/QualityTierProvider';
import type { CognitionUniforms } from '@/components/canvas/SuperbrainScene.LEGACY';

// ============================================================================
// SHARED BRAIN MATERIAL FACTORY
//
// The superbrain's loved aesthetic is EMISSION-DRIVEN: a near-black glass base
// (0x010308) wearing baked region vertex-colours that an animated 3D-Voronoi
// "neural web" (microDetail) raises into glowing synapse lines, plus a per-
// region fresnel rim, all pulsing on uTime — gated by tier and the opening
// envelopes (uArrival / uIgnite) and the approval hold (uHold).
//
// This factory lifts that EXACT recipe out of SuperbrainScene.tsx so the
// nervous system (cord + vertebrae + roots + spray) can wear the IDENTICAL
// material and sample the IDENTICAL, world-continuous Voronoi field — they are
// not "matched", they are literally the same shader sampling the same noise
// lattice, just over tube geometry instead of cortex geometry. That, plus the
// shared uTime, is what makes the web ONE continuous neural field flowing from
// the cortex into the cord, not two separate-but-similar shaders.
//
// CORTEX vs NERVE — the only deltas (all gated; bodyMode==='cortex' is
// byte-identical to the canon brain so the existing goldens hold):
//   • uBreath + uFlow uniforms wired ONLY when supplied (nerve path).
//   • microDetail scale/octaves are parameters (cortex keeps 0.6 / tier
//     octaves; nerve keeps the SAME 0.6 cell size for continuity but a cheaper
//     single-octave + 8-cell Voronoi neighbourhood — ~6× cheaper per fragment).
//   • Two nerve-only emission terms appended at the end of the ladder: a breath
//     inflation multiply and a downward arc-space data-flow band (the nerve
//     impulse travelling brain→spray). Both behind bodyMode==='nerve'.
// ============================================================================

export type BrainBodyMode = 'cortex' | 'nerve';

export interface BrainMaterialOptions {
  /** Quality tier — gates Voronoi octaves + animation (must be in the cache key). */
  tier: QualityTier;
  /** The shared cognition uniform leaves (uTime / uHold / uArrival / uIgnite). */
  uniforms: CognitionUniforms;
  /** Glass-cranium node-brain path (cortex only). Default false = canon organ flesh. */
  nodeBrain?: boolean;
  /** 'cortex' (default, byte-identical canon) or 'nerve' (cord/vertebrae/roots/spray). */
  bodyMode?: BrainBodyMode;
  /** Voronoi cell size; KEEP 0.6 on the nerve so its cells line up with the cortex. */
  webScale?: number;
  /** Octave budget. 'tier' = high→2 / else→1 (canon). 1 forces single-octave (nerve). */
  webOctaves?: 1 | 2 | 'tier';
  /** Nerve breath leaf (the cord inflates on the cortex's systole). Cortex: omit. */
  breathUniform?: { value: number } | null;
  /** Nerve flow leaf (0..N body-lengths swept; the downward impulse). Cortex: omit. */
  flowUniform?: { value: number } | null;
  /** Nerve reduced-motion leaf (1 = freeze the flow band). Cortex: omit. */
  reduceMotionUniform?: { value: number } | null;
  /** Nerve GROWTH front (0..1 arc): the spine generates downward, each part born
   *  as the front passes its arc. Default 1 = fully grown (rest, byte-identical). */
  growUniform?: { value: number } | null;
  /** Nerve flow-band GAIN (0 at rest → no traveling pulse / steady calm glow; >0
   *  only on real cognition activity → the impulse visibly races down). Default 1. */
  flowGainUniform?: { value: number } | null;
  /** Upward question flow phase (0..1 over the intake->brainstem band). */
  intakeFlowUniform?: { value: number } | null;
  /** Upward question flow gain. */
  intakeGainUniform?: { value: number } | null;
  /** 0..1 warmth mix for the reply-down flow. */
  replyWarmUniform?: { value: number } | null;
  /** Spectral-v1 posture HUE (damped THREE.Color) blended OVER the regional palette. */
  postureColorUniform?: { value: THREE.Color } | null;
  /** Posture blend strength 0..0.8 (0 = byte-identical canon). */
  postureTintUniform?: { value: number } | null;
}

// ── NERVE TUNABLES (operator tunes the cord's share of the brain's life) ─────
/** Nerve breath depth: emission *= 0.92 + 0.08*uBreath (cord inflates with cortex). */
const NERVE_BREATH_FLOOR = 0.92;
const NERVE_BREATH_DEPTH = 0.08;
/** Downward data-flow band: a gaussian impulse in arc-space, brain→spray. */
const NERVE_FLOW_BAND_SHARP = 7.0;   // higher = tighter band (~14% of the body at 7.0)
const NERVE_FLOW_BAND_GAIN = 0.9;    // peak extra emission at the impulse head
/** Upward intake band: a tighter cyan packet running intake->brainstem only. */
const NERVE_INTAKE_BAND_SHARP = 11.0;
const NERVE_INTAKE_BAND_GAIN = 0.88;
const NERVE_INTAKE_ARC_MAX = 0.24;

/** Resolve the octave count actually compiled for a (mode, tier, request). */
function resolveOctaves(webOctaves: 1 | 2 | 'tier', tier: QualityTier): 1 | 2 {
  if (webOctaves === 'tier') return tier === 'high' ? 2 : 1;
  return webOctaves;
}

/**
 * Build the brain's MeshPhysicalMaterial — the shared living-flesh shader.
 * Called with cortex defaults it reproduces the canon brain byte-for-byte;
 * called with { bodyMode: 'nerve', ... } it wears the same web over tubes.
 */
export function makeBrainMaterial(options: BrainMaterialOptions): THREE.MeshPhysicalMaterial {
  const {
    tier,
    uniforms,
    nodeBrain = false,
    bodyMode = 'cortex',
    webScale = 0.6,
    webOctaves = 'tier',
    breathUniform = null,
    flowUniform = null,
    reduceMotionUniform = null,
    growUniform = null,
    flowGainUniform = null,
    intakeFlowUniform = null,
    intakeGainUniform = null,
    replyWarmUniform = null,
    postureColorUniform = null,
    postureTintUniform = null,
  } = options;

  const isNerve = bodyMode === 'nerve';
  const octaves = resolveOctaves(webOctaves, tier);
  // Nerve web-aesthetic uniform leaves (live-tunable). Defaults intentionally
  // start near canon and get dialed in the browser. webScale is the SEED for the
  // frequency leaf but the nerve overrides it far finer (smooth tube needs it).
  const nerveU = isNerve
    ? {
        // First-pass nerve aesthetic (analysis-derived; live-tunable via
        // window.__NERVE, to be locked in the operator's browser). The cord is a
        // SMOOTH tube ~0.36 wide with NO gyri/sulci, so at the cortex's 0.6 cell
        // size <1 cell spans it → it reads glassy. A FAR finer cell size makes
        // the Voronoi the cord's flesh; higher contrast sharpens the web; tamed
        // core/fresnel stop the smooth tube blooming white.
        uNerveScale: { value: webScale }, // seeded from the call site (nerve passes a fine value)
        uNerveContrastLo: { value: 0.24 }, // darker cell interiors (brain-like distinct cells)
        uNerveContrastHi: { value: 0.6 },  // bright glowing cell edges
        uNerveCoreGlow: { value: 2.3 },    // tamed vs cortex 4.0 (smooth tube won't bloom white)
        uNerveFresnel: { value: 1.05 },    // tamed vs cortex 2.0 (smooth-tube rim stays subtle)
      }
    : null;
  // Nerve uses an 8-cell Voronoi neighbourhood (x,y,z ∈ {-1,0}) instead of the
  // cortex's 27 cells — deterministic cell points keep the web continuous while
  // halving+ the loop. Cortex always uses the full 27.
  const cellLo = isNerve ? -1 : -1;
  const cellHi = isNerve ? 0 : 1;
  const cellLoop = (axis: string) => `for(int ${axis}=${cellLo}; ${axis}<=${cellHi}; ${axis}++)`;

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

  // COMPUTER BRAIN: drop the cortex to a near-transparent GLASS CRANIUM so the
  // node-network glows THROUGH it. Canon path stays fully opaque. (Cortex only.)
  if (nodeBrain) {
    mat.transparent = true;
    mat.opacity = 0.16;
    mat.depthWrite = false;
  }

  mat.onBeforeCompile = (shader) => {
    // Link the shared sentience leaves into the shader.
    shader.uniforms.uTime = uniforms.uTime;
    shader.uniforms.uHold = uniforms.uHold;
    // Opening envelopes: drive the reveal (coalescence) + single-shot ignition
    // seed flash. Both default to the SETTLED value (0) so canon REST emission
    // is byte-identical.
    shader.uniforms.uArrival = uniforms.uArrival;
    shader.uniforms.uIgnite = uniforms.uIgnite;
    // Posture HUE (spectral-v1) — blended OVER the regional palette on BOTH the
    // cortex and the nerve so the whole body shifts hue by lifecycle state.
    // Defaults to rest violet, tint 0 (byte-identical canon when unsupplied).
    shader.uniforms.uPostureColor =
      postureColorUniform ?? uniforms.uPosture ?? { value: new THREE.Color(150 / 255, 120 / 255, 255 / 255) };
    shader.uniforms.uPostureTint = postureTintUniform ?? uniforms.uPostureTint ?? { value: 0 };
    shader.uniforms.uPostureCommit = uniforms.uPostureCommit ?? { value: 0 };
    // NERVE-only leaves — the cord breathes + carries the downward impulse.
    if (isNerve) {
      shader.uniforms.uBreath = breathUniform ?? uniforms.uBreath;
      shader.uniforms.uFlow = flowUniform ?? { value: 0 };
      shader.uniforms.uReduceMotion = reduceMotionUniform ?? { value: 0 };
      shader.uniforms.uGrow = growUniform ?? { value: 1 };
      shader.uniforms.uFlowGain = flowGainUniform ?? { value: 1 };
      shader.uniforms.uIntakeFlow = intakeFlowUniform ?? { value: 0 };
      shader.uniforms.uIntakeGain = intakeGainUniform ?? { value: 0 };
      shader.uniforms.uReplyWarm = replyWarmUniform ?? { value: 0 };
      // NERVE web-aesthetic leaves — the cord is a SMOOTH tube with no gyri/sulci
      // (unlike the GLB cortex), so its Voronoi must run FAR finer + higher-
      // contrast to read as the same living flesh. These are live-tunable
      // (NervousSystem copies window.__NERVE into them) so the look can be dialed
      // in the operator's browser, then baked. Cortex never declares them.
      shader.uniforms.uNerveScale = nerveU!.uNerveScale;
      shader.uniforms.uNerveContrastLo = nerveU!.uNerveContrastLo;
      shader.uniforms.uNerveContrastHi = nerveU!.uNerveContrastHi;
      shader.uniforms.uNerveCoreGlow = nerveU!.uNerveCoreGlow;
      shader.uniforms.uNerveFresnel = nerveU!.uNerveFresnel;
    }

    // Pass local position to the fragment shader for stable high-frequency
    // noise. IDENTICAL line on cortex + nerve — the continuity contract: the
    // nerve geometry is authored in the same brain-group-local frame, so
    // position*2.0 samples the SAME unbroken Voronoi lattice.
    shader.vertexShader = shader.vertexShader.replace(
      '#include <common>',
      `#include <common>
       varying vec3 vLocalPos;
       ${isNerve ? 'attribute float aArc;\n       attribute vec3 aBirth;\n       uniform float uGrow;\n       varying float vArc;\n       varying float vBorn;' : ''}
      `
    );
    shader.vertexShader = shader.vertexShader.replace(
      '#include <begin_vertex>',
      `#include <begin_vertex>
       // NB: vLocalPos samples the FINAL position (not the growing one) so the
       // Voronoi web is locked to the final shape and is merely REVEALED as the
       // part is born — the web doesn't slide/swim during growth.
       vLocalPos = position * 2.0; // Stabilized local scale
       ${isNerve ? `vArc = aArc;
       // GROWTH FRONT: a part at arc aArc is unborn until uGrow reaches it, then
       // inflates from its birth point (cord → own centerline; vertebra → its
       // spine anchor; root → its cord attachment; spray → the conus) over a soft
       // band. uGrow==1 (rest) -> born==1 everywhere -> transformed==position.
       float born = clamp((uGrow - aArc) / 0.12, 0.0, 1.0);
       born = born * born * (3.0 - 2.0 * born); // smoothstep ease
       vBorn = born;
       transformed = mix(aBirth, position, born);` : ''}
      `
    );

    shader.fragmentShader = shader.fragmentShader.replace(
      '#include <common>',
      `#include <common>
       uniform float uTime;
       uniform float uHold;
       uniform float uArrival;
       uniform float uIgnite;
       uniform vec3 uPostureColor;
       uniform float uPostureTint;
       uniform float uPostureCommit;
       ${isNerve ? 'uniform float uBreath;\n       uniform float uFlow;\n       uniform float uFlowGain;\n       uniform float uIntakeFlow;\n       uniform float uIntakeGain;\n       uniform float uReplyWarm;\n       uniform float uReduceMotion;\n       uniform float uGrow;\n       uniform float uNerveScale;\n       uniform float uNerveContrastLo;\n       uniform float uNerveContrastHi;\n       uniform float uNerveCoreGlow;\n       uniform float uNerveFresnel;\n       varying float vArc;\n       varying float vBorn;' : ''}
       varying vec3 vLocalPos;

       vec3 hash33(vec3 p) {
           p = vec3(dot(p, vec3(127.1, 311.7, 74.7)),
                    dot(p, vec3(269.5, 183.3, 246.1)),
                    dot(p, vec3(113.5, 271.9, 124.6)));
           return fract(sin(p) * 43758.5453123);
       }

       // Animated 3D Voronoi for flowing, living neural synapses.
       // Cortex iterates the full 27-cell neighbourhood; the nerve iterates an
       // 8-cell neighbourhood (deterministic cell points keep the web
       // continuous across the seam at half+ the cost on a thin tube surface).
       float voronoi(vec3 x) {
           vec3 p = floor(x);
           vec3 f = fract(x);
           float res = 100.0;
           ${cellLoop('k')} {
               ${cellLoop('j')} {
                   ${cellLoop('i')} {
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

        // Continuous glowing neural web (edges of the Voronoi cells).
       float microDetail(vec3 pos) {
           ${nodeBrain ? `return 0.0; // node-brain: cortex stops being flesh` : `
           float scale = ${isNerve ? 'uNerveScale' : webScale.toFixed(4)};
           // Do not invert! We want distance to center.
           // Centers are 0.0 (dark), edges are ~0.8 (bright)
           float v1 = voronoi(pos * scale);
           ${octaves === 2
             ? `float v2 = voronoi(pos * scale * 2.0 + vec3(v1));
           // Combine into a multi-scale continuous web
           float webbing = v1 * 0.7 + v2 * 0.3;`
             : `// Single-octave web (half the loops)
           float webbing = v1;`}

           // Isolate the highest values to create thin, sharp, glowing interconnected lines
           return smoothstep(${isNerve ? 'uNerveContrastLo' : '0.4'}, ${isNerve ? 'uNerveContrastHi' : '0.8'}, webbing);`}
       }
      `
    );

    shader.fragmentShader = shader.fragmentShader.replace(
      '#include <normal_fragment_begin>',
      `#include <normal_fragment_begin>
       // PROCEDURAL BUMP MAPPING (Normal Perturbation)
       // Smooth, thick organic bump (multiplier 0.015 to prevent sandy artifacts).
       // Evaluated ONCE per fragment and shared with the emission pass below
       // (each microDetail call is the heaviest cost on screen).
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
       // Make the diffuse base extremely dark so the emissive glow pops —
       // the look is driven purely by emission.
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

       // ── Posture HUE (spectral-v1): blend the live posture color OVER the
       //    SACRED regional palette — MULTIPLIED, never replaced, so each region
       //    keeps its relative AO/luminance/structure and only its hue glides by
       //    state. *1.9 restores energy lost multiplying two <1 colors.
       //    uPostureTint==0 -> byte-identical canon. Feeds the whole emission ladder.
       // Multiply (preserve regional structure) vs committed flat hue (the poster);
       // uPostureCommit dials between them. Both keep per-region luminance, so the
       // brain's bright/dark structure survives even when fully committed.
       vec3 posMul = safeColor * uPostureColor * 1.9;
       float postureLum = dot(safeColor, vec3(0.299, 0.587, 0.114));
       vec3 posCommit = uPostureColor * postureLum * 2.4;
       vec3 posCol = mix(posMul, posCommit, clamp(uPostureCommit, 0.0, 1.0));
       safeColor = mix(safeColor, posCol, clamp(uPostureTint, 0.0, 0.8));

       // 1. Core Regional Glow: drive the emission with the baked regional
       // colors, modulated by the Voronoi network (detailed + organic).
       totalEmissiveRadiance += safeColor * pow(cDetail, 1.5) * ${isNerve ? 'uNerveCoreGlow' : '4.0'};

       // 2. Vibrant Edge Rim Light: smooth Fresnel matching the region color.
       vec3 viewDir = normalize(vViewPosition);
       vec3 geomNormal = normalize(vNormal);
       float fresnel = pow(1.0 - max(dot(viewDir, geomNormal), 0.0), 2.5);

       // Organic breathing pulse — held steady and bright during a hold.
       float pulse = sin(uTime * 2.0) * 0.5 + 0.5;
       float pulseMix = mix(mix(0.7, 1.5, pulse), 1.25, uHold);

       ${nodeBrain
         ? `totalEmissiveRadiance += safeColor * fresnel * 0.35 * pulseMix;`
         : `totalEmissiveRadiance += safeColor * fresnel * ${isNerve ? 'uNerveFresnel' : '2.0'} * pulseMix;`}

       // Approval hold: tint toward YELLOW-zone amber, structure preserved.
       vec3 holdTone = vec3(1.0, 0.62, 0.22);
       totalEmissiveRadiance = mix(
         totalEmissiveRadiance,
         totalEmissiveRadiance * holdTone + holdTone * 0.05,
         uHold * 0.85
       );

       // ── Opening reveal (additive: uArrival==0 -> canon REST) ──
       float reveal = 1.0 - uArrival;
       totalEmissiveRadiance *= mix(0.12, 1.0, reveal);
       // uIgnite — the single-shot warm-white seed flash.
       totalEmissiveRadiance += safeColor * uIgnite * 1.6 + vec3(0.9, 0.95, 1.0) * uIgnite * 0.5;
       ${isNerve ? `
       // ── NERVE-only life (the cord shares the cortex's systole + carries the
       //    downward nerve impulse). Both behind bodyMode==='nerve'. ──
       // Breath inflation: the cord brightens/dims on the SAME systole value the
       // cortex inflates its geometry by — the CNS breathes as one body.
       float nerveBreath = ${NERVE_BREATH_FLOOR.toFixed(2)} + ${NERVE_BREATH_DEPTH.toFixed(2)} * uBreath;
       totalEmissiveRadiance *= nerveBreath;
       // Downward data-flow band: ONE coherent gaussian impulse sweeping arc-
       // space brain->spray (a nerve impulse propagating down the body). Frozen
       // amplitude under reduced motion (uFlow advance is also frozen module-side).
       float flowHead = fract(uFlow);
       float flowBand = exp(-pow((vArc - flowHead) * ${NERVE_FLOW_BAND_SHARP.toFixed(1)}, 2.0));
       // uFlowGain is 0 at REST (steady calm glow — no traveling strobe) and only
       // rises on real cognition activity, when a command visibly races down the cord.
       vec3 flowColor = mix(safeColor, vec3(1.0, 0.62, 0.22), clamp(uReplyWarm, 0.0, 1.0));
       totalEmissiveRadiance += flowColor * flowBand * ${NERVE_FLOW_BAND_GAIN.toFixed(2)} * uFlowGain * (1.0 - uReduceMotion);
       // Question-up band: a cooler cyan packet rising from the brainstem intake
       // into the cortex on conversational send. Purely nerve-gated and dark at rest.
       float intakeHead = mix(${NERVE_INTAKE_ARC_MAX.toFixed(2)}, 0.0, fract(uIntakeFlow));
       float intakeBand = exp(-pow((vArc - intakeHead) * ${NERVE_INTAKE_BAND_SHARP.toFixed(1)}, 2.0));
       vec3 intakeColor = mix(safeColor, vec3(0.36, 0.88, 0.98), 0.88);
       totalEmissiveRadiance += intakeColor * intakeBand * ${NERVE_INTAKE_BAND_GAIN.toFixed(2)} * uIntakeGain * (1.0 - uReduceMotion);
       // GROWTH reveal: an unborn part (collapsed onto its birth point) is dark,
       // so the spine visibly GENERATES downward — vertebrae igniting as the front
       // reaches them. A thin leading hot-line at the growth front sells the birth.
       totalEmissiveRadiance *= smoothstep(0.0, 0.3, vBorn);
       float growEdge = smoothstep(0.10, 0.0, abs(vArc - uGrow)) * step(0.001, uGrow) * step(uGrow, 0.999);
       totalEmissiveRadiance += safeColor * growEdge * 0.8;
       ` : ''}
      `
    );
  };

  // The GLSL varies by tier / nodeBrain / bodyMode / octave budget, so the
  // compiled-program cache key MUST include every branch — a constant key makes
  // THREE reuse the first-compiled (possibly degraded) program for the session.
  mat.customProgramCacheKey = () =>
    `superbrain_v10_${tier}_${nodeBrain ? 'node' : 'organ'}_${bodyMode}_o${octaves}`;

  // Expose the nerve aesthetic leaves so the caller can live-tune them
  // (NervousSystem copies window.__NERVE into these each frame during dial-in).
  if (nerveU) (mat as unknown as { __nerveU: typeof nerveU }).__nerveU = nerveU;

  return mat;
}
