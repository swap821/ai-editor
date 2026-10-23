import { act } from 'react';
import { _roots, advance, createRoot, extend, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { PerspectiveCamera, Vector3 } from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import PresenceViewport from '../../superbrain/components/canvas/PresenceViewport';
import CosmicBackground from '../../superbrain/components/canvas/CosmicBackground';
import { OrganismFraming } from '../../superbrain/components/canvas/SuperbrainScene.LEGACY';
import { setAmbientMotionPaused } from '../../superbrain/lib/reducedMotion';

// Framing needs no anatomy. Replace only the legacy module's unrelated asset
// preload; the installed camera/framing/sky implementations remain real.
vi.mock('../../superbrain/lib/brainScene', () => ({ preloadBrainScene() {}, useBrainScene: () => null }));

extend({ Group: THREE.Group, Points: THREE.Points, PointsMaterial: THREE.PointsMaterial });

beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: false }));
  localStorage.removeItem('gagos-pause-motion-v1');
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ clearRect() {}, fillText() {} } as unknown as CanvasRenderingContext2D);
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); localStorage.removeItem('gagos-pause-motion-v1'); });

async function withPresence(run: (subject: {
  camera: PerspectiveCamera;
  focus: HTMLTextAreaElement;
  work: (working: boolean) => Promise<void>;
  paint: (milliseconds: number) => void;
  resize: () => Promise<void>;
  field: THREE.Points | undefined;
  renderer: RootState['gl'];
  scene: THREE.Scene;
  controls: { target: THREE.Vector3; enabled?: boolean };
}) => Promise<void>, backdrop = false, framing = false) {
  const host = document.createElement('div'); host.className = 'lm-app'; host.dataset.working = 'false';
  const pane = document.createElement('div'); pane.className = 'lm-scene';
  const canvas = document.createElement('canvas');
  const focus = document.createElement('textarea'); host.append(pane, canvas, focus); document.body.append(host);
  let working = false, resized = false, now = 0;
  vi.spyOn(performance, 'now').mockImplementation(() => now);
  vi.spyOn(pane, 'getBoundingClientRect').mockImplementation(() => resized
    ? new DOMRect(0, 118, 390, 168)
    : working ? new DOMRect(0, 144, 409.6, 576) : new DOMRect(448, 144, 832, 576));
  vi.spyOn(canvas, 'getBoundingClientRect').mockImplementation(() => new DOMRect(0, 0, resized ? 390 : 1280, resized ? 568 : 720));
  const camera = new PerspectiveCamera(26, 1280 / 720, 0.1, 100);
  camera.position.z = 15; camera.updateMatrixWorld();
  const root = createRoot(canvas), store = _roots.get(canvas)!.store;
  const phoneFocusRef = { current: false }, workPaneRef = { current: false };
  const controlsRef: { current: { target: THREE.Vector3; enabled?: boolean } } = { current: { target: new THREE.Vector3(0, -0.5, 0) } };
  const gl = { domElement: canvas, render() {}, setSize() {}, setPixelRatio() {}, getPixelRatio: () => 1,
    getCurrentViewport: (target: THREE.Vector4) => target.set(0, 0, 1280, 720) } as unknown as RootState['gl'];
  await root.configure({ gl, camera, scene: undefined, frameloop: 'never', size: { width: 1280, height: 720, top: 0, left: 0 } });
  try {
    await act(async () => { root.render(<><PresenceViewport phoneFocusRef={phoneFocusRef} workPaneRef={workPaneRef} />
      {framing && <OrganismFraming controlsRef={controlsRef} phoneFocusRef={phoneFocusRef} workPaneRef={workPaneRef} />}
      {backdrop && <CosmicBackground tier="low" reducedMotion />}</>); });
    let field: THREE.Points | undefined;
    store.getState().scene.traverse(object => { if (object instanceof THREE.Points) field = object; });
    focus.focus(); focus.value = 'Keep typing now';
    await run({ camera, focus, field, renderer: gl, scene: store.getState().scene, controls: controlsRef.current,
      work: async next => { working = next; await act(async () => { host.dataset.working = String(next); }); },
      paint: milliseconds => { now = milliseconds; act(() => advance(milliseconds / 1000, false, store.getState())); },
      resize: async () => { resized = true; await act(async () => { window.dispatchEvent(new Event('resize')); }); },
    });
  } finally {
    await act(async () => { root.unmount(); });
    expect(camera.view?.enabled).toBe(false);
    expect(camera.aspect).toBeCloseTo(1280 / 720, 9);
    host.remove();
  }
}

const screenX = (camera: PerspectiveCamera) => (new Vector3(0, 0, 0).project(camera).x + 1) * 640;

it.each(['os', 'pause'] as const)('fits the actual lens and aim without zoom travel on a zero-delta reduced-motion paint (%s)', async preference => {
  if (preference === 'os') vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: true }));
  else setAmbientMotionPaused(true);
  await withPresence(async ({ camera, controls, work, paint, focus }) => {
    controls.enabled = false; // actual disabled-controls path must still aim
    paint(0); expect(camera.fov).toBe(24); expect(controls.target.y).toBe(-0.75);
    expect(camera.getWorldDirection(new Vector3()).distanceTo(new Vector3(0, -0.75, -15).normalize())).toBeLessThan(1e-10);
    await work(true); paint(0);
    expect(camera.fov).toBe(41.293); expect(controls.target.y).toBe(-0.75);
    const projection = camera.projectionMatrix.clone(), rotation = camera.quaternion.clone();
    paint(120); expect(camera.projectionMatrix.equals(projection)).toBe(true); expect(camera.quaternion.equals(rotation)).toBe(true);
    expect(document.activeElement).toBe(focus); expect(focus.value).toBe('Keep typing now');
    await work(false); paint(120); expect(camera.fov).toBe(24);
  }, false, true);
});

it('settles an in-flight lens on a live pause, then preserves ordinary damping for the next request', async () => {
  await withPresence(async ({ camera, controls, work, paint }) => {
    controls.enabled = false;
    await work(true); paint(90); expect(camera.fov).toBeLessThan(41.293); expect(camera.fov).toBeGreaterThan(26);
    await act(async () => { setAmbientMotionPaused(true); });
    paint(90); expect(camera.fov).toBe(41.293); expect(controls.target.y).toBe(-0.75);
    await act(async () => { setAmbientMotionPaused(false); });
    await work(false); paint(90 + 1000 / 60);
    expect(camera.fov).toBeCloseTo(24 + (41.293 - 24) * Math.exp(-3 / 60), 8);
  }, false, true);
});

it('moves the existing projection through intermediate positions instead of snapping on work open/Close', async () => {
  await withPresence(async ({ camera, focus, work, paint }) => {
    expect(screenX(camera)).toBeCloseTo(864, 5);
    await work(true);
    expect(screenX(camera)).toBeCloseTo(864, 5); // first frame remains the displayed body
    paint(130);
    expect(screenX(camera)).toBeGreaterThan(204.8);
    expect(screenX(camera)).toBeLessThan(864);
    expect(document.activeElement).toBe(focus); expect(focus.value).toBe('Keep typing now');
    paint(260); expect(screenX(camera)).toBeCloseTo(204.8, 5);
    await work(false); expect(screenX(camera)).toBeCloseTo(204.8, 5);
    paint(390); expect(screenX(camera)).toBeGreaterThan(204.8); expect(screenX(camera)).toBeLessThan(864);
    paint(520); expect(screenX(camera)).toBeCloseTo(864, 5);
  });
});

it('reverses from the displayed frame and does not queue or restart on duplicate layout notifications', async () => {
  await withPresence(async ({ camera, work, paint }) => {
    await work(true); paint(90);
    const interrupted = screenX(camera);
    expect(interrupted).toBeGreaterThan(204.8); expect(interrupted).toBeLessThan(864);
    await work(false); expect(screenX(camera)).toBeCloseTo(interrupted, 8);
    paint(150); expect(screenX(camera)).toBeGreaterThan(interrupted);
    await work(false); // redundant mutation must not restart the260ms window
    paint(350); expect(screenX(camera)).toBeCloseTo(864, 5);
    paint(900); expect(screenX(camera)).toBeCloseTo(864, 5);
  });
});

it('settles immediately when reduced motion is enabled during travel', async () => {
  await withPresence(async ({ camera, work, paint }) => {
    await work(true); paint(90);
    expect(screenX(camera)).toBeGreaterThan(204.8);
    await act(async () => { localStorage.setItem('gagos-pause-motion-v1', 'true'); window.dispatchEvent(new Event('gagos:motion-preference')); });
    expect(screenX(camera)).toBeCloseTo(204.8, 5);
    await work(false); expect(screenX(camera)).toBeCloseTo(864, 5);
  });
});

it('cancels travel for an immediate safe viewport/keyboard refit', async () => {
  await withPresence(async ({ camera, work, paint, resize, focus }) => {
    await work(true); paint(90); await resize();
    expect(camera.view).toMatchObject({ fullWidth: 390, fullHeight: 168, offsetX: 0, offsetY: -118, width: 390, height: 568 });
    const projection = camera.projectionMatrix.clone();
    paint(350); expect(camera.projectionMatrix.equals(projection)).toBe(true);
    expect(document.activeElement).toBe(focus);
  });
});

it('does not snap or restart travel for an unrelated bubbling color transition', async () => {
  await withPresence(async ({ camera, work, paint }) => {
    await work(true); paint(90); const current = screenX(camera);
    const unrelated = document.createElement('button'); document.body.append(unrelated);
    try {
      await act(async () => {
        const event = new Event('transitionend', { bubbles: true });
        Object.defineProperty(event, 'propertyName', { value: 'color' }); unrelated.dispatchEvent(event);
      });
      expect(screenX(camera)).toBeCloseTo(current, 8);
      paint(130); expect(screenX(camera)).toBeGreaterThan(204.8); expect(screenX(camera)).toBeLessThan(current);
      paint(260); expect(screenX(camera)).toBeCloseTo(204.8, 5);
    } finally { unrelated.remove(); }
  });
});

it('keeps actual framing on the destination-aspect lens path while the body projection travels', async () => {
  await withPresence(async ({ camera, work, paint, field, renderer, scene }) => {
    const material = field!.material as THREE.PointsMaterial;
    const shader = { uniforms: THREE.UniformsUtils.clone(THREE.ShaderLib.points.uniforms),
      vertexShader: THREE.ShaderLib.points.vertexShader, fragmentShader: THREE.ShaderLib.points.fragmentShader } as THREE.WebGLProgramParametersWithUniforms;
    material.onBeforeCompile(shader, renderer);
    await work(true);
    for (let tick = 1; tick <= 8; tick++) paint(tick * 1000 / 60);
    // Prior immediate destination aspect409.6/576 => literal41.293° target.
    // Framing's original3/s lens damping must not follow the animated aspect.
    const expectedFov = 41.293 + (26 - 41.293) * Math.exp(-3 * 8 / 60);
    expect(camera.fov).toBeCloseTo(expectedFov, 8);
    field!.onBeforeRender(renderer, scene, camera, field!.geometry, material,
      null as unknown as Parameters<THREE.Points['onBeforeRender']>[5]);
    const prior = camera.clone(); prior.fov = expectedFov; prior.setViewOffset(409.6, 576, 0, -144, 1280, 720);
    for (let index = 0; index < 16; index++) expect(shader.uniforms.uAmbientProjection.value.elements[index]).toBeCloseTo(prior.projectionMatrix.elements[index], 8);
  }, true, true);
});

it('keeps the real sky at the settled projection while only the body camera travels', async () => {
  await withPresence(async ({ camera, work, paint, field, renderer, scene }) => {
    const material = field!.material as THREE.PointsMaterial;
    const shader = { uniforms: THREE.UniformsUtils.clone(THREE.ShaderLib.points.uniforms),
      vertexShader: THREE.ShaderLib.points.vertexShader, fragmentShader: THREE.ShaderLib.points.fragmentShader } as THREE.WebGLProgramParametersWithUniforms;
    material.onBeforeCompile(shader, renderer);
    const geometry = field!.geometry;
    const colors = Array.from(geometry.getAttribute('color').array);
    await work(true); paint(90);
    camera.zoom = 1.25; camera.filmOffset = 0.5; camera.updateProjectionMatrix();
    const moving = camera.projectionMatrix.clone();
    field!.onBeforeRender(renderer, scene, camera, geometry, material,
      null as unknown as Parameters<THREE.Points['onBeforeRender']>[5]);
    // Independent Three camera computes the final literal working pane.
    const settled = camera.clone(); settled.setViewOffset(409.6, 576, 0, -144, 1280, 720);
    expect(shader.uniforms.uAmbientProjection?.value.elements).toEqual(settled.projectionMatrix.elements);
    expect(camera.projectionMatrix.equals(moving)).toBe(true); // no shared-camera draw mutation
    expect(shader.uniforms.uPresenceClip.value.toArray()).toEqual([0, 0, 0.32, 0.8]);
    expect(field!.geometry).toBe(geometry); expect(Array.from(geometry.getAttribute('color').array)).toEqual(colors);
  }, true);
});
