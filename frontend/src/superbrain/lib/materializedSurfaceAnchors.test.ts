import { describe, expect, it } from 'vitest';
import { SEGMENT_ANCHORS } from '@/lib/spineAnatomy';
import {
  BRAINSTEM_INTAKE_LOCAL,
  DEFAULT_VERTEBRA_SEAT_INDEX,
  getApprovalSurfacePlacement,
  getContentSurfacePlacement,
  getInputSurfacePlacement,
  selectNextAvailableVertebraSeat,
} from './materializedSurfaceAnchors';

describe('materializedSurfaceAnchors', () => {
  it('keeps the input surface born from the brainstem intake', () => {
    const placement = getInputSurfacePlacement();
    expect(placement.originLocal).toEqual(BRAINSTEM_INTAKE_LOCAL);
    expect(placement.targetLocal[0]).toBeGreaterThan(placement.originLocal[0]);
    expect(placement.targetLocal[1]).toBeGreaterThan(placement.originLocal[1]);
  });

  it('seats the content surface on a vertebra and pushes it outward from the spine', () => {
    const placement = getContentSurfacePlacement();
    expect(placement.seatIndex).toBe(DEFAULT_VERTEBRA_SEAT_INDEX);
    expect(placement.originLocal[0]).toBeGreaterThan(SEGMENT_ANCHORS[DEFAULT_VERTEBRA_SEAT_INDEX].x);
    expect(placement.originLocal[1]).toBeGreaterThan(SEGMENT_ANCHORS[DEFAULT_VERTEBRA_SEAT_INDEX].y);
    expect(placement.targetLocal[1]).toBeGreaterThan(placement.originLocal[1]);
    expect(placement.targetLocal[0]).toBeGreaterThan(placement.originLocal[0]);
    expect(placement.targetLocal[2]).toBeGreaterThan(placement.originLocal[2]);
  });

  it('can seat a content surface on a later vertebra without changing the outward offset rule', () => {
    const placement = getContentSurfacePlacement(4);
    expect(placement.seatIndex).toBe(4);
    expect(placement.originLocal[1]).toBeGreaterThan(SEGMENT_ANCHORS[4].y);
    expect(placement.targetLocal[0]).toBeGreaterThan(placement.originLocal[0]);
  });

  it('uses the same vertebral seat for approval but keeps it closer than the content slab', () => {
    const approval = getApprovalSurfacePlacement(3);
    const content = getContentSurfacePlacement(3);
    expect(approval.seatIndex).toBe(content.seatIndex);
    expect(approval.targetLocal[0]).toBeLessThan(content.targetLocal[0]);
    expect(approval.targetLocal[2]).toBeLessThan(content.targetLocal[2]);
  });

  it('chooses the next visible free vertebra before falling back to the default', () => {
    expect(selectNextAvailableVertebraSeat([])).toBe(DEFAULT_VERTEBRA_SEAT_INDEX);
    expect(selectNextAvailableVertebraSeat([DEFAULT_VERTEBRA_SEAT_INDEX])).toBe(3);
    expect(selectNextAvailableVertebraSeat([DEFAULT_VERTEBRA_SEAT_INDEX], 4)).toBe(4);
  });
});
