// voyageDrift (north-star: "an autonomous AI-OS superbrain travelling constant
// into the deep-vast knowledgeable infinite space — the brain never stops
// voyaging"). A perpetual, gentle whole-body drift + bank for the points home
// being — turns the static turntable pose back into a voyaging organism
// (poster-gap audit P1.4 / Motion-cohesion).
//
// Pure + deterministic in `time` (seconds). The renderer adds these offsets to
// the brain GROUP — brain + spine ride the SAME matrix, so the spine weld stays
// rigid (this is a whole-body voyage, never an independent brain bob). The sine
// basis (0.16 / 0.09 Hz-ish) is shared with the scene's brainDriftX so the
// camera's lookAt pursuit (CameraDrift) stays phase-coherent with the being.
// Reduced-motion suppresses the travel (no vestibular drift). Geometry/motion
// only — sacred palette untouched.

/** ~45% of the mesh-branch drift amplitude (audit: "40-50% mesh amplitude"). */
export const VOYAGE_AMPLITUDE = 0.45;
/** Drift-velocity → bank-roll gain (matches the scene's BANK_GAIN). */
export const VOYAGE_BANK_GAIN = 0.633;

export interface VoyageDriftInput {
  /** Scene clock elapsed time, in seconds. */
  time: number;
  /** Reduced-motion: suppress the voyage travel entirely. */
  reducedMotion: boolean;
}

export interface VoyageDrift {
  /** Add to group position.x — the slow lateral wander through space. */
  offsetX: number;
  /** Add to group position.y — a gentle vertical swell. */
  offsetY: number;
  /** Add to group rotation.z — banks into the turn (ship-like). */
  roll: number;
}

// Same frequencies as the scene's brainDriftX/brainDriftVelocityX so the camera
// pursuit tracks the being. offsetX is the lateral wander; driftVelX is its time
// derivative (the bank follows the NEGATIVE direction of the lateral velocity).
const driftX = (t: number) => Math.sin(t * 0.16) * 0.24 + Math.cos(t * 0.09) * 0.1;
const driftVelX = (t: number) => Math.cos(t * 0.16) * 0.0384 - Math.sin(t * 0.09) * 0.009;
const swellY = (t: number) => Math.sin(t * 0.13) * 0.06 + Math.cos(t * 0.07) * 0.03;

const round4 = (v: number) => Math.round(v * 10000) / 10000 + 0; // +0 normalises -0 → 0

export function deriveVoyageDrift({ time, reducedMotion }: VoyageDriftInput): VoyageDrift {
  if (reducedMotion) return { offsetX: 0, offsetY: 0, roll: 0 };
  const a = VOYAGE_AMPLITUDE;
  return {
    offsetX: round4(driftX(time) * a),
    offsetY: round4(swellY(time) * a),
    roll: round4(-driftVelX(time) * VOYAGE_BANK_GAIN * a),
  };
}
