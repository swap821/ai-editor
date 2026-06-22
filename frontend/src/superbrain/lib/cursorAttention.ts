// cursorAttention (poster phase 3 — "the being NOTICES you"): the living being
// leans + the cortex brightens toward the operator's pointer. Pure contract: the
// renderer damps the raw pointer and passes it here, then applies the returned
// lean (added onto the static body rotation) and folds the brighten into the
// cortex-heat uniform. No time, no randomness, no three.js — fully testable.
//
// NOTE: distinct from brainAttentionPosture (the being leaning toward a focused
// TAB) and attentionConduction (the nerve paths between tabs). This one is about
// the cursor — the being attending to the human, not its own workspace.

/** Max yaw (rad) added to the body rotation.y at the screen edge — a degree or two. */
export const ATTENTION_MAX_YAW = 0.06;
/** Max pitch (rad) added to the body rotation.x at the screen edge. */
export const ATTENTION_MAX_PITCH = 0.04;
/** Max cortex-heat (0..1) folded into uAwaken when fully engaged. A gentle notice. */
export const ATTENTION_BRIGHTEN = 0.32;

export interface CursorAttentionInput {
  /** Pointer X in NDC (-1 left .. +1 right). Pre-damped by the renderer. */
  pointerX: number;
  /** Pointer Y in NDC (-1 bottom .. +1 top). Pre-damped by the renderer. */
  pointerY: number;
  /** Master gate — the being is attending to the cursor (false → fully neutral). */
  active: boolean;
  /** Reduced-motion: suppress the lean (no vestibular travel); keep the brighten. */
  reducedMotion: boolean;
}

export interface CursorAttention {
  /** Add to body rotation.y (toward the pointer's horizontal position). */
  leanYaw: number;
  /** Add to body rotation.x (toward the pointer's vertical position). */
  leanPitch: number;
  /** Cortex-heat 0..1 to fold (max) into the awaken uniform — brightens toward you. */
  brighten: number;
}

const NEUTRAL: CursorAttention = { leanYaw: 0, leanPitch: 0, brighten: 0 };

const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));
const round4 = (v: number) => Math.round(v * 10000) / 10000 + 0; // +0 normalises -0 → 0

export function deriveCursorAttention({
  pointerX,
  pointerY,
  active,
  reducedMotion,
}: CursorAttentionInput): CursorAttention {
  if (!active) return NEUTRAL;
  const cx = clamp(pointerX, -1, 1);
  const cy = clamp(pointerY, -1, 1);
  // Engagement = how far the cursor sits from dead-centre (capped at 1 in the
  // corners). Centre → minimal notice; edges → full warmth. The lean carries the
  // DIRECTION, this scalar carries the INTENSITY of the cortex brightening.
  const engagement = Math.min(1, Math.hypot(cx, cy));
  // The lean follows the cursor; the pitch sign matches the mesh path
  // (rotation.x += -pointerY), so the head tips UP toward a high cursor.
  const leanYaw = reducedMotion ? 0 : round4(cx * ATTENTION_MAX_YAW);
  const leanPitch = reducedMotion ? 0 : round4(-cy * ATTENTION_MAX_PITCH);
  // Brighten survives reduced-motion (it is luminance, not travel).
  const brighten = round4(engagement * ATTENTION_BRIGHTEN);
  return { leanYaw, leanPitch, brighten };
}
