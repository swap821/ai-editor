import { act } from 'react';
import { _roots, advance, createRoot, extend, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import SuperbrainReactiveEffects from '../../workbench/SuperbrainReactiveEffects';
import { deriveBeingPresentation, type BeingFacts } from './semanticKernel';
import { __resetTabStoreForTests } from '../../superbrain/lib/tabStore';
import { __resetSpineFusionForTests, setSpineFusion } from '../../superbrain/lib/spineFusionBus';
import { __resetAuroraBridgeForTests } from '../../workbench/verifyAuroraBridge';
import { __resetSpineFlashBridgeForTests } from '../../workbench/spineFlashBridge';

// The installed R3F reconciler, semantic/physical projection and real Three
// geometry run. Only the WebGL draw is substituted: not raster/device proof.
extend({ Group: THREE.Group, Mesh: THREE.Mesh, SphereGeometry: THREE.SphereGeometry,
  TorusGeometry: THREE.TorusGeometry, BoxGeometry: THREE.BoxGeometry, MeshBasicMaterial: THREE.MeshBasicMaterial });
beforeEach(() => {
  __resetTabStoreForTests(); __resetSpineFusionForTests(); setSpineFusion(1, [0, 0, 0]);
  __resetAuroraBridgeForTests(); __resetSpineFlashBridgeForTests();
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
});
afterEach(() => {
  __resetTabStoreForTests(); __resetSpineFusionForTests();
  __resetAuroraBridgeForTests(); __resetSpineFlashBridgeForTests();
  vi.restoreAllMocks(); vi.unstubAllGlobals();
});

// A regression that renders every authority boundary as the same complete
// ring must fail even with all material colors discarded and time frozen.
it.each([false, true])('distinguishes held, refused and stopped body boundaries without color or motion; reduced=%s', async reduced => {
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: reduced }));
  const canvas = document.createElement('canvas'), root = createRoot(canvas), store = _roots.get(canvas)!.store;
  const gl = { domElement: canvas, getPixelRatio: () => 1, setSize() {}, setPixelRatio() {},
    render() {} } as unknown as RootState['gl'];
  await root.configure({ gl, scene: new THREE.Scene(), frameloop: 'never',
    size: { width: 720, height: 720, top: 0, left: 0 } });
  const base: BeingFacts = { transport: 'connected', projection: 'fresh', mirrorStatus: 'online', hasSnapshot: true,
    taskActivity: 'idle', verification: 'unknown', stop: 'clear' };
  const show = async (facts: Partial<BeingFacts>) => {
    await act(async () => root.render(<SuperbrainReactiveEffects presentationOverride={deriveBeingPresentation({ ...base, ...facts })} />));
    act(() => advance(0, false, store.getState()));
    let boundary: THREE.Object3D | undefined;
    store.getState().scene.traverse(object => {
      if ((object as THREE.Object3D & { __r3f?: { props: Record<string, unknown> } }).__r3f?.props['data-testid'] === 'sovereign-membrane') boundary = object;
    });
    const meshes: THREE.Mesh[] = [];
    boundary?.traverse(object => { if (object instanceof THREE.Mesh) meshes.push(object); });
    return { boundary, meshes };
  };
  try {
    const held = await show({ approvalPending: true });
    expect.soft(held.meshes, 'held has two separated arcs, not a closed execution halo').toHaveLength(2);
    for (const mesh of held.meshes) {
      expect.soft((mesh.geometry as THREE.TorusGeometry).parameters.arc).toBeLessThan(Math.PI);
    }
    const refused = await show({ taskActivity: 'refused' });
    expect.soft(refused.meshes, 'refusal keeps its closed boundary and a static blocking stroke').toHaveLength(2);
    expect.soft(refused.meshes.some(mesh => mesh.geometry instanceof THREE.BoxGeometry)).toBe(true);
    const stopped = await show({ stop: 'engaged', approvalPending: true, taskActivity: 'refused' });
    expect(stopped.meshes).toHaveLength(1);
    expect.soft((stopped.meshes[0].geometry as THREE.TorusGeometry).parameters.tubularSegments,
      'observed Stop wins with an eight-sided boundary, even over a held/refused input').toBe(8);
    const camera = store.getState().camera;
    const normal = new THREE.Vector3(), facing = new THREE.Vector3(), rotation = new THREE.Quaternion();
    for (const yaw of [0, Math.PI / 2, Math.PI]) {
      camera.rotation.set(0.2, yaw, 0.1);
      act(() => advance(0, false, store.getState()));
      normal.set(0, 0, 1).applyQuaternion(stopped.boundary!.getWorldQuaternion(rotation));
      facing.set(0, 0, 1).applyQuaternion(camera.getWorldQuaternion(rotation));
      expect.soft(normal.dot(facing), 'the body-attached boundary must not collapse edge-on as the camera changes').toBeCloseTo(1, 5);
    }
    const geometry = stopped.meshes[0].geometry;
    const positions = geometry.getAttribute('position').array.slice();
    act(() => { for (let frame = 1; frame <= 60; frame++) advance(frame / 60, false, store.getState()); });
    expect(stopped.meshes[0].geometry).toBe(geometry);
    expect(geometry.getAttribute('position').array).toEqual(positions);
    expect((await show({ taskActivity: 'idle' })).boundary, 'ordinary rest must not invent an authority boundary').toBeUndefined();
  } finally {
    await act(async () => root.unmount());
  }
});
