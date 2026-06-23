// frontend/src/superbrain/lib/pointFieldMaterial.ts
import * as THREE from 'three';

export interface PointFieldUniformOverrides {
  uTime?: { value: number };
  uPostureColor?: { value: THREE.Color };
  uPostureTint?: { value: number };
  /** Shared organism breath (asymmetric metabolic systole). Pass the scene's
   *  uBreath so the points breathe on the SAME clock as the mesh/nerves/aura. */
  uBreath?: { value: number };
}

const VERTEX = /* glsl */ `
  uniform float uPixelRatio; // device pixel ratio — DPR-correct on-screen size
  uniform float uRefDist;    // reference camera distance (~ brain distance) for weak depth
  uniform float uSize;       // base point size in CSS px
  uniform float uAttenK;     // 0 = flat poster (constant size), ~0.3 = weak depth
  uniform float uTime;       // shared scene clock — drives breathe/flow
  uniform float uBreath;     // shared organism breath (asymmetric systole) — phase-lock
  uniform float uGrow;       // 0 = no breath, 1 = full breath gain
  uniform float uFlowSpeed;  // body-axis flow-band sweep speed
  uniform float uArrival;    // 0 = scattered inrush origin, 1 = condensed in place
  uniform float uReabsorb;   // 0 = present, 1 = dissolved up/away
  uniform float uSprayHide;  // 0 = cauda tail shown, 1 = tail retracted (while orchestrating)
  uniform float uSprayBand;  // body-axis cutoff: points with aBand below this are the "tail"
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
  varying float vAxis;       // raw normalized body axis (0 roots -> 1 cortex) for ignite weighting
  void main() {
    vColor = aColor;
    vSeed = aPhase;
    vAxis = aBand;
    vec3 p = position;
    // BREATHE: coherent whole-body inhale/exhale along the surface normal, driven
    // by the SHARED organism breath (uBreath — the same asymmetric metabolic
    // systole the mesh/nerves/aura ride), so brain + spine breathe as ONE clock
    // instead of a separate fast sine (the dual-rhythm the poster-gap audit
    // flagged). A tiny per-point shimmer keeps each puncta individually alive on
    // top of the coherent breath.
    p += aNormal * (uGrow * 0.014 * length(position) * uBreath);
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
    // SPRAY HIDE: while orchestrating, the cauda-equina TAIL (lowest body-axis
    // points — the willow spray + intake rings) retracts so the bottom clears for
    // the active work surface. Points above the cutoff are untouched; the tail
    // shrinks to nothing as uSprayHide -> 1. (Operator call 2026-06-23.)
    float tailMask = smoothstep(uSprayBand * 0.25, uSprayBand, aBand);
    float sprayFactor = mix(1.0, tailMask, clamp(uSprayHide, 0.0, 1.0));
    gl_PointSize = min(uSize * aSize * uPixelRatio * atten * (1.0 + band * 0.2) * vAlpha * sprayFactor, 64.0);
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
  varying float vAxis;
  uniform vec3 uPostureColor;
  uniform float uPostureTint;
  uniform float uGlowMul;
  uniform float uFogDensity;
  uniform float uTime;
  uniform float uBodyOpacity; // 1 = solid; <1 dims the cloud so inner memory-nodes show through
  uniform float uIgnite;      // single-shot arrival "ignition of awareness" flash (cortex-weighted luminance)
  uniform float uAwaken;      // conversation: the cortex HEATS while the being notices/converses (cortex-weighted luminance)
  uniform float uStatePulse;  // orchestration: "nerves carry the state" — a luminance pulse travels the spine/roots while working
  uniform float uReabsorbGlow; // reabsorption: the cortex INHALE bell (0..1, overshoot→settle) as a tab's energy lands in the head
  uniform float uReabsorbRise; // reabsorption: 0..1 climb of the TRAVELLING energy band up the spine (vAxis), decelerating into the cortex
  uniform float uWakeWave;     // summon/wake: 0..1 climb of a luminance pulse that RUSHES up the body when the being notices you (hands into the cortex heat)
  uniform float uFlinch;       // dismiss/settle beats: transient whole-body luminance throb — error WINCE (agitated) / approval-RELEASE burst (luminance only; hue rides the posture tint)
  uniform float uReplyRise;   // conversation: 0 idle .. 1 reply active — a luminance bead-band climbs the spine (vAxis 0->1) into the cortex as the being speaks back
  uniform float uVertebrae;   // orchestration: 0 smooth cord .. 1 reveal distinct vertebral segments down the spine (poster phase 5 "spine reveals vertebrae")
  uniform float uArrival;      // 0 = scattered/arriving (dark), 1 = condensed (full) — the dark->light ignition ramp
  uniform float uArrivalDark;  // floor brightness at uArrival=0 (the "born from darkness" beat); dialable, never 0 by accident
  uniform float uFogStart;     // depth haze: view-Z where recession begins (poster depth slab)
  uniform float uHazeStrength; // depth haze: how strongly distant points recede toward zero (additive-correct; 0 = prior look)
  uniform float uRolloffKnee;  // filmic highlight rolloff: luminance at/below this is byte-unchanged
  uniform float uRolloff;      // filmic highlight rolloff: compress ONLY the hottest cores so they stay COLORED (hue-preserving) instead of clipping to white (0 = prior look)
  void main() {
    // Soft round sprite — rebuilt from the known-good base (1-d*2 stays in [0,1],
    // so pow() never goes NaN; the old smoothstep/fog path was producing NaN that
    // silently blanked the whole field).
    float d = length(gl_PointCoord - 0.5);
    if (d > 0.5) discard;
    float t = clamp(1.0 - d * 2.0, 0.0, 1.0);
    float glow = pow(t, 2.4);                 // wide soft halo
    float core = pow(t, 9.0);                  // tight bright core
    float intensity = glow * 0.62 + core * 0.85;
    // gentle desynced twinkle
    intensity *= 0.82 + 0.18 * sin(uTime * 0.7 + vSeed);
    // Energy-restore (x1.6): vColor * uPostureColor multiplies two sub-1 colors,
    // darkening the cloud under a strong posture tint (the think dim). The cortex
    // already compensates (brainMaterial); the point shader did not. Scalar lift =
    // brightness only, hue/saturation preserved (sacred palette).
    vec3 c = mix(vColor, vColor * uPostureColor * 1.6, clamp(uPostureTint, 0.0, 0.8));
    c += vColor * vBand * 0.4;                  // flow band brightens as it sweeps
    c *= uGlowMul;
    // ARRIVAL ignition: a single-shot "ignition of awareness" flash, weighted to
    // the cortex (vAxis high), luminance-only — pushes RGB past the bloom knee so
    // the existing PostFX flares once. NEVER touches hue (sacred palette).
    float ignite = clamp(uIgnite, 0.0, 1.0) * smoothstep(0.45, 1.0, vAxis);
    // AWAKENING (poster phase 3): the cortex visibly HEATS (luminance only) while
    // the being notices/converses — weighted to the head (vAxis high), capped at
    // +0.5x so the existing bloom blooms but the hue is preserved.
    float awaken = clamp(uAwaken, 0.0, 1.0) * smoothstep(0.4, 1.0, vAxis) * 0.5;
    // ORCHESTRATION (poster phase 5): "nerves carry the state" — a luminance pulse
    // travels the SPINE/roots (vAxis low) at a metabolic rate while the being works.
    // Luminance only; hue preserved.
    float spineMask = 1.0 - smoothstep(0.35, 0.55, vAxis);
    // SOUL P3: while orchestrating, data flows DOWN the spine into the work — the
    // pulse travels brain→roots (+vAxis so the peak descends as uTime grows) with
    // sharper bead-like crests, reading as the being DRIVING the focused tab.
    float spineWave = 0.5 + 0.5 * sin(uTime * 3.0 + vAxis * 14.0);
    float statePulse = clamp(uStatePulse, 0.0, 1.0) * spineMask * (0.4 + 0.6 * pow(spineWave, 2.2));
    // REABSORPTION (poster phase 7, #wow signature 3): the finished work's energy
    // returns UP the spine as a TRAVELLING band (roots→cortex, decelerating), then the
    // cortex INHALES as it lands — a staged inward gesture, not a static glow lobe.
    // uReabsorbRise = the climbing band centre; uReabsorbGlow = the inhale bell. The band
    // appears just after launch and DISSOLVES into the head (handing off to the inhale).
    float rCenter = clamp(uReabsorbRise, 0.0, 1.0);
    float rBand = exp(-pow((vAxis - rCenter) / 0.16, 2.0))
                * smoothstep(0.015, 0.10, rCenter)
                * (1.0 - smoothstep(0.82, 1.0, rCenter));
    float reabsorbInhale = clamp(uReabsorbGlow, 0.0, 1.0) * smoothstep(0.45, 1.0, vAxis);
    float reabsorbGlow = rBand * 1.25 + reabsorbInhale * 0.6;
    // SUMMON / WAKE (#wow signature 2): the instant the being NOTICES you, a luminance
    // pulse RUSHES up the body (roots→cortex) and dissolves into the head — "the being
    // comes alive", handing off into the uAwaken cortex heat. Same travelling-band
    // mechanic; brighter + faster than reabsorption. Luminance only (hue preserved).
    float wCenter = clamp(uWakeWave, 0.0, 1.0);
    float wakeWave = exp(-pow((vAxis - wCenter) / 0.18, 2.0))
                   * smoothstep(0.01, 0.08, wCenter)
                   * (1.0 - smoothstep(0.85, 1.0, wCenter)) * 1.15;
    // REPLY RISE (poster phase 2/3): "response flows back UP the spine". While the
    // being speaks, a gaussian bead-band climbs the body axis roots(0)->cortex(1),
    // gated by uReplyRise so it fades in/out with the reply. Luminance only (hue
    // preserved, sacred palette) — the climb hands off into the uAwaken cortex heat.
    float riseActive = clamp(uReplyRise, 0.0, 1.0);
    float riseCenter = fract(uTime * 0.6);
    float riseBand = exp(-pow((vAxis - riseCenter) / 0.14, 2.0));
    float replyRise = riseActive * riseBand * 0.9;
    // VERTEBRAE REVEAL (poster phase 5): while orchestrating, the cord shows distinct
    // vertebral SEGMENTS — periodic bright bands down the spine (~12, matching the 12
    // SEGMENT_ANCHORS the tabs seat on), so "the spine extends and reveals vertebrae /
    // vertebrae are addressable seats" reads on the points being. Spine region only
    // (spineMask), luminance-only (hue preserved, sacred palette); uVertebrae 0 at rest.
    float vertSeg = 0.5 + 0.5 * sin(vAxis * 140.0);
    float vertebrae = clamp(uVertebrae, 0.0, 1.0) * spineMask * smoothstep(0.62, 0.98, vertSeg) * 0.7;
    vec3 emissive = c * intensity * uBodyOpacity * (1.0 + ignite * 2.5 + awaken + statePulse * 0.8 + reabsorbGlow + replyRise + vertebrae + wakeWave + clamp(uFlinch, 0.0, 1.0));
    // P2.6 ARRIVAL dark->light ignition (poster phase 1): the field LIGHTS UP from
    // darkness as it condenses (uArrival 0=scattered/dark -> 1=condensed/full), so the
    // being is "born from the data it travels through" rather than appearing fully lit.
    // #wow signature 2 (summon/wake): STAGED as a wave UP the body — the smoothstep START
    // is offset by vAxis, so the roots/spine light FIRST and the cortex lights LAST (a
    // 3-beat cascade, not a flat simultaneous fade-in). The end stays 0.82 so REST
    // (uArrival=1 >= 0.82) is byte-identical for EVERY point and roots are unchanged.
    // The cortex settle-bloom rides the existing uIgnite pulse (cortex-weighted). Floored
    // at uArrivalDark; luminance only (hue preserved, sacred palette).
    float arrivalLight = mix(uArrivalDark, 1.0, smoothstep(vAxis * 0.45, 0.82, uArrival));
    emissive *= arrivalLight;
    // P2.1 DEPTH HAZE (poster depth-slab): distant points recede toward zero so the
    // being reads as a VOLUME in space, not a flat decal. Additive-correct (dim, not
    // alpha-blend). uFogStart/Density/Strength are live __POINTFIELD dials; strength 0
    // reproduces the prior look exactly.
    float haze = 1.0 - exp(-max(vViewZ - uFogStart, 0.0) * uFogDensity);
    emissive *= (1.0 - clamp(haze * uHazeStrength, 0.0, 0.92));
    // P2.2 FILMIC HIGHLIGHT ROLLOFF: compress ONLY the hottest cores (luminance above
    // uRolloffKnee) so they stay COLORED instead of clipping to flat white. The bulk
    // of the field (below the knee) is byte-unchanged — the crisp, no-white-haze look
    // holds, because haze accumulation lives in the mid-values this never touches.
    // Hue/saturation preserved (luminance-only scale → sacred palette).
    float lum = max(dot(emissive, vec3(0.2126, 0.7152, 0.0722)), 1e-4);
    float over = max(lum - uRolloffKnee, 0.0);
    // Below the knee: rolledLum == lum (NO-OP — the crisp field is byte-unchanged).
    // Above the knee: compress only the excess. min(lum,knee) keeps the sub-knee
    // base intact; a bare knee+over would boost every dim point up to the knee and
    // wash the whole field (the regression live-verification caught).
    float rolledLum = min(lum, uRolloffKnee) + over / (1.0 + over * uRolloff);
    emissive *= rolledLum / lum;
    gl_FragColor = vec4(emissive, intensity);
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
      uSize: { value: 2.8 },       // finer puncta (poster's dense fine-dot read; pairs with the 200k+ count on the RTX 3050)
      uAttenK: { value: 0.2 },     // weak depth; 0 = fully flat
      uFogDensity: { value: 0.12 },// depth-haze falloff rate (was 0.02 + unused); pairs with uFogStart/uHazeStrength for the poster depth slab. Dial: window.__POINTFIELD.uFogDensity
      uGlowMul: { value: 1.35 },   // RTX-tuned crisp (was 2.55): lower emission so the dense cortex shows folds + the node lattice instead of a white-haze bloom. Still >1 so PostFX Bloom catches the brightest cores. Dial: window.__POINTFIELD.uGlowMul
      uBodyOpacity: { value: 1.0 },// damped to ~0.5 while orchestrating so inner memory-nodes show
      uIgnite: { value: 0 },       // single-shot arrival ignition flash (cortex-weighted luminance, no hue change)
      uAwaken: { value: 0 },       // conversation cortex-heat (cortex-weighted luminance, no hue change)
      uStatePulse: { value: 0 },   // orchestration spine state-pulse (spine-weighted luminance, no hue change)
      uReabsorbGlow: { value: 0 }, // reabsorption cortex-inhale bell (cortex-weighted luminance, no hue change)
      uReabsorbRise: { value: 0 }, // reabsorption travelling-band climb (roots→cortex)
      uWakeWave: { value: 1 }, // summon/wake luminance pulse climb (1 = dissolved/idle, so no wave at rest)
      uFlinch: { value: 0 }, // error-wince / approval-release transient luminance throb (0 = idle)
      uReplyRise: { value: 0 },    // conversation reply rise-band (spine->cortex luminance, no hue change)
      uVertebrae: { value: 0 },    // orchestration: reveal vertebral segments down the spine (luminance, no hue change). Dial: window.__POINTFIELD.uVertebrae
      uSprayHide: { value: 0 },    // orchestration: retract the cauda-equina tail (low aBand) so the bottom clears for the active surface
      uSprayBand: { value: 0.17 }, // body-axis cutoff below which a point is "tail". Dial: window.__POINTFIELD.uSprayBand
      uArrivalDark: { value: 0.12 }, // arrival ignition floor (born-from-darkness); raise toward 1 to disable. Dial: window.__POINTFIELD.uArrivalDark
      uFogStart: { value: 15.0 },     // depth haze begins ~at the brain (camera ~uRefDist). Dial: window.__POINTFIELD.uFogStart
      uHazeStrength: { value: 0.45 }, // subtle depth recession; raise on the RTX for a deeper poster slab. Dial: window.__POINTFIELD.uHazeStrength
      uRolloffKnee: { value: 1.6 },   // luminance below this is untouched (the crisp field holds). Dial: window.__POINTFIELD.uRolloffKnee
      uRolloff: { value: 0.5 },       // compress only the hottest cores so they stay colored. Dial: window.__POINTFIELD.uRolloff
      uBreath: overrides.uBreath ?? { value: 0.5 }, // shared organism breath (0.5 = rest midpoint); pass scene uBreath to phase-lock
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
  material.customProgramCacheKey = () => 'pointfield_v19';
  return material;
}
