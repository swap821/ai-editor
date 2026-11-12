import * as THREE from 'three';
import { describe, expect, it } from 'vitest';
import { buildFireflyGeometry } from './ConductionPaths';

const TAU = Math.PI * 2;

function makePlane(widthSegments: number, heightSegments: number, z: number, red = false) {
  const geometry = new THREE.PlaneGeometry(1, 1, widthSegments, heightSegments);
  if (red) {
    const vertexCount = geometry.getAttribute('position').count;
    const reds = new Float32Array(vertexCount * 3);
    for (let i = 0; i < vertexCount; i++) reds[i * 3] = 1;
    geometry.setAttribute('color', new THREE.BufferAttribute(reds, 3));
  }
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
  mesh.position.set(0, 0, z);
  return mesh;
}

function attr(geometry: THREE.BufferGeometry, name: string) {
  return geometry.getAttribute(name) as THREE.BufferAttribute;
}

describe('buildFireflyGeometry', () => {
  it('creates all per-firefly attributes with sensible sizes and ranges', () => {
    const root = new THREE.Group();
    root.add(makePlane(2, 2, 0));
    const count = 50;

    const geometry = buildFireflyGeometry(root, count);

    expect(attr(geometry, 'position').count).toBe(count);
    expect(attr(geometry, 'position').itemSize).toBe(3);
    expect(attr(geometry, 'aColor').itemSize).toBe(3);
    expect(attr(geometry, 'aPhase').itemSize).toBe(1);
    expect(attr(geometry, 'aSpeed').count).toBe(count);
    expect(attr(geometry, 'aSize').count).toBe(count);

    for (let i = 0; i < count; i++) {
      expect(attr(geometry, 'aPhase').getX(i)).toBeGreaterThanOrEqual(0);
      expect(attr(geometry, 'aPhase').getX(i)).toBeLessThan(TAU);
      expect(attr(geometry, 'aSpeed').getX(i)).toBeGreaterThanOrEqual(0.55);
      expect(attr(geometry, 'aSpeed').getX(i)).toBeLessThan(1.55);
      expect(attr(geometry, 'aSize').getX(i)).toBeGreaterThanOrEqual(0.7);
      expect(attr(geometry, 'aSize').getX(i)).toBeLessThan(1.3);
    }
  });

  it('is deterministic for identical input', () => {
    const build = () => {
      const root = new THREE.Group();
      root.add(makePlane(3, 3, 1));
      return buildFireflyGeometry(root, 30);
    };

    const a = build();
    const b = build();

    expect(Array.from(attr(a, 'position').array)).toEqual(Array.from(attr(b, 'position').array));
    expect(Array.from(attr(a, 'aPhase').array)).toEqual(Array.from(attr(b, 'aPhase').array));
    // Not degenerate: points are spread out, not all identical.
    const xs = new Set(Array.from(attr(a, 'position').array).filter((_, i) => i % 3 === 0));
    expect(xs.size).toBeGreaterThan(5);
  });

  it('applies the world matrix and lifts points slightly along the normal', () => {
    const root = new THREE.Group();
    root.position.set(10, 0, 0);
    root.add(makePlane(1, 1, 5));

    const geometry = buildFireflyGeometry(root, 20);
    const positions = attr(geometry, 'position');

    for (let i = 0; i < 20; i++) {
      expect(positions.getX(i)).toBeGreaterThanOrEqual(9.5 - 1e-6);
      expect(positions.getX(i)).toBeLessThanOrEqual(10.5 + 1e-6);
      expect(positions.getY(i)).toBeGreaterThanOrEqual(-0.5 - 1e-6);
      expect(positions.getY(i)).toBeLessThanOrEqual(0.5 + 1e-6);
      expect(positions.getZ(i)).toBeCloseTo(5.004, 4);
    }
  });

  it('samples a geometry shared between meshes only once', () => {
    const first = makePlane(1, 1, 0);
    const second = new THREE.Mesh(first.geometry, first.material);
    second.position.set(0, 0, 20);
    const root = new THREE.Group();
    root.add(first, second);

    const geometry = buildFireflyGeometry(root, 16);
    const positions = attr(geometry, 'position');

    for (let i = 0; i < 16; i++) {
      expect(positions.getZ(i)).toBeCloseTo(0.004, 4);
    }
  });

  it('splits points between meshes in proportion to triangle count', () => {
    const small = makePlane(1, 1, 0); // 2 triangles
    const large = makePlane(3, 1, 10); // 6 triangles
    const root = new THREE.Group();
    root.add(small, large);

    const geometry = buildFireflyGeometry(root, 8);
    const positions = attr(geometry, 'position');

    let nearSmall = 0;
    let nearLarge = 0;
    for (let i = 0; i < 8; i++) {
      if (positions.getZ(i) < 5) nearSmall++;
      else nearLarge++;
    }
    expect(nearSmall).toBe(2);
    expect(nearLarge).toBe(6);
  });

  it('copies interpolated vertex colors into aColor', () => {
    const root = new THREE.Group();
    root.add(makePlane(2, 2, 0, true));

    const geometry = buildFireflyGeometry(root, 10);
    const colors = attr(geometry, 'aColor');

    for (let i = 0; i < 10; i++) {
      expect(colors.getX(i)).toBeCloseTo(1, 5);
      expect(colors.getY(i)).toBeCloseTo(0, 5);
      expect(colors.getZ(i)).toBeCloseTo(0, 5);
    }
  });
});
