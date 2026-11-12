import { describe, expect, it } from 'vitest';
import { BufferAttribute, Color, Vector3 } from 'three';
import { createWorkspaceNerve, type WorkspaceNerveState } from './workspaceNerveState';

function positionsOf(nerve: WorkspaceNerveState, key: 'geometry' | 'particles'): BufferAttribute {
  const attribute = nerve[key].getAttribute('position');
  if (!(attribute instanceof BufferAttribute)) throw new Error('position attribute missing');
  return attribute;
}

describe('createWorkspaceNerve', () => {
  it('builds a tube grid of 49 rings by 9 vertices with unit-circle cross sections', () => {
    const nerve = createWorkspaceNerve();
    const position = positionsOf(nerve, 'geometry');

    expect(position.itemSize).toBe(3);
    expect(position.count).toBe(49 * 9);

    // ring 0, first vertex: x=0, angle 0
    expect(position.getX(0)).toBe(0);
    expect(position.getY(0)).toBeCloseTo(1);
    expect(position.getZ(0)).toBeCloseTo(0);

    // ring 24, vertex 2: x=0.5, angle pi/2
    const v = 24 * 9 + 2;
    expect(position.getX(v)).toBeCloseTo(0.5);
    expect(position.getY(v)).toBeCloseTo(0);
    expect(position.getZ(v)).toBeCloseTo(1);

    // last ring reaches x=1 and every vertex lies on the unit circle
    for (let i = 0; i < position.count; i++) {
      expect(Math.hypot(position.getY(i), position.getZ(i))).toBeCloseTo(1);
    }
    expect(position.getX(48 * 9)).toBeCloseTo(1);
  });

  it('indexes two triangles per quad and only references existing vertices', () => {
    const { geometry } = createWorkspaceNerve();
    const index = geometry.getIndex();
    if (!index) throw new Error('index missing');

    expect(index.count).toBe(48 * 8 * 6);
    // first quad: a=0, b=9
    expect(Array.from(index.array.slice(0, 6))).toEqual([0, 9, 1, 9, 10, 1]);
    for (let i = 0; i < index.count; i++) {
      expect(index.getX(i)).toBeLessThan(49 * 9);
    }
  });

  it('generates 600 deterministic dust particles within their ranges', () => {
    const first = positionsOf(createWorkspaceNerve(), 'particles');
    const second = positionsOf(createWorkspaceNerve(), 'particles');

    expect(first.count).toBe(600);
    expect(Array.from(first.array)).toEqual(Array.from(second.array));
    for (let i = 0; i < first.count; i++) {
      expect(first.getX(i)).toBeGreaterThanOrEqual(0);
      expect(first.getX(i)).toBeLessThan(1);
      expect(first.getY(i)).toBeGreaterThanOrEqual(0);
      expect(first.getY(i)).toBeLessThan(Math.PI * 2);
      expect(first.getZ(i)).toBeGreaterThanOrEqual(0);
      expect(first.getZ(i)).toBeLessThan(1);
    }
    // not degenerate: values vary
    expect(new Set(Array.from(first.array)).size).toBeGreaterThan(100);
  });

  it('starts with no scene objects and default uniforms', () => {
    const nerve = createWorkspaceNerve();

    expect(nerve.mesh).toBeNull();
    expect(nerve.points).toBeNull();
    expect(nerve.material).toBeNull();
    expect(nerve.dustMaterial).toBeNull();

    const { uniforms } = nerve;
    for (const key of ['p0', 'p1', 'p2', 'p3'] as const) {
      expect(uniforms[key].value).toBeInstanceOf(Vector3);
      expect(uniforms[key].value.toArray()).toEqual([0, 0, 0]);
    }
    expect(uniforms.radius.value).toBe(0);
    expect(uniforms.reach.value).toBe(0);
    expect(uniforms.dpr.value).toBe(1);
    expect(uniforms.breath.value).toBe(0.5);
    expect(uniforms.signal.value).toBe(-1);
    expect(uniforms.color.value).toBeInstanceOf(Color);
    expect(uniforms.color.value.r).toBeGreaterThanOrEqual(0);
    expect(uniforms.color.value.r).toBeLessThanOrEqual(1);
  });

  it('returns independent resources on each call', () => {
    const a = createWorkspaceNerve();
    const b = createWorkspaceNerve();

    a.uniforms.p0.value.set(1, 2, 3);
    a.uniforms.radius.value = 7;

    expect(b.uniforms.p0.value.toArray()).toEqual([0, 0, 0]);
    expect(b.uniforms.radius.value).toBe(0);
    expect(a.geometry).not.toBe(b.geometry);
    expect(a.particles).not.toBe(b.particles);
  });
});
