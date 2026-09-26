import * as THREE from 'three';

/** Preserve authored effect-space sizing while following a body's live pose. */
export function copyBodyGroupPoseMatrix(source: THREE.Matrix4, target: THREE.Matrix4): void {
  target.extractRotation(source);
  const { elements } = source;
  target.setPosition(elements[12], elements[13], elements[14]);
}
