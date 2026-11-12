import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  readBeingMode: vi.fn<() => string>(),
  fuseSpinePoint: vi.fn<(point: readonly number[]) => [number, number, number]>(),
}));

vi.mock('./beingMode', () => ({
  readBeingMode: mocks.readBeingMode,
}));

vi.mock('./spineFusionState', () => ({
  fuseSpinePoint: mocks.fuseSpinePoint,
}));

import {
  VERTEBRA_SEAT_ORDER,
  getApprovalSurfacePlacement,
  getContentSurfacePlacement,
  getInputSurfacePlacement,
  selectNextAvailableVertebraSeat,
} from './surfacePlacement';

beforeEach(() => {
  mocks.readBeingMode.mockReset();
  mocks.fuseSpinePoint.mockReset();
  mocks.readBeingMode.mockReturnValue('rest');
  mocks.fuseSpinePoint.mockReturnValue([10, 20, 30]);
});

describe('getInputSurfacePlacement', () => {
  it('targets the fixed input position', () => {
    expect(getInputSurfacePlacement().targetLocal).toEqual([0.28, -0.78, 0.16]);
  });
});

describe('selectNextAvailableVertebraSeat', () => {
  it('picks the first seat in order when nothing is occupied', () => {
    expect(selectNextAvailableVertebraSeat()).toBe(VERTEBRA_SEAT_ORDER[0]);
    expect(selectNextAvailableVertebraSeat([])).toBe(VERTEBRA_SEAT_ORDER[0]);
  });

  it('skips occupied seats following the seat order', () => {
    expect(selectNextAvailableVertebraSeat([VERTEBRA_SEAT_ORDER[0]])).toBe(VERTEBRA_SEAT_ORDER[1]);
    expect(
      selectNextAvailableVertebraSeat([VERTEBRA_SEAT_ORDER[0], VERTEBRA_SEAT_ORDER[1]]),
    ).toBe(VERTEBRA_SEAT_ORDER[2]);
  });

  it('honours a free preferred seat and falls back when it is occupied', () => {
    const preferred = VERTEBRA_SEAT_ORDER[3];
    expect(selectNextAvailableVertebraSeat([], preferred)).toBe(preferred);
    expect(selectNextAvailableVertebraSeat([preferred], preferred)).toBe(VERTEBRA_SEAT_ORDER[0]);
    expect(selectNextAvailableVertebraSeat([], null)).toBe(VERTEBRA_SEAT_ORDER[0]);
  });
});

describe('seated surface placements', () => {
  it('offsets content origin and target relative to the same seat anchor', () => {
    const seat = VERTEBRA_SEAT_ORDER[1];
    const placement = getContentSurfacePlacement(seat);
    expect(placement.seatIndex).toBe(seat);
    expect(placement.targetLocal[0] - placement.originLocal[0]).toBeCloseTo(0.78);
    expect(placement.targetLocal[1] - placement.originLocal[1]).toBeCloseTo(0.14);
    expect(placement.targetLocal[2] - placement.originLocal[2]).toBeCloseTo(0.21);
    expect(mocks.fuseSpinePoint).not.toHaveBeenCalled();
  });

  it('uses a smaller offset for approval placements', () => {
    const seat = VERTEBRA_SEAT_ORDER[2];
    const placement = getApprovalSurfacePlacement(seat);
    expect(placement.seatIndex).toBe(seat);
    expect(placement.targetLocal[0] - placement.originLocal[0]).toBeCloseTo(0.72);
    expect(placement.targetLocal[1] - placement.originLocal[1]).toBeCloseTo(0.08);
    expect(placement.targetLocal[2] - placement.originLocal[2]).toBeCloseTo(0.17);
  });

  it('builds on the fused point in points mode', () => {
    mocks.readBeingMode.mockReturnValue('points');
    const seat = VERTEBRA_SEAT_ORDER[0];

    const content = getContentSurfacePlacement(seat);
    expect(mocks.fuseSpinePoint).toHaveBeenCalledTimes(1);
    expect(content.originLocal[0]).toBeCloseTo(10.04);
    expect(content.originLocal[1]).toBeCloseTo(20.02);
    expect(content.originLocal[2]).toBeCloseTo(30.03);
    expect(content.targetLocal[0]).toBeCloseTo(10.82);
    expect(content.targetLocal[1]).toBeCloseTo(20.16);
    expect(content.targetLocal[2]).toBeCloseTo(30.24);

    const approval = getApprovalSurfacePlacement(seat);
    expect(approval.targetLocal[0]).toBeCloseTo(10.76);
    expect(approval.targetLocal[1]).toBeCloseTo(20.1);
    expect(approval.targetLocal[2]).toBeCloseTo(30.2);
  });
});
