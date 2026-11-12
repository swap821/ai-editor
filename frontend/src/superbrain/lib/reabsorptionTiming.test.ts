import { describe, expect, it } from 'vitest';
import { POINTS_SLAB_RETRACT_MS, POINTS_REABSORPTION_MS } from './reabsorptionTiming';

describe('reabsorptionTiming', () => {
  it('exposes the close choreography durations in milliseconds', () => {
    expect(POINTS_SLAB_RETRACT_MS).toBe(1300);
    expect(POINTS_REABSORPTION_MS).toBe(1700);
  });

  it('keeps the seat release later than the mounted return', () => {
    expect(POINTS_REABSORPTION_MS).toBeGreaterThan(POINTS_SLAB_RETRACT_MS);
  });

  it('uses positive whole-millisecond values usable as timer delays', () => {
    for (const value of [POINTS_SLAB_RETRACT_MS, POINTS_REABSORPTION_MS]) {
      expect(Number.isInteger(value)).toBe(true);
      expect(value).toBeGreaterThan(0);
    }
  });
});
