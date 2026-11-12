import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import {
  CORD_Z,
  SEGMENT_ANCHORS,
  SEGMENT_BOTTOM_Y,
  SEGMENT_COUNT,
  SEGMENT_TOP_Y,
} from './spineAnatomy';
import * as data from './spineAnatomyData';

describe('spineAnatomy re-exports', () => {
  it('exposes the same shared constants as spineAnatomyData', () => {
    expect(CORD_Z).toBe(data.CORD_Z);
    expect(SEGMENT_COUNT).toBe(data.SEGMENT_COUNT);
    expect(SEGMENT_TOP_Y).toBe(data.SEGMENT_TOP_Y);
    expect(SEGMENT_BOTTOM_Y).toBe(data.SEGMENT_BOTTOM_Y);
  });
});

describe('SEGMENT_ANCHORS', () => {
  it('is a non-empty list of THREE.Vector3 instances', () => {
    expect(SEGMENT_ANCHORS.length).toBeGreaterThan(0);
    for (const anchor of SEGMENT_ANCHORS) {
      expect(anchor).toBeInstanceOf(THREE.Vector3);
    }
  });

  it('holds finite coordinates for every anchor', () => {
    for (const anchor of SEGMENT_ANCHORS) {
      expect(Number.isFinite(anchor.x)).toBe(true);
      expect(Number.isFinite(anchor.y)).toBe(true);
      expect(Number.isFinite(anchor.z)).toBe(true);
    }
  });

  it('creates a separate vector object for each anchor', () => {
    expect(new Set(SEGMENT_ANCHORS).size).toBe(SEGMENT_ANCHORS.length);
  });
});
