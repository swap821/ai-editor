import { act, useEffect } from 'react';
import { _roots, advance, createRoot, extend, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import TierGovernor from '../../superbrain/components/canvas/TierGovernor';
import RenderFrameLoop from '../../superbrain/components/canvas/RenderFrameLoop';
import { QualityTierProvider, useQualityTier, type QualityTier } from '../../superbrain/components/QualityTierProvider';
import { useFeatureGate } from '../../superbrain/core/Performance/FeatureGate';
import { setAmbientMotionPaused } from '../../superbrain/lib/reducedMotion';

// Real governor, installed drei PerformanceMonitor, quality owner, frame policy,
// visibility and R3F store. Only WebGL and frame arrival are controlled. This
// verifies sampled-pacing -> applied-DPR lifecycle, NOT GPU speed or visual fit.
extend({ Mesh: THREE.Mesh, SphereGeometry: THREE.SphereGeometry, MeshBasicMaterial: THREE.MeshBasicMaterial });
let wallMs: number;
let quality: ReturnType<typeof useQualityTier>;
function Scene() {
  const sleeping = useFeatureGate();
  const current = useQualityTier();
  useEffect(() => { quality = current; }, [current]);
  return <>
    <RenderFrameLoop sleeping={sleeping} />
    <TierGovernor />
    <mesh><sphereGeometry args={[1, 8, 8]} /><meshBasicMaterial color="#7bf5fb" /></mesh>
  </>;
}
beforeEach(() => {
  wallMs = 10_000;
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'requestAnimationFrame', 'cancelAnimationFrame'] });
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: false }));
  vi.spyOn(performance, 'now').mockImplementation(() => wallMs);
  vi.spyOn(Date, 'now').mockImplementation(() => wallMs);
  Object.defineProperty(document, 'hidden', { configurable: true, value: true });
  document.dispatchEvent(new Event('visibilitychange'));
  localStorage.removeItem('gagos-pause-motion-v1');
  localStorage.removeItem('gag-quality-tier-v3');
  localStorage.removeItem('gag-quality-tier-v4');
});
afterEach(() => {
  Reflect.deleteProperty(document, 'hidden'); document.dispatchEvent(new Event('visibilitychange'));
  localStorage.removeItem('gagos-pause-motion-v1'); localStorage.removeItem('gag-quality-tier-v3');
  localStorage.removeItem('gag-quality-tier-v4');
  vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers();
});

async function mountGovernor(tier: QualityTier = 'high') {
  localStorage.setItem('gag-quality-tier-v3', tier);
  const ceiling = { high: 1.5, medium: 1.25, low: 1 }[tier];
  const canvas = document.createElement('canvas'), root = createRoot(canvas), store = _roots.get(canvas)!.store;
  let pixelRatio = ceiling, paints = 0;
  const applied: number[] = [];
  const renderer = { domElement: canvas, render(scene: THREE.Scene) { scene.updateMatrixWorld(true); paints++; },
    setSize() {}, setPixelRatio(value: number) { pixelRatio = value; applied.push(value); },
    getPixelRatio: () => pixelRatio } as unknown as RootState['gl'];
  await root.configure({ gl: renderer, dpr: ceiling, scene: new THREE.Scene(), camera: new THREE.PerspectiveCamera(),
    frameloop: 'never', size: { width: 400, height: 400, top: 0, left: 0 } });
  await act(async () => { root.render(<QualityTierProvider><Scene /></QualityTierProvider>); });
  expect(store.getState().frameloop).toBe('never');
  let body!: THREE.Mesh;
  store.getState().scene.traverse(object => { if (object instanceof THREE.Mesh) body = object; });
  const geometry = body.geometry, material = body.material;
  // Warmup expires while hidden; it cannot sample throttled/background frames.
  wallMs += 4_000;
  await act(async () => { vi.advanceTimersByTime(4_000); });
  const visibility = async (hidden: boolean) => act(async () => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: hidden });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await visibility(false);
  expect(store.getState().frameloop).toBe('always');
  const step = (ms: number) => {
    wallMs += ms;
    const state = store.getState();
    if (state.frameloop === 'always' || (state.frameloop === 'demand' && state.internal.frames > 0)) {
      act(() => advance(wallMs / 1000, true, state));
    }
  };
  return { store, applied, body, geometry, material, visibility, step,
    sample(ms: number, frames: number) { for (let i = 0; i < frames; i++) step(ms); },
    dpr: () => store.getState().viewport.dpr, pixels: () => pixelRatio, paints: () => paints,
    close: () => act(async () => { root.unmount(); vi.advanceTimersByTime(600); }),
  };
}

describe('the actual resolution-relief lifecycle', () => {
  // Break caught: finite PerformanceMonitor flipflops counts every above/below
  // budget window (even clamped healthy ones), permanently killing adaptation.
  it.each(['high', 'medium', 'low'] as const)('still responds to load after prolonged healthy frames, tier=%s', async tier => {
    const governor = await mountGovernor(tier);
    const ceiling = { high: 1.5, medium: 1.25, low: 1 }[tier];
    try {
      governor.sample(10, 1_300); // >4 healthy windows: no actual backend work
      expect(governor.dpr()).toBe(ceiling);
      governor.sample(40, 900); // enough existing 10x250ms windows to reach floor
      expect.soft(governor.dpr(), 'healthy rest must not disable later load relief').toBeCloseTo(1, 6);
      expect.soft(governor.pixels()).toBeCloseTo(1, 6);
      governor.sample(10, 3_000);
      expect.soft(governor.dpr(), 'sharpness restores from measured recovery').toBe(ceiling);
      expect(quality.baseTier).toBe(tier); expect(quality.tier).toBe(tier); expect(quality.perfTier).toBe(tier);
      expect(localStorage.getItem('gag-quality-tier-v3')).toBe(tier);
      expect(governor.applied.every(dpr => dpr >= 1 && dpr <= ceiling)).toBe(true);
      expect(governor.body.geometry).toBe(governor.geometry); expect(governor.body.material).toBe(governor.material);
      expect(governor.store.getState().scene.children).toContain(governor.body);
    } finally { await governor.close(); }
  });

  it('continues sustained relief past four declines and restores after genuine recovery', async () => {
    const governor = await mountGovernor();
    try {
      governor.sample(40, 900);
      expect.soft(governor.dpr(), 'a lifetime update quota cannot stop ongoing measured relief').toBeCloseTo(1, 6);
      governor.sample(10, 3_000);
      expect.soft(governor.dpr(), 'the monitor cannot remain latched off at a reduced resolution').toBe(1.5);
      expect(localStorage.getItem('gag-quality-tier-v3')).toBe('high');
    } finally { await governor.close(); }
  });

  it('holds the relieved resolution inside the existing hysteresis band', async () => {
    const governor = await mountGovernor();
    try {
      governor.sample(40, 100); expect(governor.dpr()).toBeCloseTo(1.45, 6);
      const relieved = governor.dpr();
      governor.sample(20, 900); // installed sampling produces ~54fps, between 50 and58
      expect(governor.dpr()).toBe(relieved); expect(governor.pixels()).toBe(relieved);
      governor.sample(10, 3_000); expect(governor.dpr()).toBe(1.5);
    } finally { await governor.close(); }
  });

  it('reports the new manual tier immediately and does not mix a previous tier into its first pacing sample', async () => {
    const governor = await mountGovernor();
    const profile = () => (window as typeof window & {
      __getPerf?: () => { fps: number | null; tier: string; dpr: number };
    }).__getPerf!();
    try {
      governor.sample(40, 100);
      expect(profile().tier).toBe('high'); expect(profile().fps).not.toBeNull();
      await act(async () => { quality.setTier('low'); });
      expect.soft(profile().tier, 'profiling cannot still call the chosen low tier high').toBe('low');
      expect.soft(profile().fps, 'a new cost profile has no qualified pacing sample yet').toBeNull();
      governor.sample(40, 5); //200ms; too short for a fresh half-second sample
      expect.soft(profile().fps, 'the previous tier partial accumulator must not qualify this sample').toBeNull();
      governor.sample(40, 10);
      expect(profile().tier).toBe('low'); expect(profile().fps).toBe(25);
      expect(localStorage.getItem('gag-quality-tier-v3')).toBe('low');
      expect(governor.body.geometry).toBe(governor.geometry);
      expect(governor.body.material).toBe(governor.material);
    } finally { await governor.close(); }
  });

  it('preserves resolution through actual motion pause and hidden gaps, then samples a fresh active window', async () => {
    const governor = await mountGovernor();
    try {
      governor.sample(40, 100); // one real sampled decline, before any fallback quota
      expect(governor.dpr()).toBeCloseTo(1.45, 6);
      const relieved = governor.dpr();
      await act(async () => { setAmbientMotionPaused(true); });
      expect(governor.store.getState().frameloop).toBe('demand');
      governor.step(5_000); const settled = governor.paints();
      governor.step(40_000);
      expect(governor.paints()).toBe(settled); expect(governor.dpr()).toBe(relieved);
      await governor.visibility(true);
      expect(governor.store.getState().frameloop).toBe('never');
      governor.step(40_000);
      expect(governor.paints()).toBe(settled); expect(governor.dpr()).toBe(relieved);
      await governor.visibility(false);
      expect(governor.store.getState().frameloop).toBe('demand');
      expect(governor.dpr()).toBe(relieved);
      await act(async () => { setAmbientMotionPaused(false); });
      expect(governor.store.getState().frameloop).toBe('always');
      expect(governor.dpr()).toBe(relieved); // no optimistic reset before evidence
      governor.sample(10, 300);
      expect(governor.dpr()).toBe(1.5);
      expect(quality.baseTier).toBe('high');
    } finally { await governor.close(); }
  });
});
