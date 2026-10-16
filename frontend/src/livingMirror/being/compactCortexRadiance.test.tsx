import { act } from 'react';
import { _roots, advance, createRoot, extend, useFrame, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import BrainPointField from '../../superbrain/components/canvas/BrainPointField';
import { SCENE_UNIFORMS } from '../../superbrain/components/canvas/SuperbrainScene.LEGACY';
import type { PhysicalBodyProjection } from '../../superbrain/lib/bodyPosture';

vi.mock('../../superbrain/lib/brainScene', () => ({ preloadBrainScene() {} }));
extend({ Points: THREE.Points, Group: THREE.Group });
beforeEach(() => { vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true); });
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

const physical: PhysicalBodyProjection = {
  phase: 'resting', taskState: 'done-unverified', coherence: 'coherent', motion: 'breathe',
  cortex: { posture: 'unverified' }, verification: { state: 'unverified' }, membrane: { state: 'clear' },
};

// BrainModel/AmbientFloat update ancestors in later default-priority frame
// subscriptions. Their achieved pose, not the previous frame, reaches the draw.
function LateDockPose({ readScale }: { readScale: () => number }) {
  useFrame(({ scene }) => { scene.getObjectByName('projection-dock')!.scale.setScalar(readScale()); });
  return null;
}

function drawRenderer(canvas: HTMLCanvasElement): RootState['gl'] {
  const gl = { domElement: canvas, setSize() {}, setPixelRatio() {}, getPixelRatio: () => 2,
    render(scene: THREE.Scene, camera: THREE.Camera) {
      scene.traverse(object => {
        if (object instanceof THREE.Points) {
          object.onBeforeRender(gl as unknown as THREE.WebGLRenderer, scene, camera,
            object.geometry, object.material as THREE.Material, null!);
        }
      });
    },
  };
  return gl as unknown as RootState['gl'];
}

// Regression: carrying the full-size cloud's radiance into the tiny product
// pane washes out its folds. Exercise the actual material/frame/resize owner,
// not a mocked point field or a source-text assertion. WebGL alone is replaced.
it.each([false, true])('keeps a compact product cortex lit without full-size radiance; reduced motion=%s', async reduced => {
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: reduced }));
  const canvas = document.createElement('canvas');
  const root = createRoot(canvas), store = _roots.get(canvas)!.store;
  const camera = new THREE.PerspectiveCamera();
  const gl = drawRenderer(canvas);
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

// A taller pane is not a larger cortex. A dock/camera fit can compress the
// same point population into fewer pixels while the pane remains unchanged.
// Reverting the achieved-footprint allocation must fail this real consumer.
it.each([false, true])('budgets cortex light against its achieved projection, not the pane; reduced motion=%s', async reduced => {
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: reduced }));
  const canvas = document.createElement('canvas');
  const root = createRoot(canvas), store = _roots.get(canvas)!.store;
  const camera = new THREE.PerspectiveCamera(45, 320 / 576, 0.1, 100);
  camera.position.set(0, 0, 15);
  camera.updateMatrixWorld();
  const gl = drawRenderer(canvas);
  const source = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.MeshBasicMaterial({ color: '#7bf5fb' }));
  const uniforms = { ...SCENE_UNIFORMS, uTime: { value: 0 }, uArrival: { value: 0 }, uIgnite: { value: 0 } };
  await root.configure({ gl, scene: new THREE.Scene(), camera, frameloop: 'never',
    size: { width: 320, height: 576, top: 0, left: 0 } });
  let dockScale = 1;
  const readScale = () => dockScale;
  const render = (projection?: PhysicalBodyProjection) => root.render(<>
    <group name="projection-dock">
      <BrainPointField source={source} uniforms={uniforms} physical={projection}
        count={200000} spineCount={500} baseSize={2} />
    </group>
    <LateDockPose readScale={readScale} />
  </>);
  try {
    await act(async () => { render(physical); });
    act(() => advance(1, false, store.getState()));
    const dock = store.getState().scene.getObjectByName('projection-dock')!;
    const body = dock.children[0] as THREE.Points;
    const geometry = body.geometry, material = body.material as THREE.ShaderMaterial;
    // Snapshot ALL sampled values. Typed-array copies / scalar comparisons
    // avoid millions of generic assertion visits, not any anatomy coverage.
    const colors = geometry.getAttribute('aColor').array.slice();
    const positions = geometry.getAttribute('position').array.slice();
    const cortexEnergy = () => material.uniforms.uCortexProjectionEnergy?.value ?? 1;
    const full = cortexEnergy();
    expect.soft(full).toBeGreaterThan(0);
    expect.soft(full).toBeLessThan(0.6); // authored high-tier population in an approximately 94px square
    // Source RGB already contains intensity and SRC_ALPHA multiplies by it
    // again. The blended radial kernel is ~2.826%, not ~7.724%, of the square.
    expect(material.blending).toBe(THREE.AdditiveBlending);
    expect(material.premultipliedAlpha).toBe(false);
    expect.soft(full).toBeGreaterThan(0.2);
    expect(material.uniforms.uProjectionEnergy.value).toBe(1); // spine keeps its original light

    // The later frame subscriber changes the ancestor AFTER the point-field's
    // frame callback. Its draw must use this frame's half-size / quarter-area pose.
    dockScale = 0.5;
    act(() => advance(2, false, store.getState()));
    const compact = cortexEnergy();
    expect.soft(compact / full).toBeCloseTo(0.25, 2);
    expect.soft(compact).toBeGreaterThan(0);
    expect(material.uniforms.uProjectionEnergy.value).toBe(1);

    await act(async () => { store.getState().setSize(320, 720, 0, 0); });
    camera.setViewOffset(320, 576, 0, -100, 320, 720);
    act(() => advance(3, false, store.getState()));
    expect.soft(cortexEnergy()).toBeCloseTo(compact, 5); // expanded nerve coverage is not extra head area
    const cortexMask = geometry.getAttribute('aCortex');
    expect(cortexMask?.count).toBe(200500);
    expect(cortexMask.array.subarray(0, 200000).every(value => value === 1)).toBe(true);
    expect(cortexMask.array.subarray(200000).every(value => value === 0)).toBe(true);
    expect(body.geometry).toBe(geometry);
    const currentPositions = geometry.getAttribute('position').array;
    const currentColors = geometry.getAttribute('aColor').array;
    expect(currentPositions).toHaveLength(positions.length);
    expect(currentColors).toHaveLength(colors.length);
    expect(currentPositions.every((value, index) => Object.is(value, positions[index]))).toBe(true);
    expect(currentColors.every((value, index) => Object.is(value, colors[index]))).toBe(true);

    await act(async () => { render(); });
    act(() => advance(4, false, store.getState()));
    expect(cortexEnergy()).toBe(1); // standalone lab look is not automatically changed
    expect(body.geometry).toBe(geometry);
  } finally {
    await act(async () => { root.unmount(); });
    source.geometry.dispose(); (source.material as THREE.Material).dispose();
  }
});
