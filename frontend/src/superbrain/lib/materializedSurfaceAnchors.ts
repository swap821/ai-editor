import * as THREE from 'three';
import { SEGMENT_ANCHORS } from '@/components/canvas/NervousSystem';

export interface MaterializedSurfacePlacement {
  originLocal: [number, number, number];
  targetLocal: [number, number, number];
  seatIndex?: number;
}

export const BRAINSTEM_INTAKE_LOCAL: [number, number, number] = [0, -1.08, -0.42];

const INPUT_TARGET_LOCAL = new THREE.Vector3(0.28, -0.78, 0.16);
const SEATED_VERTEBRA_INDEX = 2;
const SEAT_FEED_OFFSET = new THREE.Vector3(0.04, 0.02, 0.03);
const CONTENT_TARGET_OFFSET = new THREE.Vector3(0.58, 0.16, 0.22);
const APPROVAL_TARGET_OFFSET = new THREE.Vector3(0.48, 0.1, 0.16);

function toTuple(vector: THREE.Vector3): [number, number, number] {
  return [vector.x, vector.y, vector.z];
}

export function getInputSurfacePlacement(): MaterializedSurfacePlacement {
  return {
    originLocal: BRAINSTEM_INTAKE_LOCAL,
    targetLocal: toTuple(INPUT_TARGET_LOCAL),
  };
}

function getSeatedVertebraPlacement(offset: THREE.Vector3): MaterializedSurfacePlacement {
  const anchor = SEGMENT_ANCHORS[SEATED_VERTEBRA_INDEX];
  const origin = anchor.clone().add(SEAT_FEED_OFFSET);
  const target = anchor.clone().add(offset);
  return {
    originLocal: toTuple(origin),
    targetLocal: toTuple(target),
    seatIndex: SEATED_VERTEBRA_INDEX,
  };
}

export function getContentSurfacePlacement(): MaterializedSurfacePlacement {
  return getSeatedVertebraPlacement(CONTENT_TARGET_OFFSET);
}

export function getApprovalSurfacePlacement(): MaterializedSurfacePlacement {
  return getSeatedVertebraPlacement(APPROVAL_TARGET_OFFSET);
}
