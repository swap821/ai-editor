import { describe, expect, it } from 'vitest';
import {
  BASE_TILT_X,
  BASE_TILT_Z,
  INNER_RADIUS,
  OUTER_RADIUS,
  PARTICLE_COUNT,
  TAU,
  createDiskData,
} from './CoreGeometry';

function minMax(values: Float32Array) {
  let min = Infinity;
  let max = -Infinity;
  for (const value of values) {
    if (value < min) min = value;
    if (value > max) max = value;
  }
  return { min, max };
}

describe('CoreGeometry constants', () => {
  it('exposes a full turn and an ordered radius range', () => {
    expect(TAU).toBe(Math.PI * 2);
    expect(INNER_RADIUS).toBeLessThan(OUTER_RADIUS);
    expect(BASE_TILT_X).toBe(0.42);
    expect(BASE_TILT_Z).toBe(-0.14);
  });
});

describe('createDiskData', () => {
  it('allocates one entry per particle in every buffer', () => {
    const data = createDiskData();
    expect(data.positions).toBeInstanceOf(Float32Array);
    expect(data.positions.length).toBe(PARTICLE_COUNT * 3);
    for (const key of [
      'angles',
      'offsets',
      'speeds',
      'phases',
      'sizes',
      'tints',
      'jitters',
    ] as const) {
      expect(data[key]).toBeInstanceOf(Float32Array);
      expect(data[key].length).toBe(PARTICLE_COUNT);
    }
    expect(data.positions.every((value) => value === 0)).toBe(true);
  });

  it('is deterministic across calls and returns fresh buffers', () => {
    const first = createDiskData();
    const second = createDiskData();
    expect(second.angles).not.toBe(first.angles);
    expect(Array.from(second.angles)).toEqual(Array.from(first.angles));
    expect(Array.from(second.offsets)).toEqual(Array.from(first.offsets));
    expect(Array.from(second.tints)).toEqual(Array.from(first.tints));
    expect(Array.from(second.jitters)).toEqual(Array.from(first.jitters));
  });

  it('keeps every attribute inside its documented range', () => {
    const data = createDiskData();
    const eps = 1e-5;

    const angles = minMax(data.angles);
    expect(angles.min).toBeGreaterThanOrEqual(0);
    expect(angles.max).toBeLessThanOrEqual(TAU + eps);

    const offsets = minMax(data.offsets);
    expect(offsets.min).toBeGreaterThanOrEqual(-1 - eps);
    expect(offsets.max).toBeLessThanOrEqual(1 + eps);

    const speeds = minMax(data.speeds);
    expect(speeds.min).toBeGreaterThanOrEqual(0.75 - eps);
    expect(speeds.max).toBeLessThanOrEqual(1.3 + eps);

    const phases = minMax(data.phases);
    expect(phases.min).toBeGreaterThanOrEqual(0);
    expect(phases.max).toBeLessThanOrEqual(1 + eps);

    const sizes = minMax(data.sizes);
    expect(sizes.min).toBeGreaterThanOrEqual(0.5 - eps);
    expect(sizes.max).toBeLessThanOrEqual(1.35 + eps);

    const jitters = minMax(data.jitters);
    expect(jitters.min).toBeGreaterThanOrEqual(-1 - eps);
    expect(jitters.max).toBeLessThanOrEqual(1 + eps);
  });

  it('produces varied values rather than a constant stream', () => {
    const data = createDiskData();
    expect(new Set(data.angles).size).toBeGreaterThan(700);
    expect(new Set(data.speeds).size).toBeGreaterThan(700);

    // offsets are the sum of two uniforms minus one: centred on zero
    let sum = 0;
    for (const value of data.offsets) sum += value;
    expect(Math.abs(sum / PARTICLE_COUNT)).toBeLessThan(0.1);
  });

  it('assigns tints from {0,1,2,3} with tint 0 the most common', () => {
    const { tints } = createDiskData();
    const counts = [0, 0, 0, 0];
    for (const tint of tints) {
      expect([0, 1, 2, 3]).toContain(tint);
      counts[tint] += 1;
    }
    expect(counts.reduce((a, b) => a + b, 0)).toBe(PARTICLE_COUNT);
    for (const count of counts) {
      expect(count).toBeGreaterThan(0);
    }
    expect(counts[0] / PARTICLE_COUNT).toBeGreaterThan(0.5);
    expect(counts[0] / PARTICLE_COUNT).toBeLessThan(0.7);
    expect(counts[0]).toBeGreaterThan(counts[3]);
    expect(counts[3]).toBeGreaterThan(counts[2]);
  });
});
