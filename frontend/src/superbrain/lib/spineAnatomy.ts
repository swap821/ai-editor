import * as THREE from 'three';
import { SEGMENT_ANCHOR_COORDINATES } from './spineAnatomyData';
export { CORD_Z, SEGMENT_COUNT, SEGMENT_TOP_Y, SEGMENT_BOTTOM_Y } from './spineAnatomyData';

/** The same shared vertebral coordinates, represented as scene-local vectors. */
export const SEGMENT_ANCHORS: ReadonlyArray<THREE.Vector3> = SEGMENT_ANCHOR_COORDINATES.map(
  point => new THREE.Vector3(...point),
);
