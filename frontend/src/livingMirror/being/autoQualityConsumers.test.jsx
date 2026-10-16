import { act, useEffect } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { _roots, advance } from '@react-three/fiber';
import { EffectComposer, EffectPass } from 'postprocessing';
import * as THREE from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import WorkspaceCanvas from '../../superbrain/components/canvas/WorkspaceCanvas';
import { QualityTierProvider, useQualityTier } from '../../superbrain/components/QualityTierProvider';
import { RenderingQualityControls } from '../RenderingQualityControls';
import PhysicalStateGalleryPage from './PhysicalStateGalleryPage';
import { __resetTabStoreForTests, getTabStoreSnapshot, showContentSurface } from '../../superbrain/lib/tabStore';

// Keep the installed Canvas/bridge/root, actual FX pass setup, field, regional
// anatomy and controls. Only external assets/backend/measurement/GPU painting
// are substituted. The separate lifecycle test drives the installed monitor;
// here its public owner reports drive each real cost consumer deterministically.
vi.mock('@react-three/fiber', async importOriginal => {
  const actual = await importOriginal();
  const createSink = ({ canvas }) => {
    let ratio = 1;
    const context = { isContextLost: () => false, getContextAttributes: () => ({ alpha: false }),
      getParameter: () => 4, createRenderbuffer: () => ({}), bindRenderbuffer() {},
      renderbufferStorageMultisample() {}, deleteRenderbuffer() {} };
    return { domElement: canvas, getContext: () => context,
      getSize: target => target.set(1280, 720), getDrawingBufferSize: target => target.set(1280 * ratio, 720 * ratio),
      getPixelRatio: () => ratio, setPixelRatio: value => { ratio = value; }, setSize() {},
      render(scene) { scene.updateMatrixWorld(true); }, dispose() {}, forceContextLoss() {}, shadowMap: {},
      capabilities: { maxVaryings: 16 }, toneMapping: THREE.ACESFilmicToneMapping,
      outputColorSpace: THREE.SRGBColorSpace, autoClear: true };
  };
  return { ...actual, Canvas: props => <actual.Canvas {...props} gl={createSink} /> };
});
vi.mock('../../superbrain/lib/brainScene', async () => {
  const { Group, Mesh, BoxGeometry, MeshBasicMaterial } = await import('three');
  const scene = new Group(); scene.add(new Mesh(new BoxGeometry(), new MeshBasicMaterial()));
  return { preloadBrainScene() {}, useBrainScene: () => scene };
});
vi.mock('../../superbrain/components/canvas/MemoryHalo', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/MaterializationLayer', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/BodySpeech', () => ({ default: () => null }));

let quality, wallMs, composers;
function ObserveOwner() {
  const owner = useQualityTier();
  useEffect(() => { quality = owner; }, [owner]);
  return null;
}
const activeComposer = () => [...composers].filter(composer => composer.passes.some(pass => pass instanceof EffectPass));
const effectNames = composer => composer.passes.filter(pass => pass instanceof EffectPass)
  .flatMap(pass => Reflect.get(pass, 'effects').map(effect => effect.name));
beforeEach(() => {
  wallMs = 10000; composers = new Set(); quality = null;
  localStorage.clear(); __resetTabStoreForTests();
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('fetch', async () => new Response('{}', { status: 404 }));
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: false }));
  vi.stubGlobal('devicePixelRatio', 2);
  vi.stubGlobal('requestAnimationFrame', () => 1); vi.stubGlobal('cancelAnimationFrame', () => {});
  vi.spyOn(performance, 'now').mockImplementation(() => wallMs);
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback) { this.callback = callback; }
    observe() { queueMicrotask(() => this.callback([])); } unobserve() {} disconnect() {}
  });
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    x: 0, y: 0, left: 0, top: 0, right: 1280, bottom: 720, width: 1280, height: 720, toJSON() {} });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ clearRect() {}, fillText() {} });
  const addPass = EffectComposer.prototype.addPass;
  vi.spyOn(EffectComposer.prototype, 'addPass').mockImplementation(function(pass, index) {
    addPass.call(this, pass, index); composers.add(this);
  });
  vi.spyOn(EffectComposer.prototype, 'render').mockImplementation(function() {
    for (const pass of this.passes) if (pass.scene) pass.scene.updateMatrixWorld(true);
  });
});
afterEach(async () => {
  await act(async () => cleanup());
  __resetTabStoreForTests(); localStorage.clear(); vi.restoreAllMocks(); vi.unstubAllGlobals();
});

it('applies ordered Auto costs to real FX, sky and body while retaining color chain, regional resources and work', async () => {
  render(<QualityTierProvider><ObserveOwner /><RenderingQualityControls /><WorkspaceCanvas /></QualityTierProvider>);
  const control = screen.getByRole('combobox', { name: 'Visual detail' });
  expect(control).toHaveValue('auto');
  let canvas, store;
  await waitFor(() => {
    canvas = document.querySelector('.scene-layer canvas'); store = _roots.get(canvas)?.store;
    expect(store?.getState().controls).toBeTruthy(); expect(activeComposer()).toHaveLength(1);
  });
  const scene = store.getState().scene, camera = store.getState().camera, controls = store.getState().controls;
  const sample = () => {
    act(() => advance(wallMs / 1000, false, store.getState()));
    let body, sky; const regional = [];
    scene.traverse(object => {
      if (object instanceof THREE.Points) {
        if (object.geometry.getAttribute('aSpriteIndex')) sky = object;
        if ([256000, 78000, 51000].includes(object.geometry.getAttribute('position')?.count)) body = object;
      }
      if (object.geometry?.getAttribute('aActivation')) regional.push(object);
    });
    expect(body).toBeTruthy(); expect(sky).toBeTruthy(); expect(regional.length).toBeGreaterThan(0);
    return { body, sky, regional };
  };
  const initial = sample(), bodyParent = initial.body.parent.parent;
  const originalSky = initial.sky.geometry;
  const retiredSky = vi.fn();
  originalSky.addEventListener('dispose', retiredSky);
  const regionResources = initial.regional.map(object => [object, object.geometry, object.material]);
  let result;
  act(() => { result = showContentSurface({ filepath: 'fixture/auto.py', language: 'python',
    code: 'print("same readable result")', streaming: false }); });
  const identity = getTabStoreSnapshot().tabs.find(tab => tab.id === result.id).content;
  act(() => { quality.beginAutoCalibration(wallMs); });
  wallMs += 21000;
  const stages = [[0, 4, 3000, 1.5, 256000], [1, 0, 3000, 1.5, 256000],
    [2, 0, 900, 1.5, 256000], [3, 0, 900, 1.25, 256000], [4, 0, 900, 1, 256000],
    [5, 0, 900, 1, 78000], [6, 0, 900, 1, 51000]];
  for (const [stage, msaa, stars, dpr, points] of stages) {
    if (stage) {
      wallMs += 5000;
      await act(async () => { quality.reportAutoWindow('slow', quality.autoRevision, wallMs, true); });
    }
    await waitFor(() => {
      expect(quality.autoProfile.stage).toBe(stage);
      const observed = sample();
      expect(activeComposer()).toHaveLength(1);
      expect(activeComposer()[0].multisampling).toBe(msaa);
      expect(effectNames(activeComposer()[0])).toEqual(['BloomEffect', 'ChromaticAberrationEffect', 'GradePreEffect',
        'ToneMappingEffect', 'GradePostEffect', 'VignetteEffect', 'NoiseEffect']);
      expect(observed.sky.geometry.getAttribute('position').count).toBe(stars);
      // Externally supplied geometry is not an R3F child. Replacing it must
      // release the old real buffer, without disposing the still-active one.
      expect(retiredSky).toHaveBeenCalledTimes(stage < 2 ? 0 : 1);
      expect(observed.body.geometry.getAttribute('position').count).toBe(points);
      expect(observed.body.parent.parent).toBe(bodyParent);
      expect(store.getState().gl.getPixelRatio()).toBe(dpr);
      expect(observed.regional).toEqual(initial.regional);
      for (const [object, geometry, material] of regionResources) {
        expect(object.geometry).toBe(geometry); expect(object.material).toBe(material);
      }
    });
    expect(control).toHaveValue('auto'); expect(document.querySelector('.scene-layer canvas')).toBe(canvas);
    expect(_roots.get(canvas).store).toBe(store); expect(store.getState().camera).toBe(camera);
    expect(store.getState().controls).toBe(controls); expect(store.getState().scene).toBe(scene);
    expect(getTabStoreSnapshot().tabs.find(tab => tab.id === result.id).content).toBe(identity);
    expect(identity.code).toBe('print("same readable result")'); expect(getTabStoreSnapshot().focusId).toBe(result.id);
    expect(localStorage.getItem('gag-quality-tier-v4')).toBeNull();
  }
  fireEvent.change(control, { target: { value: 'high' } });
  await waitFor(() => { expect(sample().body.geometry.getAttribute('position').count).toBe(256000);
    expect(activeComposer()[0].multisampling).toBe(4); });
  expect(control).toHaveValue('high'); expect(localStorage.getItem('gag-quality-tier-v4')).toBe('high');
});

// Break caught: disposed geometry must follow each real replacement, not only
// the first demotion or component teardown. Active/shared resources stay live.
it('retires replaced and final sky buffers once without discarding the shared atlas or rebuilding the field', async () => {
  const view = render(<QualityTierProvider><ObserveOwner /><WorkspaceCanvas /></QualityTierProvider>);
  let store;
  await waitFor(() => {
    store = _roots.get(document.querySelector('.scene-layer canvas'))?.store;
    expect(store?.getState().controls).toBeTruthy();
  });
  const scene = store.getState().scene;
  const sky = () => {
    let field;
    scene.traverse(object => { if (object.geometry?.getAttribute('aSpriteIndex')) field = object; });
    expect(field).toBeTruthy(); return field;
  };
  const field = sky(), material = field.material;
  const shader = { uniforms: {}, vertexShader: THREE.ShaderLib.points.vertexShader,
    fragmentShader: THREE.ShaderLib.points.fragmentShader };
  material.onBeforeCompile(shader, store.getState().gl); // real shader producer, external GPU compilation
  const atlas = shader.uniforms.uAtlas.value;
  expect(atlas).toBeInstanceOf(THREE.CanvasTexture);
  const atlasDisposed = vi.fn(); atlas.addEventListener('dispose', atlasDisposed);
  const records = new Map();
  const track = geometry => {
    if (!records.has(geometry)) {
      const disposed = vi.fn(); geometry.addEventListener('dispose', disposed); records.set(geometry, disposed);
    }
    return records.get(geometry);
  };
  track(field.geometry);
  const report = async (signal, elapsed) => {
    wallMs += elapsed;
    await act(async () => { quality.reportAutoWindow(signal, quality.autoRevision, wallMs, true); });
  };
  act(() => { quality.beginAutoCalibration(wallMs); }); wallMs += 21000;
  try {
    for (let cycle = 0; cycle < 3; cycle++) {
      const high = sky().geometry; track(high);
      await report('slow', 5000);
      expect(quality.autoProfile.stage).toBe(1); expect(sky().geometry).toBe(high);
      await report('slow', 5000);
      const low = sky().geometry; track(low);
      expect(quality.autoProfile.stage).toBe(2); expect(low.getAttribute('position').count).toBe(900);
      expect(records.get(high)).toHaveBeenCalledTimes(1); expect(records.get(low)).not.toHaveBeenCalled();
      await report('healthy', 11000); await report('healthy', 2500);
      const recovered = sky().geometry; track(recovered);
      expect(quality.autoProfile.stage).toBe(1); expect(recovered.getAttribute('position').count).toBe(3000);
      expect(records.get(low)).toHaveBeenCalledTimes(1); expect(records.get(recovered)).not.toHaveBeenCalled();
      await report('healthy', 11000); await report('healthy', 2500);
      expect(quality.autoProfile.stage).toBe(0); expect(sky().geometry).toBe(recovered);
      expect(sky()).toBe(field); expect(sky().material).toBe(material);
      expect(shader.uniforms.uAtlas.value).toBe(atlas); expect(atlasDisposed).not.toHaveBeenCalled();
    }
    const active = sky().geometry;
    for (const [geometry, disposed] of records) expect(disposed).toHaveBeenCalledTimes(geometry === active ? 0 : 1);
    await act(async () => { view.unmount(); });
    await waitFor(() => expect(records.get(active)).toHaveBeenCalledTimes(1));
    for (const disposed of records.values()) expect(disposed).toHaveBeenCalledTimes(1);
    expect(atlasDisposed).not.toHaveBeenCalled();
  } finally {
    atlas.removeEventListener('dispose', atlasDisposed);
    for (const [geometry, disposed] of records) geometry.removeEventListener('dispose', disposed);
  }
});

// Break caught: a saved product Auto preference must not override the gallery's
// explicit, labelled manual tier and misrepresent its anatomy/FX comparison.
it('renders the gallery-selected tier without overwriting or inheriting the saved product Auto preference', async () => {
  localStorage.setItem('gag-quality-tier-v4', 'auto');
  localStorage.setItem('gag-quality-tier-v3', 'high');
  render(<PhysicalStateGalleryPage />);
  const control = screen.getByRole('combobox', { name: 'Quality' });
  fireEvent.change(control, { target: { value: 'low' } });
  await waitFor(() => {
    const canvas = document.querySelector('.physical-gallery__canvas canvas'), store = _roots.get(canvas)?.store;
    expect(store).toBeTruthy();
    let field;
    store.getState().scene.traverse(object => {
      if (object instanceof THREE.Points && [256000, 78000, 51000].includes(object.geometry.getAttribute('position')?.count)) field = object;
    });
    expect(field).toBeTruthy();
    expect(field.geometry.getAttribute('position').count).toBe(51000);
    expect(activeComposer()).toHaveLength(1);
    expect(effectNames(activeComposer()[0])).toEqual(['GradePreEffect', 'ToneMappingEffect', 'GradePostEffect', 'VignetteEffect']);
  });
  expect(control).toHaveValue('low');
  expect(localStorage.getItem('gag-quality-tier-v4')).toBe('auto');
  expect(localStorage.getItem('gag-quality-tier-v3')).toBe('high');
});
