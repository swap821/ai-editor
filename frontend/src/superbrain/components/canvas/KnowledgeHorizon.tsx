'use client';

// ============================================================================
// KnowledgeHorizon — PHOTOGRAPHIC deep-space sky dome.
// ============================================================================
// Rewritten per the face-lift research pass:
//   • IQ domain-warped fbm nebula (q -> r -> f), colored by the INTERMEDIATE
//     warp vectors so the gas has internal structure instead of tinted noise.
//   • Hubble-SHO palette (near-black blue -> deep teal -> amber-gold -> warm
//     near-white) authored in TRUE LINEAR space — the EffectComposer applies
//     the linear->sRGB transfer on output, so sRGB-as-linear hex renders ~3x
//     too bright (the old purple-wash bug).
//   • Luminance hierarchy: density = pow(t, 2.8), ridged striation, dark dust
//     lanes that occlude both gas and stars (occlusion = strongest depth cue).
//   • One soft diagonal galactic band lower-left -> upper-right behind the
//     brain; star density 4x inside it; off-band corners near-empty.
//   • Photographic stars: cell-hash placement, pow(hash,9) brightness law,
//     blackbody tints, sub-pixel energy conservation (grain, not confetti),
//     hard 2-3px discs, dim-star twinkle with chromatic phase offset, and
//     1px diffraction spikes on only the very brightest.
//   • Three-layer differential pointer parallax (far 0.02 / mid 0.06 / near
//     0.14) + glacial warp drift; interleaved-gradient-noise dither kills
//     the banding flat dark gradients guarantee.
// The old horizon filament plane is deleted — its unanchored parabolic arcs
// were flagged as an anti-pattern; the galactic band replaces its role.
// ============================================================================

import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

const SKY_VERTEX_SHADER = `
  varying vec3 vWorldPosition;

  void main() {
    vWorldPosition = (modelMatrix * vec4(position, 1.0)).xyz;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const SKY_FRAGMENT_SHADER = `
  precision highp float;

  uniform float uTime;
  uniform float uActivity;
  uniform vec2 uPointer; // eased on CPU (lerp 0.05/frame)
  varying vec3 vWorldPosition;

  // ── deterministic hash / noise ─────────────────────────────────────────
  float hash21(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
  }

  float valueNoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(
      mix(hash21(i), hash21(i + vec2(1.0, 0.0)), u.x),
      mix(hash21(i + vec2(0.0, 1.0)), hash21(i + 1.0), u.x),
      u.y
    );
  }

  // 3 octaves; the IQ warp uses 5 evaluations + 1 dust field = 6 total/pixel.
  float fbm3(vec2 p) {
    float sum = 0.0;
    float amplitude = 0.5;
    for (int i = 0; i < 3; i++) {
      sum += valueNoise(p) * amplitude;
      p = p * 2.03 + vec2(13.7, 7.9);
      amplitude *= 0.5;
    }
    return sum;
  }

  // Interleaved gradient noise — final-color dither.
  float ign(vec2 p) {
    return fract(52.9829189 * fract(dot(p, vec2(0.06711056, 0.00583715))));
  }

  // ── photographic star layer (cell hash) ────────────────────────────────
  // pix = screen-pixel footprint in uv units (fwidth), so disc radii and
  // spike lengths are authored in PIXELS regardless of dome distortion.
  vec3 starLayer(vec2 uv, float scale, float pix, float densityProb, float brightMul, float spikesOn) {
    vec2 g = uv * scale;
    vec2 cell = floor(g);
    vec2 fc = fract(g);

    float hPresence = hash21(cell + 31.7);
    float gate = step(hPresence, densityProb);

    // Brightness power law: thousands of faint grains, a handful dominant.
    float hB = hash21(cell + 7.3);
    float b = pow(hB, 9.0) * 1.5 * brightMul;

    // Placement jitter: spike layers keep an inset so 14px spikes stay inside
    // their cell (no neighbor taps); dense layers spread wide to avoid any
    // perceivable lattice.
    float inset = mix(0.10, 0.28, spikesOn);
    vec2 pos = vec2(hash21(cell + 13.1), hash21(cell + 17.9)) * (1.0 - 2.0 * inset) + inset;
    vec2 dPx = (fc - pos) / (scale * pix);
    float distPx = length(dPx);

    // Sub-pixel energy conservation: footprint < 1px -> draw 1px, dim by
    // the area ratio. Hard 2-3px smoothstep discs, never soft sprites.
    float rPx = sqrt(max(b, 0.0)) * 2.4;
    float drawR = clamp(rPx, 1.0, 3.0);
    float energy = min(1.0, (rPx * rPx) / (drawR * drawR));
    float disc = smoothstep(drawR, drawR * 0.35, distPx);

    // Twinkle only below 40% max brightness; the dimmest get a +-0.3 rad
    // chromatic phase offset between red and blue.
    float twinkleGate = step(b, 0.6);
    float chroma = step(b, 0.12) * 0.3;
    float rate = 1.2 + hash21(cell + 3.3) * 2.6;
    float phase = hash21(cell + 9.1) * 6.28318;
    vec3 tw = mix(
      vec3(1.0),
      0.82 + 0.18 * sin(uTime * rate + phase + vec3(chroma, 0.0, -chroma)),
      twinkleGate
    );

    // Blackbody tints: ~75% near-white, ~15% warm orange, ~10% blue-white;
    // saturation kept < 0.25. Never pure white (ACES clips it).
    float hT = hash21(cell + 23.7);
    vec3 tint = vec3(0.96, 0.97, 1.0);
    tint = mix(tint, vec3(1.0, 0.87, 0.76), step(hT, 0.15));
    tint = mix(tint, vec3(0.80, 0.88, 1.0), step(0.90, hT));

    // Diffraction spikes: top ~1.5% brightest only — two 1px axis-aligned
    // lines, length ~ sqrt(brightness) capped at 14px, inverse-square falloff.
    float spike = 0.0;
    if (spikesOn * step(0.985, hB) > 0.5) {
      float lenPx = min(sqrt(b) * 9.0, 14.0);
      float ax = abs(dPx.x);
      float ay = abs(dPx.y);
      float sx = smoothstep(1.1, 0.25, ay) * step(ax, lenPx) / (1.0 + ax * ax * 0.5);
      float sy = smoothstep(1.1, 0.25, ax) * step(ay, lenPx) / (1.0 + ay * ay * 0.5);
      spike = (sx + sy) * 0.8;
    }

    return tint * tw * gate * b * (disc * energy + spike);
  }

  void main() {
    vec3 dir = normalize(vWorldPosition);
    vec2 uv = vec2(
      atan(dir.z, dir.x) * 0.15915494 + 0.5,
      asin(clamp(dir.y, -1.0, 1.0)) * 0.31830989 + 0.5
    );
    float pix = max(length(fwidth(uv)), 1e-7);

    // ── three-layer differential parallax (the depth cue) ────────────────
    vec2 par = uPointer * 0.08;
    vec2 uvFar  = uv + par * 0.02; // nebula
    vec2 uvMid  = uv + par * 0.06; // star carpet + dust lanes
    vec2 uvNear = uv + par * 0.14; // sparse bright motes

    // ── composition: one soft diagonal galactic band, lower-left -> upper-
    // right BEHIND the brain. Core nudged off dead center (no hot spot where
    // the brain lives); off-band corners stay near-empty.
    vec3 bandNormal = normalize(vec3(1.0, -1.35, 0.0));
    float bandD = dot(dir, bandNormal) - 0.12;
    float band = exp(-bandD * bandD * 6.0);

    // ── IQ domain-warped nebula (q -> r -> f), glacial drift ─────────────
    float drift = uTime * 0.006;
    vec2 p = uvFar * 16.0; // ~2-3 noise repeats across the visible sky
    vec2 q = vec2(
      fbm3(p + vec2(drift, drift * 0.6)),
      fbm3(p + vec2(5.2, 1.3) - vec2(drift * 0.7, drift * 0.4))
    );
    vec2 r = vec2(
      fbm3(p + 2.8 * q + vec2(1.7, 9.2) + vec2(drift * 0.5, 0.0)),
      fbm3(p + 2.8 * q + vec2(8.3, 2.8) - vec2(0.0, drift * 0.4))
    );
    float f = fbm3(p + 2.8 * r);

    // Normalize fbm range so the top 2-3% of density actually exists.
    float t = clamp((f - 0.16) * 1.8, 0.0, 1.0);

    // Ridged multifractal striation — filamentary gas, not blurry fog.
    float ridge = 1.0 - abs(2.0 * valueNoise(p * 1.7 + vec2(3.1, 8.7) + drift) - 1.0);
    float striation = 0.4 + 0.6 * pow(ridge, 3.0);

    // Dark dust lanes (mid layer): occlude nebula AND stars.
    float dRaw = fbm3(uvMid * 9.0 + vec2(2.4, 7.7) + drift * 0.5);
    float d = clamp((dRaw - 0.2) * 1.4, 0.0, 1.0);
    float dustNebula = mix(0.30, 1.0, smoothstep(0.75, 0.40, d));
    float starOcclusion = smoothstep(0.7, 0.3, d);

    // Regional palette dominance: ultra-low-frequency field; left sky leans
    // teal, right leans amber.
    float regionNoise = valueNoise(uvFar * 3.5 + 11.3);
    float region = clamp(0.5 + dir.x * 0.8 + (regionNoise - 0.5) * 0.8, 0.0, 1.0);

    // ── Hubble SHO ramp, authored in LINEAR (srgb-to-linear converted) ────
    vec3 C_BLACK  = vec3(0.0015, 0.0024, 0.0052); // #050810
    vec3 C_TEAL   = vec3(0.0030, 0.0423, 0.0578); // #0a3a44
    vec3 C_AMBER  = vec3(0.4342, 0.1878, 0.0513); // #b07840
    vec3 C_WHITE  = vec3(0.8714, 0.8069, 0.6868); // #f0e8d8 — top 2-3% only
    vec3 C_BLUE   = vec3(0.0100, 0.0250, 0.0700); // secondary hue (by |q|)
    vec3 C_VIOLET = vec3(0.0800, 0.0400, 0.2000); // tertiary accent (by r.y)

    float tealW = 1.0 - 0.65 * region;
    float amberW = 0.35 + 0.65 * region;
    vec3 gas = C_BLACK;
    gas = mix(gas, C_TEAL, smoothstep(0.15, 0.60, t) * tealW);
    gas = mix(gas, C_AMBER, smoothstep(0.55, 0.88, t) * amberW);
    gas = mix(gas, C_WHITE, smoothstep(0.92, 1.0, t));

    // Color by the intermediate warp vectors — internal gas structure.
    gas = mix(gas, C_BLUE, clamp(length(q) * 0.9 - 0.3, 0.0, 1.0) * 0.30);
    gas += C_VIOLET * smoothstep(0.45, 0.85, r.y) * 0.12;

    // ── luminance hierarchy: 80% of sky < 0.04, thin filaments only ───────
    float density = pow(t, 2.8) * striation;
    float bandAmp = mix(0.12, 1.0, band);
    // Calm the exact view center — the brain owns that real estate.
    float centerCalm = 1.0 - 0.35 * smoothstep(0.92, 0.995, -dir.z);
    // Gain audited so the absolute peak (t=1, striation=1, band=1, full
    // activity) stays far under the 1.0 bloom knee: C_WHITE luma 0.812
    // * 0.58 = 0.47. The gas NEVER blooms; only stars may sparkle.
    vec3 nebula = gas * density * dustNebula * bandAmp * centerCalm
      * (0.52 + uActivity * 0.06);

    // Far layer reads farther when desaturated ~30%.
    float nebLuma = dot(nebula, vec3(0.2126, 0.7152, 0.0722));
    nebula = mix(nebula, vec3(nebLuma), 0.30);

    // ── stars: density 4x inside the band, dust-occluded ──────────────────
    float midProb = mix(0.22, 0.88, band);
    float nearProb = mix(0.16, 0.64, band);
    vec3 stars = vec3(0.0);
    stars += starLayer(uvMid + 3.7, 420.0, pix, midProb, 0.7, 0.0);
    stars += starLayer(uvNear + 9.2, 150.0, pix, nearProb, 1.0, 1.0);
    stars *= starOcclusion;

    vec3 color = nebula + stars;

    // Mandatory dither — kills the banding flat dark gradients guarantee.
    color += (ign(gl_FragCoord.xy) - 0.5) / 255.0 * 3.0;

    gl_FragColor = vec4(max(color, 0.0), 1.0);
  }
`;

export default function KnowledgeHorizon({ activity }: { activity: number }) {
  const skyMaterialRef = useRef<THREE.ShaderMaterial>(null);
  const smoothedActivityRef = useRef(activity);
  const easedPointerRef = useRef(new THREE.Vector2(0, 0));

  const skyUniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uActivity: { value: 0 },
      uPointer: { value: new THREE.Vector2(0, 0) },
    }),
    [],
  );

  useFrame((state, delta) => {
    smoothedActivityRef.current = THREE.MathUtils.damp(
      smoothedActivityRef.current,
      THREE.MathUtils.clamp(activity, 0, 1),
      3,
      delta,
    );

    // Eased pointer for the differential parallax: frame-rate independent damp.
    easedPointerRef.current.x = THREE.MathUtils.damp(easedPointerRef.current.x, state.pointer.x, 3.0, delta);
    easedPointerRef.current.y = THREE.MathUtils.damp(easedPointerRef.current.y, state.pointer.y, 3.0, delta);

    if (skyMaterialRef.current) {
      skyMaterialRef.current.uniforms.uTime.value = state.clock.elapsedTime;
      skyMaterialRef.current.uniforms.uActivity.value = smoothedActivityRef.current;
      (skyMaterialRef.current.uniforms.uPointer.value as THREE.Vector2).copy(
        easedPointerRef.current,
      );
    }
  });

  return (
    <mesh renderOrder={-2} frustumCulled={false}>
      <sphereGeometry args={[90, 48, 48]} />
      <shaderMaterial
        ref={skyMaterialRef}
        vertexShader={SKY_VERTEX_SHADER}
        fragmentShader={SKY_FRAGMENT_SHADER}
        uniforms={skyUniforms}
        side={THREE.BackSide}
        depthWrite={false}
        toneMapped={false}
      />
    </mesh>
  );
}
