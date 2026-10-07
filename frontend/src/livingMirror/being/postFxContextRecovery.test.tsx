import { act, Component, type ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { _roots, createRoot, extend, type RootState } from '@react-three/fiber';
import { PerspectiveCamera } from '@react-three/drei';
import { EffectComposer, EffectPass, type Effect } from 'postprocessing';
import * as THREE from 'three';
import PostFX from '../../superbrain/components/canvas/PostFX';

const quality = vi.hoisted(() => ({ tier: 'high' }));
vi.mock('@/components/QualityTierProvider', () => ({
  useQualityTier: () => ({ perfTier: quality.tier }),
}));
extend({ Group: THREE.Group, PerspectiveCamera: THREE.PerspectiveCamera });

// Keep the installed R3F reconciler, Drei camera cleanup, composer and complete
// product FX chain real. Only the GPU is substituted; native loss/retry remains
// a separate browser gate. In particular addPass executes the upstream code.
let root: ReturnType<typeof createRoot>;
let state: RootState;
let canvas: HTMLCanvasElement;
let lost: boolean;
let errors: Error[];
let effectsAdded: string[];
let composers: Set<EffectComposer>;
// Test-only observation of the installed pass: its runtime collection is not
// public in the declarations. Do not expose or mutate it in production.
const passEffects = (pass: EffectPass) => Reflect.get(pass, 'effects') as readonly Effect[];
const activeEffects = () => [...composers].flatMap(composer => composer.passes
  .filter((pass): pass is EffectPass => pass instanceof EffectPass)
  .flatMap(pass => passEffects(pass).map(effect => effect.name)));
class FaultProbe extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error) { errors.push(error); }
  render() { return this.state.failed ? null : this.props.children; }
}

beforeEach(async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  lost = false; errors = []; effectsAdded = []; composers = new Set(); quality.tier = 'high';
  canvas = document.createElement('canvas');
  const context = {
    getContextAttributes: () => lost ? null : { alpha: false },
    isContextLost: () => lost,
    getParameter: () => 4,
    createRenderbuffer: () => ({}), bindRenderbuffer() {},
    renderbufferStorageMultisample() {}, deleteRenderbuffer() {},
  };
  const renderer = {
    domElement: canvas, getContext: () => context,
    getSize: (target: THREE.Vector2) => target.set(500, 500),
    getDrawingBufferSize: (target: THREE.Vector2) => target.set(500, 500),
    getPixelRatio: () => 1, setPixelRatio() {}, setSize() {}, render() {},
    capabilities: { maxVaryings: 16 },
    toneMapping: THREE.ACESFilmicToneMapping, outputColorSpace: THREE.SRGBColorSpace,
    autoClear: true,
  } as unknown as THREE.WebGLRenderer;
  const actualAddPass = EffectComposer.prototype.addPass;
  vi.spyOn(EffectComposer.prototype, 'addPass').mockImplementation(function (this: EffectComposer, pass, index) {
    if (pass instanceof EffectPass) effectsAdded.push(...passEffects(pass).map(effect => effect.name));
    actualAddPass.call(this, pass, index);
    composers.add(this);
  });
  root = createRoot(canvas);
  await root.configure({ gl: renderer, camera: new THREE.PerspectiveCamera(26, 1, 0.1, 100),
    scene: new THREE.Scene(), frameloop: 'never',
    size: { width: 500, height: 500, left: 0, top: 0 } });
  state = _roots.get(canvas)!.store.getState();
});
afterEach(async () => {
  await act(async () => { root.unmount(); });
  await act(async () => { vi.advanceTimersByTime(600); });
  vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers();
});

describe('installed product post-FX under context loss', () => {
  it.each([true, false])('does not rebuild on real camera cleanup, including a not-yet-delivered loss event (delivered=%s)', async delivered => {
    // Reuse the SAME element so camera cleanup, not changed FX props, is the
    // only source of the composer's external-store update during this test.
    const fx = <PostFX />;
    const tree = (camera: boolean) => <FaultProbe>
      {camera && <PerspectiveCamera makeDefault fov={26} near={0.1} far={100} position={[0, -0.5, 15]} />}
      {fx}
    </FaultProbe>;
    await act(async () => { root.render(tree(true)); });
    expect(errors).toEqual([]);
    expect(state.get().internal.priority).toBe(1);
    expect(effectsAdded).toContain('GradePreEffect');
    expect(effectsAdded).toContain('ToneMappingEffect');
    const installedCamera = state.get().camera;
    effectsAdded = [];
    await act(async () => {
      lost = true;
      if (delivered) canvas.dispatchEvent(new Event('webglcontextlost', { cancelable: true }));
      root.render(tree(false));
    });
    expect(state.get().camera).not.toBe(installedCamera);
    expect(errors).toEqual([]);
    expect(effectsAdded).toEqual([]);
    expect(state.get().internal.priority).toBe(0);
  });

  it.each(['high', 'low'])('suspends setup and restores the unchanged %s-tier chain on the same root', async tier => {
    quality.tier = tier;
    const expected = tier === 'high'
      ? ['BloomEffect', 'ChromaticAberrationEffect', 'GradePreEffect', 'ToneMappingEffect',
        'GradePostEffect', 'VignetteEffect', 'NoiseEffect']
      : ['GradePreEffect', 'ToneMappingEffect', 'GradePostEffect', 'VignetteEffect'];
    await act(async () => { root.render(<FaultProbe><PostFX /></FaultProbe>); });
    expect(errors).toEqual([]);
    // Observe the ACTIVE passes, not setup history: R3F's initial store update
    // can reattach passes after removing the previous ones, without two chains.
    expect(activeEffects()).toEqual(expected);
    expect([...composers].filter(composer => composer.passes.some(pass => pass instanceof EffectPass))).toHaveLength(1);
    const scene = state.get().scene;
    const camera = state.get().camera;
    for (let cycle = 0; cycle < 2; cycle++) {
      effectsAdded = [];
      await act(async () => {
        lost = true;
        canvas.dispatchEvent(new Event('webglcontextlost', { cancelable: true }));
      });
      expect(state.get().internal.priority).toBe(0);
      expect(effectsAdded).toEqual([]);
      expect(activeEffects()).toEqual([]);
      await act(async () => {
        lost = false;
        canvas.dispatchEvent(new Event('webglcontextrestored'));
      });
      expect(state.get().internal.priority).toBe(1);
      expect(activeEffects()).toEqual(expected);
      expect(errors).toEqual([]);
      expect(state.get().scene).toBe(scene);
      expect(state.get().camera).toBe(camera);
    }
  });
});
