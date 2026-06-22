import { describe, it, expect } from 'vitest';
import {
  deriveOrganismCameraFrame,
  LANDSCAPE_ASPECT,
  PORTRAIT_ASPECT,
} from './organismCameraFrame';

describe('deriveOrganismCameraFrame', () => {
  it('wide desktop = the exact current framing (no regression)', () => {
    const f = deriveOrganismCameraFrame({ aspect: 1.78, activeSurfaceCount: 0 });
    expect(f.fov).toBe(26);
    expect(f.targetY).toBe(-0.5);
  });

  it('at/above the landscape threshold it is fully the desktop frame', () => {
    const f = deriveOrganismCameraFrame({ aspect: LANDSCAPE_ASPECT, activeSurfaceCount: 0 });
    expect(f).toEqual({ fov: 26, targetY: -0.5 });
  });

  it('portrait narrows fov (enlarge the being) + raises the look out of the void', () => {
    const f = deriveOrganismCameraFrame({ aspect: 0.46, activeSurfaceCount: 0 }); // tall phone
    expect(f.fov).toBeLessThan(26); // narrower → being fills more
    expect(f.targetY).toBeGreaterThan(-0.5); // raised (less negative → climbs up)
  });

  it('clamps to the portrait anchor below the portrait threshold', () => {
    const f = deriveOrganismCameraFrame({ aspect: PORTRAIT_ASPECT - 0.3, activeSurfaceCount: 0 });
    expect(f.fov).toBeCloseTo(22, 3);
    expect(f.targetY).toBeCloseTo(-0.4, 3);
  });

  it('monotonic: narrower aspect → smaller fov + higher target', () => {
    const wide = deriveOrganismCameraFrame({ aspect: 1.78, activeSurfaceCount: 0 });
    const mid = deriveOrganismCameraFrame({ aspect: 1.0, activeSurfaceCount: 0 });
    const tall = deriveOrganismCameraFrame({ aspect: 0.5, activeSurfaceCount: 0 });
    expect(mid.fov).toBeLessThan(wide.fov);
    expect(tall.fov).toBeLessThan(mid.fov);
    expect(mid.targetY).toBeGreaterThan(wide.targetY);
    expect(tall.targetY).toBeGreaterThan(mid.targetY);
  });

  it('orchestration widens fov to fit seated surfaces (capped at ~3)', () => {
    const none = deriveOrganismCameraFrame({ aspect: 1.78, activeSurfaceCount: 0 });
    const three = deriveOrganismCameraFrame({ aspect: 1.78, activeSurfaceCount: 3 });
    const many = deriveOrganismCameraFrame({ aspect: 1.78, activeSurfaceCount: 9 });
    expect(three.fov).toBeGreaterThan(none.fov);
    expect(many.fov).toBe(three.fov); // capped
  });
});
