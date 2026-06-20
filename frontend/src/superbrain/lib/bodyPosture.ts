/**
 * bodyPosture — the spectral-v1 posture-color system, bound to REAL organism state.
 *
 * The being reads its own status from its body: the whole organism shifts hue + flow
 * by the current lifecycle phase (the spec law — "status read from the body"). Colors
 * and flows are the operator's spectral-v1 bible (Living-Being Organism (spectral v1)),
 * extended with one amber HOLD posture for the human-approval gate (consistent with the
 * brainstem intake's existing amber).
 *
 * Pure contract: phase in -> posture {color, flow, label} out. Renderers blend this
 * over the canon regional palette via a tint factor; they never invent semantics.
 */
import type { OrganismLifecyclePhase } from './organismLifecycle';

export type BodyPostureKey = 'rest' | 'think' | 'stream' | 'hold' | 'complete' | 'error';

export interface BodyPosture {
  key: BodyPostureKey;
  /** sRGB 0-255, matching the spectral-v1 STATES. */
  color: readonly [number, number, number];
  /** 0..1 — how fast signal flows through spine/roots/nerves at this posture. */
  flow: number;
  /** spectral-v1 blend STRENGTH for this posture (rest≈0 clean → stream/error strong).
   *  This is what makes each posture's INTENSITY match the demoplan, not a flat tint. */
  tint: number;
  /** terse status word read off the body (no chrome). */
  label: string;
}

/** The spectral-v1 palette (+ amber HOLD). Sacred per the operator's bible. */
export const BODY_POSTURES: Record<BodyPostureKey, BodyPosture> = {
  rest: { key: 'rest', color: [150, 120, 255], flow: 0.16, tint: 0.0, label: 'Resting' },
  think: { key: 'think', color: [196, 78, 255], flow: 0.55, tint: 0.46, label: 'Thinking' },
  stream: { key: 'stream', color: [54, 214, 255], flow: 1.0, tint: 0.7, label: 'Streaming' },
  hold: { key: 'hold', color: [224, 168, 79], flow: 0.34, tint: 0.5, label: 'Holding' },
  complete: { key: 'complete', color: [62, 240, 160], flow: 0.3, tint: 0.55, label: 'Complete' },
  error: { key: 'error', color: [255, 92, 72], flow: 0.22, tint: 0.8, label: 'Error' },
};

/** Gold signal motes + snow dust accents (spectral-v1), not lifecycle states. */
export const POSTURE_GOLD: readonly [number, number, number] = [255, 210, 122];
export const POSTURE_SNOW: readonly [number, number, number] = [170, 205, 225];

const PHASE_TO_POSTURE: Record<OrganismLifecyclePhase, BodyPostureKey> = {
  booting: 'rest',
  arrival: 'think',
  rest: 'rest',
  attentive: 'think',
  intake: 'think',
  materializing: 'stream',
  working: 'stream',
  conducting: 'stream',
  approval_hold: 'hold',
  error_repair: 'error',
  completion_settle: 'complete',
  reabsorbing: 'complete',
};

export function postureKeyForPhase(phase: OrganismLifecyclePhase): BodyPostureKey {
  return PHASE_TO_POSTURE[phase] ?? 'rest';
}

/** Resolve the body posture for the current lifecycle phase. */
export function deriveBodyPosture(input: { phase: OrganismLifecyclePhase }): BodyPosture {
  return BODY_POSTURES[postureKeyForPhase(input.phase)];
}

/** Normalize an sRGB 0-255 triple to 0..1 for Three.js uniforms. */
export function postureColor01(
  color: readonly [number, number, number],
): [number, number, number] {
  return [color[0] / 255, color[1] / 255, color[2] / 255];
}

/**
 * Live tuning dial for the posture-color STRENGTH — the operator's FIDELITY call.
 * SuperbrainScene exposes this on `window.__POSTURE` in dev, so the strength can be
 * dialed in the real browser without a code change, e.g.:
 *   window.__POSTURE.brainTint = 0.72   // push toward the demoplan's dramatic shift
 *   window.__POSTURE.flowScale = 1.4    // faster signal flow
 * Read per-frame by the scene-root damping (brain/nerve — live) and at render by the
 * surfaces. Consumers HARD-cap the tint at <=0.8 (the regional palette stays legible).
 */
export const POSTURE_DIAL = {
  /** Global SCALE on each posture's intrinsic spectral tint, for the brain/nerve.
   *  1.0 = exact spectral-v1 / demoplan strength; push >1 for more drama. */
  brainScale: 1.0,
  /** Scale on each posture's tint for materialized surfaces + the conductor overlay. */
  surfaceScale: 0.62,
  /** Extra multiplier for the brainstem input surface (reads a touch stronger). */
  inputBoost: 1.15,
  /** global signal-flow speed multiplier. */
  flowScale: 1,
  /** Brain/nerve blend MODE: 0 = multiply (preserve the regional palette, canon-safe),
   *  1 = commit the whole body to the posture hue (the demoplan look). The operator
   *  dials this to match the demoplan exactly. Surfaces already commit (CPU lerp). */
  commit: 0.5,
};
