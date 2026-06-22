import { describe, it, expect } from 'vitest';
import { dprForFactor, TIER_DPR, PERF_BOUNDS } from './perfBudget';

describe('dprForFactor (60fps relief valve)', () => {
  it('factor 1 → full sharpness (tier ceiling)', () => {
    expect(dprForFactor('high', 1)).toBe(1.5);
    expect(dprForFactor('medium', 1)).toBe(1.25);
    expect(dprForFactor('low', 1)).toBe(1);
  });

  it('factor 0 → max relief (tier floor, never below 1.0 native px)', () => {
    expect(dprForFactor('high', 0)).toBe(1);
    expect(dprForFactor('medium', 0)).toBe(1);
    expect(dprForFactor('low', 0)).toBe(1);
  });

  it('interpolates linearly within the tier range', () => {
    expect(dprForFactor('high', 0.5)).toBeCloseTo(1.25, 5);
    expect(dprForFactor('medium', 0.5)).toBeCloseTo(1.125, 5);
  });

  it('clamps out-of-range factors (no runaway DPR)', () => {
    expect(dprForFactor('high', 5)).toBe(1.5);
    expect(dprForFactor('high', -3)).toBe(1);
  });

  it('low tier never flexes (floor == ceiling)', () => {
    expect(dprForFactor('low', 0.3)).toBe(1);
    expect(dprForFactor('low', 0.9)).toBe(1);
  });

  it('budget shape: floor ≤ ceiling per tier; bounds target ~60', () => {
    for (const t of ['high', 'medium', 'low'] as const) {
      expect(TIER_DPR[t][0]).toBeLessThanOrEqual(TIER_DPR[t][1]);
      expect(TIER_DPR[t][0]).toBeGreaterThanOrEqual(1); // never sub-native
    }
    expect(PERF_BOUNDS[0]).toBeLessThan(PERF_BOUNDS[1]);
    expect(PERF_BOUNDS[1]).toBeLessThanOrEqual(60);
  });
});
