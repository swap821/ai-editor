import { act } from 'react';
import { _roots, advance, createRoot, extend, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import type { OrbitControls } from 'three-stdlib';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import CortexEngine from '../../superbrain/core/CortexEngine';
import { SCENE_UNIFORMS } from '../../superbrain/components/canvas/SuperbrainScene.LEGACY';
import { __resetTabStoreForTests, closeWorkspace, focusWorkspace, getTabStoreSnapshot,
  openWorkspacePanel, setMaterializedTabLifecycle, showContentSurface } from '../../superbrain/lib/tabStore';
import { __resetSpineFusionForTests } from '../../superbrain/lib/spineFusionBus';
import { __resetLifecycleForTests } from '../../superbrain/lib/lifecycleStateMachine';
import { __resetConversationPhaseForTests } from '../../superbrain/lib/conversationPhaseBus';
import { deriveBeingPresentation } from './semanticKernel';
import { derivePhysicalSnapshot } from './physicalSnapshot';

vi.mock('../../superbrain/lib/brainScene', async () => {
  const { Group, Mesh, BoxGeometry, MeshBasicMaterial } = await import('three');
  const scene = new Group();
  scene.add(new Mesh(new BoxGeometry(), new MeshBasicMaterial({ color: '#7bf5fb' })));
  return { preloadBrainScene() {}, useBrainScene: () => scene };
});
// Keep the actual body, 51k-point geometry, pose, float, camera, installed
// controls and tab owner. External assets, glyphs, backend and WebGL are not
// acceptance evidence here; workspace painting/composer are separate owners.
vi.mock('../../superbrain/components/canvas/MemoryHalo', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/MaterializationLayer', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/PostFX', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/BodySpeech', () => ({ default: () => null }));
extend({ Group: THREE.Group, Points: THREE.Points, Mesh: THREE.Mesh,
  BufferGeometry: THREE.BufferGeometry, BufferAttribute: THREE.BufferAttribute,
  PointsMaterial: THREE.PointsMaterial, SphereGeometry: THREE.SphereGeometry,
  TorusGeometry: THREE.TorusGeometry, MeshBasicMaterial: THREE.MeshBasicMaterial,
  MeshStandardMaterial: THREE.MeshStandardMaterial, PerspectiveCamera: THREE.PerspectiveCamera,
  AmbientLight: THREE.AmbientLight, DirectionalLight: THREE.DirectionalLight,
  PointLight: THREE.PointLight, Color: THREE.Color });

beforeEach(() => {
  __resetTabStoreForTests(); __resetSpineFusionForTests();
  __resetLifecycleForTests(); __resetConversationPhaseForTests();
  localStorage.removeItem('gagos-pause-motion-v1');
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('fetch', async () => new Response('{}', { status: 404 }));
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    clearRect() {}, fillText() {},
  } as unknown as CanvasRenderingContext2D);
  SCENE_UNIFORMS.uTime.value = 0; SCENE_UNIFORMS.uBreath.value = 0.5;
  SCENE_UNIFORMS.uHold.value = 0; SCENE_UNIFORMS.uAwaken.value = 0;
  SCENE_UNIFORMS.uArrival.value = 0; SCENE_UNIFORMS.uIgnite.value = 0;
});
afterEach(() => {
  __resetTabStoreForTests(); __resetSpineFusionForTests();
  __resetLifecycleForTests(); __resetConversationPhaseForTests();
  vi.restoreAllMocks(); vi.unstubAllGlobals();
});

// Missing selected-reader gates must move the real camera/float/voyage despite
// its attentive pose. Gating on any retained tab instead must fail Conversation
// and Close positives. The oracle is actual object movement, not prop spelling.
it.each([
  { width: 1280, height: 720, reduced: false },
  { width: 390, height: 844, reduced: false },
  { width: 1280, height: 720, reduced: true },
  { width: 390, height: 844, reduced: true },
])('steadies selected reading, not retained work; $width/$height reduced=$reduced', async ({ width, height, reduced }) => {
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: reduced }));
  let frame = 0;
  vi.spyOn(performance, 'now').mockImplementation(() => 10_000 + frame * 1000 / 60);
  const canvas = document.createElement('canvas'); document.body.append(canvas);
  const root = createRoot(canvas), store = _roots.get(canvas)!.store;
  let field!: THREE.Points;
  const gl = { domElement: canvas, getPixelRatio: () => 1, setSize() {}, setPixelRatio() {},
    render(scene: THREE.Scene) {
      scene.updateMatrixWorld(true);
      scene.traverse(object => {
        if (object instanceof THREE.Points && object.geometry.getAttribute('position')?.count === 51000) field = object;
      });
    },
  } as unknown as RootState['gl'];
  await root.configure({ gl, scene: new THREE.Scene(), camera: new THREE.PerspectiveCamera(),
    frameloop: 'never', size: { width, height, left: 0, top: 0 } });
  const physical = derivePhysicalSnapshot(deriveBeingPresentation({ transport: 'connected', projection: 'fresh',
    mirrorStatus: 'online', hasSnapshot: true, taskActivity: 'complete', verification: 'unknown', stop: 'clear' }));
  const render = async (inputAttentionActive = false) => act(async () => {
    root.render(<CortexEngine mode="observe" activity={0} tier="low" physical={physical} inputAttentionActive={inputAttentionActive} />);
  });
  const step = (count = 1) => act(() => {
    for (let index = 0; index < count; index++) advance(++frame / 60, false, store.getState());
  });
  try {
    await render(); step(120);
    const controls = store.getState().controls as unknown as OrbitControls;
    const camera = store.getState().camera, geometry = field.geometry, material = field.material;
    const body = field.parent!.parent!, floating = body.parent!;
    const firstAngle = controls.getAzimuthalAngle(), firstPosition = body.position.clone();
    step(120);
    if (!reduced) {
      expect(controls.getAzimuthalAngle()).not.toBeCloseTo(firstAngle, 6);
      expect(body.position.distanceTo(firstPosition)).toBeGreaterThan(0.0001);
    } else expect(controls.getAzimuthalAngle()).toBeCloseTo(firstAngle, 12);

    let first!: ReturnType<typeof showContentSurface>, second!: ReturnType<typeof showContentSurface>;
    act(() => {
      first = showContentSurface({ filepath: 'fixture/reader-a.py', language: 'python', code: 'print("A")', streaming: false });
      second = showContentSurface({ filepath: 'fixture/reader-b.py', language: 'python', code: 'print("B")', streaming: false });
      setMaterializedTabLifecycle(first.id, 'live'); setMaterializedTabLifecycle(second.id, 'live');
    });
    for (const id of [first.id, second.id]) {
      act(() => focusWorkspace(id)); step(600); // let admitted pose/framing/damping settle
      const angle = controls.getAzimuthalAngle(), position = body.position.clone(), floatMatrix = floating.matrix.elements.slice();
      const activeTime = SCENE_UNIFORMS.uTime.value;
      step(360);
      expect.soft(controls.getAzimuthalAngle(), 'idle orbit must not turn away from selected reading').toBeCloseTo(angle, 10);
      expect.soft(floating.matrix.elements, 'floating tissue steadies while its reader is attended').toEqual(floatMatrix);
      expect.soft(body.position.distanceTo(position), 'fused body voyage does not compete with reader attention').toBeLessThan(0.000001);
      expect(SCENE_UNIFORMS.uTime.value).toBeCloseTo(reduced ? activeTime : activeTime + 6, 8);
      expect(SCENE_UNIFORMS.uAwaken.value, 'reading is not backend thinking or microphone capture').toBeLessThan(0.001);
      expect(getTabStoreSnapshot().focusId).toBe(id);
      expect(controls.enabled, 'deliberate scene inspection remains available outside typing').toBe(true);
    }

    // Typing can temporarily take attention without destroying the selection;
    // returning to the reader must not restart its independent idle orbit.
    await render(true); step(60); expect(controls.enabled).toBe(false);
    await render(false); step(600);
    const afterTyping = controls.getAzimuthalAngle(); step(120);
    expect.soft(controls.getAzimuthalAngle()).toBeCloseTo(afterTyping, 10);
    expect(getTabStoreSnapshot().focusId).toBe(second.id);

    act(() => openWorkspacePanel('history', 'Recent activity')); step(600);
    const historyAngle = controls.getAzimuthalAngle(); step(120);
    expect.soft(controls.getAzimuthalAngle(), 'DOM-only readers use the same attention owner').toBeCloseTo(historyAngle, 10);
    act(() => closeWorkspace('history')); step(120);
    const restAngle = controls.getAzimuthalAngle(), restPosition = body.position.clone(); step(120);
    if (!reduced) {
      expect(controls.getAzimuthalAngle()).not.toBeCloseTo(restAngle, 6);
      expect(body.position.distanceTo(restPosition)).toBeGreaterThan(0.0001);
    } else expect(controls.getAzimuthalAngle()).toBeCloseTo(restAngle, 12);
    expect(getTabStoreSnapshot().focusId).toBe(null);
    expect(getTabStoreSnapshot().tabs.map(tab => [tab.id, tab.content?.code, tab.lifecycle])).toEqual([
      [first.id, 'print("A")', 'live'], [second.id, 'print("B")', 'live'],
    ]);
    expect(store.getState().camera).toBe(camera); expect(store.getState().controls).toBe(controls);
    expect(field.geometry).toBe(geometry); expect(field.material).toBe(material);
    expect(field.parent!.parent!).toBe(body); expect(body.parent).toBe(floating);
    expect([physical.phase, physical.taskState]).toEqual(['resting', 'done-unverified']);
  } finally { await act(async () => { root.unmount(); }); canvas.remove(); }
});
