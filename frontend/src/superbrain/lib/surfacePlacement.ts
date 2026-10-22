import { SEGMENT_ANCHOR_COORDINATES } from './spineAnatomyData';
import { readBeingMode } from './beingMode';
import { fuseSpinePoint } from './spineFusionState';

export interface MaterializedSurfacePlacement {
  originLocal: [number, number, number];
  targetLocal: [number, number, number];
  seatIndex?: number;
}
export const BRAINSTEM_INTAKE_LOCAL: [number, number, number] = [0, -1.08, -0.42];
export const DEFAULT_VERTEBRA_SEAT_INDEX = 2;
export const VERTEBRA_SEAT_ORDER: readonly number[] = [2, 3, 1, 4, 5, 0, 6, 7, 8, 9, 10, 11]
  .filter(index => index >= 0 && index < SEGMENT_ANCHOR_COORDINATES.length);

export function getInputSurfacePlacement(): MaterializedSurfacePlacement {
  return { originLocal: BRAINSTEM_INTAKE_LOCAL, targetLocal: [0.28, -0.78, 0.16] };
}
function normalizeSeatIndex(seatIndex = DEFAULT_VERTEBRA_SEAT_INDEX): number {
  return seatIndex >= 0 && seatIndex < SEGMENT_ANCHOR_COORDINATES.length ? seatIndex : DEFAULT_VERTEBRA_SEAT_INDEX;
}
export function selectNextAvailableVertebraSeat(occupiedSeats: readonly number[] = [], preferredSeat?: number | null): number {
  const occupied = new Set(occupiedSeats);
  if (typeof preferredSeat === 'number' && preferredSeat >= 0
    && preferredSeat < SEGMENT_ANCHOR_COORDINATES.length && !occupied.has(preferredSeat)) return preferredSeat;
  return VERTEBRA_SEAT_ORDER.find(seat => !occupied.has(seat)) ?? DEFAULT_VERTEBRA_SEAT_INDEX;
}
function getSeatedVertebraPlacement(offset: readonly [number, number, number], seatIndex?: number | null): MaterializedSurfacePlacement {
  const seat = normalizeSeatIndex(seatIndex ?? DEFAULT_VERTEBRA_SEAT_INDEX);
  const anchor = SEGMENT_ANCHOR_COORDINATES[seat];
  const base = readBeingMode() === 'points' ? fuseSpinePoint(anchor) : anchor;
  return {
    originLocal: [base[0] + 0.04, base[1] + 0.02, base[2] + 0.03],
    targetLocal: [base[0] + offset[0], base[1] + offset[1], base[2] + offset[2]],
    seatIndex: seat,
  };
}
export function getContentSurfacePlacement(seatIndex?: number | null): MaterializedSurfacePlacement {
  return getSeatedVertebraPlacement([0.82, 0.16, 0.24], seatIndex);
}
export function getApprovalSurfacePlacement(seatIndex?: number | null): MaterializedSurfacePlacement {
  return getSeatedVertebraPlacement([0.76, 0.1, 0.2], seatIndex);
}
