import * as THREE from 'three';

export const CORD_Z = -0.42;            // base depth (Z) the cord descends at

export const SEGMENT_COUNT: number = 12; // # of evenly-spaced vertebral anchors down the cord
export const SEGMENT_TOP_Y = -0.92;     // Y of the topmost (cervical) anchor
export const SEGMENT_BOTTOM_Y = -2.85;  // Y of the lowest (lumbar/sacral) anchor

/**
 * SEGMENT_ANCHORS — the evenly-spaced vertebral anchor positions (group-local
 * Vector3), top→bottom. EXPORTED so the orchestration phase (P4) can SEAT a
 * materialized 3D tab at each vertebra: the rest-state cord and the future
 * conductor are literally the same anatomy (the spinal-cord law).
 * Index 0 = topmost (cervical), index SEGMENT_COUNT-1 = lowest (lumbar/sacral).
 */
export const SEGMENT_ANCHORS: ReadonlyArray<THREE.Vector3> = Array.from(
  { length: SEGMENT_COUNT },
  (_, i) => {
    const f = SEGMENT_COUNT === 1 ? 0 : i / (SEGMENT_COUNT - 1); // 0 (top) → 1 (bottom)
    const y = THREE.MathUtils.lerp(SEGMENT_TOP_Y, SEGMENT_BOTTOM_Y, f);
    // sit ON the cord (which bows gently forward mid-descent), not beside it
    const z = CORD_Z + Math.sin(f * Math.PI) * 0.04;
    return new THREE.Vector3(0, y, z);
  }
);
