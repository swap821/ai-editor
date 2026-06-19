import * as THREE from 'three';
import { SEGMENT_ANCHORS } from '@/lib/spineAnatomy';

export interface MaterializedSurfacePlacement {
  originLocal: [number, number, number];
  targetLocal: [number, number, number];
  seatIndex?: number;
}

export const BRAINSTEM_INTAKE_LOCAL: [number, number, number] = [0, -1.08, -0.42];

const INPUT_TARGET_LOCAL = new THREE.Vector3(0.28, -0.78, 0.16);
export const DEFAULT_VERTEBRA_SEAT_INDEX = 2;
export const VERTEBRA_SEAT_ORDER: readonly number[] = [2, 3, 1, 4, 5, 0, 6, 7, 8, 9, 10, 11].filter(
  (index) => index >= 0 && index < SEGMENT_ANCHORS.length,
);
const SEAT_FEED_OFFSET = new THREE.Vector3(0.04, 0.02, 0.03);
const CONTENT_TARGET_OFFSET = new THREE.Vector3(0.82, 0.16, 0.24);
const APPROVAL_TARGET_OFFSET = new THREE.Vector3(0.76, 0.1, 0.2);

function toTuple(vector: THREE.Vector3): [number, number, number] {
  return [vector.x, vector.y, vector.z];
}

export function getInputSurfacePlacement(): MaterializedSurfacePlacement {
  return {
    originLocal: BRAINSTEM_INTAKE_LOCAL,
    targetLocal: toTuple(INPUT_TARGET_LOCAL),
  };
}

function normalizeSeatIndex(seatIndex = DEFAULT_VERTEBRA_SEAT_INDEX): number {
  if (seatIndex >= 0 && seatIndex < SEGMENT_ANCHORS.length) return seatIndex;
  return DEFAULT_VERTEBRA_SEAT_INDEX;
}

export function selectNextAvailableVertebraSeat(occupiedSeats: readonly number[] = [], preferredSeat?: number | null): number {
  const occupied = new Set(occupiedSeats);
  if (
    typeof preferredSeat === 'number' &&
    preferredSeat >= 0 &&
    preferredSeat < SEGMENT_ANCHORS.length &&
    !occupied.has(preferredSeat)
  ) {
    return preferredSeat;
  }
  return VERTEBRA_SEAT_ORDER.find((seatIndex) => !occupied.has(seatIndex)) ?? DEFAULT_VERTEBRA_SEAT_INDEX;
}

function getSeatedVertebraPlacement(offset: THREE.Vector3, seatIndex?: number | null): MaterializedSurfacePlacement {
  const resolvedSeat = normalizeSeatIndex(seatIndex ?? DEFAULT_VERTEBRA_SEAT_INDEX);
  const anchor = SEGMENT_ANCHORS[resolvedSeat];
  const origin = anchor.clone().add(SEAT_FEED_OFFSET);
  const target = anchor.clone().add(offset);
  return {
    originLocal: toTuple(origin),
    targetLocal: toTuple(target),
    seatIndex: resolvedSeat,
  };
}

export function getContentSurfacePlacement(seatIndex?: number | null): MaterializedSurfacePlacement {
  return getSeatedVertebraPlacement(CONTENT_TARGET_OFFSET, seatIndex);
}

export function getApprovalSurfacePlacement(seatIndex?: number | null): MaterializedSurfacePlacement {
  return getSeatedVertebraPlacement(APPROVAL_TARGET_OFFSET, seatIndex);
}
