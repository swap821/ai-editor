import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { copyBodyGroupPoseMatrix } from './bodyEffectsFrame';

describe('copyBodyGroupPoseMatrix', () => {
  it('follows body translation and rotation without scaling calibrated effect coordinates twice', () => {
    const position = new THREE.Vector3(0.42, 0.18, -1.2);
    const rotation = new THREE.Quaternion().setFromEuler(new THREE.Euler(0.04, -0.78, 0.02));
    const authoredBodyScale = new THREE.Vector3(3.02, 3.02, 3.02);
    const source = new THREE.Matrix4().compose(position, rotation, authoredBodyScale);
    const target = new THREE.Matrix4();

    copyBodyGroupPoseMatrix(source, target);

    const effectPoint = new THREE.Vector3(0, -1.08, -0.42);
    const expected = effectPoint.clone().applyQuaternion(rotation).add(position);
    const actual = effectPoint.clone().applyMatrix4(target);
    expect(actual.distanceTo(expected)).toBeLessThan(1e-10);
    expect(target.getMaxScaleOnAxis()).toBeCloseTo(1, 10);
  });
});
