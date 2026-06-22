// perfBudget — the 60fps relief valve's pure math + budget (poster-gap audit P2.3).
//
// THE GUARANTEE, made real: when the measured frame rate sags, RESOLUTION gives
// to recover it — and ONLY resolution. The structural tier (geometry, particle
// counts, the sky) stays exactly where the operator's FIDELITY click put it, and
// hue/palette/textures are never touched. This is the FIDELITY-SACRED-vs-smooth
// resolution: let the device-pixel-ratio breathe (a runtime-only lever, never
// persisted), keep the look. drei's PerformanceMonitor measures the FPS and hands
// us a 0..1 `factor`; dprForFactor maps it into the tier's DPR range.

import type { QualityTier } from '@/components/QualityTierProvider';

/** Device-pixel-ratio budget per tier: [floor (worst sag), ceiling (full sharp)]. */
export const TIER_DPR: Record<QualityTier, [number, number]> = {
  high: [1, 1.5],
  medium: [1, 1.25],
  low: [1, 1],
};

/** FPS window the relief valve targets (60Hz): below lower → shed DPR, above
 *  upper → restore it. Tight enough to chase 60, loose enough not to flip-flop. */
export const PERF_BOUNDS: [number, number] = [50, 58];

/** DPR relief arms after the worst shader-compile jank passes (it's reversible,
 *  so a brief early false-drop self-corrects — unlike a persisted tier demote). */
export const DPR_WARMUP_MS = 4_000;
/** The structural-tier advisory waits the full warmup (boot jank ≠ evidence). */
export const ADVISORY_WARMUP_MS = 20_000;

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

/**
 * Map PerformanceMonitor's 0..1 quality factor to a concrete DPR for this tier.
 * factor 1 = full sharpness (ceiling); factor 0 = max relief (floor, never below
 * 1.0 device px so we never blur below native). Resolution only — no look change.
 */
export function dprForFactor(tier: QualityTier, factor: number): number {
  const [min, max] = TIER_DPR[tier];
  return min + (max - min) * clamp01(factor);
}
