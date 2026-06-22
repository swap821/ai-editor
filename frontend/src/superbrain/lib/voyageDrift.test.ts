import { describe, it, expect } from 'vitest';
import { deriveVoyageDrift, VOYAGE_AMPLITUDE, VOYAGE_BANK_GAIN } from './voyageDrift';

describe('deriveVoyageDrift', () => {
  it('reduced motion: no voyage travel at all', () => {
    const o = deriveVoyageDrift({ time: 12.3, reducedMotion: true });
    expect(o).toEqual({ offsetX: 0, offsetY: 0, roll: 0 });
  });

  it('t=0: the known closed-form values (cos terms dominate)', () => {
    const o = deriveVoyageDrift({ time: 0, reducedMotion: false });
    // driftX(0) = 0 + 0.1 = 0.1 → *0.45
    expect(o.offsetX).toBeCloseTo(0.1 * VOYAGE_AMPLITUDE, 4);
    // swellY(0) = 0 + 0.03 = 0.03 → *0.45
    expect(o.offsetY).toBeCloseTo(0.03 * VOYAGE_AMPLITUDE, 4);
    // driftVelX(0) = 0.0384 → roll = -0.0384*0.633*0.45 (contract rounds to 4dp)
    expect(o.roll).toBeCloseTo(-0.0384 * VOYAGE_BANK_GAIN * VOYAGE_AMPLITUDE, 4);
  });

  it('deterministic: same time → same output', () => {
    const a = deriveVoyageDrift({ time: 7.77, reducedMotion: false });
    const b = deriveVoyageDrift({ time: 7.77, reducedMotion: false });
    expect(a).toEqual(b);
  });

  it('alive: the being actually moves over time (not pinned)', () => {
    const a = deriveVoyageDrift({ time: 1, reducedMotion: false });
    const b = deriveVoyageDrift({ time: 5, reducedMotion: false });
    expect(a.offsetX).not.toBeCloseTo(b.offsetX, 3);
  });

  it('bounded: lateral wander stays gentle across a long sweep', () => {
    const maxX = (0.24 + 0.1) * VOYAGE_AMPLITUDE; // |driftX| ≤ 0.34
    for (let t = 0; t < 200; t += 0.5) {
      const o = deriveVoyageDrift({ time: t, reducedMotion: false });
      expect(Math.abs(o.offsetX)).toBeLessThanOrEqual(maxX + 1e-6);
      expect(Math.abs(o.offsetY)).toBeLessThanOrEqual(0.09 * VOYAGE_AMPLITUDE + 1e-6);
    }
  });
});
