import { act } from 'react';
import { _roots, advance, createRoot, extend, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import MaterializationLayer from '../../superbrain/components/canvas/MaterializationLayer';
import {
  __resetTabStoreForTests, closeWorkspace, finishMaterializedTabRetraction, getTabStoreSnapshot,
  reopenMaterializedTab, setMaterializedTabLifecycle, showContentSurface,
} from '../../superbrain/lib/tabStore';
import { __resetSpineFusionForTests, setBrainDockScale, setCortexAnchor, setSpineFusion } from '../../superbrain/lib/spineFusionBus';
import { getContentSurfacePlacement } from '../../superbrain/lib/materializedSurfaceAnchors';
import { createSeededRandom } from '../../superbrain/lib/seededRandom';

// Real layer, tab, particles, frame callbacks and identity/token/recovery owners.
// Only WebGL and remote font shaping are replaced. This proves the return's
// lifetime/route, not its shader pixels, hardware pacing or visual acceptance.
vi.mock('@react-three/drei', async original => ({
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
  // Fixed scatter/births make the observed return route reproducible; no
  // production geometry or seeds are changed by this test.
  vi.spyOn(Math, 'random').mockImplementation(createSeededRandom(0x7ab501));
  setSpineFusion(1, [0, 0, 0]); setCortexAnchor([0, 3, 0]); setBrainDockScale(0.6);
});
afterEach(() => {
  __resetTabStoreForTests(); __resetSpineFusionForTests(); vi.restoreAllMocks(); vi.unstubAllGlobals();
});

async function mount(reducedMotion = false) {
  let now = 10_000, time = 0;
  vi.spyOn(performance, 'now').mockImplementation(() => now);
  const tab = showContentSurface({ filepath: 'return.txt', language: 'text', code: 'retained partial result' }, getContentSurfacePlacement(3));
  setMaterializedTabLifecycle(tab.id, 'live');
  const canvas = document.createElement('canvas'), root = createRoot(canvas), store = _roots.get(canvas)!.store;
  const gl = { domElement: canvas, getPixelRatio: () => 1, render() {}, setSize() {}, setPixelRatio() {} } as unknown as RootState['gl'];
  await root.configure({ gl, scene: new THREE.Scene(), camera: new THREE.PerspectiveCamera(), frameloop: 'never',
    size: { width: 1440, height: 900, top: 0, left: 0 } });
  await act(async () => { root.render(<MaterializationLayer reducedMotion={reducedMotion} />); });
  const frame = (elapsed: number) => {
    now = 10_000 + elapsed; time += 1 / 60;
    act(() => advance(time, false, store.getState()));
  };
  const particles = () => {
    const result: THREE.Points[] = [];
    store.getState().scene.traverse(object => {
      if (object instanceof THREE.Points && object.renderOrder === 8 && object.geometry.getAttribute('position').count === 72) result.push(object);
    });
    expect(result.length).toBeLessThanOrEqual(1); // never create a duplicate return for one identity
    return result[0];
  };
  frame(0);
  const surface = store.getState().scene.children.find(object => object instanceof THREE.Group)!;
  expect(surface).toBeInstanceOf(THREE.Group);
  const hits = () => {
    store.getState().scene.updateMatrixWorld(true);
    let body!: THREE.Mesh;
    surface.traverse(object => { if (object instanceof THREE.Mesh && object.geometry.type === 'ExtrudeGeometry') body = object; });
    expect(body).toBeInstanceOf(THREE.Mesh);
    const target = body.getWorldPosition(new THREE.Vector3());
    return new THREE.Raycaster(target.clone().add(new THREE.Vector3(0, 0, 10)), new THREE.Vector3(0, 0, -1)).intersectObject(surface, true);
  };
  return { tab, frame, particles, surface, hits, unmount: async () => { await act(async () => root.unmount()); } };
}

it('keeps the real spine-to-cortex return mounted after the slab dissolves, then retires geometry without deleting its result', async () => {
  const view = await mount();
  try {
    act(() => { closeWorkspace(view.tab.id); }); // Close's public command returns void; inspect its state below
    const token = getTabStoreSnapshot().tabs.find(tab => tab.id === view.tab.id)!.retractionToken;
    expect(getTabStoreSnapshot().focusId).toBeNull(); // primary Close is immediate
    view.frame(0);
    const motes = view.particles()!;
    expect(motes).toBeInstanceOf(THREE.Points);
    const geometry = motes.geometry;
    const disposeGeometry = vi.spyOn(geometry, 'dispose'), disposeMaterial = vi.spyOn(motes.material as THREE.PointsMaterial, 'dispose');
    view.frame(1299);
    expect(view.surface.visible).toBe(true); // original dissolve timeline still reaches its final frame
    expect((motes.material as THREE.PointsMaterial).opacity).toBeGreaterThan(0.39);
    const before = new THREE.Vector3().fromBufferAttribute(geometry.getAttribute('position'), 0);
    expect(before.distanceTo(new THREE.Vector3(0, 1.8, 0))).toBeGreaterThan(0.02); // unfinished trip, not just a timer disagreement
    view.frame(1301);
    expect.soft(view.surface.visible).toBe(false); // no opaque sliver during the remaining return
    expect.soft(view.hits()).toHaveLength(0); // invisible groups must not leave a ghost hit target
    expect.soft(view.particles() === motes).toBe(true); // same mounted return, not an object dump on failure
    expect.soft(getTabStoreSnapshot().tabs.find(tab => tab.id === view.tab.id)?.retractionToken).toBe(token);
    // Its existing live cortex/dock owner can change while the return is in flight.
    setCortexAnchor([0.6, 2.6, -0.4]); setBrainDockScale(0.7);
    view.frame(1699);
    expect.soft(view.particles()?.geometry === geometry).toBe(true);
    const positions = geometry.getAttribute('position'), target = new THREE.Vector3(0.42, 1.82, -0.28);
    let furthestMote = 0;
    for (let index = 0; index < positions.count; index++) {
      const landed = new THREE.Vector3().fromBufferAttribute(positions, index);
      expect([landed.x, landed.y, landed.z].every(Number.isFinite)).toBe(true);
      furthestMote = Math.max(furthestMote, landed.distanceTo(target));
    }
    expect.soft(furthestMote).toBeLessThan(0.08); // preserve the existing small cortical scatter, not a zero-scatter fixture
    expect.soft((motes.material as THREE.PointsMaterial).opacity).toBeLessThan(0.002);
    view.frame(1701);
    expect(view.particles()).toBeUndefined();
    expect.soft(disposeGeometry).toHaveBeenCalledTimes(1);
    expect.soft(disposeMaterial).toHaveBeenCalledTimes(1);
    expect(getTabStoreSnapshot().tabs.find(tab => tab.id === view.tab.id)).toBeUndefined();
    expect(getTabStoreSnapshot().recoverableTabs?.[0]).toMatchObject({ id: view.tab.id,
      content: { code: 'retained partial result', filepath: 'return.txt' } });
    act(() => { expect(reopenMaterializedTab(view.tab.id)).toBe(true); });
    expect(getTabStoreSnapshot().tabs.find(tab => tab.id === view.tab.id)).toMatchObject({ id: view.tab.id,
      content: { code: 'retained partial result' } });
  } finally { await view.unmount(); }
});

it.each([800, 1450])('interrupts return at%s on Reopen and rejects the previous retirement token without changing the result identity', async elapsed => {
  const view = await mount();
  try {
    act(() => { closeWorkspace(view.tab.id); }); view.frame(elapsed);
    const motes = view.particles()!;
    expect(motes).toBeInstanceOf(THREE.Points);
    expect.soft(view.surface.visible).toBe(elapsed < 1300);
    const disposeGeometry = vi.spyOn(motes.geometry, 'dispose'), disposeMaterial = vi.spyOn(motes.material as THREE.PointsMaterial, 'dispose');
    const oldToken = getTabStoreSnapshot().tabs.find(tab => tab.id === view.tab.id)!.retractionToken;
    act(() => { expect(reopenMaterializedTab(view.tab.id)).toBe(true); });
    expect(view.particles()).toBeUndefined();
    expect.soft(disposeGeometry).toHaveBeenCalledTimes(1);
    expect.soft(disposeMaterial).toHaveBeenCalledTimes(1);
    act(() => { setMaterializedTabLifecycle(view.tab.id, 'live'); finishMaterializedTabRetraction(view.tab.id, oldToken); });
    view.frame(2000);
    expect(view.surface.visible).toBe(true); // same renderer can paint the reopened standalone result again
    expect(view.hits().length).toBeGreaterThan(0);
    expect(getTabStoreSnapshot().tabs).toHaveLength(1);
    expect(getTabStoreSnapshot().tabs[0]).toMatchObject({ id: view.tab.id, lifecycle: 'live', retractionToken: undefined,
      content: { code: 'retained partial result' } });
    expect(getTabStoreSnapshot().focusId).toBe(view.tab.id);
  } finally { await view.unmount(); }
});

it('keeps reduced-motion Close immediate and recoverable without a travelling return', async () => {
  const view = await mount(true);
  try {
    act(() => { closeWorkspace(view.tab.id); }); view.frame(0);
    expect(view.particles()).toBeUndefined();
    expect(getTabStoreSnapshot().tabs).toHaveLength(0);
    expect(getTabStoreSnapshot().recoverableTabs?.[0]).toMatchObject({ id: view.tab.id,
      content: { code: 'retained partial result' } });
    act(() => { expect(reopenMaterializedTab(view.tab.id)).toBe(true); }); view.frame(1);
    expect(getTabStoreSnapshot().tabs[0]).toMatchObject({ id: view.tab.id, lifecycle: 'live' });
    expect(view.particles()).toBeUndefined();
  } finally { await view.unmount(); }
});
