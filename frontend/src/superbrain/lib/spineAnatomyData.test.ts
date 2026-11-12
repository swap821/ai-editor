import { describe, expect, it } from 'vitest';
import {
  CORD_Z,
  SEGMENT_BOTTOM_Y,
  SEGMENT_COUNT,
  SEGMENT_TOP_Y,
  SEGMENT_ANCHOR_COORDINATES as points,
} from './spineAnatomyData';

describe('spine anatomy constants', () => {
  it('describes a cord that runs downward from top to bottom', () => {
    expect(SEGMENT_COUNT).toBe(12);
    expect(SEGMENT_TOP_Y).toBeGreaterThan(SEGMENT_BOTTOM_Y);
    expect(CORD_Z).toBeLessThan(0);
  });
});

describe('spine segment points', () => {
  it('has one [x, y, z] point per segment, all on the x = 0 midline', () => {
    expect(points).toHaveLength(SEGMENT_COUNT);
    for (const p of points) {
      expect(p).toHaveLength(3);
      expect(p[0]).toBe(0);
    }
  });

  it('starts at the top and ends at the bottom of the cord', () => {
    const first = points[0];
    const last = points[points.length - 1];
    expect(first[1]).toBeCloseTo(SEGMENT_TOP_Y, 10);
    expect(last[1]).toBeCloseTo(SEGMENT_BOTTOM_Y, 10);
    expect(first[2]).toBeCloseTo(CORD_Z, 10);
    expect(last[2]).toBeCloseTo(CORD_Z, 10);
  });

  it('spaces segments evenly while descending', () => {
    const step = (SEGMENT_BOTTOM_Y - SEGMENT_TOP_Y) / (SEGMENT_COUNT - 1);
    for (let i = 1; i < points.length; i += 1) {
      expect(points[i][1] - points[i - 1][1]).toBeCloseTo(step, 10);
      expect(points[i][1]).toBeLessThan(points[i - 1][1]);
    }
  });

  it('bulges forward in z by at most 0.04, symmetrically about the middle', () => {
    const mid = points[Math.floor(points.length / 2)];
    expect(mid[2]).toBeGreaterThan(CORD_Z + 0.03);
    for (const p of points) {
      expect(p[2]).toBeGreaterThanOrEqual(CORD_Z - 1e-12);
      expect(p[2]).toBeLessThanOrEqual(CORD_Z + 0.04 + 1e-12);
    }
    for (let i = 0; i < points.length; i += 1) {
      expect(points[i][2]).toBeCloseTo(points[points.length - 1 - i][2], 10);
    }
  });
});
