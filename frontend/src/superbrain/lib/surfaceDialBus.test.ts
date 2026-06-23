import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  DEFAULT_SURFACE_DIAL,
  __resetSurfaceDialForTests,
  getSurfaceDial,
  installSurfaceDialWindow,
  setSurfaceDial,
  subscribeSurfaceDial,
} from './surfaceDialBus';

afterEach(() => {
  __resetSurfaceDialForTests();
});

describe('surfaceDialBus defaults', () => {
  it('defaults to zero-regression (membrane + pointSkin OFF, all multipliers neutral)', () => {
    expect(getSurfaceDial()).toEqual({
      membrane: false,
      pointSkin: false,
      membraneOpacity: 1,
      veinOpacity: 1,
      nodeOpacity: 1,
      rimOpacity: 0.38,
      titleOpacity: 1,
    });
  });

  it('exposes the same defaults object shape as DEFAULT_SURFACE_DIAL', () => {
    expect(getSurfaceDial()).toEqual(DEFAULT_SURFACE_DIAL);
  });
});

describe('setSurfaceDial', () => {
  it('merges a partial without disturbing untouched knobs', () => {
    setSurfaceDial({ membrane: true, membraneOpacity: 0.6 });
    const d = getSurfaceDial();
    expect(d.membrane).toBe(true);
    expect(d.membraneOpacity).toBe(0.6);
    expect(d.veinOpacity).toBe(1); // untouched
    expect(d.rimOpacity).toBe(0.38); // untouched
  });

  it('returns a NEW reference on real change (so useSyncExternalStore re-renders)', () => {
    const before = getSurfaceDial();
    setSurfaceDial({ membrane: true });
    expect(getSurfaceDial()).not.toBe(before);
  });

  it('returns the SAME reference and does not notify when nothing changes', () => {
    const before = getSurfaceDial();
    const listener = vi.fn();
    subscribeSurfaceDial(listener);
    setSurfaceDial({});
    expect(getSurfaceDial()).toBe(before);
    expect(listener).not.toHaveBeenCalled();
  });

  it('ignores unknown keys', () => {
    setSurfaceDial({ bogus: 5 } as never);
    expect(getSurfaceDial()).toEqual(DEFAULT_SURFACE_DIAL);
  });

  it('ignores undefined values (leaves the knob at its prior value)', () => {
    setSurfaceDial({ membrane: true });
    setSurfaceDial({ membrane: undefined });
    expect(getSurfaceDial().membrane).toBe(true);
  });
});

describe('subscribeSurfaceDial', () => {
  it('notifies on change and stops after unsubscribe', () => {
    const listener = vi.fn();
    const unsub = subscribeSurfaceDial(listener);
    setSurfaceDial({ veinOpacity: 0.5 });
    expect(listener).toHaveBeenCalledTimes(1);
    unsub();
    setSurfaceDial({ veinOpacity: 0.2 });
    expect(listener).toHaveBeenCalledTimes(1);
  });
});

describe('installSurfaceDialWindow', () => {
  it('wires window.__SURFACE assignment and dot-mutation through setSurfaceDial', () => {
    const fake = {} as unknown as typeof globalThis;
    installSurfaceDialWindow(fake);
    const win = fake as unknown as Record<string, unknown> & { __SURFACE: any };

    // full-object assignment merges
    win.__SURFACE = { membrane: true, membraneOpacity: 0.7 };
    expect(getSurfaceDial().membrane).toBe(true);
    expect(getSurfaceDial().membraneOpacity).toBe(0.7);

    // single-knob mutation routes through the proxy
    win.__SURFACE.rimOpacity = 0.55;
    expect(getSurfaceDial().rimOpacity).toBe(0.55);

    // proof hook reads the live snapshot
    expect((win.__getSurfaceDial as () => unknown)()).toBe(getSurfaceDial());
  });
});
