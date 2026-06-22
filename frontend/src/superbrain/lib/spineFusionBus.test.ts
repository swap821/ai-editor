import { describe, it, expect, beforeEach } from 'vitest';
import {
  setSpineFusion,
  getSpineFusion,
  fuseSpinePoint,
  __resetSpineFusionForTests,
} from './spineFusionBus';

describe('spineFusionBus', () => {
  beforeEach(() => __resetSpineFusionForTests());

  it('is identity until the field is built', () => {
    expect(getSpineFusion().ready).toBe(false);
    expect(fuseSpinePoint([3, -1.2, 0.5])).toEqual([3, -1.2, 0.5]);
  });

  it('applies scale + weld once set (matches the BrainPointField mapping)', () => {
    setSpineFusion(0.3311, [0.1, -0.5, -0.02]);
    const f = getSpineFusion();
    expect(f.ready).toBe(true);
    expect(f.spineScale).toBeCloseTo(0.3311);
    // P * spineScale + weld
    const [x, y, z] = fuseSpinePoint([0, -1.272, -0.3975]);
    expect(x).toBeCloseTo(0 * 0.3311 + 0.1);
    expect(y).toBeCloseTo(-1.272 * 0.3311 - 0.5);
    expect(z).toBeCloseTo(-0.3975 * 0.3311 - 0.02);
  });
});
