import { act, createRef } from 'react';
import { cleanup, render, waitFor } from '@testing-library/react';
import { _roots, advance } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import WorkspaceCanvas from '../../superbrain/components/canvas/WorkspaceCanvas';
import { QualityTierProvider } from '../../superbrain/components/QualityTierProvider';
import { __resetTabStoreForTests, getTabStoreSnapshot, showContentSurface, showApprovalSurface } from '../../superbrain/lib/tabStore';
import { __resetSpineFusionForTests } from '../../superbrain/lib/spineFusionBus';
import { getContentSurfacePlacement, getApprovalSurfacePlacement } from '../../superbrain/lib/materializedSurfaceAnchors';
import { deriveBeingPresentation } from './semanticKernel';
import { derivePhysicalSnapshot } from './physicalSnapshot';

// Keep installed Canvas/context bridge/engine/body/camera/controls and stores.
// External GL, assets, backend and measured pane direction are supplied; this
// proves the real consumer, not hardware speed or a human visual verdict.
vi.mock('@react-three/fiber', async original => {
  const actual = await original();
  const createSink = ({ canvas }) => ({ domElement: canvas, getPixelRatio: () => 1,
    setPixelRatio() {}, setSize() {}, render(scene) { scene.updateMatrixWorld(true); },
    dispose() {}, forceContextLoss() {}, shadowMap: {} });
  return { ...actual, Canvas: props => <actual.Canvas {...props} gl={createSink} /> };
});
vi.mock('../../superbrain/lib/brainScene', async () => {
  const scene = new THREE.Group(); scene.add(new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshBasicMaterial()));
  return { preloadBrainScene() {}, useBrainScene: () => scene };
});
vi.mock('../../superbrain/components/canvas/MemoryHalo', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/MaterializationLayer', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/PostFX', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/BodySpeech', () => ({ default: () => null }));
beforeEach(() => {
  __resetTabStoreForTests(); __resetSpineFusionForTests();
  localStorage.setItem('gag-quality-tier-v3', 'low');
  localStorage.removeItem('gagos-pause-motion-v1');
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('fetch', async () => new Response('{}', { status: 404 }));
  vi.stubGlobal('requestAnimationFrame', () => 1); vi.stubGlobal('cancelAnimationFrame', () => {});
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback) { this.callback = callback; }
    observe() { queueMicrotask(() => this.callback([])); } unobserve() {} disconnect() {}
  });
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 1280, 720));
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ clearRect() {}, fillText() {} });
});
afterEach(async () => {
  await act(async () => cleanup()); __resetTabStoreForTests(); __resetSpineFusionForTests();
  localStorage.removeItem('gag-quality-tier-v3'); localStorage.removeItem('gagos-pause-motion-v1');
  vi.restoreAllMocks(); vi.unstubAllGlobals();
});

// Dropping the measured-target relay leaves the actual body leaning toward its
// authored right-hand slab even when the reader is left or centred below it.
// Changing record/focus/geometry to fix the pose must fail the identity checks.
it.each([false, true])('faces the measured owned plane through installed Canvas without moving focus or anatomy; reduced=%s', async reduced => {
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: reduced }));
  let frame = 0; vi.spyOn(performance, 'now').mockImplementation(() => 10000 + frame * 1000 / 60);
  const attentionTargetRef = createRef();
  let physical = derivePhysicalSnapshot(deriveBeingPresentation({ transport: 'connected', projection: 'fresh',
    mirrorStatus: 'online', hasSnapshot: true, taskActivity: 'complete', verification: 'unknown', stop: 'clear' }));
  const app = (measured = true) => <QualityTierProvider><WorkspaceCanvas physical={physical} attentionTargetRef={measured ? attentionTargetRef : undefined} /></QualityTierProvider>;
  const view = render(app());
  let canvas, store;
  await waitFor(() => {
    canvas = document.querySelector('.scene-layer canvas'); store = _roots.get(canvas)?.store;
    expect(store?.getState().controls).toBeTruthy();
  });
  const step = () => act(() => { for (let n = 0; n < 180; n++) advance(++frame / 60, false, store.getState()); });
  step();
  let field; store.getState().scene.traverse(object => {
    if (object instanceof THREE.Points && object.geometry.getAttribute('position')?.count === 51000) field = object;
  });
  expect(field).toBeTruthy();
  const body = field.parent.parent, geometry = field.geometry, material = field.material;
  const camera = store.getState().camera, controls = store.getState().controls;
  const neutralYaw = body.rotation.y, neutralPitch = body.rotation.x;
  let reader;
  act(() => { reader = showContentSurface({ filepath: 'fixture/aim.py', language: 'python', code: 'print("retain")' }, getContentSurfacePlacement(2)); });
  for (const [lateral, vertical] of [[1, 0.5], [-1, 0.5], [0, 1]]) {
    attentionTargetRef.current = { targetId: reader.id, lateral, vertical }; step();
    const yaw = body.rotation.y - neutralYaw;
    if (reduced || lateral === 0) expect.soft(yaw).toBeCloseTo(0, 4);
    else if (lateral > 0) expect.soft(yaw, 'actual body faces the right-hand reader').toBeGreaterThan(0);
    else expect.soft(yaw, 'actual body follows a left-hand plane, not the old right-hand slab').toBeLessThan(0);
    if (reduced) expect.soft(body.rotation.x).toBeCloseTo(neutralPitch, 4);
    else expect.soft(body.rotation.x - neutralPitch).toBeLessThan(0);
    expect(getTabStoreSnapshot().focusId).toBe(reader.id);
    expect(getTabStoreSnapshot().tabs.find(record => record.id === reader.id)?.content?.code).toBe('print("retain")');
  }
  for (const target of [null, { targetId: 'different-owner', lateral: -1, vertical: 1 },
    { targetId: reader.id, lateral: Number.NaN, vertical: 1 }]) {
    attentionTargetRef.current = target; step();
    expect.soft(body.rotation.y, 'unavailable or foreign measured planes cannot steer this body').toBeCloseTo(neutralYaw, 4);
    expect.soft(body.rotation.x).toBeCloseTo(neutralPitch, 4);
  }
  view.rerender(app(false)); step();
  if (!reduced) expect.soft(body.rotation.y - neutralYaw, 'standalone staging keeps its authored slab direction').toBeGreaterThan(0);
  view.rerender(app());
  let decision;
  act(() => { decision = showApprovalSurface({ requestRef: 'conversation-approval', summary: 'Proposed write',
    explanation: '', kindLabel: 'create', filepath: 'fixture/aim.py', content: 'proposal', diff: '', command: '' }, getApprovalSurfacePlacement(6)); });
  physical = derivePhysicalSnapshot(deriveBeingPresentation({ transport: 'connected', projection: 'fresh', mirrorStatus: 'online',
    hasSnapshot: true, approvalPending: true, stop: 'clear' }));
  attentionTargetRef.current = { targetId: decision.id, lateral: -1, vertical: 0.5 };
  view.rerender(app()); step();
  if (!reduced) expect.soft(body.rotation.y - neutralYaw, 'decision aim wins without stealing reader focus').toBeLessThan(0);
  expect(getTabStoreSnapshot().focusId).toBe(reader.id);
  physical = derivePhysicalSnapshot(deriveBeingPresentation({ transport: 'connected', projection: 'fresh', mirrorStatus: 'online',
    hasSnapshot: true, approvalPending: true, stop: 'engaged' }));
  view.rerender(app()); step();
  expect.soft(body.rotation.y).toBeCloseTo(neutralYaw, 4);
  expect.soft(body.rotation.x).toBeCloseTo(neutralPitch, 4);
  expect(field.geometry).toBe(geometry); expect(field.material).toBe(material);
  expect(field.parent.parent).toBe(body); expect(store.getState().camera).toBe(camera);
  expect(store.getState().controls).toBe(controls); expect(document.querySelector('.scene-layer canvas')).toBe(canvas);
});
