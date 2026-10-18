import { act } from 'react';
import { _roots, advance, createRoot, extend, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import CortexEngine from '../../superbrain/core/CortexEngine';
import { SCENE_UNIFORMS } from '../../superbrain/components/canvas/SuperbrainScene.LEGACY';
import { setAmbientMotionPaused } from '../../superbrain/lib/reducedMotion';
import { publishCognition } from '../../superbrain/lib/cognitionBus';
import type { PhysicalBodyProjection } from '../../superbrain/lib/bodyPosture';
import { __resetLifecycleForTests, ArrivalMode, notifyDirective, tickLifecycle, transitionToArriving } from '../../superbrain/lib/lifecycleStateMachine';
import { deriveBeingPresentation, type BeingFacts } from './semanticKernel';
import { derivePhysicalSnapshot } from './physicalSnapshot';

const fixture = vi.hoisted(() => ({ body: null as THREE.Group | null,
  burst: null as { current: { intensity: number } } | null }));
// Asset-dependent body/effects and browser controls are outside this boundary.
// The engine, preference store, floating parent, sky frame callback and R3F
// mounting/scheduler are real. No WebGL/shader execution is claimed.
vi.mock('../../superbrain/lib/brainScene', () => ({ preloadBrainScene() {} }));
vi.mock('../../superbrain/components/canvas/SuperbrainScene.LEGACY', async (original) => ({
  ...await original<typeof import('../../superbrain/components/canvas/SuperbrainScene.LEGACY')>(),
  BrainModel: ({ burst }: { burst: { current: { intensity: number } } }) => {
    fixture.burst = burst;
    return <group ref={(body) => { fixture.body = body; }} />;
  },
  OrganismFraming: () => null,
}));
vi.mock('@react-three/drei', async (original) => ({
  ...await original<typeof import('@react-three/drei')>(),
  PerspectiveCamera: () => null,
  OrbitControls: () => null,
}));
vi.mock('../../superbrain/components/canvas/PostFX', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/BodySpeech', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/CommandNerve3D', () => ({ default: () => null }));

extend({ Group: THREE.Group, Points: THREE.Points, BufferGeometry: THREE.BufferGeometry,
  BufferAttribute: THREE.BufferAttribute, PointsMaterial: THREE.PointsMaterial,
  Color: THREE.Color, AmbientLight: THREE.AmbientLight,
  DirectionalLight: THREE.DirectionalLight, PointLight: THREE.PointLight });
const resting: PhysicalBodyProjection = {
  phase: 'resting', taskState: 'idle', coherence: 'fresh', motion: 'calm',
  cortex: { posture: 'rest' }, verification: { state: 'none' }, membrane: { state: 'clear' },
};
let media: EventTarget & { matches: boolean };

beforeEach(() => {
  fixture.body = null;
  fixture.burst = null;
  localStorage.removeItem('gagos-pause-motion-v1');
  media = Object.assign(new EventTarget(), { matches: false });
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('matchMedia', () => media);
  vi.spyOn(Math, 'random').mockReturnValue(0);
  // jsdom has no Canvas2D. Replace only glyph rasterization, not sky time.
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    clearRect() {}, fillText() {},
  } as unknown as CanvasRenderingContext2D);
  SCENE_UNIFORMS.uTime.value = 0;
  SCENE_UNIFORMS.uBreath.value = 0.5;
  SCENE_UNIFORMS.uHold.value = 0;
  SCENE_UNIFORMS.uAwaken.value = 0;
  SCENE_UNIFORMS.uBurst.value = 0;
  SCENE_UNIFORMS.uWaveTimes.value.fill(-10);
  __resetLifecycleForTests();
});
afterEach(() => {
  localStorage.removeItem('gagos-pause-motion-v1');
  vi.restoreAllMocks(); vi.unstubAllGlobals();
  __resetLifecycleForTests();
});

describe('ambient pause through the real engine', () => {
  // The engine's actual shader inputs and owned burst ref are the boundary:
  // old timers/reply events must not overrule semantic -> physical state. The
  // asset double only exposes that existing ref; it does not produce the cues.
  it.each([false, true])('keeps work impulses canonical without stopping calm ambient life; reduced=%s', async (reduced) => {
    media.matches = reduced;
    let wallMs = 0;
    vi.spyOn(Date, 'now').mockImplementation(() => wallMs);
    vi.spyOn(performance, 'now').mockImplementation(() => wallMs);
    transitionToArriving(ArrivalMode.AWAKENING);
    wallMs = 10_000; tickLifecycle(); // actual lifecycle producer reaches REST
    const canvas = document.createElement('canvas'), root = createRoot(canvas), store = _roots.get(canvas)!.store;
    const renderer = { domElement: canvas, render(scene: THREE.Scene) { scene.updateMatrixWorld(true); },
      setSize() {}, setPixelRatio() {} } as unknown as RootState['gl'];
    await root.configure({ gl: renderer, scene: new THREE.Scene(), camera: new THREE.PerspectiveCamera(),
      frameloop: 'never', size: { width: 400, height: 400, top: 0, left: 0 } });
    const facts: BeingFacts = { transport: 'connected', projection: 'fresh', mirrorStatus: 'online',
      hasSnapshot: true, taskActivity: 'streaming', verification: 'unknown', stop: 'clear' };
    const working = derivePhysicalSnapshot(deriveBeingPresentation(facts));
    const render = async (physical: PhysicalBodyProjection | undefined) => act(async () => {
      root.render(<CortexEngine mode="observe" activity={0} tier="low" physical={physical} />);
    });
    let time = 0;
    const step = () => { time += 1 / 60; wallMs += 1000 / 60; act(() => advance(time, false, store.getState())); };
    const reply = () => publishCognition({ type: 'voice-speaking', source: 'reply', intensity: 1, data: { phase: 'reply' } });
    const tool = () => publishCognition({ type: 'agent-dispatch', detail: 'tool engaged: read_file' });
    try {
      const idle = derivePhysicalSnapshot(deriveBeingPresentation({ ...facts, taskActivity: 'idle' }));
      expect([idle.phase, idle.taskState]).toEqual(['resting', 'idle']);
      await render(idle); step();
      const firstPose = fixture.body!.parent!.matrixWorld.elements.slice();
      let peakUnpromptedBurst = 0;
      // Includes the old automatic burst/wave deadlines AND idle cascade.
      for (let frame = 0; frame < 2700; frame++) {
        step(); peakUnpromptedBurst = Math.max(peakUnpromptedBurst, fixture.burst!.current.intensity);
      }
      expect.soft(peakUnpromptedBurst, 'a timer is not admitted cognition').toBe(0);
      expect.soft(SCENE_UNIFORMS.uWaveTimes.value.every(start => start < 0), 'rest cannot manufacture tool waves').toBe(true);
      expect(SCENE_UNIFORMS.uTime.value).toBeCloseTo(reduced ? 0 : time, 8);
      if (reduced) expect(fixture.body!.parent!.matrixWorld.elements).toEqual(firstPose);
      else expect(fixture.body!.parent!.matrixWorld.elements).not.toEqual(firstPose);

      const cases: { patch: Partial<BeingFacts>; phase: string; task: string; heat: number; burstCeiling: number }[] = [
        { patch: { stop: 'engaged' }, phase: 'stopped', task: 'stopped', heat: 0, burstCeiling: 0 },
        { patch: { approvalPending: true }, phase: 'awaiting-human', task: 'needs-permission', heat: 0, burstCeiling: 0.78 },
        { patch: { projection: 'stale', mirrorStatus: 'stale' }, phase: 'stale', task: 'stale', heat: 0, burstCeiling: 0 },
        { patch: { transport: 'disconnected', projection: 'unavailable', mirrorStatus: 'offline', hasSnapshot: false }, phase: 'degraded', task: 'working', heat: 0, burstCeiling: 0 },
        { patch: { taskActivity: 'awaiting-replay' }, phase: 'awaiting-response', task: 'waiting-response', heat: 0, burstCeiling: 0 },
        { patch: { taskActivity: 'refused' }, phase: 'recovering', task: 'refused', heat: 0, burstCeiling: 0.504 },
        { patch: { taskActivity: 'complete' }, phase: 'resting', task: 'done-unverified', heat: 0, burstCeiling: 0 },
        { patch: { taskActivity: 'complete', verification: 'pass' }, phase: 'resting', task: 'done-verified', heat: 0, burstCeiling: 0.048 },
        { patch: { taskActivity: 'checking', verification: 'pending' }, phase: 'verifying', task: 'checking', heat: 1, burstCeiling: 0.08 },
      ];
      for (const entry of cases) {
        await render(working); reply(); tool(); step();
        expect(fixture.burst!.current.intensity).toBeGreaterThan(0);
        expect(SCENE_UNIFORMS.uAwaken.value).toBeGreaterThan(0);
        expect.soft(SCENE_UNIFORMS.uWaveTimes.value.some(start => start >= 0), 'reduced motion keeps genuine work static').toBe(!reduced);
        const projection = derivePhysicalSnapshot(deriveBeingPresentation({ ...facts, ...entry.patch }));
        expect([projection.phase, projection.taskState]).toEqual([entry.phase, entry.task]);
        // The legacy lifecycle remains ATTENTIVE; it is not a second authority.
        notifyDirective();
        const previousHeat = SCENE_UNIFORMS.uAwaken.value;
        reply(); tool(); // an impulse already queued just before the boundary
        await render(projection); step();
        expect.soft(fixture.burst!.current.intensity, `${entry.phase}: first-frame raw burst suppression`).toBe(0);
        expect.soft(SCENE_UNIFORMS.uBurst.value, `${entry.phase}: preserve only canonical secondary motion`).toBeLessThanOrEqual(entry.burstCeiling * (reduced ? 0.35 : 1));
        expect.soft(SCENE_UNIFORMS.uWaveTimes.value.every(start => SCENE_UNIFORMS.uTime.value - start >= 6), `${entry.phase}: previously active waves are dormant`).toBe(true);
        if (entry.heat === 0) expect.soft(SCENE_UNIFORMS.uAwaken.value, `${entry.phase}: heat begins withdrawing now`).toBeLessThanOrEqual(previousHeat);
        reply(); tool(); // and one arriving after the canonical boundary
        for (let frame = 0; frame < 180; frame++) step();
        expect.soft(fixture.burst!.current.intensity, `${entry.phase}: late events cannot reassert work`).toBe(0);
        expect.soft(SCENE_UNIFORMS.uAwaken.value, `${entry.phase}: canonical heat`).toBeCloseTo(entry.heat, 3);
        expect.soft(SCENE_UNIFORMS.uWaveTimes.value.every(start => SCENE_UNIFORMS.uTime.value - start >= 6), `${entry.phase}: late waves cannot reassert work`).toBe(true);
      }
      // Both canonical recovery and the external lab's existing event fallback
      // remain expressive. No new event/store owner or authoritative action.
      for (const physical of [working, undefined]) {
        await render(physical); reply(); tool(); step();
        expect(fixture.burst!.current.intensity).toBeGreaterThan(0);
        expect(SCENE_UNIFORMS.uAwaken.value).toBeGreaterThan(0);
        expect(SCENE_UNIFORMS.uWaveTimes.value.some(start => start >= 0)).toBe(!reduced);
      }
      if (!reduced) {
        let standalonePeak = 0;
        for (let frame = 0; frame < 1200; frame++) {
          step(); standalonePeak = Math.max(standalonePeak, fixture.burst!.current.intensity);
        }
        expect(standalonePeak, 'the standalone demonstration keeps its ambient timer fallback').toBeGreaterThan(0.9);
      }
      const stopped = derivePhysicalSnapshot(deriveBeingPresentation({ ...facts, stop: 'engaged' }));
      await render(working); reply(); tool();
      await render(stopped); reply(); tool();
      await render(working); step(); // no intervening paint at the quiet boundary
      expect(fixture.burst!.current.intensity).toBe(0);
      expect(SCENE_UNIFORMS.uWaveTimes.value.every(start => SCENE_UNIFORMS.uTime.value - start >= 6)).toBe(true);

      // Arrival still comes from the existing lifecycle clock, but cannot
      // resurrect a reveal/ignition after a canonical Stop or completed arrival.
      transitionToArriving(ArrivalMode.COALESCENCE);
      wallMs += 100;
      const arriving = derivePhysicalSnapshot(deriveBeingPresentation({ ...facts, lifecycle: 'arriving', taskActivity: 'idle' }));
      expect(arriving.phase).toBe('arriving');
      await render(arriving); step();
      if (reduced) {
        expect(SCENE_UNIFORMS.uArrival.value).toBe(0);
        expect(SCENE_UNIFORMS.uIgnite.value).toBe(0);
      } else {
        expect(SCENE_UNIFORMS.uArrival.value).toBeGreaterThan(0);
        expect(SCENE_UNIFORMS.uIgnite.value).toBeGreaterThan(0);
      }
      await render(stopped); step();
      expect(SCENE_UNIFORMS.uArrival.value).toBe(0);
      expect(SCENE_UNIFORMS.uIgnite.value).toBe(0);
      await render(idle); step();
      expect(SCENE_UNIFORMS.uArrival.value).toBe(0);
      expect(SCENE_UNIFORMS.uIgnite.value).toBe(0);
      expect(store.getState().internal.priority).toBe(0);
    } finally { await act(async () => { root.unmount(); }); }
  });

  it.each(['before-pause', 'during-pause'] as const)('does not replay a %s directive after completion on Resume', async (timing) => {
    const canvas = document.createElement('canvas');
    const root = createRoot(canvas);
    const store = _roots.get(canvas)!.store;
    const renderer = {
      domElement: canvas,
      render(scene: THREE.Scene) { scene.updateMatrixWorld(true); },
      setSize() {}, setPixelRatio() {},
    } as unknown as RootState['gl'];
    await root.configure({ gl: renderer, scene: new THREE.Scene(), camera: new THREE.PerspectiveCamera(),
      frameloop: 'never', size: { width: 400, height: 400, top: 0, left: 0 } });
    const step = (time: number) => act(() => advance(time, false, store.getState()));
    try {
      await act(async () => { root.render(<CortexEngine mode="observe" activity={0} tier="low" physical={resting} />); });
      step(1); step(2);
      if (timing === 'before-pause') publishCognition({ type: 'directive' });
      await act(async () => { setAmbientMotionPaused(true); });
      if (timing === 'during-pause') publishCognition({ type: 'directive' });
      step(30);
      publishCognition({ type: 'synthesis' });
      step(60); step(90);
      expect(fixture.burst!.current.intensity).toBeLessThan(0.001);
      await act(async () => { setAmbientMotionPaused(false); });
      step(91);
      // Active time is 3s, before the ordinary ambient burst deadline (>8s).
      expect(SCENE_UNIFORMS.uTime.value).toBe(3);
      expect(fixture.burst!.current.intensity).toBeLessThan(0.001);
    } finally { await act(async () => { root.unmount(); }); }
  });

  it.each(['manual', 'system'] as const)('stops body/sky clocks and floating pose for %s preference, while admitting a new hold', async (preference) => {
    const canvas = document.createElement('canvas');
    const root = createRoot(canvas);
    const store = _roots.get(canvas)!.store;
    const renderer = {
      domElement: canvas,
      render(scene: THREE.Scene) { scene.updateMatrixWorld(true); },
      setSize() {}, setPixelRatio() {},
    } as unknown as RootState['gl'];
    await root.configure({ gl: renderer, scene: new THREE.Scene(), camera: new THREE.PerspectiveCamera(),
      frameloop: 'never', size: { width: 400, height: 400, top: 0, left: 0 } });
    const render = async (physical = resting) => {
      await act(async () => { root.render(<CortexEngine mode="observe" activity={0} tier="low" physical={physical} />); });
    };
    const step = (time: number) => act(() => advance(time, false, store.getState()));
    const floatingPose = () => {
      fixture.body!.parent!.updateWorldMatrix(true, false);
      return fixture.body!.parent!.matrixWorld.elements.slice();
    };
    try {
      await render();
      step(1);
      const firstPose = floatingPose();
      step(2);
      expect(floatingPose()).not.toEqual(firstPose);
      let sky!: THREE.Points;
      store.getState().scene.traverse((object) => { if (object instanceof THREE.Points) sky = object; });
      const shader = { uniforms: {}, vertexShader: '#include <begin_vertex>', fragmentShader: '#include <map_particle_fragment>' } as unknown as Parameters<THREE.PointsMaterial['onBeforeCompile']>[0];
      (sky.material as THREE.PointsMaterial).onBeforeCompile(shader, renderer);
      const skyTime = shader.uniforms.uTime;
      const beforeSky = skyTime.value;
      const beforeTime = SCENE_UNIFORMS.uTime.value;
      const beforePose = floatingPose();
      await act(async () => {
        if (preference === 'manual') setAmbientMotionPaused(true);
        else { media.matches = true; media.dispatchEvent(new Event('change')); }
      });
      for (const time of [30, 60, 90]) {
        step(time);
        expect.soft(SCENE_UNIFORMS.uTime.value).toBe(beforeTime);
        expect.soft(SCENE_UNIFORMS.uBreath.value).toBe(0.5);
        expect.soft(skyTime.value).toBe(beforeSky);
        expect.soft(floatingPose()).toEqual(beforePose);
      }
      // Pausing presentation is not pausing semantic input or granting authority.
      await render({ ...resting, membrane: { state: 'held' }, cortex: { posture: 'attention' } });
      step(91);
      expect(SCENE_UNIFORMS.uHold.value).toBeGreaterThan(0);
      expect(SCENE_UNIFORMS.uTime.value).toBe(beforeTime);
      await act(async () => {
        if (preference === 'manual') setAmbientMotionPaused(false);
        else { media.matches = false; media.dispatchEvent(new Event('change')); }
      });
      step(92);
      expect(SCENE_UNIFORMS.uTime.value).toBe(beforeTime + 1);
      expect(skyTime.value).toBeGreaterThan(beforeSky);
      // Resuming ambient motion does not release an admitted permission hold.
      // The background can voyage, but the body remains caught at the decision.
      expect(floatingPose()).toEqual(beforePose);
      await render(resting);
      step(93);
      expect(floatingPose()).not.toEqual(beforePose);
      // Only three body-active seconds elapsed, not the93 wall-clock seconds.
      const phase = 3 * 0.46 / 4;
      const expected = new THREE.Group();
      expected.rotation.set(Math.cos(phase) / 8 * 0.025, Math.sin(phase) / 8 * 0.025, Math.sin(phase) / 20 * 0.025);
      expected.position.y = Math.sin(phase) / 10 * 0.1;
      expected.updateMatrixWorld();
      floatingPose().forEach((value, index) => expect(value).toBeCloseTo(expected.matrixWorld.elements[index], 12));
      expect(store.getState().internal.priority).toBe(0);
    } finally { await act(async () => { root.unmount(); }); }
  });
});
