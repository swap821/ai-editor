import { act } from 'react';
import { _roots, advance, createRoot, extend, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import CortexEngine from '../../superbrain/core/CortexEngine';
import { SCENE_UNIFORMS } from '../../superbrain/components/canvas/SuperbrainScene.LEGACY';
import { setAmbientMotionPaused } from '../../superbrain/lib/reducedMotion';
import { publishCognition } from '../../superbrain/lib/cognitionBus';
import type { PhysicalBodyProjection } from '../../superbrain/lib/bodyPosture';

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
});
afterEach(() => {
  localStorage.removeItem('gagos-pause-motion-v1');
  vi.restoreAllMocks(); vi.unstubAllGlobals();
});

describe('ambient pause through the real engine', () => {
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
      expect(floatingPose()).not.toEqual(beforePose);
      // Only three active seconds have elapsed, not the 92 wall-clock seconds.
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
