import { act } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { _roots, advance } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import WorkspaceCanvas from '../../superbrain/components/canvas/WorkspaceCanvas';
import { QualityTierProvider } from '../../superbrain/components/QualityTierProvider';
import { RenderingQualityControls } from '../RenderingQualityControls';
import { __resetTabStoreForTests, getTabStoreSnapshot, showContentSurface } from '../../superbrain/lib/tabStore';

// Keep the installed Canvas, context bridge, R3F root, governor, actual engine,
// point geometry and controls. Only external assets/backend/GL/DOM measurement
// are doubles. This is propagation/lifetime proof, never a hardware/FPS verdict.
vi.mock('@react-three/fiber', async (importOriginal) => {
  const actual = await importOriginal();
  const createSink = ({ canvas }) => {
    let ratio = 1;
    return { domElement: canvas, getPixelRatio: () => ratio,
      setPixelRatio: value => { ratio = value; }, setSize() {},
      render(scene) { scene.updateMatrixWorld(true); },
      dispose() {}, forceContextLoss() {}, shadowMap: {},
    };
  };
  return { ...actual, Canvas: props => <actual.Canvas {...props} gl={createSink} /> };
});
vi.mock('../../superbrain/lib/brainScene', async () => {
  const { Group, Mesh, BoxGeometry, MeshBasicMaterial } = await import('three');
  const scene = new Group();
  scene.add(new Mesh(new BoxGeometry(), new MeshBasicMaterial()));
  return { preloadBrainScene() {}, useBrainScene: () => scene };
});
vi.mock('../../superbrain/components/canvas/MemoryHalo', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/MaterializationLayer', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/PostFX', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/BodySpeech', () => ({ default: () => null }));

beforeEach(() => {
  localStorage.clear(); __resetTabStoreForTests();
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('fetch', async () => new Response('{}', { status: 404 }));
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: false }));
  vi.stubGlobal('devicePixelRatio', 2);
  // Manual advance runs the real subscribers without asserting synthetic pace.
  vi.stubGlobal('requestAnimationFrame', () => 1);
  vi.stubGlobal('cancelAnimationFrame', () => {});
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback) { this.callback = callback; }
    observe() { queueMicrotask(() => this.callback([])); }
    unobserve() {} disconnect() {}
  });
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    x: 0, y: 0, left: 0, top: 0, right: 1280, bottom: 720, width: 1280, height: 720, toJSON() {},
  });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ clearRect() {}, fillText() {} });
});
afterEach(async () => {
  await act(async () => cleanup());
  __resetTabStoreForTests(); localStorage.clear();
  vi.restoreAllMocks(); vi.unstubAllGlobals();
});

it('bridges the real DOM choice into actual field counts and applied DPR on the same installed Canvas and body', async () => {
  render(<QualityTierProvider><RenderingQualityControls /><WorkspaceCanvas /></QualityTierProvider>);
  const control = screen.getByRole('combobox', { name: 'Visual detail' });
  let canvas, store;
  await waitFor(() => {
    canvas = document.querySelector('.scene-layer canvas');
    expect(canvas).toBeInTheDocument();
    store = _roots.get(canvas)?.store;
    expect(store?.getState().controls).toBeTruthy();
  });
  const scene = store.getState().scene;
  let frame = 0;
  const sample = () => {
    act(() => advance(++frame / 60, false, store.getState()));
    let field;
    scene.traverse(object => {
      if (object instanceof THREE.Points && [256000, 78000, 51000].includes(object.geometry.getAttribute('position')?.count)) field = object;
    });
    expect(field).toBeTruthy();
    return field;
  };
  const initial = sample(), body = initial.parent.parent, camera = store.getState().camera, controls = store.getState().controls;
  let result;
  act(() => { result = showContentSurface({ filepath: 'fixture/quality.py', language: 'python', code: 'print("preserve me")', streaming: false }); });
  const identity = getTabStoreSnapshot().tabs.find(tab => tab.id === result.id)?.content;
  for (const [tier, count, dpr] of [['high', 256000, 1.5], ['medium', 78000, 1.25], ['low', 51000, 1], ['high', 256000, 1.5]]) {
    fireEvent.change(control, { target: { value: tier } });
    await waitFor(() => {
      const field = sample();
      expect(field.geometry.getAttribute('position').count).toBe(count);
      expect(field.parent.parent).toBe(body);
      expect(store.getState().gl.getPixelRatio()).toBe(dpr);
    });
    expect(document.querySelector('.scene-layer canvas')).toBe(canvas);
    expect(_roots.get(canvas).store).toBe(store);
    expect(store.getState().scene).toBe(scene);
    expect(store.getState().camera).toBe(camera);
    expect(store.getState().controls).toBe(controls);
    const retained = getTabStoreSnapshot().tabs.find(tab => tab.id === result.id);
    expect(retained.content).toBe(identity);
    expect(retained.content.code).toBe('print("preserve me")');
    expect(getTabStoreSnapshot().focusId).toBe(result.id);
    expect(localStorage.getItem('gag-quality-tier-v3')).toBe(tier);
  }
});

it('preserves the standalone lab Canvas owner instead of requiring the product wrapper', async () => {
  localStorage.setItem('gag-quality-tier-v3', 'low');
  render(<WorkspaceCanvas />);
  await waitFor(() => {
    const canvas = document.querySelector('.scene-layer canvas'), store = _roots.get(canvas)?.store;
    expect(store?.getState().controls).toBeTruthy();
    let field;
    store.getState().scene.traverse(object => {
      if (object instanceof THREE.Points && object.geometry.getAttribute('position')?.count === 51000) field = object;
    });
    expect(field).toBeTruthy(); expect(store.getState().gl.getPixelRatio()).toBe(1);
  });
});

it('keeps the same manual owner available when graphics support is absent, without claiming an active renderer', () => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
  render(<QualityTierProvider><RenderingQualityControls /><WorkspaceCanvas /></QualityTierProvider>);
  expect(document.querySelector('.webgl-fallback')).toBeInTheDocument();
  expect(document.querySelector('.scene-layer canvas')).toBeNull();
  const control = screen.getByRole('combobox', { name: 'Visual detail' });
  fireEvent.change(control, { target: { value: 'low' } });
  expect(control).toHaveValue('low');
  expect(localStorage.getItem('gag-quality-tier-v3')).toBe('low');
  expect(document.querySelector('.scene-layer canvas')).toBeNull();
});
