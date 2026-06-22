// frontend/src/superbrain/lib/spinePointField.test.ts
import { describe, it, expect } from 'vitest';
import { buildSpinePoints, BODY_AXIS_MIN, BODY_AXIS_MAX, CORD_TOP_Y } from './spinePointField';
import { SEGMENT_BOTTOM_Y } from './spineAnatomy';

const COUNT = 2000;
const SEED = 0xbeef1234;

describe('buildSpinePoints', () => {
  it('returns exactly count and all arrays have correct lengths', () => {
    const d = buildSpinePoints(COUNT, SEED);
    expect(d.count).toBe(COUNT);
    expect(d.positions).toHaveLength(COUNT * 3);
    expect(d.colors).toHaveLength(COUNT * 3);
    expect(d.normals).toHaveLength(COUNT * 3);
    expect(d.sizes).toHaveLength(COUNT);
    expect(d.phases).toHaveLength(COUNT);
    expect(d.speeds).toHaveLength(COUNT);
    expect(d.scatter).toHaveLength(COUNT * 3);
    expect(d.births).toHaveLength(COUNT);
    expect(d.bands).toHaveLength(COUNT);
  });

  it('is deterministic for fixed seed and differs for a different seed', () => {
    const a = buildSpinePoints(COUNT, SEED);
    const b = buildSpinePoints(COUNT, SEED);
    expect(Array.from(a.positions)).toEqual(Array.from(b.positions));
    const c = buildSpinePoints(COUNT, SEED + 1);
    expect(Array.from(a.positions)).not.toEqual(Array.from(c.positions));
  });

  it('wears the brain palette: non-zero, in [0,1], and multicolor (not one flat hue)', () => {
    const d = buildSpinePoints(COUNT, SEED);
    const sum = d.colors.reduce((acc, v) => acc + v, 0);
    expect(sum).toBeGreaterThan(0);

    for (let i = 0; i < d.colors.length; i++) {
      expect(d.colors[i]).toBeGreaterThanOrEqual(0);
      expect(d.colors[i]).toBeLessThanOrEqual(1 + 1e-6);
    }

    // The brain palette is multicolor — distinct hues should appear across points
    // (not a single cool gradient). Sample a handful of unique RGB triples.
    const uniq = new Set<string>();
    for (let i = 0; i < d.count; i++) {
      uniq.add(
        `${d.colors[i * 3].toFixed(2)},${d.colors[i * 3 + 1].toFixed(2)},${d.colors[i * 3 + 2].toFixed(2)}`,
      );
    }
    expect(uniq.size).toBeGreaterThan(4); // several brain hues represented
  });

  it('all bands within [0,1]', () => {
    const d = buildSpinePoints(COUNT, SEED);
    for (let i = 0; i < d.count; i++) {
      expect(d.bands[i]).toBeGreaterThanOrEqual(0);
      expect(d.bands[i]).toBeLessThanOrEqual(1);
    }
  });

  it('sizes within [0.6, 1.4]', () => {
    const d = buildSpinePoints(COUNT, SEED);
    for (let i = 0; i < d.count; i++) {
      expect(d.sizes[i]).toBeGreaterThanOrEqual(0.6);
      expect(d.sizes[i]).toBeLessThanOrEqual(1.4 + 1e-6);
    }
  });

  it('births within [0,1]', () => {
    const d = buildSpinePoints(COUNT, SEED);
    for (let i = 0; i < d.count; i++) {
      expect(d.births[i]).toBeGreaterThanOrEqual(0);
      expect(d.births[i]).toBeLessThanOrEqual(1);
    }
  });

  it('y-range sanity: all points within [SEGMENT_BOTTOM_Y - 0.6, CORD_TOP_Y + 0.1]', () => {
    const d = buildSpinePoints(COUNT, SEED);
    const yMin = SEGMENT_BOTTOM_Y - 0.6;
    const yMax = CORD_TOP_Y + 0.1;
    for (let i = 0; i < d.count; i++) {
      const y = d.positions[i * 3 + 1];
      expect(y).toBeGreaterThanOrEqual(yMin - 1e-5);
      expect(y).toBeLessThanOrEqual(yMax + 1e-5);
    }
  });

  it('exports BODY_AXIS_MIN and BODY_AXIS_MAX as numeric constants', () => {
    expect(typeof BODY_AXIS_MIN).toBe('number');
    expect(typeof BODY_AXIS_MAX).toBe('number');
    expect(BODY_AXIS_MIN).toBe(-2.85);
    expect(BODY_AXIS_MAX).toBe(0.7);
  });

  it('speeds within [0.6, 1.4]', () => {
    const d = buildSpinePoints(COUNT, SEED);
    for (let i = 0; i < d.count; i++) {
      expect(d.speeds[i]).toBeGreaterThanOrEqual(0.6);
      expect(d.speeds[i]).toBeLessThanOrEqual(1.4 + 1e-6);
    }
  });

  it('scatter vectors are unit-length (±1e-4)', () => {
    const d = buildSpinePoints(500, SEED);
    for (let i = 0; i < 500; i++) {
      const x = d.scatter[i * 3];
      const y = d.scatter[i * 3 + 1];
      const z = d.scatter[i * 3 + 2];
      const len = Math.sqrt(x * x + y * y + z * z);
      expect(len).toBeCloseTo(1, 3);
    }
  });
});
