import { describe, expect, it } from 'vitest';
import { measuredLatency } from './latency';

describe('frontend latency measurements', () => {
  it('returns the measured non-negative duration instead of a placeholder', () => {
    expect(measuredLatency(100, 117)).toBe(17);
    expect(measuredLatency(117, 100)).toBe(0);
  });

  it('fails closed for unavailable clock values', () => {
    expect(measuredLatency(Number.NaN, 117)).toBe(0);
    expect(measuredLatency(100, Number.POSITIVE_INFINITY)).toBe(0);
  });
});
