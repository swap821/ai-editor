'use client';

// ============================================================================
// PostFX.tsx — Post-Processing Pipeline
// ============================================================================
// Cinematic chain — JSX ORDER = PASS ORDER:
//   Bloom -> ChromaticAberration -> GradePre -> ToneMapping(AgX) -> GradePost
//   -> Vignette -> Noise
//
// Why ToneMapping lives here: @react-three/postprocessing forces
// renderer.toneMapping = NoToneMapping while EffectComposer is mounted, so
// without an explicit ToneMapping effect the scene has NO tone mapping at
// all — highlights hard-clip (flat pale-pink brain crown) and the frame
// reads "default renderer". AgX consumes renderer.toneMappingExposure
// (three uploads it to every program); WorkspaceCanvas sets it to 1.6.
//
// FilmGrade (two tiny custom Effects via wrapEffect):
//   • GradePre  — BEFORE the tonemap, scene-referred HDR: log-space contrast
//     around the mid-grey pivot.
//   • GradePost — AFTER the tonemap, display-referred [0,1]: W3C soft-light
//     split-tone (teal shadows / amber highlights) + vibrance. NO lift
//     control — softLight(0, s) = 0 preserves true black; the void stays void.
// Both grades merge into the existing EffectPass (only convolution effects
// like Bloom split passes) — expected cost < 0.5 ms.
//
// All values are wired from POST_FX in src/lib/constants.ts — tune THERE.
// ============================================================================

import {
  EffectComposer,
  Bloom,
  ChromaticAberration,
  ToneMapping,
  Vignette,
  Noise,
  wrapEffect,
} from '@react-three/postprocessing';
import { BlendFunction, Effect, ToneMappingMode } from 'postprocessing';
import { POST_FX } from '@/lib/constants';
import { Uniform, Vector2, Vector3 } from 'three';
import { useMemo } from 'react';
import { useQualityTier } from '@/components/QualityTierProvider';

// ── GradePre — scene-referred log-space contrast (runs BEFORE AgX) ─────────
// Pivot 0.4135884 is mid-grey (0.18) in the log encoding; contrast > 1
// steepens the curve in log space without clipping HDR scene values.

const GRADE_PRE_FRAGMENT = /* glsl */ `
  uniform float uContrast;

  void mainImage(const in vec4 inputColor, const in vec2 uv, out vec4 outputColor) {
    vec3 c = inputColor.rgb;
    vec3 lc = (log2(max(c, vec3(1e-5))) + 9.72) / 17.52;
    lc = (lc - 0.4135884) * uContrast + 0.4135884;
    c = exp2(lc * 17.52 - 9.72);
    outputColor = vec4(c, inputColor.a);
  }
`;

class GradePreEffect extends Effect {
  constructor({ contrast = POST_FX.grade.contrast }: { contrast?: number } = {}) {
    super('GradePreEffect', GRADE_PRE_FRAGMENT, {
      blendFunction: BlendFunction.SRC,
      uniforms: new Map<string, Uniform>([['uContrast', new Uniform(contrast)]]),
    });
  }
}

// ── GradePost — display-referred split-tone + vibrance (runs AFTER AgX) ────
// Split-tone is applied in gamma space (1/2.2) where soft-light behaves
// perceptually; vibrance back in linear. softLight per the W3C compositing
// spec, per channel: D(b) = ((16b-12)b+4)b for b <= 0.25, sqrt(b) above.

const GRADE_POST_FRAGMENT = /* glsl */ `
  uniform vec3 uShadowTint;
  uniform vec3 uHighTint;
  uniform float uBalance;
  uniform float uVibrance;

  float fgLuma(const in vec3 c) {
    return dot(c, vec3(0.2126, 0.7152, 0.0722));
  }

  vec3 fgSoftLight(const in vec3 b, const in vec3 s) {
    vec3 d = mix(((16.0 * b - 12.0) * b + 4.0) * b, sqrt(b), step(0.25, b));
    return mix(
      b - (1.0 - 2.0 * s) * b * (1.0 - b),
      b + (2.0 * s - 1.0) * (d - b),
      step(0.5, s)
    );
  }

  void mainImage(const in vec4 inputColor, const in vec2 uv, out vec4 outputColor) {
    vec3 c = inputColor.rgb;

    // Split-tone in gamma space.
    vec3 g = pow(max(c, vec3(0.0)), vec3(1.0 / 2.2));
    float t = clamp(fgLuma(clamp(g, 0.0, 1.0)) + uBalance, 0.0, 1.0);
    vec3 sh = mix(vec3(0.5), uShadowTint, 1.0 - t);
    vec3 hi = mix(vec3(0.5), uHighTint, t);
    g = fgSoftLight(g, sh);
    g = fgSoftLight(g, hi);
    c = pow(g, vec3(2.2));

    // Vibrance: the (1 - sat) term boosts AgX-flattened low-chroma regions
    // while protecting already-saturated filaments.
    float l = fgLuma(c);
    float sat = max(c.r, max(c.g, c.b)) - min(c.r, min(c.g, c.b));
    c = l + (c - l) * (1.0 + uVibrance * (1.0 - clamp(sat, 0.0, 1.0)));

    outputColor = vec4(c, inputColor.a);
  }
`;

interface GradePostOptions {
  shadowTint?: [number, number, number];
  highTint?: [number, number, number];
  balance?: number;
  vibrance?: number;
}

class GradePostEffect extends Effect {
  constructor({
    shadowTint = POST_FX.grade.shadowTint,
    highTint = POST_FX.grade.highTint,
    balance = POST_FX.grade.balance,
    vibrance = POST_FX.grade.vibrance,
  }: GradePostOptions = {}) {
    super('GradePostEffect', GRADE_POST_FRAGMENT, {
      blendFunction: BlendFunction.SRC,
      uniforms: new Map<string, Uniform>([
        ['uShadowTint', new Uniform(new Vector3(...shadowTint))],
        ['uHighTint', new Uniform(new Vector3(...highTint))],
        ['uBalance', new Uniform(balance)],
        ['uVibrance', new Uniform(vibrance)],
      ]),
    });
  }
}

const GradePre = wrapEffect(GradePreEffect);
const GradePost = wrapEffect(GradePostEffect);

export default function PostFX() {
  // Post-FX extras follow the PERF tier (they may breathe while the model
  // thinks); the scene's geometry follows the structural tier elsewhere.
  const { perfTier: tier } = useQualityTier();

  const aberrationOffset = useMemo(
    () => new Vector2(POST_FX.chromaticAberration.offset[0], POST_FX.chromaticAberration.offset[1]),
    []
  );

  return (
    <EffectComposer multisampling={0}>
      {/* Bloom: 0.55 threshold catches stars/aura glow; intensity raised to
          0.65 because AgX compresses the highlights bloom feeds on */}
      <>{tier !== 'low' && (
        <Bloom
          intensity={POST_FX.bloom.intensity}
          luminanceThreshold={POST_FX.bloom.luminanceThreshold}
          luminanceSmoothing={POST_FX.bloom.luminanceSmoothing}
          mipmapBlur={tier === 'high'}
        />
      )}</>

      {/* Chromatic Aberration: subtle RGB split at screen edges */}
      <>{tier === 'high' && (
        <ChromaticAberration
          blendFunction={BlendFunction.NORMAL}
          offset={aberrationOffset}
          radialModulation={true}
          modulationOffset={0.2}
        />
      )}</>

      {/* FilmGrade pass 1: log contrast on scene-referred HDR */}
      <GradePre />

      {/* AgX display transform — restores highlight rolloff (rose gradation
          on the brain crown instead of a clipped plateau) and dense blacks */}
      <ToneMapping mode={ToneMappingMode.AGX} />

      {/* FilmGrade pass 2: teal/amber split-tone + vibrance on display-referred */}
      <GradePost />

      {/* Vignette: darkness eased 0.7 -> 0.62 — the grade now carries the
          cinema; the heavier vignette was crushing corner text */}
      <Vignette
        offset={POST_FX.vignette.offset}
        darkness={POST_FX.vignette.darkness}
        blendFunction={BlendFunction.NORMAL}
      />

      {/* Noise: subtle film grain for tactile texture — must stay LAST */}
      <>{tier === 'high' && (
        <Noise
          premultiply
          blendFunction={BlendFunction.ADD}
          opacity={POST_FX.noise.opacity}
        />
      )}</>
    </EffectComposer>
  );
}
