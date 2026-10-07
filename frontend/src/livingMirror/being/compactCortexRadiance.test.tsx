import { act } from 'react';
import { _roots, advance, createRoot, extend, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import BrainPointField from '../../superbrain/components/canvas/BrainPointField';
import { SCENE_UNIFORMS } from '../../superbrain/components/canvas/SuperbrainScene.LEGACY';
import type { PhysicalBodyProjection } from '../../superbrain/lib/bodyPosture';

vi.mock('../../superbrain/lib/brainScene', () => ({ preloadBrainScene() {} }));
extend({ Points: THREE.Points });
beforeEach(() => { vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true); });
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

const physical: PhysicalBodyProjection = {
  phase: 'resting', taskState: 'done-unverified', coherence: 'coherent', motion: 'breathe',
  cortex: { posture: 'unverified' }, verification: { state: 'unverified' }, membrane: { state: 'clear' },
};

// Regression: carrying the full-size cloud's radiance into the tiny product
// pane washes out its folds. Exercise the actual material/frame/resize owner,
// not a mocked point field or a source-text assertion. WebGL alone is replaced.
it.each([false, true])('keeps a compact product cortex lit without full-size radiance; reduced motion=%s', async reduced => {
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: reduced }));
  const canvas = document.createElement('canvas');
  const root = createRoot(canvas), store = _roots.get(canvas)!.store;
  const camera = new THREE.PerspectiveCamera();
  const gl = { domElement: canvas, render() {}, setSize() {}, setPixelRatio() {},
    getPixelRatio: () => 2 } as unknown as RootState['gl'];
  const source = new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshBasicMaterial({ color: '#7bf5fb' }));
  const uniforms = { ...SCENE_UNIFORMS, uTime: { value: 0 }, uArrival: { value: 0 }, uIgnite: { value: 0 } };
  await root.configure({ gl, scene: new THREE.Scene(), camera, frameloop: 'never',
    size: { width: 398, height: 150.6, top: 0, left: 0 } });
  try {
    await act(async () => { root.render(<BrainPointField source={source} uniforms={uniforms}
      physical={physical} count={96} spineCount={32} baseSize={2} />); });
    act(() => advance(1, false, store.getState()));
    let body!: THREE.Points;
    store.getState().scene.traverse(object => { if (object instanceof THREE.Points) body = object; });
    const geometry = body.geometry, material = body.material as THREE.ShaderMaterial;
    const colors = Array.from(geometry.getAttribute('aColor').array);
    const positions = Array.from(geometry.getAttribute('position').array);
    const radiance = () => material.uniforms.uProjectionEnergy?.value
      ?? material.uniforms.uViewportScale.value ** 2; // existing shader's light allocation before repair
    expect.soft(radiance()).toBeGreaterThan(0);
    expect.soft(radiance()).toBeLessThanOrEqual(0.07); // compact lit anatomy, not a deleted cloud
    expect(material.uniforms.uViewportScale.value).toBeCloseTo(150.6 / 168);
    expect(material.uniforms.uGlowMul.value).toBe(1.35); // authored glow dial not overwritten
    expect(material.uniforms.uSize.value).toBe(2);
    expect(material.uniforms.uPixelRatio.value).toBe(2);

    // Full-stage coverage for nerves must not re-inflate the same presence
    // pane's radiance. Actual installed camera view-offset is the boundary.
    await act(async () => { store.getState().setSize(398, 699.6, 0, 0); });
    camera.setViewOffset(398, 150.6, 0, -138.6, 398, 699.6);
    act(() => advance(2, false, store.getState()));
    expect.soft(radiance()).toBeLessThanOrEqual(0.07);
    camera.setViewOffset(398, 62, 0, -138.6, 398, 699.6);
    act(() => advance(3, false, store.getState()));
    expect.soft(radiance()).toBeGreaterThan(0);
    expect.soft(radiance()).toBeLessThanOrEqual(0.012);
    camera.clearViewOffset();
    await act(async () => { store.getState().setSize(1440, 900, 0, 0); });
    act(() => advance(4, false, store.getState()));
    expect(radiance()).toBe(1); // normal-size authoring preserved
    expect(body.geometry).toBe(geometry);
    expect(geometry.getAttribute('position').count).toBe(128);
    expect(Array.from(geometry.getAttribute('position').array)).toEqual(positions);
    expect(Array.from(geometry.getAttribute('aColor').array)).toEqual(colors);

    // Removing the official projection restores the standalone lab contract,
    // without resampling anatomy or leaving a compact-light multiplier behind.
    await act(async () => { root.render(<BrainPointField source={source} uniforms={uniforms}
      count={96} spineCount={32} baseSize={2} />); store.getState().setSize(398, 150.6, 0, 0); });
    act(() => advance(5, false, store.getState()));
    expect(radiance()).toBeCloseTo(0.803584184);
    expect(body.geometry).toBe(geometry);
  } finally {
    await act(async () => { root.unmount(); });
    source.geometry.dispose(); (source.material as THREE.Material).dispose();
  }
});
