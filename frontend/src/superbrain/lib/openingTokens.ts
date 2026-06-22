// openingTokens.ts — the ONE source of truth for P1 "Opening" motion.
// Logic helpers (openingMotion.ts) and the scene shaders read the SAME
// numbers, so timing/easing never drift between the unit-tested curve and
// the rendered frame. Transform/opacity/filter only — no layout.

/** Coalescence + awakening durations (ms). Arrival is a RARE, cinematic
 *  event, so it lives at the top of the 3–4s band. */
export const OPENING_TIMINGS = {
  /** First-ever load: knowledge-field streams in and condenses. */
  coalescenceMs: 3500,
  /** Window inside coalescence where the ignition pulse peaks. */
  ignitionPeakMs: 2600,
  /** Every return: dormant cortex lights from a seed. */
  awakeningMs: 2600,
  /** First user-speak "notice" reaction (attentive lean + brighten). */
  awakenNoticeMs: 320,
  /** ATTENTIVE holds this long after the last directive, then eases to REST. */
  attentiveDecayMs: 5000,
  /** Breath cycle at rest — the one essential ambient loop. */
  breathCycleMs: 5000,
  /** Per-element nerve-lighting stagger. */
  nerveStaggerMs: 40,
} as const;

/** Custom cubic-bezier control points (NEVER bare ease / ease-in-out).
 *  Expressive ease-out for the rare arrival; tighter for the notice. */
export const OPENING_EASING = {
  /** Cinematic settle: slow-out, gentle overshoot-free landing. */
  coalescence: [0.16, 1, 0.3, 1] as const,
  /** Awakening seed spread. Consumed by openingMotion.ts once
   *  ArrivalMode.AWAKENING is wired in the scene (P1 Task 5). */
  awaken: [0.22, 1, 0.36, 1] as const,
  /** Quick attentive notice. */
  notice: [0.32, 0.72, 0, 1] as const,
} as const;

/** Coalescence never scales the cortex mesh from 0 — it fades + scales from
 *  this floor to 1 (design law: do NOT start scale from 0). */
export const COALESCENCE_SCALE_FLOOR = 0.85;
