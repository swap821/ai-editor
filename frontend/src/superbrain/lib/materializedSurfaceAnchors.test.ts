import { describe, expect, it } from 'vitest';
import { SEGMENT_ANCHORS } from '@/components/canvas/NervousSystem';
import {
  BRAINSTEM_INTAKE_LOCAL,
  getApprovalSurfacePlacement,
  getContentSurfacePlacement,
  getInputSurfacePlacement,
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
    expect(placement.seatIndex).toBe(2);
    expect(placement.originLocal[0]).toBeGreaterThan(SEGMENT_ANCHORS[2].x);
    expect(placement.originLocal[1]).toBeGreaterThan(SEGMENT_ANCHORS[2].y);
    expect(placement.targetLocal[1]).toBeGreaterThan(placement.originLocal[1]);
    expect(placement.targetLocal[0]).toBeGreaterThan(placement.originLocal[0]);
    expect(placement.targetLocal[2]).toBeGreaterThan(placement.originLocal[2]);
  });

  it('uses the same vertebral seat for approval but keeps it closer than the content slab', () => {
    const approval = getApprovalSurfacePlacement();
    const content = getContentSurfacePlacement();
    expect(approval.seatIndex).toBe(content.seatIndex);
    expect(approval.targetLocal[0]).toBeLessThan(content.targetLocal[0]);
    expect(approval.targetLocal[2]).toBeLessThan(content.targetLocal[2]);
  });
});
