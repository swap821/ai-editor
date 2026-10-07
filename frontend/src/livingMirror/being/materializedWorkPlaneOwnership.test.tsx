import { act, createRef } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { advance, createRoot, extend, _roots, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import MaterializedTab from '../../superbrain/components/canvas/MaterializedTab';
import {
  __resetTabStoreForTests, closeWorkspace, focusWorkspace, getTabStoreSnapshot,
  reopenMaterializedTab, setMaterializedTabLifecycle, showContentSurface, showApprovalSurface,
} from '../../superbrain/lib/tabStore';
import { __resetSpineFusionForTests, setBodyGroupWorldMatrix, setSpineFusion } from '../../superbrain/lib/spineFusionBus';
import { getContentSurfacePlacement, getApprovalSurfacePlacement } from '../../superbrain/lib/materializedSurfaceAnchors';
import type { PendingApproval } from '../../superbrain/lib/aiosAdapter';
import ApprovalPanel from '../../superbrain/components/ui/ApprovalPanel';
import GuidedApprovalPanel from '../GuidedApprovalPanel';
import { LivingWorkspaceShell } from '../LivingWorkspaceShell';
import { WorkspaceConnectionOverlay, WorkspaceConnectionProjection } from './WorkspaceConnectionOverlay';

// Actual R3F surface, DOM reader, identity/lifecycle stores and connection.
// Only WebGL and remote font shaping are substituted: these assertions prove
// presentation ownership, not GPU output, phone hardware or visual acceptance.
vi.mock('@react-three/drei', async (original) => ({
  ...await original<typeof import('@react-three/drei')>(),
  Text: ({ children }: { children: string }) => <group name={`text:${children}`} />,
}));
extend({ Group: THREE.Group, Mesh: THREE.Mesh, Points: THREE.Points, LineSegments: THREE.LineSegments,
  BufferGeometry: THREE.BufferGeometry, SphereGeometry: THREE.SphereGeometry, PlaneGeometry: THREE.PlaneGeometry,
  BoxGeometry: THREE.BoxGeometry, TorusGeometry: THREE.TorusGeometry, TubeGeometry: THREE.TubeGeometry,
  CylinderGeometry: THREE.CylinderGeometry, ShapeGeometry: THREE.ShapeGeometry,
  MeshBasicMaterial: THREE.MeshBasicMaterial, MeshStandardMaterial: THREE.MeshStandardMaterial,
  PointsMaterial: THREE.PointsMaterial, LineBasicMaterial: THREE.LineBasicMaterial, ShaderMaterial: THREE.ShaderMaterial });

beforeEach(() => {
  __resetTabStoreForTests(); __resetSpineFusionForTests();
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 503, json: async () => ({}) })));
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
    const empty = this instanceof HTMLElement && (this.hidden || this.style.display === 'none');
    const value = this.matches('.lm-surface, .approval-panel')
      ? { x: 477, y: 200, width: empty ? 0 : 935, height: empty ? 0 : 450 }
      : { x: 0, y: 0, width: 1440, height: 900 };
    return { ...value, left: value.x, top: value.y, right: value.x + value.width,
      bottom: value.y + value.height, toJSON: () => value };
  });
  setSpineFusion(1, [0, 0, 0]); setBodyGroupWorldMatrix(new THREE.Matrix4());
});
afterEach(() => { cleanup(); __resetTabStoreForTests(); __resetSpineFusionForTests(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

async function mount(reducedMotion: boolean, withReader = true, experienceMode: 'beginner' | 'expert' = 'beginner') {
  const first = showContentSurface({ filepath: 'first.txt', language: 'text', code: 'first retained content' }, getContentSurfacePlacement(2));
  setMaterializedTabLifecycle(first.id, 'live');
  const overlayRef = createRef<SVGSVGElement>();
  const dom = render(<div className="lm-app"><canvas />
    {withReader && <LivingWorkspaceShell experienceMode={experienceMode} />}
    <WorkspaceConnectionOverlay overlayRef={overlayRef} />
  </div>);
  const canvas = dom.container.querySelector('canvas')!;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
  camera.position.set(0, 0, 10); camera.updateMatrixWorld();
  camera.setViewOffset(460, 900, 0, 0, 1440, 900);
  const root = createRoot(canvas);
  const store = _roots.get(canvas)!.store;
  const gl = { domElement: canvas, render() {}, setSize() {}, setPixelRatio() {} } as unknown as RootState['gl'];
  await root.configure({ gl, scene, camera, frameloop: 'never', size: { width: 1440, height: 900, left: 0, top: 0 } });
  // Like PresenceViewport, install pane framing after R3F configures stage size.
  camera.setViewOffset(460, 900, 0, 0, 1440, 900);
  const sync = async () => {
    const snapshot = getTabStoreSnapshot();
    await act(async () => { root.render(<>
      {snapshot.tabs.filter(tab => tab.kind === 'content').map(tab => <MaterializedTab key={tab.id} tab={tab}
        reducedMotion={reducedMotion} focused={snapshot.focusId === tab.id} workspaceCount={snapshot.tabs.length} />)}
      <WorkspaceConnectionProjection overlayRef={overlayRef} snapshot={snapshot} />
    </>); });
    act(() => advance(1, false, store.getState()));
  };
  await sync();
  return { first, dom, scene, sync, overlayRef, store, close: async () => { await act(async () => root.unmount()); dom.unmount(); } };
}

it.each([false, true])('the real selected DOM reader owns the result without a slab across the body (reduced=%s)', async reducedMotion => {
  const view = await mount(reducedMotion);
  try {
    const slab = view.scene.children[0];
    expect(slab).toBeInstanceOf(THREE.Group);
    expect(slab.visible).toBe(false);
    expect(screen.getByText('first retained content')).toBeVisible();
    expect(view.overlayRef.current!.querySelector('path')!.getAttribute('d')).not.toBe('');
    expect(getTabStoreSnapshot().tabs[0]).toMatchObject({ id: view.first.id, lifecycle: 'live', seatIndex: 2 });
  } finally { await view.close(); }
});

it('changing readers restores the old background representation without duplicating the new attended result', async () => {
  const view = await mount(false);
  try {
    const reader = screen.getByText('first retained content');
    const body = reader.closest<HTMLElement>('.lm-surface__body')!;
    body.scrollTop = 70;
    fireEvent.scroll(body);
    const oldSlab = view.scene.children[0];
    let secondId = '';
    act(() => {
      secondId = showContentSurface({ filepath: 'second.txt', language: 'text', code: 'second content' }, getContentSurfacePlacement(3)).id;
      setMaterializedTabLifecycle(secondId, 'live'); focusWorkspace(secondId);
    });
    await view.sync();
    expect(oldSlab.visible).toBe(true);
    expect(view.scene.children[1].visible).toBe(false);
    expect(screen.getByText('second content')).toBeVisible();
    act(() => focusWorkspace(view.first.id)); await view.sync();
    expect(oldSlab.visible).toBe(false);
    expect(view.scene.children[1].visible).toBe(true);
    expect(screen.getByText('first retained content')).toBe(reader);
    expect(body.scrollTop).toBe(70);
  } finally { await view.close(); }
});

it('Close keeps the delegated geometry quiet through retirement and Reopen keeps the same reader identity', async () => {
  const view = await mount(false);
  try {
    const reader = screen.getByText('first retained content');
    const slab = view.scene.children[0];
    expect(slab.visible).toBe(false);
    act(() => closeWorkspace(view.first.id)); await view.sync();
    expect(slab.visible).toBe(false);
    expect(reader).not.toBeVisible();
    expect(getTabStoreSnapshot().recoverableTabs?.[0].id).toBe(view.first.id);
    act(() => reopenMaterializedTab(view.first.id)); await view.sync();
    expect(slab.visible).toBe(false);
    expect(screen.getByText('first retained content')).toBe(reader);
    expect(reader).toBeVisible();
  } finally { await view.close(); }
});

it('a missing or unmeasurable DOM reader keeps standalone geometry instead of silently removing work', async () => {
  const view = await mount(false, false);
  try {
    expect(view.scene.children[0].visible).toBe(true);
    const plane = document.createElement('section');
    plane.className = 'lm-surface'; plane.dataset.workspaceId = view.first.id;
    plane.style.display = 'none';
    await act(async () => view.dom.container.querySelector('.lm-app')!.append(plane));
    expect(view.scene.children[0].visible).toBe(true);
    await act(async () => { plane.style.display = ''; });
    expect(view.scene.children[0].visible).toBe(false);
    await act(async () => { plane.hidden = true; });
    expect(view.scene.children[0].visible).toBe(true);
  } finally { await view.close(); }
});

it('frame callbacks do not repeatedly measure the DOM reader', async () => {
  const view = await mount(true);
  try {
    const measure = vi.mocked(Element.prototype.getBoundingClientRect);
    const before = measure.mock.calls.length;
    // Read-only frame advancement with a steady reader; no layout or observer event.
    // The actual connection and surface callbacks run, not a mocked render hook.
    const canvas = view.dom.container.querySelector('canvas')!;
    for (let time = 2; time <= 100; time++) act(() => advance(time, false, _roots.get(canvas)!.store.getState()));
    expect(measure.mock.calls.length).toBe(before);
  } finally { await view.close(); }
});

it('the delegated slab cannot capture a pointer, and standalone focus restores its actual ray hits', async () => {
  const view = await mount(true);
  try {
    const slab = view.scene.children[0];
    let body: THREE.Mesh | undefined;
    slab.traverse(object => {
      if (object instanceof THREE.Mesh && object.geometry.type === 'ExtrudeGeometry') body = object;
    });
    const hits = () => {
      view.scene.updateMatrixWorld(true);
      const target = body!.getWorldPosition(new THREE.Vector3());
      return new THREE.Raycaster(target.clone().add(new THREE.Vector3(0, 0, 10)), new THREE.Vector3(0, 0, -1))
        .intersectObject(slab, true);
    };
    expect(body).toBeInstanceOf(THREE.Mesh);
    expect(hits()).toHaveLength(0);
    act(() => focusWorkspace(null)); await view.sync();
    expect(slab.visible).toBe(true);
    expect(hits().length).toBeGreaterThan(0);
  } finally { await view.close(); }
});

it('a compact collapsed reader keeps ownership through its reachable header', async () => {
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({ matches: query.includes('max-width'), media: query,
    addEventListener() {}, removeEventListener() {} })));
  const view = await mount(true, true, 'expert');
  try {
    const slab = view.scene.children[0];
    const reader = screen.getByText('first retained content');
    expect(slab.visible).toBe(false);
    expect(screen.getByRole('button', { name: 'Expand workspace' })).toBeVisible();
    expect(reader).not.toBeVisible();
    expect(slab.visible).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: 'Expand workspace' }));
    expect(screen.getByText('first retained content')).toBe(reader);
    expect(reader).toBeVisible();
    expect(slab.visible).toBe(false);
  } finally { await view.close(); }
});

it('another workspace identity never withdraws this surface, and removing the reader restores geometry', async () => {
  const view = await mount(true, false);
  try {
    const plane = document.createElement('section');
    plane.className = 'lm-surface'; plane.dataset.workspaceId = 'different-reader';
    await act(async () => view.dom.container.querySelector('.lm-app')!.append(plane));
    expect(view.scene.children[0].visible).toBe(true);
    await act(async () => { plane.dataset.workspaceId = view.first.id; });
    expect(view.scene.children[0].visible).toBe(false);
    await act(async () => { plane.remove(); });
    expect(view.scene.children[0].visible).toBe(true);
  } finally { await view.close(); }
});

async function mountDecision(mode: 'beginner' | 'expert', reducedMotion: boolean, requestRef = 'conversation-approval') {
  const pending: PendingApproval = { token: 'fixture-only-capability', prompt: 'Create a fixture',
    summary: 'Create fixture.py', explanation: 'Synthetic proposal', kind: 'create', filepath: 'fixture.py',
    content: 'print("fixture")', diff: '', command: '', url: '' };
  const tab = showApprovalSurface({ requestRef, kindLabel: 'create', filepath: pending.filepath,
    summary: pending.summary, explanation: pending.explanation, content: pending.content, diff: '', command: '' },
  getApprovalSurfacePlacement(3));
  setMaterializedTabLifecycle(tab.id, 'live');
  const app = (present = true, active = true) => <div className="lm-app"><canvas />
    <div className="gagos-chrome" data-approval-pending={String(active)}>
      {present && (mode === 'beginner'
        ? <GuidedApprovalPanel pending={pending} onSettled={() => {}} />
        : <ApprovalPanel pending={pending} onSettled={() => {}} />)}
    </div>
  </div>;
  const dom = render(app());
  const canvas = dom.container.querySelector('canvas')!;
  const scene = new THREE.Scene();
  const root = createRoot(canvas);
  const store = _roots.get(canvas)!.store;
  const gl = { domElement: canvas, render() {}, setSize() {}, setPixelRatio() {} } as unknown as RootState['gl'];
  await root.configure({ gl, scene, frameloop: 'never', size: { width: 1440, height: 900, left: 0, top: 0 } });
  const sync = async () => {
    const record = getTabStoreSnapshot().tabs.find(record => record.id === tab.id)!;
    await act(async () => { root.render(<MaterializedTab tab={record} reducedMotion={reducedMotion} />); });
    act(() => advance(1, false, store.getState()));
  };
  await sync();
  return { tab, dom, scene, store, sync,
    dialog: async (present: boolean, active = true) => { await act(async () => { dom.rerender(app(present, active)); }); },
    close: async () => { await act(async () => root.unmount()); dom.unmount(); } };
}

it.each([['beginner', false], ['beginner', true], ['expert', false], ['expert', true]] as const)(
  'the readable decision owns approval without a second 3D card (%s, reduced=%s)', async (mode, reducedMotion) => {
    const view = await mountDecision(mode, reducedMotion);
    try {
      const slab = view.scene.children[0];
      expect(slab.visible).toBe(false);
      expect(screen.getAllByRole('alertdialog')).toHaveLength(1);
      expect(screen.getByRole('button', { name: mode === 'beginner' ? 'Allow once' : 'AUTHORIZE' })).toBeEnabled();
      expect(screen.getByRole('button', { name: mode === 'beginner' ? "Don't allow" : 'REJECT' })).toBeEnabled();
      let body: THREE.Mesh | undefined;
      slab.traverse(object => { if (object instanceof THREE.Mesh && object.geometry.type === 'ExtrudeGeometry') body = object; });
      expect(body).toBeInstanceOf(THREE.Mesh);
      view.scene.updateMatrixWorld(true);
      const target = body!.getWorldPosition(new THREE.Vector3());
      expect(new THREE.Raycaster(target.clone().add(new THREE.Vector3(0, 0, 10)), new THREE.Vector3(0, 0, -1))
        .intersectObject(slab, true)).toHaveLength(0);
      expect(getTabStoreSnapshot().tabs.find(record => record.id === view.tab.id)).toMatchObject({
        id: view.tab.id, lifecycle: 'live', seatIndex: 3, approval: { requestRef: 'conversation-approval', filepath: 'fixture.py' },
      });
    } finally { await view.close(); }
  },
);

it('a missing, hidden or non-pending dialog restores the still-live approval card, never silently hiding the boundary', async () => {
  const view = await mountDecision('beginner', true);
  try {
    const slab = view.scene.children[0];
    expect(slab.visible).toBe(false);
    const dialog = screen.getByRole('alertdialog');
    await act(async () => { dialog.hidden = true; });
    expect(slab.visible).toBe(true);
    await act(async () => { dialog.hidden = false; });
    expect(slab.visible).toBe(false);
    await view.dialog(true, false);
    expect(slab.visible).toBe(true);
    await view.dialog(true);
    expect(slab.visible).toBe(false);
    await view.dialog(false);
    expect(slab.visible).toBe(true);
    await view.dialog(true);
    expect(slab.visible).toBe(false);
  } finally { await view.close(); }
});

it('a lab-owned approval is not withdrawn by an unrelated conversation dialog', async () => {
  const view = await mountDecision('beginner', true, 'dev-approval');
  try {
    expect(view.scene.children[0].visible).toBe(true);
    expect(screen.getByRole('alertdialog')).toBeVisible();
  } finally { await view.close(); }
});

it('an unmeasurable or off-stage dialog cannot withdraw the remaining live approval surface', async () => {
  const view = await mountDecision('beginner', true);
  try {
    const slab = view.scene.children[0];
    const dialog = screen.getByRole('alertdialog');
    for (const box of [
      { x: 477, y: 200, width: 0, height: 450 },
      { x: 1440, y: 200, width: 935, height: 450 },
    ]) {
      // The prototype is already spied for this no-layout DOM environment.
      // Give only this dialog an own method; re-spying the inherited mock
      // otherwise moves the canvas too and cannot exercise off-stage fallback.
      Object.defineProperty(dialog, 'getBoundingClientRect', { configurable: true,
        value: () => ({ ...box, left: box.x, top: box.y,
          right: box.x + box.width, bottom: box.y + box.height, toJSON: () => box }),
      });
      await act(async () => { window.dispatchEvent(new Event('resize')); });
      expect(slab.visible, JSON.stringify({ box, dialog: dialog.getBoundingClientRect(),
        stage: view.dom.container.querySelector('canvas')!.getBoundingClientRect(),
        lifecycle: getTabStoreSnapshot().tabs.find(record => record.id === view.tab.id)?.lifecycle })).toBe(true);
    }
    Reflect.deleteProperty(dialog, 'getBoundingClientRect');
    await act(async () => { window.dispatchEvent(new Event('resize')); });
    expect(slab.visible).toBe(false);
  } finally { await view.close(); }
});

it('retiring delegated approval stays quiet after its dialog leaves, with no frame-loop DOM reads', async () => {
  // Observe the actual retirement interval, not the reduced-motion frame
  // which intentionally finishes/removes a retiring non-content record.
  const view = await mountDecision('beginner', false);
  try {
    const slab = view.scene.children[0];
    const measure = vi.mocked(Element.prototype.getBoundingClientRect);
    const before = measure.mock.calls.length;
    for (let time = 2; time <= 100; time++) act(() => advance(time, false, view.store.getState()));
    expect(measure.mock.calls.length).toBe(before);
    act(() => setMaterializedTabLifecycle(view.tab.id, 'retracting'));
    await view.sync();
    await view.dialog(false);
    expect(slab.visible).toBe(false);
    expect(getTabStoreSnapshot().tabs.find(record => record.id === view.tab.id)?.lifecycle).toBe('retracting');
  } finally { await view.close(); }
});
