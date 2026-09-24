import { describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import { updateLineGeometryPoints } from './lineGeometry';

describe('updateLineGeometryPoints', () => {
  it('mutates a Drei line through its bounded segment attributes', () => {
    const start = {
      count: 2,
      data: { needsUpdate: false },
      setXYZ: vi.fn(),
    };
    const end = {
      count: 2,
      data: { needsUpdate: false },
      setXYZ: vi.fn(),
    };
    const geometry = {
      attributes: { instanceStart: start, instanceEnd: end },
      computeBoundingBox: vi.fn(),
      computeBoundingSphere: vi.fn(),
    };
    const points = [
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(1, 1, 1),
      new THREE.Vector3(2, 2, 2),
    ];

    expect(updateLineGeometryPoints(geometry, points)).toBe(true);
    expect(start.setXYZ).toHaveBeenNthCalledWith(1, 0, 0, 0, 0);
    expect(end.setXYZ).toHaveBeenNthCalledWith(1, 0, 1, 1, 1);
    expect(start.data.needsUpdate).toBe(true);
    expect(end.data.needsUpdate).toBe(true);
    expect(geometry.computeBoundingSphere).toHaveBeenCalledOnce();
  });

  it('seeds a compatible line geometry once when the segment pool is absent', () => {
    const geometry = { setPositions: vi.fn() };
    const points = [new THREE.Vector3(0, 0, 0), new THREE.Vector3(1, 1, 1)];

    expect(updateLineGeometryPoints(geometry, points)).toBe(true);
    expect(geometry.setPositions).toHaveBeenCalledOnce();
    expect(geometry.setPositions.mock.calls[0][0]).toBeInstanceOf(Float32Array);
  });
});
