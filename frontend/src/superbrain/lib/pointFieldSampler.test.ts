// frontend/src/superbrain/lib/pointFieldSampler.test.ts
import { describe, it, expect } from 'vitest';
import * as THREE from 'three';
import { samplePointField, type PointFieldSource } from './pointFieldSampler';

function coloredBox(): THREE.Object3D {
  const geo = new THREE.BoxGeometry(2, 2, 2, 4, 4, 4);
  const n = geo.getAttribute('position').count;
  const colors = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) { colors[i * 3] = 0.5; colors[i * 3 + 1] = 0.25; colors[i * 3 + 2] = 0.9; }
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  const mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial());
  const root = new THREE.Group();
  root.add(mesh);
  return root;
}

describe('samplePointField', () => {
  const sources: PointFieldSource[] = [{ object: coloredBox(), share: 1, axisMin: -1, axisMax: 1 }];

  it('produces every attribute array at the requested count', () => {
    const d = samplePointField(sources, 5000, 0xa11ce);
    expect(d.count).toBe(5000);
    expect(d.positions).toHaveLength(5000 * 3);
    expect(d.colors).toHaveLength(5000 * 3);
    expect(d.normals).toHaveLength(5000 * 3);
    expect(d.sizes).toHaveLength(5000);
    expect(d.phases).toHaveLength(5000);
    expect(d.speeds).toHaveLength(5000);
    expect(d.scatter).toHaveLength(5000 * 3);
    expect(d.births).toHaveLength(5000);
    expect(d.bands).toHaveLength(5000);
  });

  it('reads the baked region color (the COLOR_0 trap)', () => {
    const d = samplePointField(sources, 1000, 1);
    // not all-zero — color attribute was honored
    const sum = d.colors.reduce((a, b) => a + b, 0);
    expect(sum).toBeGreaterThan(0);
    expect(d.colors[0]).toBeCloseTo(0.5, 1);
    expect(d.colors[2]).toBeCloseTo(0.9, 1);
  });

  it('is deterministic for a fixed seed', () => {
    const a = samplePointField(sources, 800, 42);
    const b = samplePointField(sources, 800, 42);
    expect(Array.from(a.positions)).toEqual(Array.from(b.positions));
    const c = samplePointField(sources, 800, 43);
    expect(Array.from(a.positions)).not.toEqual(Array.from(c.positions));
  });

  it('bakes attributes into expected ranges', () => {
    const d = samplePointField(sources, 2000, 7);
    for (let i = 0; i < d.count; i++) {
      expect(d.sizes[i]).toBeGreaterThanOrEqual(0.6);
      expect(d.sizes[i]).toBeLessThanOrEqual(1.4);
      expect(d.speeds[i]).toBeGreaterThanOrEqual(0.6);
      expect(d.speeds[i]).toBeLessThanOrEqual(1.4);
      expect(d.phases[i]).toBeGreaterThanOrEqual(0);
      expect(d.phases[i]).toBeLessThanOrEqual(Math.PI * 2 + 1e-6);
      expect(d.births[i]).toBeGreaterThanOrEqual(0);
      expect(d.births[i]).toBeLessThanOrEqual(1);
      expect(d.bands[i]).toBeGreaterThanOrEqual(0);
      expect(d.bands[i]).toBeLessThanOrEqual(1);
    }
  });
});
