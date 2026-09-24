import type { BeingPhase, BeingPresentation } from './beingPresentation';
import { BODY_POSTURES, postureHex, type BodyPostureKey } from '../../superbrain/lib/bodyPosture';

/**
 * The small, renderer-facing projection of the living-being contract.
 *
 * This module deliberately contains no Three.js and no authority decisions. It
 * converts the already-derived BeingPresentation into bounded visual
 * parameters so the DOM status and the organism can share one semantic source
 * without either renderer reinterpreting backend events independently.
 */
export interface BeingScenePresentation {
  posture: BodyPostureKey;
  color: string;
  energy: number;
  coherence: number;
  flow: number;
  motionIntensity: number;
  haloOpacity: number;
  haloScale: number;
  isHeld: boolean;
}

const clamp = (value: number): number => Math.max(0, Math.min(1, value));

const postureForPhase: Record<BeingPhase, BodyPostureKey> = {
  booting: 'rest',
  ready: 'rest',
  listening: 'think',
  understanding: 'think',
  planning: 'think',
  'awaiting-human': 'hold',
  acting: 'stream',
  verifying: 'complete',
  learning: 'complete',
  reflex: 'stream',
  recovering: 'error',
  degraded: 'error',
  stale: 'error',
  stopped: 'error',
};

export function deriveBeingScenePresentation(
  presentation: BeingPresentation,
): BeingScenePresentation {
  const posture = postureForPhase[presentation.phase];
  const bodyPosture = BODY_POSTURES[posture];
  const energy = clamp(presentation.energy);
  const coherence = clamp(presentation.coherence);
  const motionIntensity = clamp(presentation.motionIntensity);

  // The halo is an acknowledgement cue, not an authority cue: it stays
  // bounded and visible for stale/stopped states while the body itself stops
  // moving when the semantic contract says motion is unsafe or unwanted.
  const haloOpacity = clamp(0.04 + (energy * 0.12) + ((1 - coherence) * 0.06));
  const haloScale = 0.92 + (energy * 0.2);
  const flow = clamp(bodyPosture.flow * (0.55 + (energy * 0.45)));

  return {
    posture,
    color: postureHex(posture),
    energy,
    coherence,
    flow,
    motionIntensity,
    haloOpacity,
    haloScale,
    isHeld: presentation.phase === 'awaiting-human',
  };
}
