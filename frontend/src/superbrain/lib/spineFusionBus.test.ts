import { describe, it, expect, beforeEach } from 'vitest';
import * as THREE from 'three';
import {
  setSpineFusion,
  getSpineFusion,
  fuseSpinePoint,
  setCortexAnchor,
  getCortexAnchor,
  setBrainDockScale,
  getBrainDockScale,
  setBodyGroupWorldMatrix,
  copyBodyGroupWorldMatrix,
  __resetSpineFusionForTests,
} from './spineFusionBus';

describe('spineFusionBus', () => {
  beforeEach(() => __resetSpineFusionForTests());

  it('is identity until the field is built', () => {
    expect(getSpineFusion().ready).toBe(false);
    expect(fuseSpinePoint([3, -1.2, 0.5])).toEqual([3, -1.2, 0.5]);
  });

  it('applies scale + weld once set (matches the BrainPointField mapping)', () => {
    setSpineFusion(0.3311, [0.1, -0.5, -0.02]);
    const f = getSpineFusion();
    expect(f.ready).toBe(true);
    expect(f.spineScale).toBeCloseTo(0.3311);
    // P * spineScale + weld
    const [x, y, z] = fuseSpinePoint([0, -1.272, -0.3975]);
    expect(x).toBeCloseTo(0 * 0.3311 + 0.1);
    expect(y).toBeCloseTo(-1.272 * 0.3311 - 0.5);
    expect(z).toBeCloseTo(-0.3975 * 0.3311 - 0.02);
  });

  it('cortex anchor defaults to the legacy [0,0.1,0] until published', () => {
    expect(getCortexAnchor()).toEqual([0, 0.1, 0]);
  });

  it('publishes the cortex anchor; reabsorb target = anchor × dock scale', () => {
    setCortexAnchor([0.03, 0.42, -0.05]);
    setBrainDockScale(0.6);
    const a = getCortexAnchor();
    expect(a).toEqual([0.03, 0.42, -0.05]);
    const ds = getBrainDockScale();
    // motes land at anchor × dock (the visible, shrunken cortex)
    expect([a[0] * ds, a[1] * ds, a[2] * ds]).toEqual([0.03 * 0.6, 0.42 * 0.6, -0.05 * 0.6]);
  });

  it('publishes the complete moving body frame for sibling scene effects', () => {
    const target = new THREE.Matrix4().makeTranslation(7, 8, 9);
    expect(copyBodyGroupWorldMatrix(target)).toBe(false);

    const source = new THREE.Matrix4().compose(
      new THREE.Vector3(1.2, -0.4, 2.1),
      new THREE.Quaternion().setFromEuler(new THREE.Euler(0.18, -0.7, 0.09)),
      new THREE.Vector3(0.82, 0.82, 0.82),
    );
    const expected = source.elements.slice();
    setBodyGroupWorldMatrix(source);
    source.identity();

    expect(copyBodyGroupWorldMatrix(target)).toBe(true);
    expect(target.elements).toEqual(expected);
  });

  it('reset restores the cortex anchor + dock scale', () => {
    setCortexAnchor([9, 9, 9]);
    setBrainDockScale(0.1);
    __resetSpineFusionForTests();
    expect(getCortexAnchor()).toEqual([0, 0.1, 0]);
    expect(getBrainDockScale()).toBe(1);
    expect(copyBodyGroupWorldMatrix(new THREE.Matrix4())).toBe(false);
  });
});
