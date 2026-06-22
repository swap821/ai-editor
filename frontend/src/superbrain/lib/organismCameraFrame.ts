// organismCameraFrame (Step-1 framing): make the camera frame the BEING instead of
// leaving it lost in a black void on portrait/mobile. The live points camera is a
// static PerspectiveCamera (fov 26) + OrbitControls (target [0,-0.5,0]); it used
// the same framing at every aspect, so a tall phone frame left the organism small
// + low with a giant dead zone.
//
// This pure contract returns an aspect-responsive frame; the points framing
// controller damps the camera FOV + the OrbitControls target height toward it
// (the two levers that don't fight OrbitControls — it owns distance). Narrower fov
// on portrait ENLARGES the being to fill the tall frame; a raised target lifts it
// out of the void. Geometry/framing only — sacred palette untouched.
//
// SAFETY: at a wide desktop aspect the frame is the current look exactly
// (fov 26 / targetY -0.5) — only portrait reframes.

export interface CameraFrameInput {
  /** viewport width / height. >1 landscape, <1 portrait. */
  aspect: number;
  /** materialized work surfaces in play (orchestration widens fov to fit them). */
  activeSurfaceCount: number;
}

export interface OrganismCameraFrame {
  /** vertical field of view (deg) — NARROWER on portrait to enlarge the being. */
  fov: number;
  /** OrbitControls target height — RAISED on portrait so the organism climbs up. */
  targetY: number;
}

/** Wide-desktop anchor = the exact current points framing (no regression). */
const LANDSCAPE: OrganismCameraFrame = { fov: 26, targetY: -0.5 };
/** Tall-portrait anchor: narrower fov (bigger being) + slightly raised target.
 *  Balanced so the crown keeps headroom and more of the CNS stays in-frame than a
 *  harder zoom; the operator fine-tunes per-device via the window.__CAMFRAME dial. */
const PORTRAIT: OrganismCameraFrame = { fov: 22, targetY: -0.4 };

export const LANDSCAPE_ASPECT = 1.5;
export const PORTRAIT_ASPECT = 0.62;
/** Max fov widening when surfaces are seated (so they aren't cropped). */
const ORCHESTRATE_FOV_GAIN = 5;

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const round3 = (v: number) => Math.round(v * 1000) / 1000;

export function deriveOrganismCameraFrame({ aspect, activeSurfaceCount }: CameraFrameInput): OrganismCameraFrame {
  // 1 at landscape, 0 at portrait.
  const wide = clamp((aspect - PORTRAIT_ASPECT) / (LANDSCAPE_ASPECT - PORTRAIT_ASPECT), 0, 1);
  const fovBase = lerp(PORTRAIT.fov, LANDSCAPE.fov, wide);
  const targetY = lerp(PORTRAIT.targetY, LANDSCAPE.targetY, wide);
  // Orchestration: widen fov a touch so seated surfaces around the being aren't
  // cropped (capped at ~3 surfaces of effect).
  const orchestrateFov = (Math.min(activeSurfaceCount, 3) / 3) * ORCHESTRATE_FOV_GAIN;
  return {
    fov: round3(fovBase + orchestrateFov),
    targetY: round3(targetY),
  };
}
