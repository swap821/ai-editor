import { act } from 'react';
import { _roots, advance, createRoot, extend, type RootState } from '@react-three/fiber';
import { GLTFLoader, type OrbitControls } from 'three-stdlib';
import * as THREE from 'three';
import { afterEach, beforeAll, beforeEach, expect, it, onTestFinished, vi } from 'vitest';
import CortexEngine from '../../superbrain/core/CortexEngine';
import PresenceViewport from '../../superbrain/components/canvas/PresenceViewport';
import { SCENE_UNIFORMS } from '../../superbrain/components/canvas/SuperbrainScene.LEGACY';
import { __resetTabStoreForTests, focusWorkspace, getTabStoreSnapshot, openWorkspacePanel, setMaterializedTabLifecycle, showApprovalSurface, showContentSurface } from '../../superbrain/lib/tabStore';
import { __resetSpineFusionForTests, getCortexAnchor } from '../../superbrain/lib/spineFusionBus';
import type { PhysicalBodyProjection } from '../../superbrain/lib/bodyPosture';

const fixture = vi.hoisted(() => ({ source: null as THREE.Group | null, withBackdrop: false, withWorkspaces: false }));
// Keep an immutable real projection operation: a timed-out asynchronous case
// must never capture a previous case's observer as its forwarding target.
const nativeVectorProject = THREE.Vector3.prototype.project;
vi.mock('../../superbrain/lib/brainScene', () => ({ preloadBrainScene() {}, useBrainScene: () => fixture.source }));
// Real protected GLB, point sampling/fused spine, body transforms, Drei camera /
// OrbitControls and projection run. Only unrelated scene content and WebGL are
// replaced. This is CPU silhouette/layout proof, not shader or hardware proof.
vi.mock('../../superbrain/components/canvas/NodeLattice', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/MemoryHalo', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/MaterializationLayer', async () => {
  const actual = await vi.importActual<typeof import('../../superbrain/components/canvas/MaterializationLayer')>(
    '../../superbrain/components/canvas/MaterializationLayer');
  return { default: (props: Parameters<typeof actual.default>[0]) => fixture.withWorkspaces ? <actual.default {...props} /> : null };
});
vi.mock('@react-three/drei', async original => ({
  ...await original<typeof import('@react-three/drei')>(),
  Text: ({ children }: { children: string }) => <group name={`text:${children}`} />,
}));
vi.mock('../../superbrain/components/canvas/CosmicBackground', async () => {
  const actual = await vi.importActual<typeof import('../../superbrain/components/canvas/CosmicBackground')>(
    '../../superbrain/components/canvas/CosmicBackground');
  return { default: (props: Parameters<typeof actual.default>[0]) => fixture.withBackdrop ? <actual.default {...props} /> : null };
});
vi.mock('../../superbrain/components/canvas/BodySpeech', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/PostFX', () => ({ default: () => null }));

extend({ Group: THREE.Group, Points: THREE.Points, Mesh: THREE.Mesh, Color: THREE.Color,
  PerspectiveCamera: THREE.PerspectiveCamera, BufferGeometry: THREE.BufferGeometry,
  SphereGeometry: THREE.SphereGeometry, TorusGeometry: THREE.TorusGeometry,
  MeshBasicMaterial: THREE.MeshBasicMaterial, MeshStandardMaterial: THREE.MeshStandardMaterial, PointsMaterial: THREE.PointsMaterial,
  AmbientLight: THREE.AmbientLight, DirectionalLight: THREE.DirectionalLight, PointLight: THREE.PointLight,
  LineSegments: THREE.LineSegments, PlaneGeometry: THREE.PlaneGeometry, BoxGeometry: THREE.BoxGeometry,
  TubeGeometry: THREE.TubeGeometry, CylinderGeometry: THREE.CylinderGeometry, ShapeGeometry: THREE.ShapeGeometry,
  LineBasicMaterial: THREE.LineBasicMaterial, ShaderMaterial: THREE.ShaderMaterial });
beforeAll(async () => {
  const { readFile } = await vi.importActual<{ readFile: (path: string) => Promise<Uint8Array> }>('node:fs/promises');
  const bytes = await readFile('public/models/brain.glb');
  const loader = new GLTFLoader();
  loader.register(() => ({ name: 'KHR_materials_pbrSpecularGlossiness', beforeRoot: () => Promise.resolve() }));
  // Copy Node's Buffer into the test realm's ArrayBuffer for GLTFLoader's
  // instanceof check; the protected binary itself is read-only.
  const binary = new Uint8Array(bytes.length); binary.set(bytes);
  fixture.source = (await loader.parseAsync(binary.buffer, '')).scene;
});
beforeEach(() => {
  fixture.withBackdrop = false;
  fixture.withWorkspaces = false;
  __resetTabStoreForTests(); __resetSpineFusionForTests();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    clearRect() {}, fillText() {},
  } as unknown as CanvasRenderingContext2D);
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: true }));
  SCENE_UNIFORMS.uTime.value = 0; SCENE_UNIFORMS.uBreath.value = 0.5;
  SCENE_UNIFORMS.uArrival.value = 0; SCENE_UNIFORMS.uAwaken.value = 0;
  SCENE_UNIFORMS.uHold.value = 0; // isolate the shared leaf after actual hold/Stop scenarios
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); __resetTabStoreForTests(); __resetSpineFusionForTests(); });

// The onscreen-only fit passes while a real waiting card still covers the
// cortex. Exercise the actual protected GLB/body/layer/current camera together;
// only font shaping and WebGL are substituted, not placement or anatomy.
const crowdingScenarios = [false, true].flatMap(reduced => [3, 12].flatMap(workCount => [false, true].flatMap(phone =>
  ['baseline', 'zoom', 'switch'].map(scenario => ({ reduced, workCount, phone, scenario })))));
// Original baseline cases retain the runner's5s default. The new min-zoom and
// switching journeys run the same810 real frames plus installed-control
// updates/focus transitions and every-vertex/pair geometry checks. Their15s
// functional-test budget is not a device/frame-rate or product-latency claim;
// simulated timing, geometry thresholds and coverage floors are unchanged.
for (const crowdingScenario of ['baseline', 'zoom', 'switch']) {
it.each(crowdingScenarios.filter(({ scenario }) => scenario === crowdingScenario))(
  'keeps waiting work clear through active input, ambient movement and camera transitions; reduced=$reduced work=$workCount phone=$phone scenario=$scenario', async ({ reduced, workCount, phone, scenario }) => {
    let finished = false;
    let projectionObserver: THREE.Vector3['project'] | undefined;
    const releaseProjectionObserver = () => {
      if (THREE.Vector3.prototype.project === projectionObserver) THREE.Vector3.prototype.project = nativeVectorProject;
    };
    onTestFinished(() => { finished = true; releaseProjectionObserver(); });
    fixture.withWorkspaces = true;
    vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: reduced }));
    localStorage.removeItem('gagos-pause-motion-v1');
    const tabs = Array.from({ length: workCount }, (_, seat) => {
      const tab = showContentSurface({ filepath: `retained-${seat}.txt`, language: 'text', code: `retained content ${seat}` }, { seatIndex: seat });
      setMaterializedTabLifecycle(tab.id, 'live'); return tab;
    });
    focusWorkspace(tabs[0].id);
    const host = document.createElement('div'); host.className = 'lm-app'; host.dataset.working = 'true';
    const pane = document.createElement('div'); pane.className = 'lm-scene';
    const header = document.createElement('header'); header.className = 'lm-header';
    const mode = document.createElement('div'); mode.className = 'gagos-experience-mode';
    const reader = document.createElement('section'); reader.className = 'lm-surface'; reader.dataset.workspaceId = tabs[0].id;
    reader.textContent = tabs[0].content!.code;
    const canvas = document.createElement('canvas'); host.append(pane, header, mode, reader, canvas); document.body.append(host);
    // Match the measured inset fixture, including its mode row and stage.
    // A whole-window surrogate had no overlap and was only characterization.
    const stage = phone ? new DOMRect(0, 0, 320, 568) : new DOMRect(0, 61, 1440, 839);
    const anatomyPane = phone ? new DOMRect(0, 118, 320, 60) : new DOMRect(0, 61, 460.8125, 839);
    vi.spyOn(host, 'getBoundingClientRect').mockReturnValue(stage);
    vi.spyOn(pane, 'getBoundingClientRect').mockReturnValue(anatomyPane);
    vi.spyOn(header, 'getBoundingClientRect').mockReturnValue(phone ? new DOMRect(28, 20, 264, 44) : new DOMRect(28, 81, 1384, 44));
    vi.spyOn(mode, 'getBoundingClientRect').mockReturnValue(phone ? new DOMRect(28, 76, 264, 30) : new DOMRect(28, 137, 369.578125, 62));
    vi.spyOn(reader, 'getBoundingClientRect').mockReturnValue(phone ? new DOMRect(12, 178, 296, 44) : new DOMRect(476.796875, 279, 935.203125, 407));
    vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue(stage);
    const root = createRoot(canvas), store = _roots.get(canvas)!.store;
    const gl = { domElement: canvas, render() {}, setSize() {}, setPixelRatio() {}, getPixelRatio: () => 1 } as unknown as RootState['gl'];
    await root.configure({ gl, scene: new THREE.Scene(), camera: new THREE.PerspectiveCamera(),
      frameloop: 'never', size: { width: stage.width, height: stage.height, top: 0, left: 0 } });
    try {
      if (finished) return;
      const physical: PhysicalBodyProjection = {
        phase: 'resting', taskState: 'done-unverified', coherence: 'coherent', motion: 'breathe',
        cortex: { posture: 'unverified' }, verification: { state: 'unverified' }, membrane: { state: 'clear' },
      };
      const render = async (inputAttentionActive: boolean) => {
        await act(async () => { root.render(<CortexEngine mode="observe" activity={0} tier="low"
          inputAttentionActive={inputAttentionActive} physical={physical} />); });
      };
      await render(true);
      if (finished) return;
      const scene = store.getState().scene, camera = store.getState().camera;
      const controls = store.getState().controls as unknown as OrbitControls;
      let body!: THREE.Points;
      scene.traverse(node => { if (node instanceof THREE.Points && node.geometry.getAttribute('aBand')) body = node; });
      expect(body.geometry.getAttribute('position').count).toBe(51000);
      const point = new THREE.Vector3(), pixel = new THREE.Vector2();
      const projectionView = new THREE.Matrix4(), projectionWorld = new THREE.Matrix4();
      const checkClearance = () => {
      scene.updateMatrixWorld(true); camera.updateMatrixWorld();
      projectionView.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
      projectionWorld.multiplyMatrices(projectionView, body.matrixWorld);
      const cortex = new THREE.Box2(), positions = body.geometry.getAttribute('position');
      // The low tier samples40000 protected brain vertices before its11000
      // fused cord vertices. Expected bounds come from the painted anatomy,
      // not the placement solver or its publication.
      // Keep independent outline measurement outside the live .project probe.
      // These are Three's exact projection operations; all vertices remain
      // checked, but the observer must measure consumers, not its own oracle.
      for (let vertex = 0; vertex < 40000; vertex++) {
        point.fromBufferAttribute(positions, vertex).applyMatrix4(projectionWorld);
        cortex.expandByPoint(pixel.set((point.x + 1) * stage.width / 2, stage.top + (1 - point.y) * stage.height / 2));
      }
      let waiting = 0;
      const centers: THREE.Vector2[] = [];
      const slabs: THREE.Box2[] = [];
      const envelope = new THREE.Box2();
      let cortexOverlap = false;
      scene.traverse(node => {
        if (!(node instanceof THREE.Mesh) || node.geometry.type !== 'ExtrudeGeometry') return;
        for (let owner: THREE.Object3D | null = node; owner; owner = owner.parent) if (!owner.visible) return;
        waiting++;
        const slab = new THREE.Box2(), vertices = node.geometry.getAttribute('position');
        projectionWorld.multiplyMatrices(projectionView, node.matrixWorld);
        for (let vertex = 0; vertex < vertices.count; vertex++) {
          point.fromBufferAttribute(vertices, vertex).applyMatrix4(projectionWorld);
          slab.expandByPoint(pixel.set((point.x + 1) * stage.width / 2, stage.top + (1 - point.y) * stage.height / 2));
        }
        cortexOverlap = slab.intersectsBox(cortex) || cortexOverlap;
        centers.push(slab.getCenter(new THREE.Vector2()));
        slabs.push(slab);
        envelope.union(slab);
      });
      expect(waiting).toBe(workCount - 1); // no silent disappearance to pass overlap
      expect.soft(cortexOverlap).toBe(false);
      expect.soft(envelope.min.x).toBeGreaterThanOrEqual(12); expect.soft(envelope.max.x).toBeLessThanOrEqual(anatomyPane.right - 12);
      expect.soft(envelope.min.y).toBeGreaterThanOrEqual(phone ? 130 : 223); expect.soft(envelope.max.y).toBeLessThanOrEqual(anatomyPane.bottom - 12);
      let minimumSeparation = Infinity;
      for (let index = 0; index < centers.length; index++) {
        for (const other of centers.slice(index + 1)) minimumSeparation = Math.min(minimumSeparation, centers[index].distanceTo(other));
      }
      expect.soft(minimumSeparation).toBeGreaterThan(1);
      // Distinct centers still let the actual waiting slabs hide one another.
      // Use independently projected mesh bounds, not the placement budget.
      let overlap: { slab: THREE.Box2; other: THREE.Box2 } | null = null;
      for (let index = 0; index < slabs.length; index++) {
        for (const other of slabs.slice(index + 1)) if (slabs[index].intersectsBox(other)) overlap = { slab: slabs[index], other };
      }
      expect.soft(overlap, overlap ? JSON.stringify(overlap) : undefined).toBeNull();
      };
      for (let tick = 1; tick <= 630; tick++) {
        act(() => advance(tick / 60, false, store.getState()));
        if (tick < 360 || tick % 90 !== 0) continue;
        controls.autoRotate = false;
        const angle = [0, 0.7, 2.2, 4.5][(tick - 360) / 90];
        controls.setAzimuthalAngle(angle);
        for (let settle = 0; settle < 256; settle++) controls.update();
        const difference = controls.getAzimuthalAngle() - angle;
        expect(Math.abs(Math.atan2(Math.sin(difference), Math.cos(difference)))).toBeLessThan(1e-7);
        // Install the current HUD positions after the achieved camera orbit.
        act(() => advance(tick / 60, false, store.getState()));
        if (scenario === 'baseline') checkClearance();
      }

      // Retain the original active-input reproduction, then release input so
      // the real AmbientFloat/voyage ancestors and Drei orbit update actually
      // move. No repeated settling updates before these intermediate frames.
      await render(false);
      if (finished) return;
      const expectedInverse = new THREE.Matrix4();
      const currentWorld = new THREE.Matrix4();
      let projectedSamples = 0, staleProjectionError = 0;
      // Observe every real projection without retaining Vitest mock-call
      // records for every frame/point. The oracle and all samples are unchanged.
      projectionObserver = function (this: THREE.Vector3, viewCamera: THREE.Camera) {
        if (viewCamera === camera) {
          currentWorld.compose(camera.position, camera.quaternion, camera.scale);
          if (camera.parent) currentWorld.premultiply(camera.parent.matrixWorld);
          expectedInverse.copy(currentWorld).invert();
          for (let component = 0; component < 16; component++) {
            staleProjectionError = Math.max(staleProjectionError,
              Math.abs(expectedInverse.elements[component] - camera.matrixWorldInverse.elements[component]));
          }
          projectedSamples++;
        }
        return nativeVectorProject.call(this, viewCamera);
      };
      THREE.Vector3.prototype.project = projectionObserver;
      let ambientStart: THREE.Matrix4 | null = null, actualBodyMovement = 0;
      for (let tick = 631; tick <= 810; tick++) {
        act(() => advance(tick / 60, false, store.getState()));
        scene.updateMatrixWorld(true);
        if (tick === 660) ambientStart = body.matrixWorld.clone();
        if (ambientStart) {
          for (let component = 0; component < 16; component++) {
            actualBodyMovement = Math.max(actualBodyMovement,
              Math.abs(body.matrixWorld.elements[component] - ambientStart.elements[component]));
          }
        }
        if (tick >= 660 && tick % 15 === 0) {
          const consumerSamples = projectedSamples;
          if (scenario === 'baseline') checkClearance();
          expect(projectedSamples).toBe(consumerSamples); // oracle cannot supply the live-projection evidence
        }
      }
      releaseProjectionObserver();
      expect(projectedSamples).toBeGreaterThan(0);
      expect(staleProjectionError).toBeLessThan(1e-9);
      if (!reduced) expect(actualBodyMovement).toBeGreaterThan(1e-5);
      expect(getTabStoreSnapshot().focusId).toBe(tabs[0].id);
      expect(reader.textContent).toBe('retained content 0');
      expect(getTabStoreSnapshot().tabs.filter(tab => tab.kind === 'content')).toHaveLength(workCount);
      // The reader owns the work-side allocation on desktop just as on phone.
      // Retained results must not take a second allowance from the organism's
      // private pane through the old fullscreen card-count docking policy.
      expect.soft(body.parent!.scale.x).toBeCloseTo(1, 5);
      const fullBody = new THREE.Box2(), fullPositions = body.geometry.getAttribute('position');
      for (let vertex = 0; vertex < fullPositions.count; vertex++) {
        point.fromBufferAttribute(fullPositions, vertex).applyMatrix4(body.matrixWorld)
          .applyMatrix4(camera.matrixWorldInverse).applyMatrix4(camera.projectionMatrix);
        fullBody.expandByPoint(pixel.set((point.x + 1) * stage.width / 2, stage.top + (1 - point.y) * stage.height / 2));
      }
      expect.soft(fullBody.min.x).toBeGreaterThanOrEqual(anatomyPane.left);
      expect.soft(fullBody.max.x).toBeLessThanOrEqual(anatomyPane.right);
      expect.soft(fullBody.min.y).toBeGreaterThanOrEqual(phone ? 118 : 211);
      expect.soft(fullBody.max.y).toBeLessThanOrEqual(anatomyPane.bottom);
      if (scenario === 'baseline') return;
      // Zoom is an ordinary installed-control interaction, not an oversized
      // synthetic head. Exercise its actual admitted closest distance as well
      // as the default-distance orbit samples above.
      controls.autoRotate = false;
      for (const angle of [0, 0.7, 2.2, 4.5]) {
        controls.setAzimuthalAngle(angle);
        for (let settle = 0; settle < 256; settle++) controls.update();
        camera.position.sub(controls.target).setLength(controls.minDistance).add(controls.target);
        controls.update();
        expect(controls.getDistance()).toBeCloseTo(6, 7);
        act(() => advance(14, false, store.getState()));
        if (scenario === 'zoom') checkClearance();
      }
      if (scenario === 'zoom') return;
      // Select through the real attention store while body/controls continue
      // moving. Reader delegation changes identity without replacing anatomy,
      // clearing results, or waiting for a settled focus pose.
      const geometry = body.geometry;
      for (const [selection, tab] of tabs.entries()) {
        await act(async () => {
          reader.dataset.workspaceId = tab.id; reader.textContent = tab.content!.code;
          focusWorkspace(tab.id);
        });
        if (finished) return;
        for (let tick = 1; tick <= 12; tick++) {
          act(() => advance(14 + selection * 0.2 + tick / 60, false, store.getState()));
          if (tick === 1 || tick === 6 || tick === 12) checkClearance();
        }
        expect(getTabStoreSnapshot().focusId).toBe(tab.id);
        expect(getTabStoreSnapshot().tabs.map(record => record.id)).toEqual(tabs.map(record => record.id));
        expect(reader.textContent).toBe(tab.content!.code);
        expect(body.geometry).toBe(geometry);
        expect(body.parent!.scale.x).toBeCloseTo(1, 5);
      }
    } finally { releaseProjectionObserver(); await act(async () => { root.unmount(); }); host.remove(); }
  },
  crowdingScenario === 'baseline' ? undefined : 15000,
);
}

// No result exists to suppress pointer attention via conductor fallback.
// This directly protects the panel guard and held/Stop precedence with History.
it.each([false, true])('yields pointer attention to panel-only History and preserves sovereign priority; reduced motion=%s', async reduced => {
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: reduced }));
  localStorage.removeItem('gagos-pause-motion-v1');
  const physical: PhysicalBodyProjection = { phase: 'resting', taskState: 'idle', coherence: 'fresh',
    motion: 'calm', cortex: { posture: 'rest' }, verification: { state: 'none' }, membrane: { state: 'clear' } };
  const canvas = document.createElement('canvas'), root = createRoot(canvas), store = _roots.get(canvas)!.store;
  const gl = { domElement: canvas, getPixelRatio: () => 1, render() {}, setSize() {}, setPixelRatio() {} } as unknown as RootState['gl'];
  await root.configure({ gl, scene: new THREE.Scene(), camera: new THREE.PerspectiveCamera(), frameloop: 'never',
    size: { width: 1440, height: 900, top: 0, left: 0 } });
  let time = 0;
  const frames = (count: number, pointerX: number) => {
    store.getState().pointer.set(pointerX, 0.8);
    for (let tick = 0; tick < count; tick++) {
      time += 1 / 60; act(() => advance(time, false, store.getState()));
    }
    store.getState().scene.updateMatrixWorld(true);
  };
  const render = async (projection = physical, inputAttentionActive = false) => {
    await act(async () => { root.render(<CortexEngine mode="observe" activity={0} tier="low" physical={projection}
      inputAttentionActive={inputAttentionActive} />); });
  };
  try {
    await render(); frames(600, -1);
    let cloud!: THREE.Points;
    store.getState().scene.traverse(object => { if (object instanceof THREE.Points) cloud = object; });
    const body = cloud.parent!.parent!, geometry = cloud.geometry;
    if (!reduced) expect(body.rotation.y).toBeLessThan(-0.8); // real pointer response before panel admission
    await act(async () => { openWorkspacePanel('history', 'Recent activity'); });
    expect(getTabStoreSnapshot().tabs).toHaveLength(0);
    frames(600, 1);
    expect.soft(body.rotation.y).toBeCloseTo(-0.78, 5);
    const material = cloud.material as THREE.ShaderMaterial;
    expect.soft(material.uniforms.uAwaken.value).toBeLessThan(0.0001);
    frames(240, -1);
    expect.soft(body.rotation.y).toBeCloseTo(-0.78, 5);
    expect.soft(material.uniforms.uAwaken.value).toBeLessThan(0.0001);
    await act(async () => {
      const decision = showApprovalSurface({ requestRef: 'history-priority-fixture', summary: 'Proposed write',
        explanation: '', diff: '+ proposed', command: '', kindLabel: 'Write', filepath: 'proposed.py', content: 'proposed' },
        { seatIndex: 6, originLocal: [0, -2, 0], targetLocal: [1, -1.8, 0.8] });
      setMaterializedTabLifecycle(decision.id, 'live');
    });
    await render({ ...physical, phase: 'awaiting-human', taskState: 'needs-permission', motion: 'hold',
      cortex: { posture: 'attention' }, membrane: { state: 'held' } }, true); frames(600, -1);
    if (reduced) expect(body.rotation.y).toBeCloseTo(-0.78, 5);
    else expect(body.rotation.y).toBeGreaterThan(-0.78); // actual decision wins over input and History
    expect(getTabStoreSnapshot().focusId).toBe('history');
    await render({ ...physical, phase: 'stopped', taskState: 'stopped',
      cortex: { posture: 'stopped' }, membrane: { state: 'stopped' } }, true); frames(600, 1);
    expect(body.rotation.y).toBeCloseTo(-0.78, 5);
    expect(body.rotation.x).toBeCloseTo(0.05, 5);
    expect(getTabStoreSnapshot().focusId).toBe('history');
    expect(cloud.geometry).toBe(geometry);
  } finally { await act(async () => { root.unmount(); }); }
});

// Mutation caught: selecting a real DOM panel leaves the fused body aiming at
// a background result (or at the pointer) while cortical currents use the panel.
it.each([{ full: false, reduced: false }, { full: true, reduced: false },
  { full: false, reduced: true }, { full: true, reduced: true }])(
  'keeps body attention with selected History; seats full=$full reduced motion=$reduced', async ({ full, reduced }) => {
    vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: reduced }));
    localStorage.removeItem('gagos-pause-motion-v1');
    const reader = showContentSurface({ filepath: 'retained.py', language: 'python', code: 'retained partial' },
      { seatIndex: 3, originLocal: [0, -1.4, 0], targetLocal: [-1, -1, 0.8] });
    setMaterializedTabLifecycle(reader.id, 'live');
    if (full) for (let seat = 0; seat < 12; seat++) {
      if (seat === 3) continue;
      const result = showContentSurface({ filepath: `background-${seat}.py`, language: 'python', code: 'background' },
        { seatIndex: seat, originLocal: [0, -1.4, 0], targetLocal: [-1, -1, 0.8] });
      setMaterializedTabLifecycle(result.id, 'live');
    }
    const physical: PhysicalBodyProjection = { phase: 'resting', taskState: 'idle', coherence: 'fresh',
      motion: 'calm', cortex: { posture: 'rest' }, verification: { state: 'none' }, membrane: { state: 'clear' } };
    const canvas = document.createElement('canvas'), root = createRoot(canvas), store = _roots.get(canvas)!.store;
    const gl = { domElement: canvas, getPixelRatio: () => 1, render() {}, setSize() {}, setPixelRatio() {} } as unknown as RootState['gl'];
    await root.configure({ gl, scene: new THREE.Scene(), camera: new THREE.PerspectiveCamera(), frameloop: 'never',
      size: { width: 1440, height: 900, top: 0, left: 0 } });
    let time = 0;
    const frames = (count: number, pointerX: number) => {
      store.getState().pointer.set(pointerX, 0.8);
      for (let tick = 0; tick < count; tick++) {
        time += 1 / 60; act(() => advance(time, false, store.getState()));
      }
      store.getState().scene.updateMatrixWorld(true);
    };
    const render = async (inputAttentionActive = false) => {
      await act(async () => { root.render(<CortexEngine mode="observe" activity={0} tier="low" physical={physical}
        inputAttentionActive={inputAttentionActive} />); });
    };
    try {
      await render(); frames(600, -1);
      let cloud!: THREE.Points;
      store.getState().scene.traverse(object => { if (object instanceof THREE.Points) cloud = object; });
      const body = cloud.parent!.parent!, geometry = cloud.geometry;
      if (!reduced) expect(body.rotation.y).toBeLessThan(-0.78);
      await act(async () => { openWorkspacePanel('history', 'Recent activity'); });
      const panel = getTabStoreSnapshot().panels!.find(candidate => candidate.id === 'history')!;
      expect(panel.seatIndex === null).toBe(full);
      frames(600, 1);
      expect.soft(body.rotation.y).toBeCloseTo(-0.78, 5); // panel owns attention, never the left result/right pointer
      if (full || reduced) expect.soft(body.rotation.x).toBeCloseTo(0.05, 5);
      else expect.soft(body.rotation.x).toBeLessThan(0.05); // real admitted panel anchor
      frames(240, -1);
      expect.soft(body.rotation.y).toBeCloseTo(-0.78, 5);
      expect(getTabStoreSnapshot().focusId).toBe('history');
      expect(getTabStoreSnapshot().tabs.find(tab => tab.id === reader.id)?.content?.code).toBe('retained partial');
      expect(cloud.geometry).toBe(geometry);
      expect(SCENE_UNIFORMS.uHold.value).toBe(0);
      await render(true); frames(600, 1);
      if (!reduced) expect(body.rotation.x).toBeLessThan(0.05); // local intake can still take attention
      expect(getTabStoreSnapshot().focusId).toBe('history');
      await render(false);
      await act(async () => { focusWorkspace(reader.id); }); frames(600, 1);
      if (!reduced) expect(body.rotation.y).toBeLessThan(-0.78); // same result returns, without remount
      expect(getTabStoreSnapshot().focusId).toBe(reader.id);
      expect(cloud.geometry).toBe(geometry);
    } finally { await act(async () => { root.unmount(); }); }
  });

// Mutation caught: the intake current owning engagement while the real body
// still aims at a retained reader, follows the pointer or automatically orbits.
it.each([false, true])('returns fused body attention from the reader to local input and back; reduced motion=%s', async reduced => {
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: reduced }));
  localStorage.removeItem('gagos-pause-motion-v1');
  const reader = showContentSurface({ filepath: 'retained.py', language: 'python', code: 'retained partial' },
    { seatIndex: 3, originLocal: [0, -1.4, 0], targetLocal: [-1, -1, 0.8] });
  setMaterializedTabLifecycle(reader.id, 'live');
  const physical: PhysicalBodyProjection = { phase: 'resting', taskState: 'idle', coherence: 'fresh',
    motion: 'calm', cortex: { posture: 'rest' }, verification: { state: 'none' }, membrane: { state: 'clear' } };
  const canvas = document.createElement('canvas'), root = createRoot(canvas), store = _roots.get(canvas)!.store;
  const gl = { domElement: canvas, getPixelRatio: () => 1, render() {}, setSize() {}, setPixelRatio() {} } as unknown as RootState['gl'];
  await root.configure({ gl, scene: new THREE.Scene(), camera: new THREE.PerspectiveCamera(), frameloop: 'never',
    size: { width: 1440, height: 900, top: 0, left: 0 } });
  let time = 0;
  const frames = (count: number, pointerX: number) => {
    store.getState().pointer.set(pointerX, 0.8);
    for (let tick = 0; tick < count; tick++) {
      time += 1 / 60; act(() => advance(time, false, store.getState()));
    }
    store.getState().scene.updateMatrixWorld(true);
  };
  const render = async (inputAttentionActive: boolean, projection = physical) => {
    await act(async () => { root.render(<CortexEngine mode="observe" activity={0} tier="low" physical={projection}
      {...{ inputAttentionActive }} />); });
  };
  try {
    await render(false); frames(600, -1);
    let cloud!: THREE.Points;
    store.getState().scene.traverse(object => { if (object instanceof THREE.Points) cloud = object; });
    const body = cloud.parent!.parent!, geometry = cloud.geometry;
    if (!reduced) expect(body.rotation.y).toBeLessThan(-0.78); // retained left reader
    await render(true);
    const controls = store.getState().controls as unknown as OrbitControls;
    expect.soft(controls.autoRotate).toBe(false);
    expect.soft(controls.enabled).toBe(false); // scene drag must not compete with text/capture
    frames(600, 1);
    expect.soft(body.rotation.y).toBeCloseTo(-0.78, 5); // central intake, not the left reader/right cursor
    if (reduced) expect.soft(body.rotation.x).toBeCloseTo(0.05, 5);
    else expect.soft(body.rotation.x).toBeLessThan(0.05); // existing bounded downward attention
    const parentPose = body.parent!.matrixWorld.clone(), angle = controls.getAzimuthalAngle();
    frames(240, -1);
    expect.soft(Math.max(...body.parent!.matrixWorld.elements.map((value, index) => Math.abs(value - parentPose.elements[index])))).toBeLessThan(0.0001);
    expect.soft(controls.getAzimuthalAngle()).toBeCloseTo(angle, 8);
    expect(getTabStoreSnapshot().focusId).toBe(reader.id);
    expect(getTabStoreSnapshot().tabs.find(tab => tab.id === reader.id)?.content?.code).toBe('retained partial');
    expect(cloud.geometry).toBe(geometry);
    expect(SCENE_UNIFORMS.uHold.value).toBe(0); // engagement is not permission/model work

    await render(false); frames(240, 1);
    expect(controls.autoRotate).toBe(false); // returning to selected reading is not idle
    expect(controls.enabled).toBe(true);
    expect(controls.getAzimuthalAngle()).toBeCloseTo(angle, 8);
    if (!reduced) expect(body.rotation.y).toBeLessThan(-0.78);
    expect(cloud.geometry).toBe(geometry);
    expect(getTabStoreSnapshot().focusId).toBe(reader.id);

    await render(true, { ...physical, phase: 'stopped', taskState: 'stopped', cortex: { posture: 'stopped' },
      membrane: { state: 'stopped' } });
    frames(600, 1);
    expect(body.rotation.y).toBeCloseTo(-0.78, 5);
    expect(body.rotation.x).toBeCloseTo(0.05, 5); // Stop wins even with local engagement
    expect(cloud.geometry).toBe(geometry);
  } finally { await act(async () => { root.unmount(); }); }
});

// Installed controls deliberately block gestures during input, but their
// framing target still changes when work appears or the viewport rotates.
it.each([false, true])('keeps phone framing synchronized during input and smooth on release; reduced motion=%s', async reduced => {
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: reduced }));
  localStorage.removeItem('gagos-pause-motion-v1');
  const host = document.createElement('div'); host.className = 'lm-app';
  const pane = document.createElement('div'); pane.className = 'lm-scene';
  const canvas = document.createElement('canvas'); host.append(pane, canvas); document.body.append(host);
  let width = 390, height = 844, paneBounds = new DOMRect(0, 0, width, height);
  vi.spyOn(pane, 'getBoundingClientRect').mockImplementation(() => paneBounds);
  vi.spyOn(canvas, 'getBoundingClientRect').mockImplementation(() => new DOMRect(0, 0, width, height));
  const root = createRoot(canvas), store = _roots.get(canvas)!.store;
  const gl = { domElement: canvas, getPixelRatio: () => 1, render() {}, setSize() {}, setPixelRatio() {} } as unknown as RootState['gl'];
  await root.configure({ gl, scene: new THREE.Scene(), camera: new THREE.PerspectiveCamera(),
    frameloop: 'never', size: { width, height, top: 0, left: 0 } });
  let time = 0;
  const frames = (count: number) => {
    let maxAimError = 0;
    for (let tick = 0; tick < count; tick++) {
      time += 1 / 60; act(() => advance(time, false, store.getState()));
      const { camera, controls: activeControls } = store.getState();
      const target = (activeControls as unknown as OrbitControls).target;
      maxAimError = Math.max(maxAimError, camera.getWorldDirection(new THREE.Vector3())
        .angleTo(target.clone().sub(camera.position).normalize()));
    }
    return maxAimError;
  };
  const render = async (inputAttentionActive: boolean) => {
    await act(async () => { root.render(<CortexEngine mode="observe" activity={0} tier="low" inputAttentionActive={inputAttentionActive} />); });
  };
  try {
    await render(false); frames(600);
    const camera = store.getState().camera, controls = store.getState().controls as unknown as OrbitControls;
    await render(true);
    let reader!: ReturnType<typeof showContentSurface>;
    await act(async () => {
      reader = showContentSurface({ filepath: 'retained.py', language: 'python', code: 'same partial' }, { seatIndex: 3 });
      setMaterializedTabLifecycle(reader.id, 'live');
    });
    host.dataset.working = 'true'; paneBounds = new DOMRect(0, 118, width, 220);
    window.dispatchEvent(new Event('resize'));
    expect.soft(frames(240)).toBeLessThan(1e-7); // actual forward axis agrees with changing target
    expect(controls.target.y).toBeCloseTo(-0.75, 4);
    expect(controls.enabled).toBe(false); expect(controls.autoRotate).toBe(false);
    const position = camera.position.clone(), orientation = camera.quaternion.clone();
    canvas.dispatchEvent(new WheelEvent('wheel', { deltaY: -100, bubbles: true, cancelable: true }));
    canvas.dispatchEvent(Object.assign(new Event('pointerdown'), { pointerId: 1, pointerType: 'mouse', button: 0, clientX: 40, clientY: 40 }));
    canvas.dispatchEvent(Object.assign(new Event('pointermove'), { pointerId: 1, pointerType: 'mouse', clientX: 140, clientY: 120 }));
    frames(240);
    expect(camera.position.distanceTo(position)).toBeLessThan(1e-8);
    expect(camera.quaternion.angleTo(orientation)).toBeLessThan(1e-6); // no gesture-owned zoom/rotation

    width = 844; height = 390; paneBounds = new DOMRect(0, 0, width * 0.32, height);
    // Installed R3F configure reapplies omitted defaults. A size-only call
    // switches to 'always', so advance() reads wall-clock deltas instead of
    // these 1/60 timestamps and can leave the release target unsettled.
    await act(async () => { await root.configure({ frameloop: 'never', size: { width, height, top: 0, left: 0 } }); });
    expect(store.getState().frameloop).toBe('never'); // manual advances must keep their deterministic clock across resize
    window.dispatchEvent(new Event('resize'));
    expect.soft(frames(600)).toBeLessThan(1e-7);
    expect(store.getState().camera).toBe(camera); expect(store.getState().controls).toBe(controls);
    expect(controls.enabled).toBe(false);
    const beforeRelease = camera.quaternion.clone();
    await render(false); frames(1);
    expect.soft(camera.quaternion.angleTo(beforeRelease)).toBeLessThan(0.001); // no deferred layout correction
    expect(controls.enabled).toBe(true); expect(controls.autoRotate).toBe(false);
    expect(getTabStoreSnapshot().focusId).toBe(reader.id);
    expect(getTabStoreSnapshot().tabs.find(tab => tab.id === reader.id)?.content?.code).toBe('same partial');
    expect(store.getState().internal.priority).toBe(0);
  } finally { await act(async () => { root.unmount(); }); host.remove(); }
});

// Mutation caught: a held body following the cursor/ambient orbit instead of
// the admitted approval, or choosing the reader merely because it has focus.
it.each([false, true])('holds the fused body and camera toward permission without stealing the reader; reduced motion=%s', async reduced => {
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: reduced }));
  localStorage.removeItem('gagos-pause-motion-v1');
  const reader = showContentSurface({ filepath: 'retained.py', language: 'python', code: 'retained partial' },
    { seatIndex: 3, originLocal: [0, -1.4, 0], targetLocal: [-1, -1, 0.8] });
  setMaterializedTabLifecycle(reader.id, 'live');
  const decision = showApprovalSurface({ requestRef: 'held-fixture', summary: 'Proposed write', explanation: '',
    diff: '+ proposed', command: '', kindLabel: 'Write', filepath: 'proposed.py', content: 'proposed' },
    { seatIndex: 6, originLocal: [0, -2, 0], targetLocal: [1, -1.8, 0.8] });
  setMaterializedTabLifecycle(decision.id, 'live');
  const held: PhysicalBodyProjection = { phase: 'awaiting-human', taskState: 'needs-permission', coherence: 'fresh',
    motion: 'hold', cortex: { posture: 'attention' }, verification: { state: 'none' }, membrane: { state: 'held' } };
  const canvas = document.createElement('canvas'), root = createRoot(canvas), store = _roots.get(canvas)!.store;
  const gl = { domElement: canvas, getPixelRatio: () => 1, render() {}, setSize() {}, setPixelRatio() {} } as unknown as RootState['gl'];
  await root.configure({ gl, scene: new THREE.Scene(), camera: new THREE.PerspectiveCamera(), frameloop: 'never',
    size: { width: 1440, height: 900, top: 0, left: 0 } });
  let time = 0;
  const frames = (count: number, pointerX: number) => {
    store.getState().pointer.set(pointerX, 0.8);
    for (let tick = 0; tick < count; tick++) {
      time += 1 / 60; act(() => advance(time, false, store.getState()));
    }
    store.getState().scene.updateMatrixWorld(true);
  };
  const render = async (physical: PhysicalBodyProjection, inputAttentionActive = false) => {
    await act(async () => { root.render(<CortexEngine mode="observe" activity={0} tier="low" physical={physical}
      {...{ inputAttentionActive }} />); });
  };
  const released: PhysicalBodyProjection = { ...held, phase: 'resting', taskState: 'idle', motion: 'calm',
    cortex: { posture: 'rest' }, membrane: { state: 'clear' } };
  try {
    await render(released);
    frames(120, -1); // enter a hold from the same mounted, attentive body
    await render(held, true);
    const controls = store.getState().controls as unknown as OrbitControls;
    expect.soft(controls.autoRotate).toBe(false);
    frames(600, -1);
    let cloud!: THREE.Points;
    store.getState().scene.traverse(object => { if (object instanceof THREE.Points) cloud = object; });
    const body = cloud.parent!.parent!;
    const geometry = cloud.geometry, material = cloud.material as THREE.ShaderMaterial;
    // Literal base yaw is -0.78. The admitted right-hand decision must win over
    // both the left reader and a left pointer; reduced motion adds no travel.
    if (reduced) expect.soft(body.rotation.y).toBeCloseTo(-0.78, 8);
    else expect.soft(body.rotation.y).toBeGreaterThan(-0.78);
    const pose = body.matrixWorld.clone(), angle = controls.getAzimuthalAngle();
    const heat = material.uniforms.uAwaken.value;
    expect.soft(heat).toBeLessThan(0.0001); // no unrelated pointer-heat floor
    frames(240, 1);
    expect.soft(Math.max(...body.matrixWorld.elements.map((value, index) => Math.abs(value - pose.elements[index])))).toBeLessThan(0.0001);
    expect.soft(controls.getAzimuthalAngle()).toBeCloseTo(angle, 8);
    expect.soft(material.uniforms.uAwaken.value).toBeCloseTo(heat, 4);
    expect(getTabStoreSnapshot().focusId).toBe(reader.id);
    expect(getTabStoreSnapshot().tabs.find(tab => tab.id === reader.id)?.content?.code).toBe('retained partial');
    expect(cloud.geometry).toBe(geometry);
    expect(store.getState().internal.priority).toBe(0);

    // Semantic release outranks a retained approval geometry record; it is not
    // another hold authority. Return to the same reader, not idle auto-orbit,
    // without remounting work; deliberate camera inspection stays available.
    await render(released);
    expect(controls.autoRotate).toBe(false);
    expect(controls.enabled).toBe(true);
    frames(240, 0);
    expect(controls.getAzimuthalAngle()).toBeCloseTo(angle, 8);
    if (!reduced) expect(body.rotation.y).toBeLessThan(-0.78); // left reader, not the retained right approval
    expect(cloud.geometry).toBe(geometry);
    expect(getTabStoreSnapshot().focusId).toBe(reader.id);

    await render({ ...released, phase: 'stopped', taskState: 'stopped', cortex: { posture: 'stopped' },
      membrane: { state: 'stopped' } }, true);
    expect(controls.autoRotate).toBe(false);
    frames(600, -1);
    const stoppedPose = body.matrixWorld.clone(), stoppedAngle = controls.getAzimuthalAngle();
    frames(240, 1);
    expect(Math.max(...body.matrixWorld.elements.map((value, index) => Math.abs(value - stoppedPose.elements[index])))).toBeLessThan(0.0001);
    expect(controls.getAzimuthalAngle()).toBeCloseTo(stoppedAngle, 8);
    expect(cloud.geometry).toBe(geometry);
  } finally { await act(async () => { root.unmount(); }); }
});

it.each([
  { width: 768, height: 521, fitted: true },
  { width: 900, height: 720, fitted: true },
  { width: 1199, height: 720, fitted: true },
  { width: 900, height: 520, fitted: true },
  { width: 1280, height: 520, fitted: true },
  { width: 844, height: 390, fitted: true },
  { width: 1280, height: 720, fitted: true },
  { width: 390, height: 844, fitted: true },
])('keeps active fit and retained-work policy across Focus transitions at $width × $height', async ({ width, height, fitted }) => {
  const host = document.createElement('div'); host.className = 'lm-app';
  host.dataset.beingFocus = 'true'; host.dataset.working = 'true';
  const marker = document.createElement('div'); marker.className = 'lm-scene';
  const canvas = document.createElement('canvas');
  host.append(marker, canvas); document.body.append(host);
  vi.spyOn(marker, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, width, height));
  vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, width, height));
  const root = createRoot(canvas);
  const fitRef = { current: false };
  const workPaneRef = { current: false };
  const camera = new THREE.PerspectiveCamera();
  const renderer = { domElement: canvas, render() {}, setSize() {}, setPixelRatio() {} } as unknown as RootState['gl'];
  await root.configure({ gl: renderer, scene: new THREE.Scene(), camera,
    frameloop: 'never', size: { width, height, left: 0, top: 0 } });
  try {
    await act(async () => { root.render(<PresenceViewport phoneFocusRef={fitRef} workPaneRef={workPaneRef} />); });
    expect(fitRef.current).toBe(fitted);
    expect(workPaneRef.current).toBe(true);
    expect(camera.view).toMatchObject({ fullWidth: width, fullHeight: height, offsetX: 0, offsetY: 0 });
    await act(async () => { host.dataset.working = 'false'; window.dispatchEvent(new Event('resize')); });
    // Desktop resting Focus keeps the count-neutral anatomy fit; phone
    // resting Focus retains its existing measured-controls policy instead.
    expect(workPaneRef.current).toBe(width >= 768);
    expect(fitRef.current).toBe(true);
    expect(camera.view).toMatchObject(width >= 768
      ? { fullWidth: width, fullHeight: height - 12, offsetX: 0, offsetY: 0 }
      : { fullWidth: width - 24, fullHeight: height - 24, offsetX: -12, offsetY: -12 });
    await act(async () => { host.dataset.working = 'true'; window.dispatchEvent(new Event('resize')); });
    expect(workPaneRef.current).toBe(true);
    await act(async () => { root.render(null); });
    expect(fitRef.current).toBe(false); expect(workPaneRef.current).toBe(false); expect(camera.view?.enabled).toBe(false);
  } finally { await act(async () => { root.unmount(); }); host.remove(); }
});

it.each([
  { width: 390, height: 844, chatTop: 710 },
  { width: 320, height: 568, chatTop: 434 },
  { width: 390, height: 844, chatTop: 644, noticeHeight: 112 },
  // Independently recorded native active-Focus rectangles, expanded work.
  { width: 390, height: 844, chatTop: 628, activePane: [0, 164, 390, 168] },
  { width: 320, height: 568, chatTop: 364, activePane: [0, 164, 320, 86] },
  { width: 1280, height: 720, chatTop: 524, activePane: [0, 144, 409.609375, 576] },
  { width: 768, height: 521, chatTop: 323, activePane: [0, 144, 245.765625, 377] },
  { width: 900, height: 720, chatTop: 488, activePane: [0, 144, 288, 576] },
  { width: 1199, height: 720, chatTop: 488, activePane: [0, 144, 383.6875, 576] },
  // The native fixture has a shorter containing app, not a full-height phone.
  // Two independent admitted content records exercise real orchestration;
  // the native result plus History panel is not two materialized content tabs.
  { width: 398, height: 700, chatTop: 474, activePane: [0, 164, 398, 104.6], workspaceCount: 2, beingFocus: false },
  { width: 390, height: 844, chatTop: 628, activePane: [0, 164, 390, 168], workspaceCount: 2, beingFocus: true },
  // Recorded repaired Guided pane, with and without the actual Focus policy.
  { width: 398, height: 700, chatTop: 474, activePane: [0, 118, 398, 150.6], workspaceCount: 2, beingFocus: false },
  { width: 398, height: 700, chatTop: 474, activePane: [0, 118, 398, 150.6], workspaceCount: 2, beingFocus: true },
])('keeps the real fused body in the control-free presence region at $width × $height', async ({ width, height, chatTop, noticeHeight = 74.75, activePane, workspaceCount = 0, beingFocus = true }) => {
  // In one recorded Guided two-content case, mount the real backdrop too:
  // its projected focus must land on the actual protected cortical points.
  fixture.withBackdrop = activePane?.[1] === 118 && !beingFocus;
  for (let index = 0; index < workspaceCount; index++) {
    const tab = showContentSurface({ filepath: index ? 'gagos://history' : 'fixture/hello.py', language: 'text', code: 'retained work' }, { seatIndex: index + 2 });
    setMaterializedTabLifecycle(tab.id, 'live');
  }
  const host = document.createElement('div'); host.className = 'lm-app'; host.dataset.beingFocus = String(beingFocus);
  const marker = document.createElement('div'); marker.className = 'lm-scene';
  const header = document.createElement('header'); header.className = 'lm-header';
  const mode = document.createElement('div'); mode.className = 'gagos-experience-mode';
  const notice = document.createElement('div'); notice.className = 'lm-connection';
  const chat = document.createElement('div'); chat.className = 'gagos-chat';
  const canvas = document.createElement('canvas');
  if (activePane) host.dataset.working = 'true';
  const resizeCallbacks = new Map<ResizeObserverCallback, Set<Element>>();
  vi.stubGlobal('ResizeObserver', class {
    private targets = new Set<Element>();
    constructor(private callback: ResizeObserverCallback) { resizeCallbacks.set(callback, this.targets); }
    observe(target: Element) { this.targets.add(target); }
    unobserve(target: Element) { this.targets.delete(target); }
    disconnect() { resizeCallbacks.delete(this.callback); }
  });
  host.append(marker, header, mode, notice, chat, canvas); document.body.append(host);
  let paneBounds = activePane ? new DOMRect(...activePane) : new DOMRect(0, 0, width, height);
  const paneRect = vi.spyOn(marker, 'getBoundingClientRect').mockImplementation(() => paneBounds);
  vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, width, height));
  vi.spyOn(header, 'getBoundingClientRect').mockReturnValue(new DOMRect(16, 64, width - 32, 42));
  vi.spyOn(mode, 'getBoundingClientRect').mockReturnValue(new DOMRect(70, 12, 240, 54));
  let noticeBounds = new DOMRect(12, activePane ? height - 82 : 124, width - 24, noticeHeight);
  let chatBounds = new DOMRect(12, chatTop, width - 24, 122);
  const noticeRect = vi.spyOn(notice, 'getBoundingClientRect').mockImplementation(() => noticeBounds);
  vi.spyOn(chat, 'getBoundingClientRect').mockImplementation(() => chatBounds);
  const root = createRoot(canvas); const store = _roots.get(canvas)!.store;
  const renderer = { domElement: canvas, getPixelRatio: () => 1, render() {}, setSize() {}, setPixelRatio() {},
    getCurrentViewport: (target: THREE.Vector4) => target.set(0, 0, width, height) } as unknown as RootState['gl'];
  await root.configure({ gl: renderer, scene: new THREE.Scene(), camera: new THREE.PerspectiveCamera(),
    frameloop: 'never', size: { width, height, left: 0, top: 0 } });
  try {
    await act(async () => { root.render(<CortexEngine mode="observe" activity={0} tier="low" />); });
    const measuredReads = noticeRect.mock.calls.length;
    const paneReads = paneRect.mock.calls.length;
    for (let tick = 1; tick <= 180; tick++) act(() => advance(tick / 60, false, store.getState()));
    expect(noticeRect.mock.calls).toHaveLength(measuredReads); // never measure in useFrame
    expect(paneRect.mock.calls).toHaveLength(paneReads);
    const camera = store.getState().camera as THREE.PerspectiveCamera;
    const controls = store.getState().controls as unknown as OrbitControls;
    let body!: THREE.Points;
    store.getState().scene.traverse(object => { if (object instanceof THREE.Points) body = object; });
    let backdrop: THREE.Points | undefined;
    store.getState().scene.traverse(object => {
      if (object instanceof THREE.Points && object.material instanceof THREE.PointsMaterial) backdrop = object;
    });
    const backdropShader = { uniforms: THREE.UniformsUtils.clone(THREE.ShaderLib.points.uniforms),
      vertexShader: THREE.ShaderLib.points.vertexShader, fragmentShader: THREE.ShaderLib.points.fragmentShader,
    } as THREE.WebGLProgramParametersWithUniforms;
    if (fixture.withBackdrop) {
      expect(backdrop).toBeDefined();
      (backdrop!.material as THREE.PointsMaterial).onBeforeCompile(backdropShader, renderer);
    }
    const positions = body.geometry.getAttribute('position');
    const p = new THREE.Vector3();
    const pixel = new THREE.Vector2();
    const assertBodyFits = (left: number, right: number, top: number, bottom: number) => {
      store.getState().scene.updateMatrixWorld(true); camera.updateMatrixWorld();
      const extents = new THREE.Box2();
      let allFinite = true, maxDepth = 0;
      for (let vertex = 0; vertex < positions.count; vertex++) {
        p.fromBufferAttribute(positions, vertex).applyMatrix4(body.matrixWorld).project(camera);
        allFinite &&= Number.isFinite(p.x + p.y + p.z);
        maxDepth = Math.max(maxDepth, Math.abs(p.z));
        extents.expandByPoint(pixel.set((p.x + 1) * width / 2, (1 - p.y) * height / 2));
      }
      // Keep every point in the check, but batch assertions rather than pay
      // ~400k assertion/temporary-object allocations per coverage case.
      expect(allFinite).toBe(true); expect(maxDepth).toBeLessThan(1);
      expect.soft(extents.min.x).toBeGreaterThanOrEqual(left);
      expect.soft(extents.max.x).toBeLessThanOrEqual(right);
      expect.soft(extents.min.y).toBeGreaterThanOrEqual(top);
      expect.soft(extents.max.y).toBeLessThanOrEqual(bottom);
      // Catch a zoomed-out thumbnail even when every protected point fits.
      // The actual crown/spine/roots must occupy the measured phone pane,
      // including side/rear orbit poses, without taking space from its reader.
      if (activePane?.[1] === 118) {
        expect.soft(extents.max.y - extents.min.y).toBeGreaterThanOrEqual((bottom - top) * 0.8);
      }
      if (backdrop) {
        backdrop.onBeforeRender(renderer, store.getState().scene, camera, backdrop.geometry,
          backdrop.material as THREE.PointsMaterial, null as unknown as Parameters<THREE.Points['onBeforeRender']>[5]);
        const quiet = backdropShader.uniforms.uCortexQuiet.value as THREE.Vector4;
        const actualHead = new THREE.Vector3(...getCortexAnchor()).applyMatrix4(body.matrixWorld).project(camera);
        expect(quiet.z).toBeGreaterThan(0); expect(quiet.w).toBeGreaterThan(0);
        expect(quiet.x).toBeCloseTo(actualHead.x * 0.5 + 0.5, 7);
        expect(quiet.y).toBeCloseTo(actualHead.y * 0.5 + 0.5, 7);
        expect(backdrop.geometry.getAttribute('position').count).toBe(900);
      }
    };
    for (const azimuth of [0, 0.7, 2.2, 4.5]) {
      controls.setAzimuthalAngle(azimuth);
      let angularError = Infinity;
      // Keep production damping enabled; settle the installed controls and
      // verify the actual pose instead of mistaking the requested angle for it.
      for (let tick = 0; tick < 256 && angularError > 1e-7; tick++) {
        controls.update();
        const difference = controls.getAzimuthalAngle() - azimuth;
        angularError = Math.abs(Math.atan2(Math.sin(difference), Math.cos(difference)));
      }
      expect(angularError).toBeLessThan(1e-7);
      if (activePane) assertBodyFits(paneBounds.left, paneBounds.right, paneBounds.top, paneBounds.bottom);
      else assertBodyFits(12, width - 12, 124 + noticeHeight + 12, chatTop - 12);
    }
    // A taller receipt and dock can change without changing canvas dimensions.
    noticeBounds = new DOMRect(24, 124, width - 48, noticeHeight + 20);
    chatBounds = new DOMRect(24, chatTop - 24, width - 48, 146);
    // Retained work owns the space below this independent pane rectangle.
    // A layout change must reframe the same body/camera, not the whole stage.
    if (activePane) paneBounds = new DOMRect(paneBounds.left + 12, paneBounds.top + 12, paneBounds.width - 24, paneBounds.height - 24);
    let notified = 0;
    for (const [callback, targets] of resizeCallbacks) {
      if (!targets.has(notice) || !targets.has(chat)) continue;
      const entries: ResizeObserverEntry[] = [marker, notice, chat].map(target => ({
        target, contentRect: target === marker ? paneBounds : target === notice ? noticeBounds : chatBounds,
        borderBoxSize: [], contentBoxSize: [], devicePixelContentBoxSize: [],
      }));
      callback(entries, {} as ResizeObserver);
      notified++;
    }
    expect(notified).toBeGreaterThan(0);
    act(() => advance(3.5, false, store.getState()));
    if (activePane) {
      expect(camera.view).toMatchObject({ fullWidth: paneBounds.width, fullHeight: paneBounds.height,
        offsetX: -paneBounds.left, offsetY: -paneBounds.top });
      // Settle the production lens after changing the actual pane aspect.
      for (let tick = 1; tick <= 180; tick++) act(() => advance(3.5 + tick / 60, false, store.getState()));
      assertBodyFits(paneBounds.left, paneBounds.right, paneBounds.top, paneBounds.bottom);
    } else {
      expect(camera.view).toMatchObject({ fullWidth: width - 48,
        fullHeight: chatTop - 24 - (124 + noticeHeight + 20) - 24, offsetX: -24,
        offsetY: -(124 + noticeHeight + 32) });
      assertBodyFits(24, width - 24, 124 + noticeHeight + 32, chatTop - 36);
    }
    expect(store.getState().internal.priority).toBe(0); // not a second render owner
    // Viewport adaptation must not install another camera or controls owner.
    host.dataset.beingFocus = 'false'; window.dispatchEvent(new Event('resize'));
    act(() => advance(7, false, store.getState()));
    expect(store.getState().camera).toBe(camera); expect(store.getState().controls).toBe(controls);
    expect(body.parent).not.toBeNull();
    const restingView = camera.view;
    expect(restingView).toMatchObject(activePane ? { fullWidth: paneBounds.width, fullHeight: paneBounds.height,
      offsetX: -paneBounds.left, offsetY: -paneBounds.top } : { fullWidth: width, fullHeight: height, offsetX: 0, offsetY: 0 });
    await act(async () => { root.render(null); });
    expect(camera.view?.enabled).toBe(false);
    expect(resizeCallbacks.size).toBe(0);
  } finally { await act(async () => { root.unmount(); }); host.remove(); }
});

it.each([false, true].flatMap(reduced => [false, true].map(focus => ({ reduced, focus }))))(
  'fits the same moving anatomy in the short-landscape work-side pane; reduced=$reduced Focus=$focus',
  async ({ reduced, focus }) => {
    vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: reduced }));
    localStorage.removeItem('gagos-pause-motion-v1');
    const tab = showContentSurface({ filepath: 'fixture/hello.py', language: 'python', code: 'print("hello")' }, { seatIndex: 2 });
    setMaterializedTabLifecycle(tab.id, 'live');
    const host = document.createElement('div'); host.className = 'lm-app';
    host.dataset.working = 'true'; host.dataset.beingFocus = String(focus);
    const pane = document.createElement('div'); pane.className = 'lm-scene';
    const header = document.createElement('header'); header.className = 'lm-header';
    const canvas = document.createElement('canvas'); host.append(pane, header, canvas); document.body.append(host);
    // Independent short-layout fixture dimensions:32% width, Stop below8..52,
    // presence64..378. Never derive expected pixels from the fitting helper.
    vi.spyOn(pane, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 64, 270.08, 314));
    vi.spyOn(header, 'getBoundingClientRect').mockReturnValue(new DOMRect(28, 8, 788, 44));
    vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 844, 390));
    const root = createRoot(canvas), store = _roots.get(canvas)!.store;
    const gl = { domElement: canvas, render() {}, setSize() {}, setPixelRatio() {}, getPixelRatio: () => 1 } as unknown as RootState['gl'];
    await root.configure({ gl, scene: new THREE.Scene(), camera: new THREE.PerspectiveCamera(),
      frameloop: 'never', size: { width: 844, height: 390, top: 0, left: 0 } });
    try {
      await act(async () => { root.render(<CortexEngine mode="observe" activity={0} tier="low" physical={{
        phase: 'resting', taskState: 'done-unverified', coherence: 'coherent', motion: 'breathe',
        cortex: { posture: 'unverified' }, verification: { state: 'unverified' }, membrane: { state: 'clear' },
      }} />); });
      const camera = store.getState().camera as THREE.PerspectiveCamera;
      const controls = store.getState().controls;
      let body!: THREE.Points;
      store.getState().scene.traverse(object => { if (object instanceof THREE.Points) body = object; });
      const geometry = body.geometry, positions = geometry.getAttribute('position');
      const p = new THREE.Vector3(), box = new THREE.Box2(), pixel = new THREE.Vector2();
      for (let tick = 1; tick <= 360; tick++) {
        act(() => advance(tick / 60, false, store.getState()));
        if (tick < 180 || tick % 90 !== 0) continue;
        store.getState().scene.updateMatrixWorld(true); camera.updateMatrixWorld(); box.makeEmpty();
        let finite = true, depth = 0;
        for (let vertex = 0; vertex < positions.count; vertex++) {
          p.fromBufferAttribute(positions, vertex).applyMatrix4(body.matrixWorld).project(camera);
          finite &&= Number.isFinite(p.x + p.y + p.z); depth = Math.max(depth, Math.abs(p.z));
          box.expandByPoint(pixel.set((p.x + 1) * 422, (1 - p.y) * 195));
        }
        expect(finite).toBe(true); expect(depth).toBeLessThan(1);
        expect.soft(box.min.x).toBeGreaterThanOrEqual(0); expect.soft(box.max.x).toBeLessThanOrEqual(270.08);
        expect.soft(box.min.y).toBeGreaterThanOrEqual(64); expect.soft(box.max.y).toBeLessThanOrEqual(378);
      }
      expect(positions.count).toBe(51000); expect(body.geometry).toBe(geometry);
      expect(camera.view).toMatchObject({ fullWidth: 270.08, fullHeight: 314, offsetX: 0, offsetY: -64 });
      expect(store.getState().camera).toBe(camera); expect(store.getState().controls).toBe(controls);
      expect(getTabStoreSnapshot().focusId).toBe(tab.id);
      expect(getTabStoreSnapshot().tabs.find(candidate => candidate.id === tab.id)?.content?.code).toBe('print("hello")');
    } finally { await act(async () => { root.unmount(); }); host.remove(); }
  },
);

// Native ordinary447px rest: the authored scene marker ends behind the
// conversation. The same fused body must fit the real control-free space,
// without requiring Focus or changing the body/camera/control owners.
it.each([false, true].flatMap(reduced => [false, true].flatMap(expert =>
  [0, 1, 3, 12].map(workCount => ({ reduced, expert, workCount }))))) (
  'keeps full narrow resting anatomy above conversation despite retained work; reduced=$reduced expert=$expert work=$workCount', async ({ reduced, expert, workCount }) => {
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: reduced }));
  localStorage.removeItem('gagos-pause-motion-v1');
  fixture.withWorkspaces = workCount > 0;
  for (let seat = 0; seat < workCount; seat++) {
    const tab = showContentSurface({ filepath: `rest-retained-${seat}.txt`, language: 'text', code: `saved work ${seat}` }, { seatIndex: seat });
    setMaterializedTabLifecycle(tab.id, 'live');
  }
  focusWorkspace(null); // the operator returned to the intake; results stay open
  const width = 447, height = 605.40625;
  const host = document.createElement('div'); host.className = 'lm-app';
  host.dataset.working = 'false'; host.dataset.beingFocus = 'false';
  host.style.setProperty('--lm-narrow-rest-presence', '1');
  const pane = document.createElement('div'); pane.className = 'lm-scene';
  const header = document.createElement('header'); header.className = 'lm-header';
  const mode = document.createElement('div'); mode.className = 'gagos-experience-mode';
  const navigation = document.createElement('nav'); navigation.className = 'lm-navigation';
  const chat = document.createElement('div'); chat.className = 'gagos-chat';
  const notice = document.createElement('div'); notice.className = 'lm-connection';
  const canvas = document.createElement('canvas'); host.append(pane, header, mode, navigation, chat, notice, canvas); document.body.append(host);
  vi.spyOn(pane, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 110, width, 222.984375));
  vi.spyOn(header, 'getBoundingClientRect').mockReturnValue(new DOMRect(16, 62, 415, 44));
  vi.spyOn(mode, 'getBoundingClientRect').mockReturnValue(new DOMRect(108.515625, 10, 165.96875, 62));
  vi.spyOn(navigation, 'getBoundingClientRect').mockReturnValue(expert ? new DOMRect(16, 122, 415, 44) : new DOMRect());
  const bodyTop = expert ? 178 : 122;
  let chatBounds = expert ? new DOMRect(16, 275.40625, 415, 240) : new DOMRect(16, 278.40625, 415, 195);
  const chatRead = vi.spyOn(chat, 'getBoundingClientRect').mockImplementation(() => chatBounds);
  vi.spyOn(notice, 'getBoundingClientRect').mockReturnValue(new DOMRect(16, 522.65625, 415, 74.75));
  vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, width, height));
  const observers = new Map<ResizeObserverCallback, Set<Element>>();
  vi.stubGlobal('ResizeObserver', class {
    private targets = new Set<Element>();
    constructor(private callback: ResizeObserverCallback) { observers.set(callback, this.targets); }
    observe(target: Element) { this.targets.add(target); }
    unobserve(target: Element) { this.targets.delete(target); }
    disconnect() { observers.delete(this.callback); }
  });
  const root = createRoot(canvas), store = _roots.get(canvas)!.store;
  const gl = { domElement: canvas, render() {}, setSize() {}, setPixelRatio() {}, getPixelRatio: () => 1 } as unknown as RootState['gl'];
  await root.configure({ gl, scene: new THREE.Scene(), camera: new THREE.PerspectiveCamera(),
    frameloop: 'never', size: { width, height, top: 0, left: 0 } });
  try {
    await act(async () => { root.render(<CortexEngine mode="observe" activity={0} tier="low" physical={{
      phase: 'resting', taskState: 'idle', coherence: 'fresh', motion: 'calm',
      cortex: { posture: 'rest' }, verification: { state: 'none' }, membrane: { state: 'clear' },
    }} />); });
    const camera = store.getState().camera as THREE.PerspectiveCamera;
    const controls = store.getState().controls as unknown as OrbitControls;
    let body!: THREE.Points;
    store.getState().scene.traverse(object => { if (object instanceof THREE.Points && object.geometry.getAttribute('aBand')) body = object; });
    const geometry = body.geometry, positions = geometry.getAttribute('position');
    const point = new THREE.Vector3(), pixel = new THREE.Vector2(), box = new THREE.Box2();
    const projectionView = new THREE.Matrix4(), projectionWorld = new THREE.Matrix4();
    let time = 0;
    const frames = (count: number) => {
      for (let tick = 0; tick < count; tick++) { time += 1 / 60; act(() => advance(time, false, store.getState())); }
    };
    const assertBodyFits = () => {
      store.getState().scene.updateMatrixWorld(true); camera.updateMatrixWorld(); box.makeEmpty();
      projectionView.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
      const slabs: THREE.Box2[] = [];
      store.getState().scene.traverse(object => {
        if (!(object instanceof THREE.Mesh) || object.geometry.type !== 'ExtrudeGeometry') return;
        for (let owner: THREE.Object3D | null = object; owner; owner = owner.parent) if (!owner.visible) return;
        const slab = new THREE.Box2(), vertices = object.geometry.getAttribute('position');
        projectionWorld.multiplyMatrices(projectionView, object.matrixWorld);
        for (let vertex = 0; vertex < vertices.count; vertex++) {
          point.fromBufferAttribute(vertices, vertex).applyMatrix4(projectionWorld);
          slab.expandByPoint(pixel.set((point.x + 1) * width / 2, (1 - point.y) * height / 2));
        }
        slabs.push(slab);
      });
      expect(slabs).toHaveLength(workCount);
      // The same exact Three projection, composed once rather than three
      // matrix applications per vertex. Keep every painted vertex and bound.
      projectionWorld.multiplyMatrices(projectionView, body.matrixWorld);
      let coveredAnatomy = 0;
      let finite = true, depth = 0;
      for (let vertex = 0; vertex < positions.count; vertex++) {
        point.fromBufferAttribute(positions, vertex).applyMatrix4(projectionWorld);
        finite &&= Number.isFinite(point.x + point.y + point.z); depth = Math.max(depth, Math.abs(point.z));
        box.expandByPoint(pixel.set((point.x + 1) * width / 2, (1 - point.y) * height / 2));
        for (const slab of slabs) {
          if (!slab.containsPoint(pixel)) continue;
          coveredAnatomy++; break;
        }
      }
      expect.soft(coveredAnatomy).toBe(0); // full protected brain AND fused cord/roots, not only cortex
      for (let index = 0; index < slabs.length; index++) {
        const slab = slabs[index];
        expect.soft(slab.min.x).toBeGreaterThanOrEqual(16); expect.soft(slab.max.x).toBeLessThanOrEqual(431);
        expect.soft(slab.min.y).toBeGreaterThanOrEqual(bodyTop); expect.soft(slab.max.y).toBeLessThanOrEqual(chatBounds.top - 12);
        for (const other of slabs.slice(index + 1)) expect.soft(slab.intersectsBox(other)).toBe(false);
      }
      expect(finite).toBe(true); expect(depth).toBeLessThan(1);
      expect.soft(box.min.x).toBeGreaterThanOrEqual(16); expect.soft(box.max.x).toBeLessThanOrEqual(431);
      expect.soft(box.min.y).toBeGreaterThanOrEqual(bodyTop); expect.soft(box.max.y).toBeLessThanOrEqual(chatBounds.top - 12);
    };
    frames(360); assertBodyFits();
    // This is already an anatomy-only camera window. Retained cards must not
    // apply the standalone canvas's second shrink/crown lift inside it.
    expect.soft(body.parent!.scale.x).toBeCloseTo(1, 5);
    expect.soft(camera.fov).toBeCloseTo(24, 1);
    const measuredReads = chatRead.mock.calls.length;
    // Resting voyage is tested above/below; pause only auto-rotation while
    // reaching explicit side/rear angles, keeping installed damping enabled.
    const autoRotate = controls.autoRotate; controls.autoRotate = false;
    for (const azimuth of [0, 0.7, 2.2, 4.5]) {
      controls.setAzimuthalAngle(azimuth);
      let angularError = Infinity;
      for (let tick = 0; tick < 256 && angularError > 1e-7; tick++) {
        controls.update(); const difference = controls.getAzimuthalAngle() - azimuth;
        angularError = Math.abs(Math.atan2(Math.sin(difference), Math.cos(difference)));
      }
      expect(angularError).toBeLessThan(1e-7);
      // HUD positions are installed by the real frame loop after orbit moves.
      frames(1); assertBodyFits();
    }
    controls.autoRotate = autoRotate;
    expect(chatRead.mock.calls).toHaveLength(measuredReads); // no layout reads in animation frames
    expect(camera.view).toMatchObject({ fullWidth: 415, fullHeight: chatBounds.top - bodyTop - 16, offsetX: -16, offsetY: -bodyTop });
    chatBounds = new DOMRect(16, 254.40625, 415, 219);
    let notified = 0;
    for (const [callback, targets] of observers) {
      if (!targets.has(chat)) continue;
      callback([{ target: chat, contentRect: chatBounds, borderBoxSize: [], contentBoxSize: [], devicePixelContentBoxSize: [] }], {} as ResizeObserver);
      notified++;
    }
    expect(notified).toBeGreaterThan(0); frames(360); assertBodyFits();
    expect(camera.view).toMatchObject({ fullWidth: 415, fullHeight: chatBounds.top - bodyTop - 16, offsetX: -16, offsetY: -bodyTop });
    expect([...observers.values()].some(targets => targets.has(navigation))).toBe(true);
    // A real renderer resize re-renders the adapter. An exhausted control-free
    // region must not run cleanup and throw away its last valid projection.
    const lastView = { ...camera.view! }, lastChatBounds = chatBounds;
    chatBounds = new DOMRect(16, bodyTop - 12, 415, 300);
    await act(async () => { await root.configure({ frameloop: 'never',
      size: { width, height: height - 48, top: 0, left: 0 } }); });
    expect(store.getState().frameloop).toBe('never');
    for (const [callback, targets] of observers) {
      if (!targets.has(chat)) continue;
      callback([{ target: chat, contentRect: chatBounds, borderBoxSize: [], contentBoxSize: [], devicePixelContentBoxSize: [] }], {} as ResizeObserver);
    }
    frames(12); expect(camera.view).toMatchObject(lastView);
    chatBounds = lastChatBounds;
    await act(async () => { await root.configure({ frameloop: 'never', size: { width, height, top: 0, left: 0 } }); });
    for (const [callback, targets] of observers) {
      if (!targets.has(chat)) continue;
      callback([{ target: chat, contentRect: chatBounds, borderBoxSize: [], contentBoxSize: [], devicePixelContentBoxSize: [] }], {} as ResizeObserver);
    }
    frames(360); assertBodyFits();
    expect(positions.count).toBe(51000); expect(body.geometry).toBe(geometry);
    expect(store.getState().camera).toBe(camera); expect(store.getState().controls).toBe(controls);
    expect(store.getState().internal.priority).toBe(0); expect(getTabStoreSnapshot().tabs).toHaveLength(workCount);
    let waiting = 0;
    store.getState().scene.traverse(object => {
      if (object instanceof THREE.Mesh && object.geometry.type === 'ExtrudeGeometry') {
        let visible = true;
        for (let owner: THREE.Object3D | null = object; owner; owner = owner.parent) visible &&= owner.visible;
        if (visible) waiting++;
      }
    });
    expect(waiting).toBe(workCount); // do not gain presence by discarding work
    await act(async () => { root.render(null); });
    expect(camera.view?.enabled).toBe(false);
  } finally { await act(async () => { root.unmount(); }); host.remove(); }
  expect(observers.size).toBe(0);
});

// Native1280x900 Conversation: waiting slabs overlap one another and the
// fused roots because a head-only, per-card correction shares no row budget.
// Exercise the same engine/layer and every painted vertex, not solver bounds.
it.each([false, true].flatMap(reduced => [false, true].flatMap(expert =>
  [false, true].flatMap(focus => [0, 1, 3, 12].map(workCount => ({ reduced, expert, focus, workCount })))))) (
  'keeps desktop resting work separate from full anatomy and other work; reduced=$reduced expert=$expert Focus=$focus work=$workCount', async ({ reduced, expert, focus, workCount }) => {
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: reduced }));
  localStorage.removeItem('gagos-pause-motion-v1');
  fixture.withWorkspaces = workCount > 0;
  const tabs = Array.from({ length: workCount }, (_, seat) => {
    const tab = showContentSurface({ filepath: `desktop-rest-${seat}.txt`, language: 'text', code: `saved desktop work ${seat}` }, { seatIndex: seat });
    setMaterializedTabLifecycle(tab.id, 'live'); return tab;
  });
  focusWorkspace(null);
  const host = document.createElement('div'); host.className = 'lm-app';
  host.dataset.working = 'false'; host.dataset.beingFocus = String(focus);
  host.dataset.experienceMode = expert ? 'expert' : 'beginner';
  const pane = document.createElement('div'); pane.className = 'lm-scene';
  const header = document.createElement('header'); header.className = 'lm-header';
  const mode = document.createElement('div'); mode.className = 'gagos-experience-mode';
  const chat = document.createElement('div'); chat.className = 'gagos-chat';
  const canvas = document.createElement('canvas'); host.append(pane, header, mode, chat, canvas); document.body.append(host);
  // Native1280x900 Focus is full-width. Expert retains its144px header
  // band; Guided's marker still covers the stage and its live control rows.
  // Retained results must not shrink the same being in either mode.
  const stage = new DOMRect(0, 61, 1280, 839), anatomyPane = focus
    ? (expert ? new DOMRect(0, 205, 1280, 695) : stage) : new DOMRect(448, 61, 832, 839);
  const clearTop = focus ? (expert ? 217 : 211) : 137;
  vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue(stage);
  vi.spyOn(pane, 'getBoundingClientRect').mockReturnValue(anatomyPane);
  vi.spyOn(header, 'getBoundingClientRect').mockReturnValue(new DOMRect(28, 81, 1224, focus && expert ? 60.796875 : 44));
  vi.spyOn(mode, 'getBoundingClientRect').mockReturnValue(focus && expert
    ? new DOMRect(411.78125, 79, 378.15625, 62) : new DOMRect(28, 137, 369.578125, 62));
  vi.spyOn(chat, 'getBoundingClientRect').mockReturnValue(focus
    ? new DOMRect(832, 719.859375, 420, 162.140625) : new DOMRect(28, 217, 390, 453));
  // These are independently observed painted controls, not fit-owner bounds.
  // Guided's wrapped status is taller; waiting work must clear both versions
  // and the draft composer without being hidden or shrinking the anatomy.
  const paintedControls: THREE.Box2[] = [];
  if (focus) {
    const status = document.createElement('div'); status.className = 'gagos-status';
    const notice = document.createElement('div'); notice.className = 'lm-connection';
    host.append(status, notice);
    vi.spyOn(status, 'getBoundingClientRect').mockReturnValue(expert
      ? new DOMRect(28, 678, 273.484375, 44) : new DOMRect(28, 640.40625, 369.59375, 81.59375));
    vi.spyOn(notice, 'getBoundingClientRect').mockReturnValue(expert
      ? new DOMRect(28, 173, 360, 75.328125) : new DOMRect(28, 173, 360, 54.734375));
    for (const element of [chat, status, notice]) {
      const rect = element.getBoundingClientRect();
      paintedControls.push(new THREE.Box2(new THREE.Vector2(rect.left, rect.top), new THREE.Vector2(rect.right, rect.bottom)));
    }
  }
  const root = createRoot(canvas), store = _roots.get(canvas)!.store;
  const gl = { domElement: canvas, render() {}, setSize() {}, setPixelRatio() {}, getPixelRatio: () => 1 } as unknown as RootState['gl'];
  await root.configure({ gl, scene: new THREE.Scene(), camera: new THREE.PerspectiveCamera(),
    frameloop: 'never', size: { width: stage.width, height: stage.height, top: 0, left: 0 } });
  try {
    await act(async () => { root.render(<CortexEngine mode="observe" activity={0} tier="low" physical={{
      phase: 'resting', taskState: 'idle', coherence: 'fresh', motion: 'calm',
      cortex: { posture: 'rest' }, verification: { state: 'none' }, membrane: { state: 'clear' },
    }} />); });
    const camera = store.getState().camera as THREE.PerspectiveCamera;
    const controls = store.getState().controls as unknown as OrbitControls;
    const scene = store.getState().scene;
    let body!: THREE.Points;
    scene.traverse(object => { if (object instanceof THREE.Points && object.geometry.getAttribute('aBand')) body = object; });
    const geometry = body.geometry, positions = geometry.getAttribute('position');
    const point = new THREE.Vector3(), pixel = new THREE.Vector2();
    const projectionView = new THREE.Matrix4(), projectionWorld = new THREE.Matrix4();
    let time = 0;
    const frames = (count: number) => {
      for (let tick = 0; tick < count; tick++) { time += 1 / 60; act(() => advance(time, false, store.getState())); }
    };
    const checkClearance = () => {
      scene.updateMatrixWorld(true); camera.updateMatrixWorld();
      projectionView.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
      const slabs: THREE.Box2[] = [];
      scene.traverse(object => {
        if (!(object instanceof THREE.Mesh) || object.geometry.type !== 'ExtrudeGeometry') return;
        for (let owner: THREE.Object3D | null = object; owner; owner = owner.parent) if (!owner.visible) return;
        const slab = new THREE.Box2(), vertices = object.geometry.getAttribute('position');
        projectionWorld.multiplyMatrices(projectionView, object.matrixWorld);
        for (let vertex = 0; vertex < vertices.count; vertex++) {
          point.fromBufferAttribute(vertices, vertex).applyMatrix4(projectionWorld);
          expect(Number.isFinite(point.x + point.y + point.z)).toBe(true);
          expect(Math.abs(point.z)).toBeLessThan(1);
          slab.expandByPoint(pixel.set((point.x + 1) * stage.width / 2, stage.top + (1 - point.y) * stage.height / 2));
        }
        const size = slab.getSize(new THREE.Vector2());
        expect(size.x).toBeGreaterThan(0); expect(size.y).toBeGreaterThan(0);
        slabs.push(slab);
      });
      expect(slabs).toHaveLength(workCount);
      projectionWorld.multiplyMatrices(projectionView, body.matrixWorld);
      let covered = 0, controlCovered = 0;
      const anatomy = new THREE.Box2();
      let finite = true, depth = 0;
      for (let vertex = 0; vertex < positions.count; vertex++) {
        point.fromBufferAttribute(positions, vertex).applyMatrix4(projectionWorld);
        pixel.set((point.x + 1) * stage.width / 2, stage.top + (1 - point.y) * stage.height / 2);
        finite &&= Number.isFinite(point.x + point.y + point.z); depth = Math.max(depth, Math.abs(point.z));
        anatomy.expandByPoint(pixel);
        if (slabs.some(slab => slab.containsPoint(pixel))) covered++;
        if (paintedControls.some(control => control.containsPoint(pixel))) controlCovered++;
      }
      expect.soft(covered, JSON.stringify({ time, azimuth: controls.getAzimuthalAngle(), anatomy, slabs })).toBe(0);
      expect.soft(controlCovered, 'painted controls must not cover any anatomy vertex').toBe(0);
      expect(finite).toBe(true); expect(depth).toBeLessThan(1);
      expect.soft(anatomy.min.x).toBeGreaterThanOrEqual(anatomyPane.left + 12);
      expect.soft(anatomy.max.x).toBeLessThanOrEqual(anatomyPane.right - 12);
      expect.soft(anatomy.min.y).toBeGreaterThanOrEqual(clearTop);
      expect.soft(anatomy.max.y).toBeLessThanOrEqual(888);
      for (let index = 0; index < slabs.length; index++) {
        const slab = slabs[index];
        expect.soft(slab.min.x).toBeGreaterThanOrEqual(anatomyPane.left + 12);
        expect.soft(slab.max.x).toBeLessThanOrEqual(anatomyPane.right - 12);
        expect.soft(slab.min.y).toBeGreaterThanOrEqual(clearTop);
        expect.soft(slab.max.y).toBeLessThanOrEqual(anatomyPane.bottom - 12);
        for (const control of paintedControls) expect.soft(slab.intersectsBox(control), 'waiting work must clear painted controls').toBe(false);
        for (const other of slabs.slice(index + 1)) expect.soft(slab.intersectsBox(other)).toBe(false);
      }
    };
    frames(360); checkClearance();
    expect(body.parent!.scale.x).toBeCloseTo(1, 5);
    const autoRotate = controls.autoRotate; controls.autoRotate = false;
    for (const azimuth of [0, 0.7, 2.2, 4.5]) {
      controls.setAzimuthalAngle(azimuth);
      let angularError = Infinity;
      for (let tick = 0; tick < 256 && angularError > 1e-7; tick++) {
        controls.update(); const difference = controls.getAzimuthalAngle() - azimuth;
        angularError = Math.abs(Math.atan2(Math.sin(difference), Math.cos(difference)));
      }
      expect(angularError).toBeLessThan(1e-7); frames(1); checkClearance();
    }
    controls.autoRotate = autoRotate;
    expect(positions.count).toBe(51000); expect(body.geometry).toBe(geometry);
    expect(store.getState().camera).toBe(camera); expect(store.getState().controls).toBe(controls);
    expect(getTabStoreSnapshot().focusId).toBeNull();
    expect(getTabStoreSnapshot().tabs.map(tab => [tab.id, tab.content?.code])).toEqual(tabs.map(tab => [tab.id, tab.content?.code]));
  } finally { await act(async () => { root.unmount(); }); host.remove(); }
});

it.each([false, true])('remeasures desktop resting Focus controls without replacing owners; Expert=%s', async expert => {
  const tab = showContentSurface({ filepath: 'retained-focus.txt', language: 'text', code: 'keep the complete result' }, { seatIndex: 1 });
  setMaterializedTabLifecycle(tab.id, 'live'); focusWorkspace(null);
  const host = document.createElement('div'); host.className = 'lm-app';
  host.dataset.working = 'false'; host.dataset.beingFocus = 'true';
  const pane = document.createElement('div'); pane.className = 'lm-scene';
  const status = document.createElement('div'); status.className = 'gagos-status';
  const notice = document.createElement('div'); notice.className = 'lm-connection';
  const chat = document.createElement('div'); chat.className = 'gagos-chat';
  const canvas = document.createElement('canvas'); host.append(pane, status, notice, chat, canvas); document.body.append(host);
  const stage = new DOMRect(0, 61, 1280, 839);
  vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue(stage);
  vi.spyOn(pane, 'getBoundingClientRect').mockReturnValue(expert ? new DOMRect(0, 205, 1280, 695) : stage);
  let statusTop = expert ? 678 : 640.40625, noticeHeight = expert ? 75.328125 : 54.734375;
  const statusRead = vi.spyOn(status, 'getBoundingClientRect').mockImplementation(() => new DOMRect(28, statusTop, 369.59375, 722 - statusTop));
  vi.spyOn(notice, 'getBoundingClientRect').mockImplementation(() => new DOMRect(28, 173, 360, noticeHeight));
  vi.spyOn(chat, 'getBoundingClientRect').mockReturnValue(new DOMRect(832, 719.859375, 420, 162.140625));
  const observers = new Map<ResizeObserverCallback, Set<Element>>();
  vi.stubGlobal('ResizeObserver', class {
    private targets = new Set<Element>();
    constructor(callback: ResizeObserverCallback) { observers.set(callback, this.targets); }
    observe(target: Element) { this.targets.add(target); }
    unobserve(target: Element) { this.targets.delete(target); }
    disconnect() { for (const [callback, targets] of observers) if (targets === this.targets) observers.delete(callback); }
  });
  const root = createRoot(canvas), store = _roots.get(canvas)!.store;
  const camera = new THREE.PerspectiveCamera(), fitRef = { current: false }, workPaneRef = { current: false };
  const gl = { domElement: canvas, render() {}, setSize() {}, setPixelRatio() {} } as unknown as RootState['gl'];
  await root.configure({ gl, scene: new THREE.Scene(), camera, frameloop: 'never', size: { width: 1280, height: 839, top: 0, left: 0 } });
  const notify = (element: Element) => {
    let notified = 0;
    for (const [callback, targets] of observers) if (targets.has(element)) {
      callback([{ target: element, contentRect: element.getBoundingClientRect(), borderBoxSize: [], contentBoxSize: [], devicePixelContentBoxSize: [] }], {} as ResizeObserver); notified++;
    }
    expect(notified).toBeGreaterThan(0);
  };
  try {
    await act(async () => { root.render(<PresenceViewport phoneFocusRef={fitRef} workPaneRef={workPaneRef} />); });
    const assertClear = () => {
      const view = camera.view!;
      expect(view.enabled).toBe(true);
      const top = stage.top - view.offsetY, bottom = top + view.fullHeight;
      expect(top).toBeGreaterThanOrEqual(notice.getBoundingClientRect().bottom + 12);
      expect(bottom).toBeLessThanOrEqual(status.getBoundingClientRect().top - 12);
      expect(bottom).toBeLessThanOrEqual(chat.getBoundingClientRect().top - 12);
      expect(view.fullWidth).toBe(1280); expect(fitRef.current).toBe(true); expect(workPaneRef.current).toBe(true);
    };
    assertClear();
    const reads = statusRead.mock.calls.length;
    for (let tick = 1; tick <= 60; tick++) act(() => advance(tick / 60, false, store.getState()));
    expect(statusRead.mock.calls).toHaveLength(reads); // no per-frame DOM reads
    statusTop = 590;
    act(() => notify(status)); assertClear();
    noticeHeight = 132;
    act(() => notify(notice)); assertClear();
    const usable = { ...camera.view };
    // No drawable band: preserve the last valid camera while controls win.
    statusTop = 300;
    act(() => notify(status)); expect(camera.view).toEqual(usable);
    statusTop = 590;
    act(() => notify(status)); assertClear();
    expect(store.getState().camera).toBe(camera); expect(store.getState().internal.priority).toBe(0);
    expect(getTabStoreSnapshot().focusId).toBeNull();
    expect(getTabStoreSnapshot().tabs.map(result => [result.id, result.content?.code])).toEqual([[tab.id, 'keep the complete result']]);
    await act(async () => { root.render(null); });
    expect(observers.size).toBe(0); expect(camera.view?.enabled).toBe(false);
    expect(fitRef.current).toBe(false); expect(workPaneRef.current).toBe(false);
  } finally { await act(async () => { root.unmount(); }); host.remove(); }
});

// The CSS breakpoint is viewport-wide, while its renderer may lose10px to a
// native fixture scrollbar. The phone-Focus branch must not replace this
// existing right-side presence pane or leave a stale whole-stage projection.
it.each([false, true])('keeps short resting Focus anatomy in its CSS-owned pane at a758px canvas; reduced=%s', async reduced => {
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: reduced }));
  localStorage.removeItem('gagos-pause-motion-v1');
  const host = document.createElement('div'); host.className = 'lm-app';
  host.dataset.working = 'false'; host.dataset.beingFocus = 'true';
  host.style.setProperty('--lm-short-rest-presence', '1');
  const pane = document.createElement('div'); pane.className = 'lm-scene';
  const header = document.createElement('header'); header.className = 'lm-header';
  const chat = document.createElement('div'); chat.className = 'gagos-chat';
  const notice = document.createElement('div'); notice.className = 'lm-connection';
  const canvas = document.createElement('canvas'); host.append(pane, header, chat, notice, canvas); document.body.append(host);
  vi.spyOn(pane, 'getBoundingClientRect').mockReturnValue(new DOMRect(394.15625, 64, 351.84375, 284));
  vi.spyOn(header, 'getBoundingClientRect').mockReturnValue(new DOMRect(28, 8, 702, 44));
  vi.spyOn(chat, 'getBoundingClientRect').mockReturnValue(new DOMRect(28, 168, 350.15625, 56));
  vi.spyOn(notice, 'getBoundingClientRect').mockReturnValue(new DOMRect(28, 298, 350.15625, 54));
  vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 758, 360));
  const root = createRoot(canvas), store = _roots.get(canvas)!.store;
  const gl = { domElement: canvas, render() {}, setSize() {}, setPixelRatio() {}, getPixelRatio: () => 1 } as unknown as RootState['gl'];
  await root.configure({ gl, scene: new THREE.Scene(), camera: new THREE.PerspectiveCamera(),
    frameloop: 'never', size: { width: 758, height: 360, top: 0, left: 0 } });
  try {
    await act(async () => { root.render(<CortexEngine mode="observe" activity={0} tier="low" physical={{
      phase: 'resting', taskState: 'idle', coherence: 'fresh', motion: 'calm',
      cortex: { posture: 'rest' }, verification: { state: 'none' }, membrane: { state: 'clear' },
    }} />); });
    const camera = store.getState().camera as THREE.PerspectiveCamera;
    const controls = store.getState().controls;
    let body!: THREE.Points;
    store.getState().scene.traverse(object => { if (object instanceof THREE.Points) body = object; });
    const geometry = body.geometry, positions = geometry.getAttribute('position');
    const point = new THREE.Vector3(), box = new THREE.Box2(), pixel = new THREE.Vector2();
    for (let tick = 1; tick <= 360; tick++) {
      act(() => advance(tick / 60, false, store.getState()));
      if (tick < 180 || tick % 90 !== 0) continue;
      store.getState().scene.updateMatrixWorld(true); camera.updateMatrixWorld(); box.makeEmpty();
      let finite = true, depth = 0;
      for (let vertex = 0; vertex < positions.count; vertex++) {
        point.fromBufferAttribute(positions, vertex).applyMatrix4(body.matrixWorld).project(camera);
        finite &&= Number.isFinite(point.x + point.y + point.z); depth = Math.max(depth, Math.abs(point.z));
        box.expandByPoint(pixel.set((point.x + 1) * 379, (1 - point.y) * 180));
      }
      expect(finite).toBe(true); expect(depth).toBeLessThan(1);
      expect.soft(box.min.x).toBeGreaterThanOrEqual(394.15625); expect.soft(box.max.x).toBeLessThanOrEqual(746);
      expect.soft(box.min.y).toBeGreaterThanOrEqual(64); expect.soft(box.max.y).toBeLessThanOrEqual(348);
    }
    expect(positions.count).toBe(51000); expect(body.geometry).toBe(geometry);
    expect(camera.view).toMatchObject({ fullWidth: 351.84375, fullHeight: 284, offsetX: -394.15625, offsetY: -64 });
    expect(store.getState().camera).toBe(camera); expect(store.getState().controls).toBe(controls);
    host.dataset.beingFocus = 'false'; window.dispatchEvent(new Event('resize'));
    act(() => advance(7, false, store.getState()));
    expect(camera.view).toMatchObject({ fullWidth: 351.84375, fullHeight: 284, offsetX: -394.15625, offsetY: -64 });
    expect(getTabStoreSnapshot().tabs).toHaveLength(0);
  } finally { await act(async () => { root.unmount(); }); host.remove(); }
});

it.each([false, true])('keeps ordinary active desktop anatomy below measured controls; reduced motion=%s', async reduced => {
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: reduced }));
  localStorage.removeItem('gagos-pause-motion-v1');
  const tab = showContentSurface({ filepath: 'fixture/hello.py', language: 'python', code: 'print("hello")' }, { seatIndex: 2 });
  setMaterializedTabLifecycle(tab.id, 'live');
  // Native1440x900 fixture: app starts60.8px down; these rectangles are
  // relative to its839.2px full-stage canvas, not a guessed viewport cap.
  const host = document.createElement('div'); host.className = 'lm-app';
  host.dataset.working = 'true'; host.dataset.beingFocus = 'false';
  const pane = document.createElement('div'); pane.className = 'lm-scene';
  const header = document.createElement('header'); header.className = 'lm-header';
  const mode = document.createElement('div'); mode.className = 'gagos-experience-mode';
  const canvas = document.createElement('canvas');
  host.append(pane, header, mode, canvas); document.body.append(host);
  vi.spyOn(pane, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 460.8, 839.2));
  vi.spyOn(header, 'getBoundingClientRect').mockReturnValue(new DOMRect(28, 20, 1384, 44));
  let modeHeight = 61.2;
  const modeRead = vi.spyOn(mode, 'getBoundingClientRect').mockImplementation(() => new DOMRect(28, 76, 368.7625, modeHeight));
  vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 1440, 839.2));
  const observers = new Map<ResizeObserverCallback, Set<Element>>();
  vi.stubGlobal('ResizeObserver', class {
    private targets = new Set<Element>();
    constructor(callback: ResizeObserverCallback) { observers.set(callback, this.targets); }
    observe(target: Element) { this.targets.add(target); }
    unobserve(target: Element) { this.targets.delete(target); }
    disconnect() { for (const [callback, targets] of observers) if (targets === this.targets) observers.delete(callback); }
  });
  const root = createRoot(canvas), store = _roots.get(canvas)!.store;
  const gl = { domElement: canvas, render() {}, setSize() {}, setPixelRatio() {}, getPixelRatio: () => 1 } as unknown as RootState['gl'];
  await root.configure({ gl, scene: new THREE.Scene(), camera: new THREE.PerspectiveCamera(),
    frameloop: 'never', size: { width: 1440, height: 839.2, top: 0, left: 0 } });
  try {
    await act(async () => { root.render(<CortexEngine mode="observe" activity={0} tier="low" physical={{
      phase: 'resting', taskState: 'done-unverified', coherence: 'coherent', motion: 'breathe',
      cortex: { posture: 'unverified' }, verification: { state: 'unverified' }, membrane: { state: 'clear' },
    }} />); });
    for (let tick = 1; tick <= 180; tick++) act(() => advance(tick / 60, false, store.getState()));
    const camera = store.getState().camera as THREE.PerspectiveCamera;
    const controls = store.getState().controls as unknown as OrbitControls;
    let body!: THREE.Points;
    store.getState().scene.traverse(object => { if (object instanceof THREE.Points) body = object; });
    const geometry = body.geometry, positions = geometry.getAttribute('position');
    const firstAngle = controls.getAzimuthalAngle();
    const point = new THREE.Vector3();
    const bounds = new THREE.Box2(), pixel = new THREE.Vector2();
    const assertFits = (top: number) => {
      store.getState().scene.updateMatrixWorld(true); camera.updateMatrixWorld(); bounds.makeEmpty();
      let finite = true, depth = 0;
      for (let vertex = 0; vertex < positions.count; vertex++) {
        point.fromBufferAttribute(positions, vertex).applyMatrix4(body.matrixWorld).project(camera);
        finite &&= Number.isFinite(point.x + point.y + point.z); depth = Math.max(depth, Math.abs(point.z));
        bounds.expandByPoint(pixel.set((point.x + 1) * 720, (1 - point.y) * 419.6));
      }
      expect(finite).toBe(true); expect(depth).toBeLessThan(1);
      expect.soft(bounds.min.x).toBeGreaterThanOrEqual(0);
      expect.soft(bounds.max.x).toBeLessThanOrEqual(460.8);
      expect.soft(bounds.min.y).toBeGreaterThanOrEqual(top);
      expect.soft(bounds.max.y).toBeLessThanOrEqual(839.2);
    };
    expect.soft(camera.view).toMatchObject({ fullWidth: 460.8, fullHeight: 690, offsetX: 0, offsetY: -149.2 });
    const layoutReads = modeRead.mock.calls.length;
    for (let tick = 181; tick <= 540; tick++) {
      act(() => advance(tick / 60, false, store.getState()));
      if (tick % 120 === 0) assertFits(149.2);
    }
    expect(modeRead.mock.calls).toHaveLength(layoutReads); // observer-owned, not per-frame layout reads
    expect(controls.getAzimuthalAngle()).toBeCloseTo(firstAngle, 10);
    expect(controls.autoRotate).toBe(false);
    expect(controls.enabled).toBe(true);
    // Wrapped/enlarged controls retarget this same camera without moving work.
    modeHeight = 131.2;
    let notified = 0;
    for (const [callback, targets] of observers) if (targets.has(mode)) {
      callback([{ target: mode, contentRect: new DOMRect(28, 76, 368.7625, modeHeight),
        borderBoxSize: [], contentBoxSize: [], devicePixelContentBoxSize: [] }], {} as ResizeObserver); notified++;
    }
    expect(notified).toBeGreaterThan(0);
    for (let tick = 541; tick <= 720; tick++) act(() => advance(tick / 60, false, store.getState()));
    expect.soft(camera.view).toMatchObject({ fullWidth: 460.8, fullHeight: 620, offsetX: 0, offsetY: -219.2 });
    assertFits(219.2);
    // Selected reading steadies idle motion, not explicit scene inspection.
    // Preserve the ordinary desktop's actual protected-anatomy fit through
    // achieved side/rear views, rather than depending on a small idle arc.
    for (const azimuth of [0, 0.7, 2.2, 4.5]) {
      controls.setAzimuthalAngle(azimuth);
      let angularError = Infinity;
      for (let tick = 0; tick < 256 && angularError > 1e-7; tick++) {
        controls.update();
        const difference = controls.getAzimuthalAngle() - azimuth;
        angularError = Math.abs(Math.atan2(Math.sin(difference), Math.cos(difference)));
      }
      expect(angularError).toBeLessThan(1e-7);
      act(() => advance(12 + (azimuth + 1) / 10, false, store.getState()));
      assertFits(219.2);
    }
    expect(modeRead.mock.calls).toHaveLength(layoutReads + 1); // only the explicit resize measurement
    expect(body.geometry).toBe(geometry); expect(positions.count).toBe(51000);
    expect(store.getState().camera).toBe(camera); expect(store.getState().controls).toBe(controls);
    expect(store.getState().internal.priority).toBe(0);
    host.dataset.working = 'false'; window.dispatchEvent(new Event('resize'));
    act(() => advance(13, false, store.getState()));
    // Returning to ordinary rest keeps the measured header/mode clearance;
    // it no longer restores the old full-height projection behind controls.
    expect(camera.view).toMatchObject({ fullWidth: 460.8, fullHeight: 620, offsetX: 0, offsetY: -219.2 });
    await act(async () => { root.render(null); });
    expect(camera.view?.enabled).toBe(false); expect(observers.size).toBe(0);
  } finally { await act(async () => { root.unmount(); }); host.remove(); }
});
