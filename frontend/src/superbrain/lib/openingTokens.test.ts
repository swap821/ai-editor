import { describe, expect, it } from 'vitest';
import { OPENING_EASING, OPENING_TIMINGS } from './openingTokens';

describe('OPENING_TIMINGS', () => {
  it('exposes the exact millisecond durations', () => {
    expect(OPENING_TIMINGS).toEqual({
      coalescenceMs: 3500,
      ignitionPeakMs: 2600,
      awakeningMs: 2600,
      awakenNoticeMs: 320,
      attentiveDecayMs: 5000,
      breathCycleMs: 5000,
      nerveStaggerMs: 40,
    });
  });

  it('keeps the ignition peak inside the coalescence window', () => {
    expect(OPENING_TIMINGS.ignitionPeakMs).toBeLessThan(
      OPENING_TIMINGS.coalescenceMs,
    );
  });

  it('keeps the arrival within the 3-4s cinematic band', () => {
    expect(OPENING_TIMINGS.coalescenceMs).toBeGreaterThanOrEqual(3000);
    expect(OPENING_TIMINGS.coalescenceMs).toBeLessThanOrEqual(4000);
  });
});

describe('OPENING_EASING', () => {
  it('exposes the exact cubic-bezier control points', () => {
    expect(OPENING_EASING.coalescence).toEqual([0.16, 1, 0.3, 1]);
    expect(OPENING_EASING.awaken).toEqual([0.22, 1, 0.36, 1]);
    expect(OPENING_EASING.notice).toEqual([0.32, 0.72, 0, 1]);
  });

  it('uses valid cubic-bezier curves with x values in [0, 1]', () => {
    for (const curve of Object.values(OPENING_EASING)) {
      expect(curve).toHaveLength(4);
      const [x1, , x2] = curve;
      expect(x1).toBeGreaterThanOrEqual(0);
      expect(x1).toBeLessThanOrEqual(1);
      expect(x2).toBeGreaterThanOrEqual(0);
      expect(x2).toBeLessThanOrEqual(1);
    }
  });
});
