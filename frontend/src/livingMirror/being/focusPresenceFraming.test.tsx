import { act } from 'react';
import { _roots, advance, createRoot, extend, type RootState } from '@react-three/fiber';
import { GLTFLoader, type OrbitControls } from 'three-stdlib';
import * as THREE from 'three';
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest';
import CortexEngine from '../../superbrain/core/CortexEngine';
import PresenceViewport from '../../superbrain/components/canvas/PresenceViewport';
import { SCENE_UNIFORMS } from '../../superbrain/components/canvas/SuperbrainScene.LEGACY';
import { __resetTabStoreForTests, setMaterializedTabLifecycle, showContentSurface } from '../../superbrain/lib/tabStore';
import { __resetSpineFusionForTests, getCortexAnchor } from '../../superbrain/lib/spineFusionBus';

const fixture = vi.hoisted(() => ({ source: null as THREE.Group | null, withBackdrop: false }));
vi.mock('../../superbrain/lib/brainScene', () => ({ preloadBrainScene() {}, useBrainScene: () => fixture.source }));
// Real protected GLB, point sampling/fused spine, body transforms, Drei camera /
// OrbitControls and projection run. Only unrelated scene content and WebGL are
// replaced. This is CPU silhouette/layout proof, not shader or hardware proof.
vi.mock('../../superbrain/components/canvas/NodeLattice', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/MemoryHalo', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/MaterializationLayer', () => ({ default: () => null }));
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
  AmbientLight: THREE.AmbientLight, DirectionalLight: THREE.DirectionalLight, PointLight: THREE.PointLight });
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
  __resetTabStoreForTests(); __resetSpineFusionForTests();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    clearRect() {}, fillText() {},
  } as unknown as CanvasRenderingContext2D);
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: true }));
  SCENE_UNIFORMS.uTime.value = 0; SCENE_UNIFORMS.uBreath.value = 0.5;
  SCENE_UNIFORMS.uArrival.value = 0; SCENE_UNIFORMS.uAwaken.value = 0;
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); __resetTabStoreForTests(); __resetSpineFusionForTests(); });

it.each([
  { width: 768, height: 521, fitted: true },
  { width: 900, height: 720, fitted: true },
  { width: 1199, height: 720, fitted: true },
  { width: 900, height: 520, fitted: false },
  { width: 1280, height: 520, fitted: false },
  { width: 1280, height: 720, fitted: true },
  { width: 390, height: 844, fitted: true },
])('limits the active Focus fit to complete layout branches at $width × $height', async ({ width, height, fitted }) => {
  const host = document.createElement('div'); host.className = 'lm-app';
  host.dataset.beingFocus = 'true'; host.dataset.working = 'true';
  const marker = document.createElement('div'); marker.className = 'lm-scene';
  const canvas = document.createElement('canvas');
  host.append(marker, canvas); document.body.append(host);
  vi.spyOn(marker, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, width, height));
  vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, width, height));
  const root = createRoot(canvas);
  const fitRef = { current: false };
  const camera = new THREE.PerspectiveCamera();
  const renderer = { domElement: canvas, render() {}, setSize() {}, setPixelRatio() {} } as unknown as RootState['gl'];
  await root.configure({ gl: renderer, scene: new THREE.Scene(), camera,
    frameloop: 'never', size: { width, height, left: 0, top: 0 } });
  try {
    await act(async () => { root.render(<PresenceViewport phoneFocusRef={fitRef} />); });
    expect(fitRef.current).toBe(fitted);
    expect(camera.view).toMatchObject({ fullWidth: width, fullHeight: height, offsetX: 0, offsetY: 0 });
    await act(async () => { root.render(null); });
    expect(fitRef.current).toBe(false); expect(camera.view?.enabled).toBe(false);
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
    if (reduced) expect(controls.getAzimuthalAngle()).toBeCloseTo(firstAngle, 10);
    else expect(Math.abs(controls.getAzimuthalAngle() - firstAngle)).toBeGreaterThan(0.01);
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
    expect(body.geometry).toBe(geometry); expect(positions.count).toBe(51000);
    expect(store.getState().camera).toBe(camera); expect(store.getState().controls).toBe(controls);
    expect(store.getState().internal.priority).toBe(0);
    host.dataset.working = 'false'; window.dispatchEvent(new Event('resize'));
    act(() => advance(13, false, store.getState()));
    expect(camera.view).toMatchObject({ fullWidth: 460.8, fullHeight: 839.2, offsetX: 0, offsetY: 0 });
    await act(async () => { root.render(null); });
    expect(camera.view?.enabled).toBe(false); expect(observers.size).toBe(0);
  } finally { await act(async () => { root.unmount(); }); host.remove(); }
});
