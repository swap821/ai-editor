import * as THREE from 'three';
import { copyBodyGroupWorldMatrix, copyBodyShapeWorldFrame, getCortexAnchor, getSpineFusion } from '../superbrain/lib/spineFusionBus';
import { SEGMENT_ANCHORS } from '../superbrain/lib/spineAnatomy';

/** Preserve authored effect-space sizing while following a body's live pose. */
export function copyBodyGroupPoseMatrix(source: THREE.Matrix4, target: THREE.Matrix4): void {
  target.extractRotation(source);
  const { elements } = source;
  target.setPosition(elements[12], elements[13], elements[14]);
}

/** Caller-owned scratch, not a second body pose or animation clock. */
export function createCortexEffectFrame() {
  return {
    bodyWorld: new THREE.Matrix4(), poseInverse: new THREE.Matrix4(),
    shapeWorld: new THREE.Matrix4(), shapeToEffects: new THREE.Matrix4(), bounds: new THREE.Box3(),
    offset: new THREE.Vector3(), target: new THREE.Vector3(),
  };
}

export type CortexEffectFrame = ReturnType<typeof createCortexEffectFrame>;

/** Resolve the actual mounted field into the existing unit-scale effect frame.
 * Only anchor positions inherit anatomy scale; cue radii and authored offsets do not. */
export function copyCortexEffectFrame(frame: CortexEffectFrame, authoredOrigin: THREE.Vector3): boolean {
  frame.offset.set(0, 0, 0);
  if (!copyBodyGroupWorldMatrix(frame.bodyWorld) || !copyBodyShapeWorldFrame(frame.bounds, frame.shapeWorld)) return false;
  copyBodyGroupPoseMatrix(frame.bodyWorld, frame.poseInverse);
  if (!frame.poseInverse.elements.every(Number.isFinite)) return false;
  frame.shapeToEffects.copy(frame.poseInverse.invert()).multiply(frame.shapeWorld);
  const anchor = getCortexAnchor();
  frame.offset.set(anchor[0], anchor[1], anchor[2]).applyMatrix4(frame.shapeToEffects).sub(authoredOrigin);
  if (Number.isFinite(frame.offset.x + frame.offset.y + frame.offset.z)) return true;
  frame.offset.set(0, 0, 0);
  return false;
}

/** Target in the translated cue group's authored coordinates. No allocation. */
export function copyCortexEffectTarget(frame: CortexEffectFrame, input: boolean, seatIndex: number | null): THREE.Vector3 | null {
  if (!input && (!Number.isInteger(seatIndex) || seatIndex === null || seatIndex < 0 || seatIndex >= SEGMENT_ANCHORS.length)) return null;
  const dial = input && typeof window !== 'undefined' ? (window as unknown as { __FUNNEL_Y?: unknown }).__FUNNEL_Y : undefined;
  if (typeof dial === 'number' && Number.isFinite(dial)) {
    frame.target.set(0, dial, 0);
  } else {
    const raw = input ? null : SEGMENT_ANCHORS[seatIndex ?? 0];
    frame.target.set(raw?.x ?? 0, raw?.y ?? -2.85, raw?.z ?? -0.42);
    const fusion = getSpineFusion();
    if (fusion.ready) {
      frame.target.multiplyScalar(fusion.spineScale);
      frame.target.x += fusion.weld[0]; frame.target.y += fusion.weld[1]; frame.target.z += fusion.weld[2];
    }
  }
  return frame.target.applyMatrix4(frame.shapeToEffects).sub(frame.offset);
}
