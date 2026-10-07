import { act } from 'react';
import { _roots, advance, createRoot, extend, useFrame, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import CortexEngine from '../../superbrain/core/CortexEngine';
import { SCENE_UNIFORMS } from '../../superbrain/components/canvas/SuperbrainScene.LEGACY';
import { __resetSpineFusionForTests, setBodyGroupWorldMatrix } from '../../superbrain/lib/spineFusionBus';
import { __resetStemAnchorForTests, getStemAnchor } from '../../superbrain/lib/stemAnchorBus';
import { __resetFunnelAnchorForTests, getFunnelAnchor } from '../../superbrain/lib/funnelAnchorBus';
import { __resetTabStoreForTests, showContentSurface } from '../../superbrain/lib/tabStore';
import { setAmbientMotionPaused } from '../../superbrain/lib/reducedMotion';
import BodyIntakeAnchors from '../../superbrain/components/canvas/BodyIntakeAnchors';
import { deriveOrganismCameraFrame } from '../../superbrain/lib/organismCameraFrame';

const fixture = vi.hoisted(() => ({ field: null as THREE.Group | null, realCamera: false }));
// The actual engine, BrainModel transforms, AmbientFloat, buses, command nerve
// and R3F scheduler are mounted. Only asset/effect content and WebGL are replaced;
// this is transform/attachment proof, not GLB anatomy or GPU visual acceptance.
vi.mock('../../superbrain/lib/brainScene', async () => {
  const { Group } = await import('three');
  const scene = new Group();
  return { preloadBrainScene() {}, useBrainScene: () => scene };
});
vi.mock('../../superbrain/components/canvas/BrainPointField', () => ({
  default: () => <group ref={(field) => { fixture.field = field; }} />,
}));
vi.mock('../../superbrain/components/canvas/NodeLattice', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/MemoryHalo', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/MaterializationLayer', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/CosmicBackground', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/BodySpeech', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/PostFX', () => ({ default: () => null }));
vi.mock('@react-three/drei', async (original) => {
  const actual = await original<typeof import('@react-three/drei')>();
  return { ...actual,
    PerspectiveCamera: (props: Parameters<typeof actual.PerspectiveCamera>[0]) => fixture.realCamera ? <actual.PerspectiveCamera {...props} /> : null,
    OrbitControls: () => null,
  };
});

extend({ Group: THREE.Group, Mesh: THREE.Mesh, Color: THREE.Color, PerspectiveCamera: THREE.PerspectiveCamera,
  BufferGeometry: THREE.BufferGeometry, SphereGeometry: THREE.SphereGeometry,
  TorusGeometry: THREE.TorusGeometry, MeshBasicMaterial: THREE.MeshBasicMaterial,
  MeshStandardMaterial: THREE.MeshStandardMaterial, AmbientLight: THREE.AmbientLight,
  DirectionalLight: THREE.DirectionalLight, PointLight: THREE.PointLight });

beforeEach(() => {
  fixture.field = null; fixture.realCamera = false;
  __resetSpineFusionForTests(); __resetStemAnchorForTests();
  __resetFunnelAnchorForTests(); __resetTabStoreForTests();
  localStorage.removeItem('gagos-pause-motion-v1');
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: false }));
  SCENE_UNIFORMS.uTime.value = 0;
  SCENE_UNIFORMS.uBreath.value = 0.5;
  SCENE_UNIFORMS.uArrival.value = 0;
  SCENE_UNIFORMS.uAwaken.value = 0;
  const button = document.createElement('button');
  button.className = 'gagos-send';
  document.body.append(button);
  vi.spyOn(button, 'getBoundingClientRect').mockReturnValue(new DOMRect(470, 564, 44, 44));
});
afterEach(() => {
  document.querySelector('.gagos-send')?.remove();
  __resetSpineFusionForTests(); __resetStemAnchorForTests();
  __resetFunnelAnchorForTests(); __resetTabStoreForTests();
  vi.restoreAllMocks(); vi.unstubAllGlobals();
});

describe('intake attachment through the rendered engine', () => {
  it.each([
    { name: 'desktop conversation', stage: [1280, 720], pane: [448, 0, 832, 720], send: [201, 434] },
    { name: 'mobile rest', stage: [390, 844], pane: [0, 110, 390, 354.203125], send: [310, 564] },
    { name: 'compact work', stage: [320, 568], pane: [0, 164, 320, 62], send: [254, 476] },
  ])('preserves the body pane while painting the intake across the full $name stage', async ({ stage, pane, send }) => {
    // These are independently recorded browser rectangles. JSDOM supplies no
    // CSS layout; the actual camera/framing/body/nerve and R3F render owner run.
    const host = document.createElement('div'); host.className = 'lm-app';
    const marker = document.createElement('div'); marker.className = 'lm-scene';
    const canvas = document.createElement('canvas');
    host.append(marker, canvas); document.body.append(host);
    fixture.realCamera = true;
    let bounds = new DOMRect(...pane);
    vi.spyOn(marker, 'getBoundingClientRect').mockImplementation(() => bounds);
    vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, ...stage));
    vi.mocked(document.querySelector('.gagos-send')!.getBoundingClientRect).mockReturnValue(new DOMRect(...send, 44, 44));
    const root = createRoot(canvas); const store = _roots.get(canvas)!.store;
    const camera = new THREE.PerspectiveCamera(26, stage[0] / stage[1], 0.1, 100);
    camera.position.set(0, -0.5, 15); camera.lookAt(0, -0.5, 0); camera.updateMatrixWorld();
    const frames: { body: number; input: number; inside: boolean }[] = [];
    const renderer = { domElement: canvas, getPixelRatio: () => 1, render(scene: THREE.Scene, activeCamera: THREE.Camera) {
      scene.updateMatrixWorld(true);
      const socket = fixture.field!.localToWorld(new THREE.Vector3(0, -0.85, 0));
      // Independent old-pane camera, not the production view-offset helper.
      const baseline = new THREE.PerspectiveCamera(deriveOrganismCameraFrame({
        aspect: bounds.width / bounds.height, activeSurfaceCount: 0,
      }).fov, bounds.width / bounds.height, 0.1, 100);
      baseline.position.copy(activeCamera.position); baseline.quaternion.copy(activeCamera.quaternion);
      baseline.updateMatrixWorld();
      const old = socket.clone().project(baseline); const current = socket.clone().project(activeCamera);
      const expected = new THREE.Vector2(bounds.left + (old.x + 1) * bounds.width / 2, bounds.top + (1 - old.y) * bounds.height / 2);
      const actual = new THREE.Vector2((current.x + 1) * stage[0] / 2, (1 - current.y) * stage[1] / 2);
      let junction!: THREE.Group;
      let tube!: THREE.Mesh<THREE.TubeGeometry>;
      scene.traverse(object => {
        if (object instanceof THREE.Mesh && object.geometry instanceof THREE.SphereGeometry
          && object.geometry.parameters.radius === 0.026) junction = object.parent as THREE.Group;
        if (object instanceof THREE.Mesh && object.geometry instanceof THREE.TubeGeometry) tube = object as THREE.Mesh<THREE.TubeGeometry>;
      });
      const endpoint = junction.position.clone().project(activeCamera);
      const positions = tube.geometry.getAttribute('position');
      let tubeInside = true;
      for (let vertex = 0; vertex < positions.count; vertex++) {
        const point = new THREE.Vector3().fromBufferAttribute(positions, vertex).applyMatrix4(tube.matrixWorld).project(activeCamera);
        tubeInside &&= [point.x, point.y, point.z].every(value => Number.isFinite(value) && Math.abs(value) <= 1);
      }
      frames.push({ body: actual.distanceTo(expected), input: new THREE.Vector2((endpoint.x + 1) * stage[0] / 2,
        (1 - endpoint.y) * stage[1] / 2).distanceTo(new THREE.Vector2(send[0] + 22, send[1] + 22)),
      inside: tubeInside && Math.abs(endpoint.x) <= 1 && Math.abs(endpoint.y) <= 1 && Math.abs(endpoint.z) <= 1 });
    }, setSize() {}, setPixelRatio() {} } as unknown as RootState['gl'];
    await root.configure({ gl: renderer, scene: new THREE.Scene(), camera, frameloop: 'never',
      size: { width: stage[0], height: stage[1], left: 0, top: 0 } });
    function ComposerOwner() { useFrame(({ gl, scene, camera: cam }) => gl.render(scene, cam), 1); return null; }
    try {
      await act(async () => { root.render(<><CortexEngine mode="observe" activity={0} tier="low" /><ComposerOwner /></>); });
      act(() => advance(100, false, store.getState()));
      expect(frames).toHaveLength(1);
      expect.soft(frames[0].body).toBeLessThan(0.01);
      expect.soft(frames[0].input).toBeLessThan(1e-6);
      expect(frames[0].inside).toBe(true);
      expect(store.getState().internal.priority).toBe(1);
      const activeCamera = store.getState().camera;
      const field = fixture.field;
      // Real Drei default-camera installation is retained while the DOM pane
      // becomes full-stage Focus, then returns without replacing the body.
      expect(activeCamera).not.toBe(camera);
      bounds = new DOMRect(0, 0, ...stage);
      window.dispatchEvent(new Event('resize'));
      act(() => advance(200, false, store.getState()));
      expect.soft(frames[1].body).toBeLessThan(0.01);
      bounds = new DOMRect(...pane);
      window.dispatchEvent(new Event('resize'));
      act(() => advance(300, false, store.getState()));
      expect.soft(frames[2].body).toBeLessThan(0.01);
      expect.soft(frames[2].input).toBeLessThan(1e-6);
      expect(frames.every(frame => frame.inside)).toBe(true);
      expect(store.getState().camera).toBe(activeCamera);
      expect(fixture.field).toBe(field);
      await act(async () => { root.render(null); });
      expect((activeCamera as THREE.PerspectiveCamera).view?.enabled).toBe(false);
    } finally { await act(async () => { root.unmount(); }); host.remove(); }
  });

  it.each([false, true])('matches this frame of the scaled/floating body with composer=%s', async (composer) => {
    const canvas = document.createElement('canvas');
    const root = createRoot(canvas);
    const store = _roots.get(canvas)!.store;
    const camera = new THREE.PerspectiveCamera(26, 1, 0.1, 100);
    camera.position.set(0, -0.5, 15);
    camera.lookAt(0, -0.5, 0);
    camera.updateMatrixWorld();
    const captures: { stem: number; funnel: number; socket: number; input: number }[] = [];
    const renderer = {
      render(scene: THREE.Scene, renderedCamera: THREE.Camera) {
        scene.updateMatrixWorld(true);
        const field = fixture.field!;
        // Independently transform the authored local sockets through the actual
        // inner visual group, outer posture and floating parent seen by render.
        const stemWorld = field.localToWorld(new THREE.Vector3(0, -0.35, 0));
        const funnelWorld = field.localToWorld(new THREE.Vector3(0, -0.85, 0));
        const stemNdc = stemWorld.project(renderedCamera);
        const stem = getStemAnchor();
        const funnel = getFunnelAnchor();
        const expectedStem = new THREE.Vector2(80 + (stemNdc.x + 1) * 250, 164 + (1 - stemNdc.y) * 250);
        let socket!: THREE.Group;
        let input!: THREE.Group;
        scene.traverse((object) => {
          if (!(object instanceof THREE.Mesh) || !(object.geometry instanceof THREE.SphereGeometry)) return;
          if (object.geometry.parameters.radius === 0.034) socket = object.parent as THREE.Group;
          if (object.geometry.parameters.radius === 0.026) input = object.parent as THREE.Group;
        });
        const inputNdc = input.position.clone().project(renderedCamera);
        const inputScreen = new THREE.Vector2(80 + (inputNdc.x + 1) * 250, 164 + (1 - inputNdc.y) * 250);
        captures.push({
          stem: new THREE.Vector2(stem.x, stem.y).distanceTo(expectedStem),
          funnel: new THREE.Vector3(...funnel.world).distanceTo(funnelWorld),
          socket: socket.position.distanceTo(funnelWorld),
          // The DOM button's center is (492,586), independent of canvas origin.
          input: inputScreen.distanceTo(new THREE.Vector2(492, 586)),
        });
      },
      setSize() {}, setPixelRatio() {},
    } as unknown as RootState['gl'];
    await root.configure({ gl: renderer, scene: new THREE.Scene(), camera,
      frameloop: 'never', size: { width: 500, height: 500, left: 80, top: 164 } });
    function ComposerOwner() {
      useFrame(({ gl, scene, camera: activeCamera }) => gl.render(scene, activeCamera), 1);
      return null;
    }
    try {
      // Two explicitly synthetic materialized surfaces induce the real dock scale;
      // ordinary inspection panels do not count as materialized work in this store.
      showContentSurface({ filepath: 'fixture://intake-a', language: '', code: 'Fixture A' });
      showContentSurface({ filepath: 'fixture://intake-b', language: '', code: 'Fixture B' });
      await act(async () => { root.render(<>
        <CortexEngine mode="observe" activity={0} tier="low" physical={{
          phase: 'resting', taskState: 'idle', coherence: 'fresh', motion: 'calm',
          cortex: { posture: 'attention' }, verification: { state: 'none' }, membrane: { state: 'clear' },
        }} />
        {composer && <ComposerOwner />}
      </>); });
      for (const time of [1, 2, 3]) act(() => advance(time, false, store.getState()));
      expect(captures).toHaveLength(3);
      expect(fixture.field!.parent!.scale.x).toBeLessThan(1);
      for (const frame of captures) {
        expect.soft(frame.stem).toBeLessThan(1e-6);
        expect.soft(frame.funnel).toBeLessThan(1e-9);
        expect.soft(frame.socket).toBeLessThan(1e-9);
        expect.soft(frame.input).toBeLessThan(1e-6);
      }
      expect(store.getState().internal.priority).toBe(composer ? 1 : 0);
      let beads!: THREE.Group;
      store.getState().scene.traverse((object) => {
        if (object instanceof THREE.Mesh && object.geometry instanceof THREE.SphereGeometry
          && object.geometry.parameters.radius === 0.02) beads = object.parent as THREE.Group;
      });
      expect(getFunnelAnchor().flow).toBe(0.32);
      expect(beads.visible).toBe(true);
      const beforePause = beads.children.map(bead => bead.position.toArray());
      await act(async () => { setAmbientMotionPaused(true); });
      act(() => advance(3.016, false, store.getState()));
      expect(getFunnelAnchor().flow).toBe(0);
      expect(beads.visible).toBe(false);
      act(() => advance(60, false, store.getState()));
      expect(beads.children.map(bead => bead.position.toArray())).toEqual(beforePause);
      await act(async () => { setAmbientMotionPaused(false); });
      act(() => advance(60.016, false, store.getState()));
      expect(getFunnelAnchor().flow).toBe(0.32);
      expect(beads.visible).toBe(true);
    } finally { await act(async () => { root.unmount(); }); }
  });

  it('hides clipped sockets and releases only its own anchors on root replacement', async () => {
    const roots = [document.createElement('canvas'), document.createElement('canvas')].map(canvas => {
      const root = createRoot(canvas);
      return { root, store: _roots.get(canvas)!.store };
    });
    const renderer = { render() {}, setSize() {}, setPixelRatio() {} } as unknown as RootState['gl'];
    const physical = { phase: 'resting', taskState: 'idle', coherence: 'fresh', motion: 'calm',
      cortex: { posture: 'attention' }, verification: { state: 'none' }, membrane: { state: 'clear' } } as const;
    for (const { root } of roots) await root.configure({ gl: renderer, scene: new THREE.Scene(),
      camera: new THREE.PerspectiveCamera(26, 1, 0.1, 100), frameloop: 'never',
      size: { width: 500, height: 500, left: 80, top: 164 } });
    const step = (index: number, time: number) => act(() => advance(time, false, roots[index].store.getState()));
    try {
      // Exercise the supported snapshot publisher with independently chosen
      // view-space poses, rather than mocking matrix reads or clipping logic.
      setBodyGroupWorldMatrix(new THREE.Matrix4().makeTranslation(0, 0, -5));
      await act(async () => { roots[0].root.render(<BodyIntakeAnchors physical={physical} reducedMotion />); });
      step(0, 1);
      expect(getFunnelAnchor().visible).toBe(true);
      expect(getFunnelAnchor().intake).toBe(0.72);
      expect(getFunnelAnchor().flow).toBe(0);
      setBodyGroupWorldMatrix(new THREE.Matrix4().makeTranslation(20, 0, -5));
      step(0, 2);
      expect(getStemAnchor().visible).toBe(false);
      expect(getFunnelAnchor().visible).toBe(false);
      // Center the funnel in X/Y so this rejects near-plane depth alone.
      setBodyGroupWorldMatrix(new THREE.Matrix4().makeTranslation(0, 0.85, -0.01));
      step(0, 3);
      const nearNdc = new THREE.Vector3(...getFunnelAnchor().world).project(roots[0].store.getState().camera);
      expect(nearNdc.x).toBe(0);
      expect(nearNdc.y).toBe(0);
      expect(nearNdc.z).toBeLessThan(-1);
      expect(getFunnelAnchor().visible).toBe(false);
      setBodyGroupWorldMatrix(new THREE.Matrix4().makeTranslation(0, 0, -5));
      await act(async () => { roots[1].root.render(<BodyIntakeAnchors physical={physical} reducedMotion />); });
      step(1, 1);
      const replacementStem = getStemAnchor();
      const replacementFunnel = getFunnelAnchor();
      await act(async () => { roots[0].root.render(null); });
      expect(getStemAnchor()).toBe(replacementStem);
      expect(getFunnelAnchor()).toBe(replacementFunnel);
      expect(getFunnelAnchor().visible).toBe(true);
      await act(async () => { roots[1].root.render(null); });
      expect(getStemAnchor().visible).toBe(false);
      expect(getFunnelAnchor()).toMatchObject({ visible: false, intake: 0, flow: 0 });
    } finally {
      for (const { root } of roots) await act(async () => { root.unmount(); });
    }
  });
});
