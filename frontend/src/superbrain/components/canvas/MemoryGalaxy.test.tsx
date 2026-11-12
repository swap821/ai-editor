import { act, cleanup, render } from '@testing-library/react';
import * as THREE from 'three';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import MemoryGalaxy from './MemoryGalaxy';

type Row = {
  skill_id: number;
  success_count: number;
  reuse_success_count: number;
  strength: number;
  quarantined: boolean;
};

const h = vi.hoisted(() => ({
  trails: [] as Row[],
  telemetry: null as null | (() => void),
  cognition: null as null | ((e: { type: string; detail?: string }) => void),
  frame: null as null | ((s: { clock: { elapsedTime: number } }) => void),
  telemetryUnsubs: 0,
  cognitionUnsubs: 0,
}));

vi.mock('@react-three/fiber', () => ({
  useFrame: (cb: (s: { clock: { elapsedTime: number } }) => void) => {
    h.frame = cb;
  },
}));

vi.mock('@/lib/cognitionBus', () => ({
  subscribeCognition: (cb: (e: { type: string; detail?: string }) => void) => {
    h.cognition = cb;
    return () => {
      h.cognitionUnsubs += 1;
    };
  },
}));

vi.mock('@/lib/aiosAdapter', () => ({
  getKnownTrails: () => h.trails,
  subscribeTelemetry: (cb: () => void) => {
    h.telemetry = cb;
    return () => {
      h.telemetryUnsubs += 1;
    };
  },
}));

const TRAILS: Row[] = [
  { skill_id: 5, success_count: 2, reuse_success_count: 1, strength: 0.5, quarantined: true },
  { skill_id: 2, success_count: 3, reuse_success_count: 1, strength: 1.7, quarantined: false },
];

describe('MemoryGalaxy', () => {
  const geometries: THREE.BufferGeometry[] = [];
  let disposeSpy: ReturnType<typeof vi.spyOn>;
  let drawRangeSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    h.trails = [];
    h.telemetry = null;
    h.cognition = null;
    h.frame = null;
    h.telemetryUnsubs = 0;
    h.cognitionUnsubs = 0;
    geometries.length = 0;
    const original = THREE.BufferGeometry.prototype.setDrawRange;
    drawRangeSpy = vi
      .spyOn(THREE.BufferGeometry.prototype, 'setDrawRange')
      .mockImplementation(function (this: THREE.BufferGeometry, start: number, count: number) {
        geometries.push(this);
        original.call(this, start, count);
      });
    disposeSpy = vi.spyOn(THREE.BufferGeometry.prototype, 'dispose');
  });

  afterEach(() => {
    cleanup();
    drawRangeSpy.mockRestore();
    disposeSpy.mockRestore();
  });

  it('renders nothing while dormant and shows stars once trails appear', () => {
    const { container } = render(<MemoryGalaxy />);
    expect(container.querySelector('points')).toBeNull();

    h.trails = [TRAILS[0]];
    act(() => h.telemetry?.());
    expect(container.querySelector('points')).not.toBeNull();
    expect(geometries[0].drawRange.count).toBe(1);
  });

  it('writes per-star attributes sorted by skill id', () => {
    h.trails = TRAILS;
    const { container } = render(<MemoryGalaxy />);
    expect(container.querySelector('points')).not.toBeNull();

    const geo = geometries[0];
    expect(geo.drawRange.count).toBe(2);
    expect((window as unknown as Record<string, unknown>).__gagGalaxyCount).toBe(2);
    const at = (name: string, i: number) => geo.getAttribute(name).array[i];

    // slot 0 = skill 2 (4 walks, strength clamped to 1, healthy, even id => positive speed)
    expect(at('aSize', 0)).toBeCloseTo(2.4 + 4 * 0.55, 4);
    expect(at('aStrength', 0)).toBe(1);
    expect(at('aQuarantine', 0)).toBe(0);
    expect(at('aSpeed', 0)).toBeGreaterThanOrEqual(0.008);
    expect(at('aSpeed', 0)).toBeLessThanOrEqual(0.022);
    // slot 1 = skill 5 (3 walks, quarantined, odd id => negative speed)
    expect(at('aSize', 1)).toBeCloseTo(2.4 + 3 * 0.55, 4);
    expect(at('aStrength', 1)).toBeCloseTo(0.5, 5);
    expect(at('aQuarantine', 1)).toBe(1);
    expect(at('aSpeed', 1)).toBeLessThanOrEqual(-0.008);
    expect(at('aSpeed', 1)).toBeGreaterThanOrEqual(-0.022);
    expect(at('aRadius', 0)).toBeGreaterThanOrEqual(7.5);
    expect(at('aRadius', 0)).toBeLessThanOrEqual(13);
  });

  it('flashes only the star named by a knowledge or burst event', () => {
    h.trails = TRAILS;
    render(<MemoryGalaxy />);
    const flash = geometries[0].getAttribute('aFlash').array;
    expect(flash[0]).toBe(-10);
    expect(flash[1]).toBe(-10);

    act(() => h.frame?.({ clock: { elapsedTime: 3.5 } }));
    act(() => h.cognition?.({ type: 'idle', detail: 'trail #2' }));
    expect(flash[0]).toBe(-10);
    act(() => h.cognition?.({ type: 'burst', detail: 'recall of trail #999' }));
    expect(flash[0]).toBe(-10);
    expect(flash[1]).toBe(-10);

    act(() => h.cognition?.({ type: 'burst', detail: 'recall of trail #5' }));
    expect(flash[1]).toBeCloseTo(3.5, 5);
    expect(flash[0]).toBe(-10);
  });

  it('resyncs on telemetry and cleans up on unmount', () => {
    h.trails = [TRAILS[0]];
    const { unmount } = render(<MemoryGalaxy />);
    expect(geometries[0].drawRange.count).toBe(1);

    h.trails = TRAILS;
    act(() => h.telemetry?.());
    expect(geometries[0].drawRange.count).toBe(2);

    unmount();
    expect(h.telemetryUnsubs).toBe(1);
    expect(h.cognitionUnsubs).toBe(1);
    expect(disposeSpy).toHaveBeenCalledTimes(1);
  });
});
