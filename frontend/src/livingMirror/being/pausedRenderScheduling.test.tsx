import { act, useEffect, useLayoutEffect, useRef, type ComponentProps, type ReactNode } from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { _roots, createRoot, extend, useFrame, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import WorkspaceCanvas from '../../superbrain/components/canvas/WorkspaceCanvas';
import { setAmbientMotionPaused } from '../../superbrain/lib/reducedMotion';
import { publishCognition } from '../../superbrain/lib/cognitionBus';
import { DPR_WARMUP_MS } from '../../superbrain/lib/perfBudget';
import { SCENE_UNIFORMS } from '../../superbrain/components/canvas/SuperbrainScene.LEGACY';
import { installKeyboardViewportTracking } from '../keyboardViewport';

const fixture = vi.hoisted(() => ({ state: null as RootState | null, paints: 0,
  canvas: null as HTMLCanvasElement | null, monitorMounted: false, composer: false, realControls: false,
  assetPending: null as Promise<void> | null,
  monitorChange: null as null | ((sample: { fps: number; factor: number }) => void) }));
// Only the DOM Canvas host, WebGL and unrelated scene contents are replaced.
// Frame scheduling, store, clock, visibility, cognition and pause preference are real.
vi.mock('@react-three/fiber', async (original) => ({
  ...await original<typeof import('@react-three/fiber')>(),
  Canvas: ({ children }: { children: ReactNode }) => {
    const rootRef = useRef<ReturnType<typeof createRoot> | null>(null);
    const readyRef = useRef(false);
    const latestChildren = useRef(children);
    latestChildren.current = children;
    useLayoutEffect(() => {
      const canvas = document.createElement('canvas');
      fixture.canvas = canvas;
      const root = createRoot(canvas);
      rootRef.current = root;
      const gl = { domElement: canvas, render() { fixture.paints++; }, setSize() {}, setPixelRatio() {}, getPixelRatio: () => 1 } as unknown as RootState['gl'];
      let disposed = false;
      const camera = new THREE.PerspectiveCamera(26, 1, 0.1, 100);
      camera.position.set(0, -0.5, 15);
      void root.configure({ gl, dpr: 1.5, scene: new THREE.Scene(), camera,
        size: { width: 500, height: 500, left: 0, top: 0 } }).then(() => {
        if (!disposed) {
          fixture.state = _roots.get(canvas)!.store.getState();
          readyRef.current = true;
          root.render(latestChildren.current);
        }
      });
      return () => { disposed = true; readyRef.current = false; root.unmount(); };
    }, []);
    useLayoutEffect(() => {
      if (readyRef.current) rootRef.current!.render(children);
    }, [children]);
    return null;
  },
}));
extend({ Group: THREE.Group, Mesh: THREE.Mesh, Color: THREE.Color, Fog: THREE.Fog,
  BufferGeometry: THREE.BufferGeometry, SphereGeometry: THREE.SphereGeometry,
  TorusGeometry: THREE.TorusGeometry, MeshBasicMaterial: THREE.MeshBasicMaterial,
  MeshStandardMaterial: THREE.MeshStandardMaterial, AmbientLight: THREE.AmbientLight,
  DirectionalLight: THREE.DirectionalLight, PointLight: THREE.PointLight });
vi.mock('@/components/QualityTierProvider', () => ({
  QualityTierProvider: ({ children }: { children: ReactNode }) => children,
  useQualityTier: () => ({ tier: 'high', perfTier: 'high', baseTier: 'high', generating: false }),
}));
// Keep the actual engine, body transforms, clock/uniforms and nerve consumers.
// Assets, point content, FX and controls are substituted: no GPU/anatomy proof.
vi.mock('../../superbrain/lib/brainScene', async () => {
  const { Group } = await import('three');
  const scene = new Group();
  return { preloadBrainScene() {}, useBrainScene: () => { if (fixture.assetPending) throw fixture.assetPending; return scene; } };
});
vi.mock('../../superbrain/components/canvas/BrainPointField', () => ({ default: () => <group /> }));
vi.mock('../../superbrain/components/canvas/NodeLattice', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/MemoryHalo', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/MaterializationLayer', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/CosmicBackground', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/BodySpeech', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/PostFX', () => ({ default: function ComposerOwner() {
  useFrame(({ gl, scene, camera }) => { if (fixture.composer) gl.render(scene, camera); }, fixture.composer ? 1 : 0);
  return null;
} }));
vi.mock('@react-three/drei', async (original) => {
  const actual = await original<typeof import('@react-three/drei')>();
  const ActualControls = actual.OrbitControls;
  return { ...actual,
  PerspectiveCamera: () => null,
  OrbitControls: function OptionalControls(props: ComponentProps<typeof ActualControls>) {
    return fixture.realControls ? <ActualControls {...props} /> : null;
  },
  PerformanceMonitor: ({ onChange }: { onChange: (sample: { fps: number; factor: number }) => void }) => {
    fixture.monitorChange = onChange;
    useEffect(() => { fixture.monitorMounted = true; return () => { fixture.monitorMounted = false; }; }, []);
    return null;
  },
}; });
vi.mock('../../superbrain/components/canvas/WebGLErrorBoundary', () => ({
  WebGLErrorBoundary: ({ children }: { children: ReactNode }) => children, WebGLFallback: () => null,
}));
vi.mock('../../superbrain/lib/aiosAdapter', () => ({ startAiosPolling: () => () => {} }));

let mediaPreference: EventTarget & { matches: boolean };
beforeEach(() => {
  fixture.state = null; fixture.paints = 0; fixture.canvas = null;
  fixture.composer = false;
  fixture.realControls = false; fixture.assetPending = null;
  SCENE_UNIFORMS.uHold.value = 0; SCENE_UNIFORMS.uTime.value = 0;
  fixture.monitorMounted = false; fixture.monitorChange = null;
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval',
    'requestAnimationFrame', 'cancelAnimationFrame', 'performance', 'Date'] });
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  mediaPreference = Object.assign(new EventTarget(), { matches: false });
  vi.stubGlobal('matchMedia', () => mediaPreference);
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({} as WebGLRenderingContext);
  Object.defineProperty(document, 'hidden', { configurable: true, value: false });
  document.dispatchEvent(new Event('visibilitychange'));
  localStorage.removeItem('gagos-pause-motion-v1');
});
afterEach(async () => {
  await act(async () => { cleanup(); });
  await act(async () => { vi.advanceTimersByTime(600); });
  Reflect.deleteProperty(document, 'hidden');
  document.dispatchEvent(new Event('visibilitychange'));
  localStorage.removeItem('gagos-pause-motion-v1');
  vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers();
});
const elapse = async (ms: number) => { await act(async () => { vi.advanceTimersByTime(ms); }); };
const physical = { phase: 'resting', taskState: 'idle', coherence: 'fresh', motion: 'calm',
  cortex: { posture: 'rest' }, verification: { state: 'none' }, membrane: { state: 'clear' } };

describe('paused installed renderer scheduling', () => {
  it.each(['viewport resize', 'viewport scroll', 'composer transition'] as const)(
    'reattaches the actual intake after an idle %s without resuming ambient motion', async (trigger) => {
      // Real keyboard tracking changes the DOM dock while Canvas size and the
      // body facts stay unchanged. JSDOM has no CSS layout; these hand-derived
      // rects model a same-size dock translated 300px, not a physical keyboard.
      const viewport = Object.assign(new EventTarget(), { height: 844, offsetTop: 0, scale: 1 });
      vi.stubGlobal('visualViewport', viewport);
      const host = document.createElement('div');
      host.className = 'lm-app';
      const chat = document.createElement('section');
      chat.className = 'gagos-chat';
      const bar = document.createElement('div');
      bar.className = 'gagos-bar';
      const input = document.createElement('input');
      input.value = 'Unsent continuity check';
      const send = document.createElement('button');
      send.className = 'gagos-send';
      bar.append(input, send); chat.append(bar); host.append(chat); document.body.append(host);
      let transitionShift = 0;
      vi.spyOn(host, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 500, 844));
      vi.spyOn(send, 'getBoundingClientRect').mockImplementation(() => new DOMRect(470,
        420 - transitionShift - Number.parseFloat(host.style.getPropertyValue('--lm-keyboard-inset') || '0'), 44, 44));
      const stopTracking = installKeyboardViewportTracking(host);
      const endpoint = () => {
        const state = fixture.state!.get();
        let junction!: THREE.Group;
        state.scene.traverse((object) => {
          if (object instanceof THREE.Mesh && object.geometry instanceof THREE.SphereGeometry
            && object.geometry.parameters.radius === 0.026) junction = object.parent as THREE.Group;
        });
        expect(junction.visible).toBe(true);
        const ndc = junction.position.clone().project(state.camera);
        return [(ndc.x + 1) * 250, (1 - ndc.y) * 250];
      };
      try {
        input.focus();
        setAmbientMotionPaused(true);
        await act(async () => { render(<WorkspaceCanvas physical={physical} />); });
        await elapse(5000);
        expect(endpoint()[0]).toBeCloseTo(492, 5);
        expect(endpoint()[1]).toBeCloseTo(442, 5);
        const canvas = fixture.canvas;
        const before = fixture.paints;
        const ambientTime = SCENE_UNIFORMS.uTime.value;
        await elapse(15000);
        expect(fixture.paints).toBe(before);
        await act(async () => {
          if (trigger === 'composer transition') {
            transitionShift = 300;
            chat.dispatchEvent(new Event('transitionend', { bubbles: true }));
          } else {
            viewport.height = trigger === 'viewport resize' ? 544 : 500;
            viewport.offsetTop = trigger === 'viewport resize' ? 0 : 44;
            viewport.dispatchEvent(new Event(trigger === 'viewport resize' ? 'resize' : 'scroll'));
          }
        });
        await elapse(100);
        if (trigger !== 'composer transition') expect(host.style.getPropertyValue('--lm-keyboard-inset')).toBe('300px');
        expect.soft(endpoint()[1]).toBeCloseTo(142, 5);
        expect.soft(fixture.paints).toBeGreaterThan(before);
        expect(fixture.canvas).toBe(canvas);
        expect(input.value).toBe('Unsent continuity check');
        expect(fixture.state!.get().frameloop).toBe('demand');
        expect(SCENE_UNIFORMS.uTime.value).toBe(ambientTime);
        await elapse(5000);
        const settled = fixture.paints;
        await elapse(15000);
        expect(fixture.paints).toBe(settled);
      } finally { stopTracking(); host.remove(); }
    },
  );

  it.each(['queued props', 'wheel', 'late asset'] as const)('discards the idle gap before the first %s paint', async (trigger) => {
    fixture.realControls = trigger === 'wheel';
    let resolveAsset!: () => void;
    if (trigger === 'late asset') fixture.assetPending = new Promise<void>(resolve => { resolveAsset = resolve; });
    const frames: { delta: number; elapsed: number }[] = [];
    function FrameProbe() {
      useFrame((state, delta) => { frames.push({ delta, elapsed: state.clock.elapsedTime }); });
      return null;
    }
    setAmbientMotionPaused(true);
    let view!: ReturnType<typeof render>;
    await act(async () => { view = render(<WorkspaceCanvas physical={physical}><FrameProbe /></WorkspaceCanvas>); });
    await elapse(5000);
    const settledPaints = fixture.paints;
    await elapse(15000);
    expect(fixture.paints).toBe(settledPaints);
    const before = fixture.state!.clock.elapsedTime;
    const cameraDistance = fixture.state!.camera.position.length();
    frames.length = 0;
    await act(async () => {
      if (trigger === 'late asset') { fixture.assetPending = null; resolveAsset(); }
      else if (trigger === 'wheel') fixture.canvas!.dispatchEvent(new WheelEvent('wheel', { deltaY: 120, cancelable: true }));
      else view.rerender(<WorkspaceCanvas physical={{ ...physical, membrane: { state: 'held' } }}><group position={[1, 0, 0]} /><FrameProbe /></WorkspaceCanvas>);
    });
    await elapse(64);
    expect(fixture.paints).toBeGreaterThan(settledPaints);
    expect(frames.length).toBeGreaterThan(0);
    expect.soft(frames[0].delta).toBeLessThan(0.025);
    expect.soft(frames[0].elapsed - before).toBeLessThan(0.025);
    if (trigger === 'wheel') expect(fixture.state!.camera.position.length()).not.toBe(cameraDistance);
  });

  it('reacts to OS changes without letting either pause source override the other', async () => {
    await act(async () => { render(<WorkspaceCanvas physical={physical} />); });
    await elapse(100);
    const canvas = fixture.canvas;
    await act(async () => { mediaPreference.matches = true; mediaPreference.dispatchEvent(new Event('change')); });
    await elapse(5000);
    const idle = fixture.paints;
    await elapse(15000);
    expect(fixture.state!.get().frameloop).toBe('demand');
    expect(fixture.paints).toBe(idle);
    await act(async () => { setAmbientMotionPaused(true); mediaPreference.matches = false; mediaPreference.dispatchEvent(new Event('change')); });
    expect(fixture.state!.get().frameloop).toBe('demand');
    await act(async () => { setAmbientMotionPaused(false); });
    expect(fixture.state!.get().frameloop).toBe('always');
    expect(fixture.canvas).toBe(canvas);
  });

  it('does not reduce resolution for deliberate demand idle, including a late monitor callback', async () => {
    await act(async () => { render(<WorkspaceCanvas physical={physical} />); });
    await elapse(DPR_WARMUP_MS + 100);
    expect(fixture.monitorMounted).toBe(true);
    const lateSample = fixture.monitorChange!;
    await act(async () => { setAmbientMotionPaused(true); });
    await elapse(5000);
    const dpr = fixture.state!.get().viewport.dpr;
    expect.soft(fixture.monitorMounted).toBe(false);
    await act(async () => { lateSample({ fps: 0.2, factor: 0 }); });
    expect.soft(fixture.state!.get().viewport.dpr).toBe(dpr);
    await act(async () => { setAmbientMotionPaused(false); });
    expect(fixture.monitorMounted).toBe(true);
  });

  it.each([false, true])('goes idle, updates the actual held body and resumes the same root (composer=%s)', async (composer) => {
    fixture.composer = composer;
    let view!: ReturnType<typeof render>;
    await act(async () => { view = render(<WorkspaceCanvas physical={physical} />); });
    await elapse(100);
    expect(fixture.paints).toBeGreaterThan(0);
    const canvas = fixture.canvas;
    await act(async () => { setAmbientMotionPaused(true); });
    await elapse(5000);
    const settled = fixture.paints;
    await elapse(15000);
    expect.soft(fixture.state!.get().frameloop).toBe('demand');
    expect.soft(fixture.paints).toBe(settled);
    await act(async () => { view.rerender(<WorkspaceCanvas physical={{ ...physical, membrane: { state: 'held' } }} />); });
    await elapse(100);
    expect(fixture.paints).toBeGreaterThan(settled);
    expect(SCENE_UNIFORMS.uHold.value).toBeGreaterThan(0);
    await elapse(5000);
    expect(SCENE_UNIFORMS.uHold.value).toBeGreaterThan(0.999);
    const afterHold = fixture.paints;
    await act(async () => { publishCognition({ type: 'approval-resolved', label: 'rejected' }); });
    await elapse(100);
    expect(fixture.paints).toBeGreaterThan(afterHold);
    await elapse(5000);
    const afterEvent = fixture.paints;
    await act(async () => { window.dispatchEvent(new Event('input')); });
    await elapse(100);
    expect(fixture.paints).toBeGreaterThan(afterEvent);
    await elapse(5000);
    const beforeRestore = fixture.paints;
    await act(async () => { fixture.canvas!.dispatchEvent(new Event('webglcontextrestored')); });
    await elapse(100);
    expect(fixture.paints).toBeGreaterThan(beforeRestore);
    await elapse(5000);
    const beforeResume = fixture.state!.clock.elapsedTime;
    await act(async () => { setAmbientMotionPaused(false); });
    expect(fixture.state!.get().frameloop).toBe('always');
    expect(fixture.state!.clock.elapsedTime).toBeCloseTo(beforeResume, 5);
    const resumed = fixture.paints;
    await elapse(1000);
    expect(fixture.paints).toBeGreaterThan(resumed + 20);
    expect(fixture.canvas).toBe(canvas);
    expect(fixture.state!.internal.priority).toBe(composer ? 1 : 0);
  });

  it('starts paused with a real first paint, refuses hidden invalidations and wakes paused without clock rewind', async () => {
    setAmbientMotionPaused(true);
    await act(async () => { render(<WorkspaceCanvas physical={physical} />); });
    await elapse(5000);
    expect(fixture.paints).toBeGreaterThan(0);
    const beforeSleep = fixture.state!.clock.elapsedTime;
    await act(async () => {
      Object.defineProperty(document, 'hidden', { configurable: true, value: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    const hiddenPaints = fixture.paints;
    await act(async () => { publishCognition({ type: 'approval-required' }); });
    await elapse(15000);
    expect(fixture.paints).toBe(hiddenPaints);
    expect(fixture.state!.clock.elapsedTime).toBeCloseTo(beforeSleep, 5);
    await act(async () => {
      Object.defineProperty(document, 'hidden', { configurable: true, value: false });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect.soft(fixture.state!.get().frameloop).toBe('demand');
    expect(fixture.state!.clock.elapsedTime).toBeCloseTo(beforeSleep, 5);
    await elapse(5000);
    const restored = fixture.paints;
    expect(restored).toBeGreaterThan(hiddenPaints);
    await elapse(15000);
    expect.soft(fixture.paints).toBe(restored);
  });
});
