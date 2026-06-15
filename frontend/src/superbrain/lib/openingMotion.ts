// openingMotion.ts — PURE timing/easing helpers for P1 "The Opening".
// No three.js, no React: unit-testable in isolation. Every value here is a
// transform/opacity/filter scalar consumed by the scene's frame loop.

import { OPENING_TIMINGS, OPENING_EASING, COALESCENCE_SCALE_FLOOR } from './openingTokens';
import type { CognitionEvent } from './cognitionBus';

/** Solve a CSS-style cubic-bezier(p1x,p1y,p2x,p2y) for y at a given x in
 *  [0,1] (Newton + bisection fallback). Endpoints (0,0) and (1,1) implied. */
export function cubicBezier(p1x: number, p1y: number, p2x: number, p2y: number): (x: number) => number {
  const cx = 3 * p1x;
  const bx = 3 * (p2x - p1x) - cx;
  const ax = 1 - cx - bx;
  const cy = 3 * p1y;
  const by = 3 * (p2y - p1y) - cy;
  const ay = 1 - cy - by;
  const sampleX = (t: number) => ((ax * t + bx) * t + cx) * t;
  const sampleY = (t: number) => ((ay * t + by) * t + cy) * t;
  const slopeX = (t: number) => (3 * ax * t + 2 * bx) * t + cx;
  return (x: number) => {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    let t = x;
    for (let i = 0; i < 8; i++) {
      const d = sampleX(t) - x;
      if (Math.abs(d) < 1e-6) return sampleY(t);
      const s = slopeX(t);
      if (Math.abs(s) < 1e-6) break;
      t -= d / s;
    }
    let lo = 0;
    let hi = 1;
    let iter = 0;
    t = x;
    while (lo < hi && ++iter < 64) {
      const cur = sampleX(t);
      if (Math.abs(cur - x) < 1e-6) break;
      if (cur < x) lo = t;
      else hi = t;
      t = (lo + hi) / 2;
    }
    return sampleY(t);
  };
}

const easeCoalescence = cubicBezier(...OPENING_EASING.coalescence);
const easeNotice = cubicBezier(...OPENING_EASING.notice);

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);

export interface CoalescenceEnvelope {
  /** Cortex opacity 0 -> 1. */
  opacity: number;
  /** Cortex scale floor -> 1 (never starts at 0). */
  scale: number;
  /** 1 = fully arriving, 0 = settled. Shaders gate inflow/pull off this. */
  arrival: number;
}

/** Eased coalescence state at elapsed ms since arrival start. */
export function coalescenceEnvelope(elapsedMs: number): CoalescenceEnvelope {
  const p = easeCoalescence(clamp01(elapsedMs / OPENING_TIMINGS.coalescenceMs));
  return {
    opacity: p,
    scale: COALESCENCE_SCALE_FLOOR + (1 - COALESCENCE_SCALE_FLOOR) * p,
    arrival: 1 - p,
  };
}

/** Single-shot ignition pulse (0 -> 1 -> 0), peaking at ignitionPeakMs. */
export function ignitionPulse(elapsedMs: number): number {
  const peak = OPENING_TIMINGS.ignitionPeakMs;
  const span = OPENING_TIMINGS.coalescenceMs;
  if (elapsedMs <= 0 || elapsedMs >= span) return 0;
  const rise = clamp01(elapsedMs / peak);
  const fall = clamp01((span - elapsedMs) / (span - peak));
  // Asymmetric bell: fast bright ignition, gentle settle.
  return Math.pow(rise, 1.4) * Math.pow(fall, 0.8);
}

/** Attentive "notice" 0 -> 1 over the notice window, then held at 1. */
export function awakenNotice(elapsedMs: number): number {
  return easeNotice(clamp01(elapsedMs / OPENING_TIMINGS.awakenNoticeMs));
}

/** prefers-reduced-motion decision — SSR-safe, lives WITH the motion code. */
export function shouldReduceMotion(win: Window | undefined = typeof window !== 'undefined' ? window : undefined): boolean {
  if (!win || typeof win.matchMedia !== 'function') return false;
  return win.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** THE SIGNAL: a user-issued directive (typed or voice) is the awakening
 *  trigger. Ambient/system events (burst/synthesis/idle) never wake it. */
export function isAwakeningTrigger(event: CognitionEvent | null | undefined): boolean {
  return !!event && event.type === 'directive';
}
