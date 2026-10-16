import { act, useEffect } from 'react';
import { _roots, advance, createRoot, extend } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import TierGovernor from '../../superbrain/components/canvas/TierGovernor';
import { QualityTierProvider, useQualityTier } from '../../superbrain/components/QualityTierProvider';

// Real owner/governor/installed PerformanceMonitor. Only GL and frame arrival
// are external sinks. No hardware/FPS/appearance verdict is inferred.
extend({ Group: THREE.Group });
let wallMs, quality;
function Scene({ densityAllowed = true }) {
  const current = useQualityTier();
  useEffect(() => { quality = current; }, [current]);
  return <><TierGovernor densityChangesAllowed={densityAllowed} /><group /></>;
}
beforeEach(() => {
  wallMs = 10000; quality = null; localStorage.clear();
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  // advance() is the sole external frame-arrival driver. A second automatic
  // RAF loop would fabricate extra frames within each controlled interval.
  vi.stubGlobal('requestAnimationFrame', () => 1);
  vi.stubGlobal('cancelAnimationFrame', () => {});
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('devicePixelRatio', 2);
  vi.spyOn(performance, 'now').mockImplementation(() => wallMs);
  Object.defineProperty(document, 'hidden', { configurable: true, value: false });
  document.dispatchEvent(new Event('visibilitychange'));
});
afterEach(() => {
  localStorage.clear(); Reflect.deleteProperty(document, 'hidden');
  document.dispatchEvent(new Event('visibilitychange'));
  vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers();
});
async function mount() {
  const canvas = document.createElement('canvas'); document.body.append(canvas);
  const root = createRoot(canvas), store = _roots.get(canvas).store;
  let ratio = 1.5;
  let lost = false;
  const gl = { domElement: canvas, setPixelRatio: value => { ratio = value; }, getPixelRatio: () => ratio,
    setSize() {}, render() {}, getContext: () => ({ isContextLost: () => lost }) };
  await root.configure({ gl, dpr: [1, 1.5], scene: new THREE.Scene(), camera: new THREE.PerspectiveCamera(),
    frameloop: 'always', size: { width: 400, height: 400, top: 0, left: 0 } });
  await act(async () => { root.render(<QualityTierProvider><Scene /></QualityTierProvider>); });
  await act(async () => { wallMs += 4000; vi.advanceTimersByTime(4000); });
  const sample = async (ms, frames) => act(async () => {
    for (let index = 0; index < frames; index++) {
      wallMs += ms; vi.advanceTimersByTime(ms);
      advance(wallMs / 1000, false, store.getState());
    }
  });
  return { canvas, store, sample, dpr: () => ratio,
    lose: value => { lost = value; },
    density: allowed => act(async () => { root.render(<QualityTierProvider><Scene densityAllowed={allowed} /></QualityTierProvider>); }),
    ready: () => act(() => window.dispatchEvent(new CustomEvent('gagos:ready', { detail: { canvas } }))),
    close: () => act(async () => { root.unmount(); vi.advanceTimersByTime(600); canvas.remove(); }) };
}

// Break caught: merely relabeling the existing DPR-only manual controller as
// Auto, or persisting a measured demotion, cannot satisfy this sequence.
it('defaults to Auto and relieves optional multisampling before reducing actual resolution', async () => {
  const renderer = await mount();
  try {
    expect(quality.preference).toBe('auto');
    renderer.ready(); await renderer.sample(10, 2100); // useful-frame warmup, not backend work
    expect(quality.autoProfile.multisampling).toBe(4);
    await renderer.sample(40, 80); // one installed slow 10x250ms window
    expect(quality.autoProfile.multisampling).toBe(0);
    expect(quality.autoProfile.skyTier).toBe('high');
    expect(quality.autoProfile.densityTier).toBe('high');
    expect(renderer.dpr()).toBe(1.5);
    expect(localStorage.getItem('gag-quality-tier-v4')).toBeNull();
    expect(localStorage.getItem('gag-quality-tier-v3')).toBeNull();
  } finally { await renderer.close(); }
});

it('excludes hidden, paused and lost-context windows and resumes with a fresh admission epoch', async () => {
  const renderer = await mount();
  try {
    renderer.ready(); await renderer.sample(10, 2100);
    const stale = quality.autoRevision;
    await act(async () => {
      Object.defineProperty(document, 'hidden', { configurable: true, value: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await renderer.sample(40, 200);
    expect(quality.autoProfile.stage).toBe(0);
    await act(async () => {
      Object.defineProperty(document, 'hidden', { configurable: true, value: false });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await act(async () => { quality.reportAutoWindow('slow', stale, wallMs + 5000, true); });
    expect(quality.autoProfile.stage).toBe(0);
    await act(async () => { renderer.store.getState().setFrameloop('demand'); });
    await renderer.sample(40, 200);
    expect(quality.autoProfile.stage).toBe(0);
    await act(async () => { renderer.store.getState().setFrameloop('always'); });
    renderer.lose(true); await renderer.sample(40, 200);
    expect(quality.autoProfile.stage).toBe(0);
    renderer.lose(false); await renderer.sample(40, 200);
    expect(quality.autoProfile.stage).toBe(1);
  } finally { await renderer.close(); }
});

it('steps through actual monitor relief and measured recovery without persisting stages or replacing the root', async () => {
  const renderer = await mount();
  const scene = renderer.store.getState().scene, camera = renderer.store.getState().camera;
  try {
    renderer.ready(); await renderer.sample(10, 2100);
    for (let stage = 1; stage <= 6; stage++) {
      await renderer.sample(40, 200);
      expect(quality.autoProfile.stage).toBe(stage);
      expect(renderer.dpr()).toBe(stage < 3 ? 1.5 : stage === 3 ? 1.25 : 1);
    }
    for (let stage = 5; stage >= 0; stage--) {
      await renderer.sample(10, 1600);
      expect(quality.autoProfile.stage).toBe(stage);
    }
    expect(renderer.store.getState().scene).toBe(scene);
    expect(renderer.store.getState().camera).toBe(camera);
    expect(localStorage.getItem('gag-quality-tier-v4')).toBeNull();
    expect(localStorage.getItem('gag-quality-tier-v3')).toBeNull();
  } finally { await renderer.close(); }
});

it('defers density changes during critical input/hold and respects manual override', async () => {
  const renderer = await mount();
  try {
    renderer.ready(); await renderer.sample(10, 2100);
    await renderer.density(false);
    for (let stage = 1; stage <= 4; stage++) await renderer.sample(40, 200);
    expect(quality.autoProfile.stage).toBe(4);
    await renderer.sample(40, 200);
    expect(quality.autoProfile.stage).toBe(4);
    expect(quality.autoProfile.densityTier).toBe('high');
    await renderer.density(true); await renderer.sample(40, 200);
    expect(quality.autoProfile.stage).toBe(5);
    await act(async () => { quality.setTier('medium'); });
    await renderer.sample(40, 300);
    expect(quality.preference).toBe('medium'); expect(quality.tier).toBe('medium');
    expect(quality.autoProfile.stage).toBe(0);
    expect(localStorage.getItem('gag-quality-tier-v4')).toBe('medium');
    expect(localStorage.getItem('gag-quality-tier-v3')).toBe('medium');
    await act(async () => { quality.setTier('auto'); });
    await renderer.sample(40, 80); // fresh calibration, not previous monitor history
    expect(quality.preference).toBe('auto'); expect(quality.autoProfile.stage).toBe(0);
    expect(localStorage.getItem('gag-quality-tier-v3')).toBe('medium');
  } finally { await renderer.close(); }
});

// Break caught: an explicit same-Auto preference must not silently reset an
// already calibrated controller to inactive while the governor stays mounted.
it('keeps current calibration and measured relief alive when Auto is explicitly selected again', async () => {
  const renderer = await mount();
  try {
    renderer.ready(); await renderer.sample(10, 2100);
    await renderer.sample(40, 200); await renderer.sample(40, 200);
    expect(quality.autoProfile.stage).toBe(2);
    const revision = quality.autoRevision;
    await act(async () => { quality.setTier('auto'); });
    expect(quality.autoProfile.stage).toBe(2);
    expect(quality.autoRevision).toBe(revision);
    expect(localStorage.getItem('gag-quality-tier-v4')).toBe('auto'); // explicit choice, NOT a measured stage
    await renderer.sample(40, 200);
    expect(quality.autoProfile.stage).toBe(3);
    expect(renderer.dpr()).toBe(1.25);
    expect(localStorage.getItem('gag-quality-tier-v3')).toBeNull();
  } finally { await renderer.close(); }
});

it('does not convert a pre-useful-frame load or a brief boot hitch into reduced detail', async () => {
  const renderer = await mount();
  try {
    await renderer.sample(40, 600);
    expect(renderer.dpr()).toBe(1.5);
    expect(quality.preference).toBe('auto');
    expect(quality.autoProfile.densityTier).toBe('high');
    renderer.ready(); await renderer.sample(40, 80); await renderer.sample(10, 2100);
    expect(quality.autoProfile.multisampling).toBe(4);
    expect(quality.autoProfile.densityTier).toBe('high');
  } finally { await renderer.close(); }
});
