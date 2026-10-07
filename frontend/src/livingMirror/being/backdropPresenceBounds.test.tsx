import { act } from 'react';
import { _roots, advance, createRoot, extend, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import CosmicBackground from '../../superbrain/components/canvas/CosmicBackground';
import { __resetSpineFusionForTests, clearBodyGroupWorldMatrix, setBodyGroupWorldMatrix,
  setBrainDockScale, setCortexAnchor } from '../../superbrain/lib/spineFusionBus';

extend({ Group: THREE.Group, Points: THREE.Points, PointsMaterial: THREE.PointsMaterial });

beforeEach(() => {
  __resetSpineFusionForTests();
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  // Canvas2D atlas rasterization and WebGL are the only substitutes. The
  // mounted field, material compile callback and draw callback remain real.
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    clearRect() {}, fillText() {},
  } as unknown as CanvasRenderingContext2D);
});
afterEach(() => { __resetSpineFusionForTests(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

async function withField(run: (field: THREE.Points, camera: THREE.PerspectiveCamera,
  shader: THREE.WebGLProgramParametersWithUniforms, draw: (viewport: THREE.Vector4) => void,
  frame: () => void) => Promise<void> | void,
  setup?: (canvas: HTMLCanvasElement) => (() => void)) {
  const canvas = document.createElement('canvas');
  const cleanupDOM = setup?.(canvas);
  const root = createRoot(canvas);
  const store = _roots.get(canvas)!.store;
  const camera = new THREE.PerspectiveCamera(26, 320 / 568, 0.1, 200);
  let currentViewport = new THREE.Vector4(0, 0, 640, 1136);
  const renderer = { domElement: canvas, render() {}, setSize() {}, setPixelRatio() {}, getPixelRatio: () => 2,
    getCurrentViewport: (target: THREE.Vector4) => target.copy(currentViewport),
  } as unknown as RootState['gl'];
  await root.configure({ gl: renderer, scene: new THREE.Scene(), camera, frameloop: 'never',
    size: { width: 320, height: 568, top: 0, left: 0 } });
  try {
    await act(async () => { root.render(<CosmicBackground tier="low" reducedMotion />); });
    act(() => advance(1, false, store.getState()));
    let field!: THREE.Points;
    store.getState().scene.traverse(object => { if (object instanceof THREE.Points) field = object; });
    const material = field.material as THREE.PointsMaterial;
    const shader = { uniforms: THREE.UniformsUtils.clone(THREE.ShaderLib.points.uniforms),
      vertexShader: THREE.ShaderLib.points.vertexShader, fragmentShader: THREE.ShaderLib.points.fragmentShader,
    } as THREE.WebGLProgramParametersWithUniforms;
    material.onBeforeCompile(shader, renderer);
    const draw = (viewport: THREE.Vector4) => {
      currentViewport = viewport;
      // Three renders ungrouped points with a null group; its current d.ts
      // incorrectly requires an Object3D Group here. Preserve runtime shape.
      field.onBeforeRender(renderer, store.getState().scene, camera, field.geometry, material,
        null as unknown as Parameters<THREE.Points['onBeforeRender']>[5]);
    };
    let frameTime = 1;
    const frame = () => { act(() => advance(++frameTime, false, store.getState())); };
    await run(field, camera, shader, draw, frame);
  } finally { await act(async () => { root.unmount(); }); cleanupDOM?.(); }
}

it('scales product knowledge glyphs with the body pane instead of reusing the minimum punctum footprint', async () => {
  const host = document.createElement('div'); host.className = 'lm-app'; document.body.append(host);
  try {
    await withField((field, camera, shader, _draw, frame) => {
      const geometry = field.geometry;
      const colors = Array.from(geometry.getAttribute('color').array);
      const atlas = shader.uniforms.uAtlas.value;
      // The 576px authored desktop pane permits the existing 34px glyph cap.
      // A 150.6px working phone pane must not retain 90% of that cap: unlike
      // individual cortex puncta, an alphabet sprite is a secondary object.
      for (const height of [62, 150.6, 168, 576, 900]) {
        camera.setViewOffset(320, height, 0, -118, 320, 568);
        frame();
        expect.soft(shader.uniforms.uViewportScale.value).toBeCloseTo(Math.min(1, height / 576), 7);
      }
      expect(field.geometry).toBe(geometry);
      expect(geometry.getAttribute('position').count).toBe(900);
      expect(Array.from(geometry.getAttribute('color').array)).toEqual(colors);
      expect(shader.uniforms.uAtlas.value).toBe(atlas);
      expect(shader.uniforms.uTime.value).toBe(0); // reduced-motion still freezes voyage
      expect(shader.vertexShader).toContain('clamp(finalSize, 2.0, 34.0) * uViewportScale');
    }, canvas => {
      host.append(canvas);
      vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 320, 568));
      return () => canvas.remove();
    });
  } finally { host.remove(); }
});

it('preserves the standalone lab glyph footprint at compact and normal pane sizes', async () => {
  await withField((_field, camera, shader, _draw, frame) => {
    for (const height of [62, 150.6, 168, 576, 900]) {
      camera.setViewOffset(320, height, 0, -118, 320, 568);
      frame();
      expect(shader.uniforms.uViewportScale.value).toBeCloseTo(Math.min(1, height / 168), 7);
    }
  });
});

it('contains glyph fragments at the current body region, not the full intake stage or stale DPR-sized buffer', async () => {
  await withField((field, camera, shader, draw) => {
    const geometry = field.geometry;
    const colors = Array.from(geometry.getAttribute('color').array);
    const atlas = shader.uniforms.uAtlas.value;
    expect(shader.uniforms.uPresenceClip).toBeDefined();
    expect(shader.uniforms.uRasterViewport).toBeDefined();
    const clip = () => shader.uniforms.uPresenceClip.value as THREE.Vector4;
    const raster = () => shader.uniforms.uRasterViewport.value as THREE.Vector4;
    camera.setViewOffset(320, 62, 0, -164, 320, 568);
    draw(new THREE.Vector4(0, 0, 640, 1136));
    expect(clip().toArray()).toEqual([0, 342 / 568, 1, 404 / 568]);
    expect(raster().toArray()).toEqual([0, 0, 640, 1136]);
    // Literal fragment samples: even a glyph whose centre is just inside
    // must not paint its outer edge into chrome. This numerical oracle checks
    // bound registration, NOT GLSL execution or downstream bloom containment.
    const accepts = (x: number, y: number) => {
      const u = (x - raster().x) / raster().z, v = (y - raster().y) / raster().w;
      return u >= clip().x && u <= clip().z && v >= clip().y && v <= clip().w;
    };
    expect(accepts(320, 685)).toBe(true);
    expect(accepts(320, 683.5)).toBe(false);
    expect(accepts(320, 809)).toBe(false);
    // Composer/alternate render-target viewport can have a different size
    // and origin than the canvas drawing buffer. Update at draw, without RAF.
    draw(new THREE.Vector4(17, 29, 160, 284));
    expect(raster().toArray()).toEqual([17, 29, 160, 284]);
    expect(accepts(97, 200.5)).toBe(true);
    expect(accepts(97, 199.75)).toBe(false);

    camera.setViewOffset(296, 211.25, -12, -210.75, 320, 568);
    draw(new THREE.Vector4(0, 0, 640, 1136));
    expect(clip().toArray()).toEqual([12 / 320, 146 / 568, 308 / 320, 357.25 / 568]);
    camera.setViewOffset(832, 576, -448, -144, 1280, 720);
    draw(new THREE.Vector4(0, 0, 2560, 1440));
    expect(clip().toArray()).toEqual([0.35, 0, 1, 0.8]);
    expect(field.geometry).toBe(geometry);
    expect(geometry.getAttribute('position').count).toBe(900);
    expect(Array.from(geometry.getAttribute('color').array)).toEqual(colors);
    expect(shader.uniforms.uAtlas.value).toBe(atlas);
    expect(camera.view?.width).toBe(1280); // stage stays full-size for intake
    expect(camera.view?.height).toBe(720);
    // Verify the real installed points template consumes these registered
    // uniforms at the fragment boundary, rather than clipping sprite centres.
    expect(shader.fragmentShader).toContain('(gl_FragCoord.xy - uRasterViewport.xy) / uRasterViewport.zw');
    expect(shader.fragmentShader).toContain('lessThan(presenceUv, uPresenceClip.xy)');
    expect(shader.fragmentShader).toContain('greaterThan(presenceUv, uPresenceClip.zw)');
  });
});

it('retains the standalone field and recovers from disabled or invalid camera views without stale bounds', async () => {
  await withField((_field, camera, shader, draw) => {
    expect(shader.uniforms.uPresenceClip).toBeDefined();
    camera.setViewOffset(320, 62, 0, -164, 320, 568);
    draw(new THREE.Vector4(0, 0, 640, 1136));
    camera.clearViewOffset();
    draw(new THREE.Vector4(0, 0, 320, 568));
    expect(shader.uniforms.uPresenceClip.value.toArray()).toEqual([0, 0, 1, 1]);
    camera.setViewOffset(320, 568, 20, 10, 280, 530);
    draw(new THREE.Vector4(0, 0, 280, 530));
    expect(shader.uniforms.uPresenceClip.value.toArray()).toEqual([0, 0, 1, 1]);
    for (const invalid of [0, NaN, Infinity]) {
      camera.view!.fullHeight = invalid;
      draw(new THREE.Vector4(0, 0, 320, 568));
      expect(shader.uniforms.uPresenceClip.value.toArray()).toEqual([0, 0, 1, 1]);
    }
  });
});

it('gives the actual moving cortex a soft quiet region without changing the field or reading layout at draw', async () => {
  const host = document.createElement('div'); host.className = 'lm-app'; document.body.append(host);
  try {
    await withField((field, camera, shader, draw) => {
      expect(shader.uniforms.uCortexQuiet).toBeDefined();
      const quiet = shader.uniforms.uCortexQuiet.value as THREE.Vector4;
      const geometry = field.geometry;
      const colors = Array.from(geometry.getAttribute('color').array);
      const atlas = shader.uniforms.uAtlas.value;
      const parent = new THREE.Group(), body = new THREE.Group(); parent.add(body);
      body.position.set(0.2, 0.12, -1.2); body.scale.setScalar(3.02);
      camera.position.set(0, 0, 18); camera.lookAt(0, -0.5, 0);
      camera.setViewOffset(320, 168, 0, -118, 320, 568);
      const anchor: [number, number, number] = [0.05, 0.12, 0];
      setCortexAnchor(anchor); setBrainDockScale(0.64);
      setBodyGroupWorldMatrix(body.matrixWorld, body);
      const reads = vi.spyOn(host, 'getBoundingClientRect');
      for (const pose of [0, 0.4, -0.6]) {
        parent.rotation.y = pose; parent.position.x = pose;
        draw(new THREE.Vector4(17, 29, 640, 1136));
        body.updateWorldMatrix(true, false); camera.updateWorldMatrix(true, false);
        const actual = new THREE.Vector3(...anchor).multiplyScalar(0.64).applyMatrix4(body.matrixWorld).project(camera);
        expect(quiet.x).toBeCloseTo(actual.x * 0.5 + 0.5, 7);
        expect(quiet.y).toBeCloseTo(actual.y * 0.5 + 0.5, 7);
        expect(quiet.w).toBeCloseTo((168 / 568) * 0.45, 7);
        expect(quiet.z).toBeCloseTo(quiet.w * 1136 / 640, 7);
      }
      const radius = quiet.w;
      draw(new THREE.Vector4(0, 0, 160, 284));
      expect(quiet.w).toBe(radius);
      expect(quiet.z / quiet.w).toBeCloseTo(284 / 160, 7);
      expect(reads).not.toHaveBeenCalled();
      expect(field.geometry).toBe(geometry);
      expect(geometry.getAttribute('position').count).toBe(900);
      expect(Array.from(geometry.getAttribute('color').array)).toEqual(colors);
      expect(shader.uniforms.uAtlas.value).toBe(atlas);
      // This checks real template consumption, not GPU execution/bloom.
      expect(shader.fragmentShader).toContain('uniform vec4 uCortexQuiet;');
      expect(shader.fragmentShader).toContain('(presenceUv - uCortexQuiet.xy) / uCortexQuiet.zw');
      expect(shader.fragmentShader).toContain('mix(0.12, 1.0, smoothstep(0.35, 1.0, cortexDistance))');
      expect(shader.fragmentShader).toContain('alpha * vAlpha * dissolve * cortexQuiet');
      clearBodyGroupWorldMatrix(body);
      draw(new THREE.Vector4(0, 0, 640, 1136));
      expect(quiet.z).toBe(0); expect(quiet.w).toBe(0);
    }, canvas => {
      host.append(canvas);
      vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 320, 568));
      return () => canvas.remove();
    });
  } finally { host.remove(); }
});

it('does not quiet standalone knowledge space or retain unavailable/offscreen cortex focus', async () => {
  const body = new THREE.Group(); body.position.z = -4;
  setBodyGroupWorldMatrix(body.matrixWorld, body);
  await withField((_field, camera, shader, draw) => {
    expect(shader.uniforms.uCortexQuiet).toBeDefined();
    camera.position.z = 18; camera.lookAt(0, 0, 0);
    draw(new THREE.Vector4(0, 0, 640, 1136));
    expect(shader.uniforms.uCortexQuiet.value.toArray()).toEqual([0, 0, 0, 0]);
  });
  const host = document.createElement('div'); host.className = 'lm-app'; document.body.append(host);
  try {
    await withField((_field, camera, shader, draw) => {
      expect(shader.uniforms.uCortexQuiet).toBeDefined();
      camera.position.z = 18; camera.lookAt(0, 0, 0);
      draw(new THREE.Vector4(0, 0, 640, 1136));
      expect(shader.uniforms.uCortexQuiet.value.w).toBeGreaterThan(0);
      for (const invalid of [0, NaN, Infinity]) {
        setBrainDockScale(invalid);
        draw(new THREE.Vector4(0, 0, 640, 1136));
        expect(shader.uniforms.uCortexQuiet.value.toArray()).toEqual([0, 0, 0, 0]);
      }
      setBrainDockScale(1); body.position.x = 1000;
      draw(new THREE.Vector4(0, 0, 640, 1136));
      expect(shader.uniforms.uCortexQuiet.value.toArray()).toEqual([0, 0, 0, 0]);
      body.position.set(0, 0, 1000);
      draw(new THREE.Vector4(0, 0, 640, 1136));
      expect(shader.uniforms.uCortexQuiet.value.toArray()).toEqual([0, 0, 0, 0]);
    }, canvas => { host.append(canvas); return () => canvas.remove(); });
  } finally { host.remove(); clearBodyGroupWorldMatrix(body); }
});

it('keeps glyph fragments out of observed in-pane chrome without reading layout during draws', async () => {
  const host = document.createElement('div'); host.className = 'lm-app';
  const chat = document.createElement('section'); chat.className = 'gagos-chat';
  const rail = document.createElement('aside'); rail.className = 'lm-workspace-rail';
  const notice = document.createElement('aside'); notice.className = 'lm-connection';
  host.append(rail, chat, notice); document.body.append(host);
  let chatRect = new DOMRect(28, 272, 354, 218);
  const chatRead = vi.spyOn(chat, 'getBoundingClientRect').mockImplementation(() => chatRect);
  const railRead = vi.spyOn(rail, 'getBoundingClientRect').mockReturnValue(new DOMRect(28, 166, 250, 96));
  const noticeRead = vi.spyOn(notice, 'getBoundingClientRect').mockReturnValue(new DOMRect(28, 556, 354, 146));
  const subscriptions = new Map<ResizeObserverCallback, Set<Element>>();
  vi.stubGlobal('ResizeObserver', class {
    targets = new Set<Element>();
    constructor(private callback: ResizeObserverCallback) { subscriptions.set(callback, this.targets); }
    observe = (element: Element) => this.targets.add(element);
    unobserve = (element: Element) => this.targets.delete(element);
    disconnect = () => { this.targets.clear(); subscriptions.delete(this.callback); };
  });
  const viewport = Object.assign(new EventTarget(), { width: 1280, height: 720,
    offsetLeft: 0, offsetTop: 0, pageLeft: 0, pageTop: 0, scale: 1, onresize: null, onscroll: null });
  vi.stubGlobal('visualViewport', viewport);
  let stageRect = new DOMRect(0, 0, 1280, 720);
  let stageRead!: ReturnType<typeof vi.spyOn>;
  try {
    await withField(async (field, camera, shader, draw) => {
      expect(shader.uniforms.uControlRectCount).toBeDefined();
      const masks = shader.uniforms.uControlRects.value as THREE.Vector4[];
      const maskValues = () => masks.slice(0, shader.uniforms.uControlRectCount.value).map(rect => rect.toArray());
      camera.setViewOffset(409.6, 576, 0, -144, 1280, 720);
      draw(new THREE.Vector4(0, 0, 2560, 1440));
      expect(maskValues()).toEqual([
        [20 / 1280, 450 / 720, 286 / 1280, 562 / 720],
        [20 / 1280, 222 / 720, 390 / 1280, 456 / 720],
        [20 / 1280, 10 / 720, 390 / 1280, 172 / 720],
      ]);
      // Actual subscriptions, not manually invoking an unrelated observer.
      expect([...subscriptions.values()].some(targets => targets.has(chat))).toBe(true);
      expect([...subscriptions.values()].some(targets => targets.has(notice))).toBe(true);
      const rectSize = { inlineSize: 354, blockSize: 242 };
      const entry: ResizeObserverEntry = { target: chat, contentRect: new DOMRect(0, 0, 354, 242),
        borderBoxSize: [rectSize], contentBoxSize: [rectSize], devicePixelContentBoxSize: [rectSize] };
      chatRect = new DOMRect(28, 248, 354, 242);
      act(() => { for (const [callback, targets] of subscriptions) {
        if (targets.has(chat)) callback([entry], {} as ResizeObserver);
      } });
      expect(maskValues()[1]).toEqual([20 / 1280, 222 / 720, 390 / 1280, 480 / 720]);
      // Same-size stage translation must refresh on the captured viewport
      // target, even when ambient rendering is paused and no RAF runs.
      stageRect = new DOMRect(20, 30, 1280, 720);
      act(() => { viewport.dispatchEvent(new Event('scroll')); });
      expect(maskValues()[1]).toEqual([0, 252 / 720, 370 / 1280, 510 / 720]);
      const reads = [chatRead.mock.calls.length, railRead.mock.calls.length,
        noticeRead.mock.calls.length, stageRead.mock.calls.length];
      const geometry = field.geometry;
      for (let i = 0; i < 100; i++) draw(new THREE.Vector4(17, 29, 640, 360));
      expect([chatRead.mock.calls.length, railRead.mock.calls.length,
        noticeRead.mock.calls.length, stageRead.mock.calls.length]).toEqual(reads);
      expect(field.geometry).toBe(geometry);
      expect(geometry.getAttribute('position').count).toBe(900);
      expect(shader.uniforms.uControlRects.value).toBe(masks);
      expect(shader.fragmentShader).toContain('uniform vec4 uControlRects[');
      expect(shader.fragmentShader).toMatch(/greaterThanEqual\(presenceUv, uControlRects\[i\]\.xy\)[\s\S]*lessThanEqual\(presenceUv, uControlRects\[i\]\.zw\)\)\) discard/);
    }, canvas => {
      host.append(canvas);
      stageRead = vi.spyOn(canvas, 'getBoundingClientRect').mockImplementation(() => stageRect);
      return () => canvas.remove();
    });
    expect(subscriptions.size).toBe(0);
    const readsAfterUnmount = chatRead.mock.calls.length;
    act(() => { viewport.dispatchEvent(new Event('scroll')); window.dispatchEvent(new Event('resize')); });
    expect(chatRead.mock.calls.length).toBe(readsAfterUnmount);
  } finally { host.remove(); }
});

it('discovers mounted chrome and removes obsolete masks instead of caching controls from first render', async () => {
  const host = document.createElement('div'); host.className = 'lm-app'; document.body.append(host);
  let rect = new DOMRect(12, 200, 296, 100);
  const notice = document.createElement('aside'); notice.className = 'lm-connection';
  vi.spyOn(notice, 'getBoundingClientRect').mockImplementation(() => rect);
  try {
    await withField(async (_field, _camera, shader) => {
      expect(shader.uniforms.uControlRectCount).toBeDefined();
      expect(shader.uniforms.uControlRectCount.value).toBe(0);
      await act(async () => { host.append(notice); });
      expect(shader.uniforms.uControlRectCount.value).toBe(1);
      expect(shader.uniforms.uControlRects.value[0].toArray()).toEqual([4 / 320, 260 / 568, 316 / 320, 376 / 568]);
      rect = new DOMRect();
      await act(async () => { notice.hidden = true; });
      expect(shader.uniforms.uControlRectCount.value).toBe(0);
      rect = new DOMRect(12, 200, 296, 100);
      await act(async () => { notice.hidden = false; });
      expect(shader.uniforms.uControlRectCount.value).toBe(1);
      await act(async () => { notice.remove(); });
      expect(shader.uniforms.uControlRectCount.value).toBe(0);
    }, canvas => {
      host.append(canvas);
      vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 320, 568));
      return () => canvas.remove();
    });
  } finally { host.remove(); }
});

it('quiets only the optional glyph field if the bounded mask budget or stage measurement is unavailable', async () => {
  const host = document.createElement('div'); host.className = 'lm-app'; document.body.append(host);
  const controls = Array.from({ length: 17 }, () => {
    const control = document.createElement('aside'); control.className = 'gagos-coach';
    vi.spyOn(control, 'getBoundingClientRect').mockReturnValue(new DOMRect(12, 200, 296, 100));
    return control;
  });
  host.append(...controls);
  let stageRect = new DOMRect(0, 0, 320, 568);
  try {
    await withField(async (field, _camera, shader) => {
      expect(shader.uniforms.uControlRectCount).toBeDefined();
      expect(shader.uniforms.uControlRectCount.value).toBe(-1);
      expect(shader.fragmentShader).toContain('if (uControlRectCount < 0) discard;');
      expect(field.geometry.getAttribute('position').count).toBe(900);
      await act(async () => { controls[16].remove(); });
      expect(shader.uniforms.uControlRectCount.value).toBe(16);
      stageRect = new DOMRect();
      act(() => { window.dispatchEvent(new Event('resize')); });
      expect(shader.uniforms.uControlRectCount.value).toBe(-1);
      stageRect = new DOMRect(0, 0, 320, 568);
      act(() => { window.dispatchEvent(new Event('resize')); });
      expect(shader.uniforms.uControlRectCount.value).toBe(16);
    }, canvas => {
      host.append(canvas);
      vi.spyOn(canvas, 'getBoundingClientRect').mockImplementation(() => stageRect);
      return () => canvas.remove();
    });
  } finally { host.remove(); }
});
