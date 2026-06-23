/**
 * motionEasing — the shared authored-easing toolkit for the being's SIGNATURE
 * motion moments (panel bloom, summon/wake, reabsorption, cascade, dismiss).
 *
 * The being's AMBIENT motion stays on THREE.MathUtils.damp() (breath, flow speed,
 * cursor lean). These curves are for the watched, gestural moments that need
 * authored character — anticipation, ease-out deceleration, an overshoot "catch",
 * and staggered layer reveals — instead of a uniform exponential glide.
 *
 * Pure, deterministic, no three.js / React. Inputs clamp at the [0,1] boundary.
 */

/** Clamp to [0,1]. */
export function clamp01(t: number): number {
  return t < 0 ? 0 : t > 1 ? 1 : t;
}

/**
 * Ease-out expo — a hard deceleration into the anchor: starts fast, decelerates
 * sharply, settles. Use for "the nerve LUNGES from the vertebra then eases into
 * its target" and for staggered layer sub-progress.
 */
export function easeOutExpo(t: number): number {
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  return 1 - Math.pow(2, -10 * t);
}

/**
 * Ease-IN cubic — slow start, ACCELERATING into the end. The opposite character of the
 * ease-outs: use for a gesture that gathers speed as it completes (the being DRINKING a
 * panel back — the retract accelerates up the curve, never a constant collapse).
 */
export function easeInCubic(t: number): number {
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  return t * t * t;
}

/** Ease-out quint — a softer cousin of expo (gentler tail). */
export function easeOutQuint(t: number): number {
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  const u = 1 - t;
  return 1 - u * u * u * u * u;
}

/**
 * Ease-out back — decelerates past 1, overshoots slightly, then settles back to 1
 * (the bloom "catch"). `overshoot` controls the peak: ~1.1 peaks at ~1.04 — a
 * subtle, premium catch, NOT a cartoon bounce. f(0)=0, f(1)=1 exactly.
 */
export function easeOutBack(t: number, overshoot = 1.1): number {
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  const c3 = overshoot + 1;
  const u = t - 1;
  return 1 + c3 * u * u * u + overshoot * u * u;
}

/**
 * Sub-progress for a STAGGERED layer. A layer that begins at `start` (0..1) of the
 * parent progress is remapped to its own [0,1] and eased-out — so a panel's layers
 * resolve in sequence (shell -> rim -> header -> content -> halo) instead of all at
 * once. Returns 0 until the parent reaches `start`.
 */
export function layerProgress(p: number, start: number): number {
  if (p <= start) return 0;
  if (start >= 1) return p >= 1 ? 1 : 0;
  return easeOutExpo((p - start) / (1 - start));
}

/**
 * One-shot rise-then-fall bell on a 0..1 clock (peak at `peak`). For a transient
 * FLASH — e.g. the vertebra socket flaring as the nerve delivers the bloom. Returns
 * 0 outside (0,1).
 */
export function flashBell(t: number, peak = 0.38): number {
  if (t <= 0 || t >= 1) return 0;
  return t < peak ? t / peak : Math.max(0, 1 - (t - peak) / (1 - peak));
}
