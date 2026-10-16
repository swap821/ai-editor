import { act } from 'react';
import { _roots, advance, createRoot, extend, useFrame, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { BrainModel, SCENE_UNIFORMS } from '../../superbrain/components/canvas/SuperbrainScene.LEGACY';
import { __resetSpineFusionForTests } from '../../superbrain/lib/spineFusionBus';
import { __resetTabStoreForTests, closeWorkspace, getTabStoreSnapshot, reopenMaterializedTab,
  setMaterializedTabLifecycle, showContentSurface } from '../../superbrain/lib/tabStore';
import { getContentSurfacePlacement } from '../../superbrain/lib/materializedSurfaceAnchors';
import { createSeededRandom } from '../../superbrain/lib/seededRandom';
import type { PhysicalBodyProjection } from '../../superbrain/lib/bodyPosture';

vi.mock('../../superbrain/lib/brainScene', async () => {
  const { Group, Mesh, BoxGeometry, MeshBasicMaterial } = await import('three');
  const scene = new Group();
  scene.add(new Mesh(new BoxGeometry(), new MeshBasicMaterial({ color: '#7bf5fb' })));
  return { preloadBrainScene() {}, useBrainScene: () => scene };
});
vi.mock('@react-three/drei', async original => ({
  ...await original<typeof import('@react-three/drei')>(),
  Text: ({ children }: { children: string }) => <group name={`text:${children}`} />,
}));
vi.mock('../../superbrain/components/canvas/NodeLattice', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/MemoryHalo', () => ({ default: () => null }));
// Real BrainModel, full low-tier field, layer, work sockets, return, store and
// R3F scheduler. Only source asset, remote font shaping, decorations and WebGL
// are substituted. This is anatomy-frame evidence, not GLB/shader/device proof.
extend({ Group: THREE.Group, Mesh: THREE.Mesh, Points: THREE.Points, LineSegments: THREE.LineSegments,
  BufferGeometry: THREE.BufferGeometry, SphereGeometry: THREE.SphereGeometry, PlaneGeometry: THREE.PlaneGeometry,
  BoxGeometry: THREE.BoxGeometry, TorusGeometry: THREE.TorusGeometry, TubeGeometry: THREE.TubeGeometry,
  CylinderGeometry: THREE.CylinderGeometry, ShapeGeometry: THREE.ShapeGeometry,
  MeshBasicMaterial: THREE.MeshBasicMaterial, MeshStandardMaterial: THREE.MeshStandardMaterial,
  PointsMaterial: THREE.PointsMaterial, LineBasicMaterial: THREE.LineBasicMaterial, ShaderMaterial: THREE.ShaderMaterial });
beforeEach(() => {
  __resetTabStoreForTests(); __resetSpineFusionForTests();
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: false }));
  vi.spyOn(Math, 'random').mockImplementation(createSeededRandom(0x7ab501));
  localStorage.removeItem('gagos-pause-motion-v1');
  SCENE_UNIFORMS.uArrival.value = 0; SCENE_UNIFORMS.uAwaken.value = 0;
  SCENE_UNIFORMS.uTime.value = 0; SCENE_UNIFORMS.uHold.value = 0;
});
afterEach(() => { __resetTabStoreForTests(); __resetSpineFusionForTests(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

// Leaving a stored, unscaled origin in ReabsorptionParticles should detach the
// dissolve from its real socket when Close releases the dedicated work pane.
// The witness is the actual painted socket, not a fusion/dock helper oracle.
it.each([{ width: 1280, height: 720 }, { width: 390, height: 844 }])(
  'returns from the live socket into the live cortex at $width×$height', async size => {
    let now = 10_000, paints = 0;
    vi.spyOn(performance, 'now').mockImplementation(() => now);
    const canvas = document.createElement('canvas'), root = createRoot(canvas), store = _roots.get(canvas)!.store;
    const camera = new THREE.PerspectiveCamera(26, size.width / size.height, 0.1, 100);
    camera.position.set(0, 0, 15); camera.updateMatrixWorld();
    let body!: THREE.Points, motes: THREE.Points | undefined;
    let sockets: THREE.Mesh[] = [];
    const gl = { domElement: canvas, getPixelRatio: () => 1, setSize() {}, setPixelRatio() {},
      render(scene: THREE.Scene) {
        paints++; scene.updateMatrixWorld(true); motes = undefined; sockets = [];
        scene.traverse(object => {
          if (object instanceof THREE.Points) {
            if (object.geometry.getAttribute('position').count === 51000) body = object;
            if (object.renderOrder === 8 && object.geometry.getAttribute('position').count === 72) motes = object;
          }
          if (object instanceof THREE.Mesh && object.renderOrder === 7
            && object.geometry instanceof THREE.SphereGeometry && object.geometry.parameters.radius === 0.05) sockets.push(object);
        });
      },
    } as unknown as RootState['gl'];
    await root.configure({ gl, camera, scene: new THREE.Scene(), frameloop: 'never', size: { ...size, left: 0, top: 0 } });
    const workPane = { current: true }, burst = { current: { intensity: 0, lastBurst: 0 } }, arrival = { current: 0 };
    const physical: PhysicalBodyProjection = { phase: 'resting', taskState: 'done-unverified', coherence: 'fresh', motion: 'calm',
      cortex: { posture: 'unverified' }, verification: { state: 'unverified' }, membrane: { state: 'clear' } };
    function ComposerOwner() { useFrame(({ gl: renderer, scene, camera: view }) => renderer.render(scene, view), 1); return null; }
    const frame = (elapsed: number) => {
      now = 10_000 + elapsed; act(() => advance(100 + elapsed / 1000, false, store.getState()));
    };
    try {
      await act(async () => { root.render(<>
        <group rotation={[0.2, -0.3, 0.1]} scale={[1.17, 0.89, 1.08]}>
          <BrainModel activity={0} mode="observe" burst={burst} arrival={arrival} tier="low" uniforms={SCENE_UNIFORMS}
            physical={physical} workPaneRef={workPane} />
        </group><ComposerOwner />
      </>); });
      frame(0);
      const bodyGeometry = body.geometry;
      let first!: ReturnType<typeof showContentSurface>;
      await act(async () => {
        for (const seat of [11, 2, 7]) {
          const tab = showContentSurface({ filepath: `fixture://return-${seat}`, language: 'text', code: `retained ${seat}`, streaming: false },
            getContentSurfacePlacement(seat));
          first ??= tab; setMaterializedTabLifecycle(tab.id, 'live');
        }
      });
      frame(0);
      expect(sockets).toHaveLength(3);
      // Seat11 is the lowest real vertebra. Render ordering changes on Close;
      // it must not be mistaken for anatomical identity.
      const socket = sockets.reduce((lowest, candidate) => candidate.position.y < lowest.position.y ? candidate : lowest);
      await act(async () => { closeWorkspace(first.id); });
      workPane.current = false; // ordinary Close: no selected DOM work plane
      frame(0);
      expect(motes).toBeInstanceOf(THREE.Points);
      const returning = motes!, geometry = returning.geometry;
      const token = getTabStoreSnapshot().tabs.find(tab => tab.id === first.id)!.retractionToken;
      let largestBirthGap = 0;
      // 300ms is still the authored dissolve-only beat: even the earliest birth
      // has not reached its .24 rise boundary. All72 scattered motes remain.
      for (let index = 0; index <= 18; index++) {
        frame(index * 300 / 18);
        const positions = geometry.getAttribute('position'), center = new THREE.Vector3();
        for (let mote = 0; mote < positions.count; mote++) center.add(new THREE.Vector3().fromBufferAttribute(positions, mote));
        center.divideScalar(positions.count);
        const socketInReturnFrame = socket.getWorldPosition(new THREE.Vector3()).applyMatrix4(returning.matrixWorld.clone().invert());
        // Authored scatter is in this local frame, not scaled world units.
        largestBirthGap = Math.max(largestBirthGap, center.distanceTo(socketInReturnFrame));
        expect(motes).toBe(returning); expect(sockets.includes(socket)).toBe(true);
      }
      expect.soft(largestBirthGap, 'dissolve remains at its currently rendered vertebra').toBeLessThan(0.08);
      for (let elapsed = 320; elapsed < 1699; elapsed += 20) frame(elapsed);
      frame(1699);
      // Independent physical head witness from the actual cloud, not the
      // published anchor or return-curve builder. The contract's upper55% head
      // region is evaluated once here; source timing/scatter remain unchanged.
      const positions = body.geometry.getAttribute('position'), mask = body.geometry.getAttribute('aCortex');
      let lo = Infinity, hi = -Infinity;
      for (let index = 0; index < positions.count; index++) if (mask.getX(index)) { lo = Math.min(lo, positions.getY(index)); hi = Math.max(hi, positions.getY(index)); }
      const cut = hi - (hi - lo) * 0.55, cortex = new THREE.Vector3();
      let count = 0;
      for (let index = 0; index < positions.count; index++) if (mask.getX(index) && positions.getY(index) >= cut) {
        cortex.add(new THREE.Vector3().fromBufferAttribute(positions, index)); count++;
      }
      cortex.divideScalar(count).applyMatrix4(body.matrixWorld).applyMatrix4(returning.matrixWorld.clone().invert());
      let furthest = 0;
      const landed = geometry.getAttribute('position');
      for (let index = 0; index < landed.count; index++) furthest = Math.max(furthest,
        new THREE.Vector3().fromBufferAttribute(landed, index).distanceTo(cortex));
      expect.soft(furthest, 'all returning motes land in this paint of the cortex').toBeLessThan(0.08);
      expect(body.geometry).toBe(bodyGeometry); expect(landed.count).toBe(72);
      expect(store.getState().internal.priority).toBe(1); expect(paints).toBeGreaterThan(80);
      let disposed = 0; geometry.addEventListener('dispose', () => disposed++);
      await act(async () => { expect(reopenMaterializedTab(first.id)).toBe(true); });
      frame(1700);
      expect(motes).toBeUndefined(); expect(disposed).toBe(1);
      expect(getTabStoreSnapshot().tabs.find(tab => tab.id === first.id)).toMatchObject({ id: first.id,
        content: { code: 'retained 11' }, retractionToken: undefined });
      expect(token).toBeTruthy();
    } finally { await act(async () => root.unmount()); }
  });
