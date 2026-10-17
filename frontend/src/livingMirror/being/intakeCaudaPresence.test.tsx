import { act } from 'react';
import { _roots, advance, createRoot, extend, useFrame, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import BrainPointField from '../../superbrain/components/canvas/BrainPointField';
import BodyIntakeAnchors from '../../superbrain/components/canvas/BodyIntakeAnchors';
import CommandNerve3D from '../../superbrain/components/canvas/CommandNerve3D';
import { SCENE_UNIFORMS } from '../../superbrain/components/canvas/SuperbrainScene.LEGACY';
import { __resetSpineFusionForTests, setBodyGroupWorldMatrix } from '../../superbrain/lib/spineFusionBus';
import { __resetFunnelAnchorForTests, getFunnelAnchor } from '../../superbrain/lib/funnelAnchorBus';
import { __resetTabStoreForTests, beginRetractingMaterializedTab, showContentSurface, upsertInputSurface } from '../../superbrain/lib/tabStore';

vi.mock('../../superbrain/lib/brainScene', () => ({ preloadBrainScene() {} }));
extend({ Points: THREE.Points, Group: THREE.Group, Mesh: THREE.Mesh,
  BufferGeometry: THREE.BufferGeometry, SphereGeometry: THREE.SphereGeometry,
  MeshBasicMaterial: THREE.MeshBasicMaterial, MeshStandardMaterial: THREE.MeshStandardMaterial });
beforeEach(() => {
  __resetSpineFusionForTests(); __resetFunnelAnchorForTests(); __resetTabStoreForTests();
  localStorage.removeItem('gagos-pause-motion-v1');
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  const send = document.createElement('button'); send.className = 'gagos-send'; document.body.append(send);
  vi.spyOn(send, 'getBoundingClientRect').mockReturnValue(new DOMRect(420, 640, 44, 44));
});
afterEach(() => {
  document.querySelector('.gagos-send')?.remove();
  __resetSpineFusionForTests(); __resetFunnelAnchorForTests(); __resetTabStoreForTests();
  vi.restoreAllMocks(); vi.unstubAllGlobals();
});

// Removing the actual shader-presence coupling must leave a visible socket at
// the withdrawn junction and fail. Real sampling, fused geometry, material,
// frame callbacks, store, anchors and nerve run. Only WebGL is substituted;
// the small analytic head is not protected-GLB, shader-raster or device proof.
it.each([[false, false], [false, true], [true, false], [true, true]] as const)(
  'withdraws and returns the intake with its actual cauda field; reduced=%s composer=%s', async (reduced, composer) => {
    vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: reduced }));
    const canvas = document.createElement('canvas'), root = createRoot(canvas), store = _roots.get(canvas)!.store;
    const camera = new THREE.PerspectiveCamera(26, 1, 0.1, 100);
    camera.position.set(0, 0, 15); camera.updateMatrixWorld();
    const source = new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshBasicMaterial({ color: '#7bf5fb' }));
    const uniforms = { ...SCENE_UNIFORMS, uTime: { value: 0 }, uArrival: { value: 0 }, uIgnite: { value: 0 } };
    const physical = { phase: 'resting', taskState: 'idle', coherence: 'fresh', motion: 'calm',
      cortex: { posture: 'attention' }, verification: { state: 'none' }, membrane: { state: 'clear' } };
    let body!: THREE.Points, tube!: THREE.Mesh, socket!: THREE.Group, input!: THREE.Group, beads!: THREE.Group;
    let paints = 0;
    const gl = { domElement: canvas, getPixelRatio: () => 1, setSize() {}, setPixelRatio() {},
      render(scene: THREE.Scene) {
        paints++;
        scene.traverse(object => {
          if (object instanceof THREE.Points) body = object;
          if (!(object instanceof THREE.Mesh)) return;
          if (object.material instanceof THREE.MeshStandardMaterial) tube = object;
          if (!(object.geometry instanceof THREE.SphereGeometry)) return;
          if (object.geometry.parameters.radius === 0.034) socket = object.parent as THREE.Group;
          if (object.geometry.parameters.radius === 0.026) input = object.parent as THREE.Group;
          if (object.geometry.parameters.radius === 0.02) beads = object.parent as THREE.Group;
        });
      },
    } as unknown as RootState['gl'];
    await root.configure({ gl, scene: new THREE.Scene(), camera, frameloop: 'never',
      size: { width: 720, height: 720, left: 0, top: 0 } });
    function ComposerOwner() { useFrame(({ gl: renderer, scene, camera: view }) => renderer.render(scene, view), 1); return null; }
    const step = (time: number) => act(() => advance(time, false, store.getState()));
    try {
      setBodyGroupWorldMatrix(new THREE.Matrix4());
      await act(async () => { root.render(<>
        <BrainPointField source={source} uniforms={uniforms} count={96} spineCount={256} spineScale={0.4} physical={physical} />
        <BodyIntakeAnchors physical={physical} reducedMotion={reduced} />
        <CommandNerve3D reducedMotion={reduced} />
        {composer && <ComposerOwner />}
      </>); });
      step(100);
      const material = body.material as THREE.ShaderMaterial, geometry = body.geometry;
      // A replacement root must build its own tube even at identical endpoints.
      expect(tube.geometry).toBeInstanceOf(THREE.TubeGeometry);
      const baseTube = (tube.material as THREE.Material).opacity;
      const baseSocket = (socket.children[0] as THREE.Mesh).material as THREE.Material;
      const baseSocketOpacity = baseSocket.opacity;
      expect(material.uniforms.uSprayHide.value).toBe(0);
      expect(geometry.getAttribute('position').count).toBe(352);
      expect(Array.from(geometry.getAttribute('aBand').array).slice(96).some(band => band === 0)).toBe(true);
      expect(tube.visible && socket.visible && input.visible).toBe(true);
      expect(baseTube).toBeGreaterThan(0.5);
      expect(getFunnelAnchor()).toMatchObject({ intake: 0.72, flow: reduced ? 0 : 0.32 });
      expect(beads.visible).toBe(!reduced);
      // A typed input alone must not retract its own receiving channel.
      upsertInputSurface('Keep the intake alive'); step(100.05);
      expect(material.uniforms.uSprayHide.value).toBe(0);
      const first = showContentSurface({ filepath: 'fixture://cauda-a', language: '', code: 'A' });
      const second = showContentSurface({ filepath: 'fixture://cauda-b', language: '', code: 'B' });
      step(100.15);
      if (!reduced) {
        // Same real material envelope, not another independently damped phase.
        const tailPresence = 1 - material.uniforms.uSprayHide.value;
        expect(tailPresence).toBeGreaterThan(0); expect(tailPresence).toBeLessThan(1);
        expect.soft((tube.material as THREE.Material).opacity / baseTube).toBeCloseTo(tailPresence, 7);
        expect.soft(baseSocket.opacity / baseSocketOpacity).toBeCloseTo(tailPresence, 7);
      }
      step(110);
      expect(material.uniforms.uSprayHide.value).toBeGreaterThan(0.999);
      expect.soft(tube.visible).toBe(false); expect.soft(socket.visible).toBe(false);
      expect.soft(input.visible).toBe(false); expect.soft(beads.visible).toBe(false);
      // Phase targets remain intact even when anatomy is withdrawn.
      expect(getFunnelAnchor()).toMatchObject({ intake: 0.72, flow: reduced ? 0 : 0.32 });
      expect(beginRetractingMaterializedTab(first.id)).toBe(true); step(111);
      expect(material.uniforms.uSprayHide.value).toBeGreaterThan(0.999);
      expect.soft(socket.visible).toBe(false); // another live result still owns withdrawal
      expect(beginRetractingMaterializedTab(second.id)).toBe(true); step(111.1);
      expect(material.uniforms.uSprayHide.value).toBeLessThan(0.999);
      expect(socket.visible && tube.visible && input.visible).toBe(true);
      step(120);
      expect(material.uniforms.uSprayHide.value).toBeLessThan(0.001);
      expect((tube.material as THREE.Material).opacity / baseTube).toBeCloseTo(1, 7);
      expect(baseSocket.opacity / baseSocketOpacity).toBeCloseTo(1, 7);
      expect(beads.visible).toBe(!reduced);
      expect(body.geometry).toBe(geometry);
      expect(store.getState().internal.priority).toBe(composer ? 1 : 0);
      expect(paints).toBe(7);
    } finally {
      await act(async () => { root.unmount(); });
      source.geometry.dispose(); (source.material as THREE.Material).dispose();
    }
  });
