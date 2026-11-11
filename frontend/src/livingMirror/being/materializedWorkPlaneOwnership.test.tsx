import { act, createRef } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { advance, createRoot, extend, _roots, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import MaterializedTab from '../../superbrain/components/canvas/MaterializedTab';
import MaterializationLayer from '../../superbrain/components/canvas/MaterializationLayer';
import {
  __resetTabStoreForTests, closeWorkspace, focusWorkspace, getTabStoreSnapshot,
  reopenMaterializedTab, setMaterializedTabLifecycle, finishMaterializedTabRetraction, showContentSurface, showApprovalSurface, updateMaterializedTab,
} from '../../superbrain/lib/tabStore';
import { __resetSpineFusionForTests, setBodyGroupWorldMatrix, setSpineFusion, setBrainDockScale, setCortexShape } from '../../superbrain/lib/spineFusionBus';
import { getContentSurfacePlacement, getApprovalSurfacePlacement } from '../../superbrain/lib/materializedSurfaceAnchors';
import type { PendingApproval } from '../../superbrain/lib/aiosAdapter';
import ApprovalPanel from '../../superbrain/components/ui/ApprovalPanel';
import GuidedApprovalPanel from '../GuidedApprovalPanel';
import { LivingWorkspaceShell } from '../LivingWorkspaceShell';
import { WorkspaceConnectionOverlay } from './WorkspaceConnectionOverlay';
import { WorkspaceConnectionProjection } from './WorkspaceConnectionProjection';
import { setAmbientMotionPaused, useReducedMotion } from '../../superbrain/lib/reducedMotion';
import { POINTS_REABSORPTION_MS, POINTS_SLAB_RETRACT_MS } from '../../superbrain/lib/reabsorptionTiming';
import type { PhysicalBodyProjection } from '../../superbrain/lib/bodyPosture';
import { deriveBeingPresentation } from './semanticKernel';
import { derivePhysicalSnapshot } from './physicalSnapshot';

// Actual R3F surface, DOM reader, identity/lifecycle stores and connection.
// Only WebGL and remote font shaping are substituted: these assertions prove
// presentation ownership, not GPU output, phone hardware or visual acceptance.
vi.mock('@react-three/drei', async (original) => ({
  ...await original<typeof import('@react-three/drei')>(),
  Text: ({ children }: { children: string }) => <group name={`text:${children}`} />,
}));
extend({ Group: THREE.Group, Mesh: THREE.Mesh, Points: THREE.Points, LineSegments: THREE.LineSegments,
  BufferGeometry: THREE.BufferGeometry, BufferAttribute: THREE.BufferAttribute, SphereGeometry: THREE.SphereGeometry, PlaneGeometry: THREE.PlaneGeometry,
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
afterEach(() => { cleanup(); __resetTabStoreForTests(); __resetSpineFusionForTests();
  window.localStorage.removeItem('gagos-pause-motion-v1'); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function MaterializedReaders({ snapshot, fullLayer = false, physical, breathRef }: { snapshot: ReturnType<typeof getTabStoreSnapshot>; fullLayer?: boolean; physical?: PhysicalBodyProjection; breathRef?: {value:number} }) {
  const reducedMotion = useReducedMotion(); // same reactive source as the actual CortexEngine
  if (fullLayer) return <MaterializationLayer reducedMotion={reducedMotion} physical={physical} breathRef={breathRef} />;
  return snapshot.tabs.filter(tab => tab.kind === 'content').map(tab => <MaterializedTab key={tab.id} tab={tab}
    reducedMotion={reducedMotion} focused={snapshot.focusId === tab.id} workspaceCount={snapshot.tabs.length} />);
}

async function mount(reducedMotion: boolean, withReader = true, experienceMode: 'beginner' | 'expert' = 'beginner', reaching = false, fullLayer = false, physical?: PhysicalBodyProjection, breathRef?: {value:number}, decoyCanvas = false) {
  setAmbientMotionPaused(reducedMotion);
  const first = showContentSurface({ filepath: 'first.txt', language: 'text', code: 'first retained content' }, getContentSurfacePlacement(2));
  if (!reaching) setMaterializedTabLifecycle(first.id, 'live');
  const overlayRef = createRef<SVGSVGElement>();
  const dom = render(<div className="lm-app">{decoyCanvas && <canvas data-decoy="true" />}<canvas data-renderer="true" />
    {withReader && <LivingWorkspaceShell experienceMode={experienceMode} />}
    <WorkspaceConnectionOverlay overlayRef={overlayRef} />
  </div>);
  const canvas = dom.container.querySelector<HTMLCanvasElement>('canvas[data-renderer]')!;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
  camera.position.set(0, 0, 10); camera.updateMatrixWorld();
  camera.setViewOffset(460, 900, 0, 0, 1440, 900);
  const root = createRoot(canvas);
  const store = _roots.get(canvas)!.store;
  const gl = { domElement: canvas, render() {}, setSize() {}, setPixelRatio() {}, getPixelRatio:()=>1 } as unknown as RootState['gl'];
  await root.configure({ gl, scene, camera, frameloop: 'never', size: { width: 1440, height: 900, left: 0, top: 0 } });
  // Like PresenceViewport, install pane framing after R3F configures stage size.
  camera.setViewOffset(460, 900, 0, 0, 1440, 900);
  const commit = async () => {
    const snapshot = getTabStoreSnapshot();
    await act(async () => { root.render(<>
      <MaterializedReaders snapshot={snapshot} fullLayer={fullLayer} physical={physical} breathRef={breathRef} />
      <WorkspaceConnectionProjection overlayRef={overlayRef} snapshot={snapshot} breathRef={breathRef} />
    </>); });
  };
  const sync = async () => { await commit(); act(() => advance(1, false, store.getState())); };
  await sync();
  return { first, dom, scene, sync, commit, overlayRef, store,
    setPhysical: async (next: PhysicalBodyProjection) => { physical = next; await sync(); },
    close: async () => { await act(async () => root.unmount()); dom.unmount(); } };
}

it('keeps the connection on the renderer when another canvas precedes it', async () => {
  vi.mocked(Element.prototype.getBoundingClientRect).mockImplementation(function (this: Element) {
    const value = this.matches('[data-decoy]')
      ? { x: 0, y: 0, width: 0, height: 0 }
      : this.matches('.lm-surface, .approval-panel')
        ? { x: 477, y: 200, width: 935, height: 450 }
        : { x: 0, y: 0, width: 1440, height: 900 };
    return { ...value, left: value.x, top: value.y, right: value.x + value.width,
      bottom: value.y + value.height, toJSON: () => value };
  });
  const view = await mount(false, true, 'beginner', false, false, undefined, undefined, true);
  try {
    expect(view.overlayRef.current!.querySelector('path')!.getAttribute('d')).not.toBe('');
    const nerve = view.scene.getObjectByName('workspace-nerve') as THREE.Mesh;
    expect(nerve.visible).toBe(true);
  } finally { await view.close(); }
});

it('signals admitted streaming changes on the real nerve and stays quiet when ambient motion is paused', async () => {
  let now = 10000;
  vi.spyOn(performance, 'now').mockImplementation(() => now);
  const view = await mount(false);
  try {
    const original = getTabStoreSnapshot().tabs.find(tab => tab.id === view.first.id)!;
    act(() => updateMaterializedTab(original.id, { content: { ...original.content!, streaming: true } }));
    await view.sync();
    const nerve = view.scene.getObjectByName('workspace-nerve') as THREE.Mesh<THREE.BufferGeometry, THREE.ShaderMaterial>;
    const fibers = view.scene.getObjectByName('workspace-nerve-fibers') as THREE.Points<THREE.BufferGeometry, THREE.ShaderMaterial>;
    expect(nerve.material.uniforms.signal?.value).toBe(-1);
    expect(fibers.material.uniforms.signal?.value).toBe(-1);
    act(() => updateMaterializedTab(original.id, { content: { ...original.content!, code: 'first retained content + chunk', streaming: true } }));
    await view.sync();
    expect(nerve.material.uniforms.signal?.value).toBeCloseTo(0, 4);
    expect(fibers.material.uniforms.signal?.value).toBeCloseTo(0, 4);
    expect(nerve.material.fragmentShader).toContain('signal');
    expect(fibers.material.fragmentShader).toContain('signal');
    now += 200; await view.sync();
    expect(nerve.material.uniforms.signal?.value).toBeGreaterThan(0.35);
    expect(nerve.material.uniforms.signal?.value).toBeLessThan(0.65);
    act(() => setAmbientMotionPaused(true)); await view.sync();
    expect(nerve.material.uniforms.signal?.value).toBe(-1);
    act(() => updateMaterializedTab(original.id, { content: { ...original.content!, code: 'quiet update', streaming: true } }));
    await view.sync();
    act(() => setAmbientMotionPaused(false)); await view.sync();
    expect(nerve.material.uniforms.signal?.value).toBe(-1);
  } finally { await view.close(); }
});

it('cancels the real nerve cue when the operating system requests reduced motion', async () => {
  let now=10000, reduced=false;
  vi.spyOn(performance,'now').mockImplementation(()=>now);
  const media=new EventTarget();
  Object.defineProperty(media,'matches',{get:()=>reduced});
  vi.stubGlobal('matchMedia',()=>media);
  const view=await mount(false);
  try {
    const original=getTabStoreSnapshot().tabs.find(tab=>tab.id===view.first.id)!;
    act(()=>updateMaterializedTab(original.id,{content:{...original.content!,streaming:true}}));await view.sync();
    act(()=>updateMaterializedTab(original.id,{content:{...original.content!,code:'admitted chunk',streaming:true}}));await view.sync();
    const nerve=view.scene.getObjectByName('workspace-nerve') as THREE.Mesh<THREE.BufferGeometry,THREE.ShaderMaterial>;
    expect(nerve.material.uniforms.signal.value).toBe(0);
    reduced=true;act(()=>media.dispatchEvent(new Event('change')));await view.sync();
    expect(nerve.material.uniforms.signal.value).toBe(-1);
    now+=50;act(()=>updateMaterializedTab(original.id,{content:{...original.content!,code:'quiet chunk',streaming:true}}));await view.sync();
    reduced=false;act(()=>media.dispatchEvent(new Event('change')));await view.sync();
    expect(nerve.material.uniforms.signal.value).toBe(-1);
  } finally {await view.close();}
});

it('writes the shared breath to both actual nerve materials and settles when motion is paused',async()=>{
  const breathRef={value:.2};
  const view=await mount(false,true,'beginner',false,false,undefined,breathRef);
  expect(view.scene.getObjectByName(`gagos-workspace-${view.first.id}`)).toBeTruthy();
  const tube=view.scene.getObjectByName('workspace-nerve') as THREE.Mesh<THREE.BufferGeometry,THREE.ShaderMaterial>;
  const fibers=view.scene.getObjectByName('workspace-nerve-fibers') as THREE.Points<THREE.BufferGeometry,THREE.ShaderMaterial>;
  expect(tube.material.uniforms.breath.value).toBe(.2);expect(fibers.material.uniforms.breath.value).toBe(.2);
  breathRef.value=.9;await view.sync();
  expect(tube.material.uniforms.breath.value).toBe(.9);expect(fibers.material.uniforms.breath.value).toBe(.9);
  act(()=>setAmbientMotionPaused(true));await view.sync();
  expect(tube.material.uniforms.breath.value).toBe(.5);expect(fibers.material.uniforms.breath.value).toBe(.5);
  await view.close();
});

it('keeps the actual 3D nerve on the reader connection and retires it with the same return',async()=>{
  let now=1000;vi.spyOn(performance,'now').mockImplementation(()=>now);
  const view=await mount(false);
  const tube=view.scene.getObjectByName('workspace-nerve') as THREE.Mesh<THREE.BufferGeometry,THREE.ShaderMaterial>;
  const fibers=view.scene.getObjectByName('workspace-nerve-fibers') as THREE.Points<THREE.BufferGeometry,THREE.ShaderMaterial>;
  expect(tube.visible).toBe(true);expect(fibers.visible).toBe(true);
  expect(fibers.geometry.getAttribute('position').count).toBe(600);
  const readPath=()=>view.overlayRef.current!.querySelector('path')!.getAttribute('d')!;
  const project=(point:THREE.Vector3)=>{const p=point.clone().project(view.store.getState().camera);return [(p.x+1)*720,(1-p.y)*450];};
  const initial=readPath(), match=initial.match(/^M ([\d.-]+) ([\d.-]+)/)!;
  const [x,y]=project(tube.material.uniforms.p0.value);expect(x).toBeCloseTo(Number(match[1]),4);expect(y).toBeCloseTo(Number(match[2]),4);
  expect(fibers.material.uniforms.reach.value).toBe(1);
  now=3000;act(()=>closeWorkspace(view.first.id));await view.sync();
  expect(tube.visible).toBe(true);expect(fibers.visible).toBe(true);
  now=3650;setBodyGroupWorldMatrix(new THREE.Matrix4().makeTranslation(2,0,0));await view.sync();
  expect(readPath()).not.toBe(initial);
  expect(tube.material.uniforms.reach.value).toBeCloseTo(.5,4);
  expect(fibers.material.uniforms.reach.value).toBeCloseTo(.5,4);
  now=4300;await view.sync();expect(tube.visible).toBe(false);expect(fibers.visible).toBe(false);
  expect(getTabStoreSnapshot().recoverableTabs?.find(tab=>tab.id===view.first.id)?.content?.code).toBe('first retained content');
  await view.close();
});

it('keeps one decorative return after immediate Close, then retires its actual GPU paint on the existing timeline',async()=>{
  let now=1000;vi.spyOn(performance,'now').mockImplementation(()=>now);
  const view=await mount(false);
  const rim=view.scene.getObjectByName('workspace-contact-rim') as THREE.Points<THREE.BufferGeometry,THREE.ShaderMaterial>;
  expect(rim).toBeTruthy();expect(rim.visible).toBe(true);
  expect(rim.material.uniforms.uVisible.value).toBe(1);
  expect(rim.material.uniforms.uUnfurl.value).toBe(1);
  const positions=rim.geometry.getAttribute('position');
  expect(positions.count).toBe(2400);expect(positions.getX(0)).toBeGreaterThan(0);
  expect(rim.material.uniforms.uViewport.value.toArray()).toEqual([1440,900]);
  expect(view.scene.getObjectsByProperty('name','workspace-contact-rim')).toHaveLength(1);
  now=3000;act(()=>closeWorkspace(view.first.id));await view.sync();
  expect(getTabStoreSnapshot().focusId).toBeNull();
  expect(getTabStoreSnapshot().recoverableTabs?.some(tab=>tab.id===view.first.id)).toBe(true);
  expect(rim.visible).toBe(true);expect(rim.material.uniforms.uReturning?.value).toBe(1);
  now=3650;await view.sync();
  expect(rim.material.uniforms.uReturnTime?.value).toBe(.5);
  expect(rim.geometry.getAttribute('position')).toBe(positions);
  now=4300;await view.sync();
  expect(rim.visible).toBe(false);expect(rim.material.uniforms.uVisible.value).toBe(0);
  await view.close();
});

it.each([0,16])('preserves painted coverage and displacement when Close interrupts unfurl at %sms',async delta=>{
  let now=1000;vi.spyOn(performance,'now').mockImplementation(()=>now);
  const view=await mount(false,true,'beginner',true);
  try {
    act(()=>setMaterializedTabLifecycle(view.first.id,'unfurling',3000));now=3000+delta;await view.sync();
    const rim=view.scene.getObjectByName('workspace-contact-rim') as THREE.Points<THREE.BufferGeometry,THREE.ShaderMaterial>;
    const data=rim.geometry.getAttribute('aData'),normal=rim.geometry.getAttribute('aOutward'),position=rim.geometry.getAttribute('position');
    const alpha=new Float32Array(data.count),pixels=new Float32Array(data.count*2);
    const origin=rim.material.uniforms.uOrigin.value,unfurl=rim.material.uniforms.uUnfurl.value;
    const smooth=(lo:number,hi:number,x:number)=>{const t=Math.min(1,Math.max(0,(x-lo)/(hi-lo)));return t*t*(3-2*t);};
    // Independent oracle for the current birth shader, before RETURN can
    // mutate its buffers. These are CPU/installed-object witnesses, not pixels.
    const spread=1-Math.pow(1-unfurl,3);let painted=0;
    for(let i=0;i<data.count;i++) {
      const separation=Math.abs(data.getX(i)-origin),travel=Math.min(separation,1-separation)*2;
      const born=smooth(travel*.82,travel*.82+.18,spread),settle=smooth(0,.20,spread-travel*.82);
      alpha[i]=born*(.38+.46*data.getY(i)+.32*(1-settle));
      pixels[i*2]=position.getX(i)+normal.getX(i)*(1-settle)*10;
      pixels[i*2+1]=position.getY(i)+normal.getY(i)*(1-settle)*10;
      if(alpha[i]>.002)painted++;
    }
    if(delta===0)expect(painted).toBe(0);else{expect(painted).toBeGreaterThan(0);expect(painted).toBeLessThan(data.count);}
    now=3500;act(()=>closeWorkspace(view.first.id));await view.sync();
    if(painted===0)expect(rim.visible,'unpainted tissue must never appear on dismissal').toBe(false);
    else {
      expect(rim.visible).toBe(true);const returningAlpha=rim.geometry.getAttribute('aReturnAlpha');let returned=0;
      for(let i=0;i<data.count;i++) {
        expect(returningAlpha.getX(i)).toBeCloseTo(alpha[i],6);
        if(returningAlpha.getX(i)>.002) {
          returned++;expect(position.getX(i)).toBeCloseTo(pixels[i*2],3);expect(position.getY(i)).toBeCloseTo(pixels[i*2+1],3);
        }
      }
      expect(returned).toBe(painted);
    }
    expect(getTabStoreSnapshot().focusId).toBeNull();
    expect(getTabStoreSnapshot().recoverableTabs?.find(tab=>tab.id===view.first.id)?.content?.code).toBe('first retained content');
  } finally {await view.close();}
});

it.each([false, true])('keeps the mounted nerve with canonical work/hold/stop while an older reader returns (reduced=%s)', async reducedMotion => {
  vi.spyOn(performance, 'now').mockReturnValue(10000);
  const project = (stop: 'engaged' | 'clear', approvalPending = false) => derivePhysicalSnapshot(deriveBeingPresentation({
    lifecycle: 'reabsorbing', transport: 'connected', projection: 'fresh', mirrorStatus: 'online', hasSnapshot: true,
    taskActivity: 'streaming', verification: 'unknown', stop, approvalPending,
  }));
  const view = await mount(reducedMotion, false, 'beginner', false, true, project('engaged'));
  try {
    act(() => {
      const current = showContentSurface({ filepath: 'currently-working.txt', language: 'text', code: 'current partial', streaming: true }, getContentSurfacePlacement(8));
      setMaterializedTabLifecycle(current.id, 'live');
    });
    await view.sync();
    const owner = view.scene.children.find(node => node.getObjectByName('text:currently-working.txt'))!;
    const tube = owner.children.find(node => node instanceof THREE.Mesh && node.renderOrder === 6) as THREE.Mesh<THREE.TubeGeometry, THREE.MeshStandardMaterial>;
    const material = tube.material;
    const baseColor = material.color.clone(), baseEmissive = material.emissive.clone();
    act(() => closeWorkspace(view.first.id));
    for (const [physical, rgb, tint] of [
      [project('clear'), [123, 245, 251], 0.434],
      [project('clear', true), [255, 126, 64], 0.31],
      [project('engaged'), [158, 120, 245], 0],
    ] as const) {
      await view.setPhysical(physical);
      // Reduced motion retires the older record synchronously in its frame.
      // Paint the resulting committed snapshot before reading live materials.
      await view.sync();
      expect(view.scene.getObjectById(tube.id)).toBe(tube);
      expect(tube.material).toBe(material);
      const target = new THREE.Color(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255);
      const wantColor = baseColor.clone().lerp(target, tint).toArray();
      const wantEmissive = baseEmissive.clone().lerp(target, tint).toArray();
      for (let index = 0; index < 3; index++) {
        expect(material.color.toArray()[index]).toBeCloseTo(wantColor[index], 6);
        expect(material.emissive.toArray()[index]).toBeCloseTo(wantEmissive[index], 6);
      }
      const older = getTabStoreSnapshot().tabs.find(tab => tab.id === view.first.id);
      if (reducedMotion) expect(older).toBeUndefined();
      else expect(older?.lifecycle).toBe('retracting');
      expect(getTabStoreSnapshot().recoverableTabs?.some(tab => tab.id === view.first.id)).toBe(true);
    }
  } finally { await view.close(); }
});

it.each([false, true])('retargets a moving HUD nerve without replacing its geometry or buffers (reduced=%s)', async reducedMotion => {
  const view = await mount(reducedMotion, true, 'beginner', false, true);
  let dispose: ReturnType<typeof vi.spyOn> | undefined;
  let closed = false;
  try {
    act(() => {
      const other = showContentSurface({ filepath: 'allocation-peer.txt', language: 'text', code: 'peer' }, getContentSurfacePlacement(8));
      setMaterializedTabLifecycle(other.id, 'live'); focusWorkspace(other.id);
    });
    await view.sync();
    const owner = view.scene.children.find(node => node.getObjectByName('text:first.txt'))!;
    const tube = owner.children.find(node => node instanceof THREE.Mesh && node.renderOrder === 6) as THREE.Mesh<THREE.TubeGeometry>;
    const geometry = tube.geometry, material = tube.material;
    const position = geometry.getAttribute('position'), normal = geometry.getAttribute('normal');
    if (!(position instanceof THREE.BufferAttribute)) throw new Error('TubeGeometry must own a non-interleaved position buffer');
    if (!(normal instanceof THREE.BufferAttribute)) throw new Error('TubeGeometry must own a non-interleaved normal buffer');
    const uv = geometry.getAttribute('uv'), index = geometry.getIndex()!;
    const buffers = [position.array, normal.array, uv.array, index.array];
    const originalPositions = Array.from(position.array);
    const version = position.version, normalVersion = normal.version;
    geometry.computeBoundingBox(); geometry.computeBoundingSphere();
    dispose = vi.spyOn(geometry, 'dispose');
    for (const scale of [0.73, 0.91, 0.64]) {
      act(() => setBrainDockScale(scale));
      await view.sync();
      expect(tube.geometry).toBe(geometry);
      expect(tube.material).toBe(material);
      expect([geometry.getAttribute('position'), geometry.getAttribute('normal'), geometry.getAttribute('uv'), geometry.getIndex()])
        .toEqual([position, normal, uv, index]);
      for (const [at, attribute] of [position, normal, uv, index].entries()) expect(attribute.array).toBe(buffers[at]);
      // Seat2 is independent of the curve factory and buffer updater.
      const anchor = new THREE.Vector3(0, -0.92 - 1.93 * 2 / 11, -0.42 + 0.04 * Math.sin(Math.PI * 2 / 11)).multiplyScalar(scale);
      expect(geometry.parameters.path.getPoint(0).distanceTo(anchor)).toBeLessThan(1e-6);
      expect(position.count).toBe(363); expect(index.count).toBe(1920);
      const reference = new THREE.TubeGeometry(geometry.parameters.path, 32, geometry.parameters.radius, 10, false);
      try {
        for (const name of ['position', 'normal', 'uv']) expect(Array.from(geometry.getAttribute(name).array)).toEqual(Array.from(reference.getAttribute(name).array));
        expect(Array.from(index.array)).toEqual(Array.from(reference.getIndex()!.array));
        reference.computeBoundingBox(); reference.computeBoundingSphere();
        expect(geometry.boundingBox).toEqual(reference.boundingBox);
        expect(geometry.boundingSphere).toEqual(reference.boundingSphere);
      } finally { reference.dispose(); }
      expect(dispose).not.toHaveBeenCalled();
    }
    expect(Array.from(position.array)).not.toEqual(originalPositions);
    expect(position.version).toBeGreaterThan(version);
    expect(normal.version).toBeGreaterThan(normalVersion);
    await view.close(); closed = true;
    expect(dispose).toHaveBeenCalledTimes(1);
  } finally { if (!closed) await view.close(); dispose?.mockRestore(); }
});

it.each(['reaching', 'retracting'] as const)('keeps the partial nerve reveal on the retarget frame during HUD %s', async lifecycle => {
  let now = 10000;
  vi.spyOn(performance, 'now').mockImplementation(() => now);
  const view = await mount(false, true, 'beginner', false, true);
  try {
    act(() => {
      const other = showContentSurface({ filepath: 'draw-range-peer.txt', language: 'text', code: 'peer' }, getContentSurfacePlacement(8));
      setMaterializedTabLifecycle(other.id, 'live'); focusWorkspace(other.id);
    });
    await view.sync();
    const owner = view.scene.children.find(node => node.getObjectByName('text:first.txt'))!;
    const tube = owner.children.find(node => node instanceof THREE.Mesh && node.renderOrder === 6) as THREE.Mesh<THREE.TubeGeometry>;
    const geometry = tube.geometry;
    act(() => {
      if (lifecycle === 'retracting') closeWorkspace(view.first.id);
      else setMaterializedTabLifecycle(view.first.id, lifecycle, now);
    });
    now += lifecycle === 'reaching' ? 150 : 1000;
    await view.sync();
    // A settled frame has the original partial lifecycle reveal.
    act(() => advance(1, false, view.store.getState()));
    expect(geometry.drawRange.count).toBeGreaterThan(0);
    expect(geometry.drawRange.count).toBeLessThan(geometry.getIndex()!.count);
    const visibleCount = geometry.drawRange.count;
    const position = geometry.getAttribute('position') as THREE.BufferAttribute;
    const positionVersion = position.version;
    act(() => setBrainDockScale(0.64));
    await view.sync();
    expect(tube.geometry).toBe(geometry);
    expect(position.version).toBeGreaterThan(positionVersion);
    // Retargeting changes the curve, not how much lifecycle progress is painted.
    expect(geometry.drawRange).toEqual({ start: 0, count: visibleCount });
    act(() => advance(1, false, view.store.getState()));
    expect(geometry.drawRange.count).toBeGreaterThan(0);
    expect(geometry.drawRange.count).toBeLessThan(geometry.getIndex()!.count);
  } finally { await view.close(); }
});

it.each([[false, 3], [true, 3], [false, 11], [true, 11]] as const)('fits and separates background slab vertices through current camera pane, focus and resize (reduced=%s, waiting=%s)', async (reducedMotion, backgroundCount) => {
  // This case observes the still-painted closing slab as well as its eventual
  // disappearance. Async renderer work must not choose that lifecycle instant.
  let now = 10000; // integer origin keeps exact millisecond boundaries representable
  vi.spyOn(performance, 'now').mockImplementation(() => now);
  const view = await mount(reducedMotion, true, 'beginner', false, true);
  try {
    act(() => {
      const seats = backgroundCount === 3 ? [4, 8, 10] : Array.from({ length: 12 }, (_, index) => index).filter(seat => seat !== 2);
      for (const seat of seats) {
        const tab = showContentSurface({ filepath: `background-${seat}.txt`, language: 'text', code: 'retained background work' }, getContentSurfacePlacement(seat));
        setMaterializedTabLifecycle(tab.id, 'live');
      }
      focusWorkspace(view.first.id);
    });
    let expectedPaintedSlabs = backgroundCount;
    const point = new THREE.Vector3(), pixel = new THREE.Vector2();
    const check = async (width: number, height: number, left: number, top: number, separated = false) => {
      const camera = view.store.getState().camera as THREE.PerspectiveCamera;
      camera.setViewOffset(width, height, -left, -top, 1440, 900);
      await view.sync(); view.scene.updateMatrixWorld(true);
      let slabs = 0;
      const centers: THREE.Vector2[] = [];
      const paintedBoxes: THREE.Box2[] = [];
      for (const root of view.scene.children) {
        if (!root.visible) continue;
        root.traverse(node => {
          if (!(node instanceof THREE.Mesh) || node.geometry.type !== 'ExtrudeGeometry') return;
          slabs++;
          const positions = node.geometry.getAttribute('position');
          const box = new THREE.Box2();
          for (let vertex = 0; vertex < positions.count; vertex++) {
            point.fromBufferAttribute(positions, vertex).applyMatrix4(node.matrixWorld).project(camera);
            box.expandByPoint(pixel.set((point.x + 1) * 720, (1 - point.y) * 450));
          }
          const marginX = Math.min(12, width / 5), marginY = Math.min(12, height / 5);
          expect.soft(box.min.x).toBeGreaterThanOrEqual(left + marginX);
          expect.soft(box.max.x).toBeLessThanOrEqual(left + width - marginX);
          expect.soft(box.min.y).toBeGreaterThanOrEqual(top + marginY);
          expect.soft(box.max.y).toBeLessThanOrEqual(top + height - marginY);
          centers.push(box.getCenter(new THREE.Vector2()));
          paintedBoxes.push(box);
        });
      }
      // Include every added point and its maximum 1 CSS-pixel raster radius;
      // the existing mesh-only framing assertion cannot establish this boundary.
      let dustCount=0;
      for (const dust of view.scene.getObjectsByProperty('name','waiting-workspace-edge') as THREE.Points[]) {
        let visible=true;for(let owner:THREE.Object3D|null=dust;owner;owner=owner.parent)if(!owner.visible)visible=false;
        if(!visible)continue;
        dustCount++;
        const positions=dust.geometry.getAttribute('position');
        for(let vertex=0;vertex<positions.count;vertex++){
          point.fromBufferAttribute(positions,vertex).applyMatrix4(dust.matrixWorld).project(camera);
          const x=(point.x+1)*720,y=(1-point.y)*450;
          expect.soft(x-1).toBeGreaterThanOrEqual(left);expect.soft(x+1).toBeLessThanOrEqual(left+width);
          expect.soft(y-1).toBeGreaterThanOrEqual(top);expect.soft(y+1).toBeLessThanOrEqual(top+height);
        }
      }
      // This lab baseline paints dust only on its first two waiting surfaces.
      expect(dustCount).toBe(Math.min(2, expectedPaintedSlabs));
      expect(slabs).toBe(expectedPaintedSlabs); // Only the actual dissolve boundary may remove paint.
      for (let index = 0; index < centers.length; index++) {
        for (const other of centers.slice(index + 1)) expect.soft(centers[index].distanceTo(other)).toBeGreaterThan(1);
      }
      if (separated) for (let index = 0; index < paintedBoxes.length; index++) {
        for (const other of paintedBoxes.slice(index + 1)) expect.soft(paintedBoxes[index].intersectsBox(other)).toBe(false);
      }
      expect(screen.getByRole('region', { name: 'Selected workspace' })).toBeVisible();
    };
    await check(460, 720, 0, 180);
    const camera = view.store.getState().camera;
    camera.position.set(7, 2, 7); camera.lookAt(0, 0, 0); camera.updateMatrixWorld(true);
    await check(330, 460, 12, 250);
    // Real product lens and inherited body transform, not a wide/unscaled
    // surrogate. Positive exhausted panes still need an explicit fit policy.
    view.scene.scale.setScalar(3.02);
    (camera as THREE.PerspectiveCamera).fov = 24;
    await check(366, 56, 12, 250);
    await check(366, 20, 12, 250);
    act(() => focusWorkspace(getTabStoreSnapshot().tabs.find(tab => tab.seatIndex === 8)!.id));
    // Focus changes which actual slab yields to its persistent reader.
    await check(460, 720, 0, 180);
    expect(screen.getByText('retained background work')).toBeVisible();
    if (backgroundCount === 11) {
      const original = getTabStoreSnapshot().tabs.map(tab => ({ id: tab.id, seatIndex: tab.seatIndex }));
      const selected = getTabStoreSnapshot().focusId;
      const reader = screen.getByRole('region', { name: 'Selected workspace' });
      await check(460, 720, 0, 180, true);
      const closing = getTabStoreSnapshot().tabs.find(tab => tab.seatIndex === 4)!;
      act(() => { closeWorkspace(closing.id); });
      if (reducedMotion) expectedPaintedSlabs--; // existing immediate reduced-motion retirement
      // The closing slab is still painted: it must not borrow the first live
      // waiting slot. This also checks the real retained DOM consumer.
      await check(460, 720, 0, 180, true);
      expect(getTabStoreSnapshot().tabs.map(tab => ({ id: tab.id, seatIndex: tab.seatIndex })))
        .toEqual(reducedMotion ? original.filter(tab => tab.id !== closing.id) : original);
      expect(getTabStoreSnapshot().focusId).toBe(selected);
      expect(screen.getByRole('region', { name: 'Selected workspace' })).toBe(reader);
      expect(screen.getByText('retained background work')).toBeVisible();
      if (!reducedMotion) {
        // Keep every existing outline/vertex/pair check at the last painted
        // instant, then prove that the record outlives its dissolved slab.
        now += POINTS_SLAB_RETRACT_MS - 1;
        await check(460, 720, 0, 180, true);
        expect(getTabStoreSnapshot().tabs.map(tab => tab.id)).toEqual(original.map(tab => tab.id));
        now++;
        expectedPaintedSlabs--;
        await check(460, 720, 0, 180, true);
        expect(getTabStoreSnapshot().tabs.map(tab => tab.id)).toEqual(original.map(tab => tab.id));
        now += POINTS_REABSORPTION_MS - POINTS_SLAB_RETRACT_MS;
        await check(460, 720, 0, 180, true);
        expect(getTabStoreSnapshot().tabs.map(tab => tab.id)).toEqual(original.filter(tab => tab.id !== closing.id).map(tab => tab.id));
        expect(getTabStoreSnapshot().recoverableTabs?.map(tab => tab.id)).toContain(closing.id);
        expect(getTabStoreSnapshot().focusId).toBe(selected);
        expect(screen.getByRole('region', { name: 'Selected workspace' })).toBe(reader);
      }
    }
  } finally { await view.close(); }
});

it.each([false, true])('keeps eleven waiting outlines separate from the mounted cortex when the paired side budget is exhausted (reduced=%s)', async reducedMotion => {
  const view = await mount(reducedMotion, true, 'beginner', false, true);
  // Controlled mounted geometry exercises the real shape publisher and Layer,
  // not a mocked fit helper. Its world envelope is the review's ±.35/±.2 witness.
  // This is numerical surface/consumer proof, not the protected GLB or GPU.
  view.scene.scale.setScalar(3.02);
  const geometry = new THREE.BoxGeometry(0.7 / 3.02, 0.4 / 3.02, 0.02 / 3.02);
  geometry.computeBoundingBox();
  const material = new THREE.MeshBasicMaterial();
  const head = new THREE.Mesh(geometry, material);
  view.scene.add(head); setCortexShape(head, geometry.boundingBox!);
  try {
    act(() => {
      for (const seat of [0, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11]) {
        const tab = showContentSurface({ filepath: `cramped-${seat}.txt`, language: 'text', code: 'retained cramped work' }, getContentSurfacePlacement(seat));
        setMaterializedTabLifecycle(tab.id, 'live');
      }
      focusWorkspace(view.first.id);
    });
    const reader = screen.getByRole('region', { name: 'Selected workspace' });
    const ids = getTabStoreSnapshot().tabs.map(tab => tab.id);
    const camera = view.store.getState().camera as THREE.PerspectiveCamera;
    camera.fov = 24;
    for (const [width, height] of [[20, 56], [56, 20], [460, 720]] as const) {
      camera.setViewOffset(width, height, -12, -250, 1440, 900);
      await view.sync(); view.scene.updateMatrixWorld(true); camera.updateMatrixWorld();
      const projectOutline = (mesh: THREE.Mesh) => {
        const box = new THREE.Box2(), positions = mesh.geometry.getAttribute('position');
        for (let vertex = 0; vertex < positions.count; vertex++) {
          const point = new THREE.Vector3().fromBufferAttribute(positions, vertex).applyMatrix4(mesh.matrixWorld).project(camera);
          box.expandByPoint(new THREE.Vector2((point.x + 1) * 720, (1 - point.y) * 450));
        }
        return box;
      };
      const cortex = projectOutline(head), slabs: THREE.Box2[] = [];
      view.scene.traverse(node => {
        if (!(node instanceof THREE.Mesh) || node.geometry.type !== 'ExtrudeGeometry') return;
        for (let owner: THREE.Object3D | null = node; owner; owner = owner.parent) if (!owner.visible) return;
        slabs.push(projectOutline(node));
      });
      expect(slabs).toHaveLength(11); // No silent removal, zero-scale or count waiver.
      for (const slab of slabs) {
        expect.soft(slab.max.x - slab.min.x).toBeGreaterThan(0);
        expect.soft(slab.max.y - slab.min.y).toBeGreaterThan(0);
        expect.soft(slab.intersectsBox(cortex), JSON.stringify({ width, height, slab, cortex })).toBe(false);
        expect.soft(slab.min.x).toBeGreaterThanOrEqual(12 + Math.min(12, width / 5));
        expect.soft(slab.max.x).toBeLessThanOrEqual(12 + width - Math.min(12, width / 5));
        expect.soft(slab.min.y).toBeGreaterThanOrEqual(250 + Math.min(12, height / 5));
        expect.soft(slab.max.y).toBeLessThanOrEqual(250 + height - Math.min(12, height / 5));
      }
      for (let index = 0; index < slabs.length; index++) for (const other of slabs.slice(index + 1)) {
        expect.soft(slabs[index].intersectsBox(other), JSON.stringify({ width, height, slab: slabs[index], other })).toBe(false);
      }
      expect(getTabStoreSnapshot().tabs.map(tab => tab.id)).toEqual(ids);
      expect(getTabStoreSnapshot().focusId).toBe(view.first.id);
      expect(screen.getByRole('region', { name: 'Selected workspace' })).toBe(reader);
      expect(screen.getByText('first retained content')).toBeVisible();
    }
  } finally { head.removeFromParent(); geometry.dispose(); material.dispose(); await view.close(); }
});

it('keeps eleven simultaneously retiring slabs in distinct painted slots with no focused workspace', async () => {
  // Freeze the actual admission/retirement clock before any async renderer work.
  // Date.now is unrelated: runner contention could otherwise consume the slab
  // lifetime during sync and test only an arbitrary subset of eleven identities.
  let now = 10000; // integer origin keeps exact millisecond boundaries representable
  vi.spyOn(performance, 'now').mockImplementation(() => now);
  const view = await mount(false, false, 'beginner', false, true);
  try {
    act(() => {
      for (const seat of [0, 1, 3, 4, 5, 6, 7, 8, 9, 10]) {
        const tab = showContentSurface({ filepath: `retiring-${seat}.txt`, language: 'text', code: 'retained' }, getContentSurfacePlacement(seat));
        setMaterializedTabLifecycle(tab.id, 'live');
      }
    });
    await view.sync();
    const originalIds = getTabStoreSnapshot().tabs.map(tab => tab.id);
    act(() => { for (const id of originalIds) closeWorkspace(id); });
    await view.sync(); view.scene.updateMatrixWorld(true);
    const boxes: THREE.Box2[] = [];
    view.scene.traverse(node => {
      if (!(node instanceof THREE.Mesh) || node.geometry.type !== 'ExtrudeGeometry') return;
      for (let owner: THREE.Object3D | null = node; owner; owner = owner.parent) if (!owner.visible) return;
      const box = new THREE.Box2(), vertices = node.geometry.getAttribute('position');
      for (let vertex = 0; vertex < vertices.count; vertex++) {
        const point = new THREE.Vector3().fromBufferAttribute(vertices, vertex).applyMatrix4(node.matrixWorld).project(view.store.getState().camera);
        box.expandByPoint(new THREE.Vector2((point.x + 1) * 720, (1 - point.y) * 450));
      }
      boxes.push(box);
    });
    expect(boxes).toHaveLength(11);
    for (let index = 0; index < boxes.length; index++) for (const other of boxes.slice(index + 1)) {
      expect.soft(boxes[index].intersectsBox(other)).toBe(false);
    }
    expect(getTabStoreSnapshot().tabs.map(tab => tab.id)).toEqual(originalIds);
    expect(getTabStoreSnapshot().tabs.every(tab => tab.lifecycle === 'retracting')).toBe(true);
    expect(getTabStoreSnapshot().focusId).toBeNull();

    const paintedCount = () => {
      let count = 0;
      view.scene.traverse(node => {
        if (!(node instanceof THREE.Mesh) || node.geometry.type !== 'ExtrudeGeometry') return;
        for (let owner: THREE.Object3D | null = node; owner; owner = owner.parent) if (!owner.visible) return;
        count++;
      });
      return count;
    };
    // The timeline is controlled, not disabled. The eleven slabs still paint
    // until the existing dissolve boundary; records survive for their return.
    now += POINTS_SLAB_RETRACT_MS - 1;
    await view.sync();
    expect(paintedCount()).toBe(11);
    now++;
    await view.sync();
    expect(paintedCount(), JSON.stringify({ now, phases: getTabStoreSnapshot().tabs.map(tab => ({
      id: tab.id, lifecycle: tab.lifecycle, elapsed: now - tab.phaseStartedAt,
    })) })).toBe(0);
    expect(getTabStoreSnapshot().tabs.map(tab => tab.id)).toEqual(originalIds);
    now += POINTS_REABSORPTION_MS - POINTS_SLAB_RETRACT_MS;
    await view.sync();
    expect(getTabStoreSnapshot().tabs, JSON.stringify({ now, phases: getTabStoreSnapshot().tabs.map(tab => ({
      id: tab.id, lifecycle: tab.lifecycle, elapsed: now - tab.phaseStartedAt,
    })) })).toHaveLength(0);
    expect(getTabStoreSnapshot().recoverableTabs?.map(tab => tab.id)).toEqual(originalIds);
  } finally { await view.close(); }
});

it.each([false, true])('actual orchestration retains each workspace nerve/socket seat across attention, insertion and body docking (reduced=%s)', async reducedMotion => {
  const view = await mount(reducedMotion, true, 'beginner', false, true);
  try {
    const reader = screen.getByText('first retained content');
    const readingBody = reader.closest<HTMLElement>('.lm-surface__body')!;
    readingBody.scrollTop = 70; fireEvent.scroll(readingBody);
    let lowerId = '';
    act(() => {
      const middle = showContentSurface({ filepath: 'middle.txt', language: 'text', code: 'middle result' }, getContentSurfacePlacement(4));
      const lower = showContentSurface({ filepath: 'lower.txt', language: 'text', code: 'lower result' }, getContentSurfacePlacement(8));
      lowerId = lower.id;
      setMaterializedTabLifecycle(middle.id, 'live'); setMaterializedTabLifecycle(lower.id, 'live');
      focusWorkspace(view.first.id);
    });
    await view.sync();
    const lowerRoot = view.scene.children.find(root => root.getObjectByName('text:lower.txt'))!;
    const tube = lowerRoot.children.find(node => node instanceof THREE.Mesh && node.renderOrder === 6) as THREE.Mesh<THREE.TubeGeometry>;
    const socket = lowerRoot.children.find(node => node instanceof THREE.Mesh && node.renderOrder === 7) as THREE.Mesh;
    // Hand-derived seat8 from the twelve-anchor cord: y=-.92-1.93*(8/11),
    // z=-.42+.04*sin(pi*8/11). Not a curve/projection helper under test.
    const anchor = new THREE.Vector3(0, -0.92 - 1.93 * 8 / 11, -0.42 + 0.04 * Math.sin(Math.PI * 8 / 11));
    let fusionScale = 1;
    const weld = new THREE.Vector3();
    const checkAnchor = (scale: number) => {
      const expected = anchor.clone().multiplyScalar(fusionScale).add(weld).multiplyScalar(scale);
      expect.soft(tube.geometry.parameters.path.getPoint(0).distanceTo(expected)).toBeLessThan(1e-6);
      expect.soft(socket.position.distanceTo(expected)).toBeLessThan(1e-6);
      expect(getTabStoreSnapshot().tabs.find(tab => tab.id === lowerId)?.seatIndex).toBe(8);
      for (const [name, seat] of [['first.txt', 2], ['middle.txt', 4], ['later.txt', 10], ['upper.txt', 1]] as const) {
        const root = view.scene.children.find(node => node.getObjectByName(`text:${name}`));
        if (!root) continue; // later/upper have not yet been inserted
        const retainedTube = root.children.find(node => node instanceof THREE.Mesh && node.renderOrder === 6) as THREE.Mesh<THREE.TubeGeometry>;
        const retainedSocket = root.children.find(node => node instanceof THREE.Mesh && node.renderOrder === 7) as THREE.Mesh;
        const ownAnchor = new THREE.Vector3(0, -0.92 - 1.93 * seat / 11, -0.42 + 0.04 * Math.sin(Math.PI * seat / 11))
          .multiplyScalar(fusionScale).add(weld).multiplyScalar(scale);
        expect.soft(retainedTube.geometry.parameters.path.getPoint(0).distanceTo(ownAnchor), name).toBeLessThan(1e-6);
        expect.soft(retainedSocket.position.distanceTo(ownAnchor), name).toBeLessThan(1e-6);
      }
    };
    expect(lowerRoot.visible).toBe(true);
    checkAnchor(1);
    // A later insertion preserves both waiting index and endpoint. React still
    // replaces declarative geometry when the work count changes; a valid
    // position cache must not bless a newly installed standalone tube.
    act(() => {
      const later = showContentSurface({ filepath: 'later.txt', language: 'text', code: 'later result' }, getContentSurfacePlacement(10));
      setMaterializedTabLifecycle(later.id, 'live');
    });
    await view.sync(); checkAnchor(1);
    // Inserting an earlier conductor seat changes waitingIndex, not identity.
    act(() => {
      const upper = showContentSurface({ filepath: 'upper.txt', language: 'text', code: 'upper result' }, getContentSurfacePlacement(1));
      setMaterializedTabLifecycle(upper.id, 'live');
    });
    await view.sync(); checkAnchor(1);
    // Endpoints remain still at this frame; a changed body origin alone must
    // refresh the live nerve, not leave it attached to the old unshrunk body.
    act(() => setBrainDockScale(0.73));
    await view.sync(); checkAnchor(0.73);
    fusionScale = 0.86; weld.set(0.12, -0.04, 0.09);
    act(() => setSpineFusion(fusionScale, [weld.x, weld.y, weld.z]));
    await view.sync(); checkAnchor(0.73);
    act(() => focusWorkspace(lowerId)); await view.sync();
    expect(lowerRoot.visible).toBe(false); // same result yields to its real DOM owner
    expect(screen.getByText('lower result')).toBeVisible();
    checkAnchor(0.73);
    const projected = anchor.clone().multiplyScalar(fusionScale).add(weld).multiplyScalar(0.73).project(view.store.getState().camera);
    const sourceX = Math.round((projected.x + 1) * 1440 / 2 * 2) / 2;
    const sourceY = Math.round((1 - projected.y) * 900 / 2 * 2) / 2;
    expect(view.overlayRef.current!.querySelector('path')!.getAttribute('d')).toMatch(new RegExp(`^M ${sourceX} ${sourceY} `));
    act(() => focusWorkspace(view.first.id)); await view.sync();
    expect(lowerRoot.visible).toBe(true); checkAnchor(0.73);
    expect(screen.getByText('first retained content')).toBe(reader);
    expect(readingBody.scrollTop).toBe(70);
  } finally { await view.close(); }
});

it.each([false, true])('reuses the live HUD tube and restores the one-workspace fallback socket with once-only retirement disposal (reduced=%s)', async reducedMotion => {
  const view = await mount(reducedMotion, true, 'beginner', false, true);
  const disposals: ReturnType<typeof vi.spyOn>[] = [];
  let closed = false;
  try {
    let otherId = '';
    act(() => {
      const other = showContentSurface({ filepath: 'other.txt', language: 'text', code: 'other result' }, getContentSurfacePlacement(8));
      otherId = other.id; setMaterializedTabLifecycle(otherId, 'live'); focusWorkspace(otherId);
      setBrainDockScale(0.73);
    });
    await view.sync();
    const firstRoot = view.scene.children.find(root => root.getObjectByName('text:first.txt'))!;
    const tube = firstRoot.children.find(node => node instanceof THREE.Mesh && node.renderOrder === 6) as THREE.Mesh<THREE.TubeGeometry>;
    const socket = firstRoot.children.find(node => node instanceof THREE.Mesh && node.renderOrder === 7) as THREE.Mesh;
    const initialHud = tube.geometry;
    const disposeInitial = vi.spyOn(initialHud, 'dispose'); disposals.push(disposeInitial);
    // Exact same stationary endpoint/root: no frame-loop allocation/disposal.
    for (let frame = 0; frame < 30; frame++) act(() => advance(1, false, view.store.getState()));
    expect(tube.geometry).toBe(initialHud); expect(disposeInitial).not.toHaveBeenCalled();
    let laterId = '';
    act(() => {
      const later = showContentSurface({ filepath: 'later.txt', language: 'text', code: 'later result' }, getContentSurfacePlacement(10));
      laterId = later.id; setMaterializedTabLifecycle(laterId, 'live');
    });
    await view.sync();
    expect(tube.geometry).toBe(initialHud);
    expect(disposeInitial).not.toHaveBeenCalled();
    act(() => {
      for (const id of [otherId, laterId]) {
        closeWorkspace(id);
        const retiring = getTabStoreSnapshot().tabs.find(tab => tab.id === id)!;
        finishMaterializedTabRetraction(id, retiring.retractionToken);
      }
    });
    await view.sync();
    // Closing other results releases attention, rather than implicitly
    // selecting this one. Explicitly select it to test its reader-loss fallback.
    act(() => focusWorkspace(view.first.id)); await view.sync();
    expect(getTabStoreSnapshot().focusId).toBe(view.first.id);
    expect(firstRoot.visible).toBe(false);
    // The real selected reader owns the last result until it becomes missing.
    await act(async () => { view.dom.container.querySelector<HTMLElement>('.lm-surface')!.hidden = true; });
    await view.sync();
    expect(firstRoot.visible).toBe(true);
    const fallbackOrigin = new THREE.Vector3(...getTabStoreSnapshot().tabs[0].originLocal);
    expect.soft(tube.geometry.parameters.path.getPoint(0).distanceTo(fallbackOrigin)).toBeLessThan(1e-6);
    expect.soft(socket.position.distanceTo(fallbackOrigin)).toBeLessThan(1e-6);
    expect.soft(disposeInitial).toHaveBeenCalledTimes(1);
    expect(tube.geometry).not.toBe(initialHud);
    // Return to orchestration, then unmount with a live dynamic tube installed.
    act(() => {
      const final = showContentSurface({ filepath: 'final.txt', language: 'text', code: 'final result' }, getContentSurfacePlacement(8));
      setMaterializedTabLifecycle(final.id, 'live'); focusWorkspace(final.id);
    });
    await view.sync();
    const finalHud = tube.geometry, disposeFinal = vi.spyOn(finalHud, 'dispose'); disposals.push(disposeFinal);
    expect(finalHud).not.toBe(initialHud);
    await view.close(); closed = true;
    expect.soft(disposeFinal).toHaveBeenCalledTimes(1);
    expect.soft(disposeInitial).toHaveBeenCalledTimes(1);
  } finally { if (!closed) await view.close(); for (const spy of disposals) spy.mockRestore(); }
});

it('an explicitly unseated standalone background placement keeps its own root through dock and fusion changes', async () => {
  const view = await mount(true, false);
  try {
    act(() => {
      updateMaterializedTab(view.first.id, { seatIndex: undefined, originLocal: [0.3, -1.4, 0.2] });
      const other = showContentSurface({ filepath: 'other.txt', language: 'text', code: 'other result' }, getContentSurfacePlacement(8));
      setMaterializedTabLifecycle(other.id, 'live'); focusWorkspace(other.id);
      setSpineFusion(0.84, [0.17, -0.03, 0.08]); setBrainDockScale(0.73);
    });
    await view.sync();
    const firstRoot = view.scene.children.find(root => root.getObjectByName('text:first.txt'))!;
    const tube = firstRoot.children.find(node => node instanceof THREE.Mesh && node.renderOrder === 6) as THREE.Mesh<THREE.TubeGeometry>;
    const socket = firstRoot.children.find(node => node instanceof THREE.Mesh && node.renderOrder === 7) as THREE.Mesh;
    const expected = new THREE.Vector3(0.3, -1.4, 0.2).multiplyScalar(0.73);
    expect.soft(tube.geometry.parameters.path.getPoint(0).distanceTo(expected)).toBeLessThan(1e-6);
    expect.soft(socket.position.distanceTo(expected)).toBeLessThan(1e-6);
  } finally { await view.close(); }
});

it.each([false, true])('the visible reader nerve follows the actual birth reach, never delaying readable work (reduced=%s)', async reducedMotion => {
  let now = 10_000;
  vi.spyOn(performance, 'now').mockImplementation(() => now);
  const view = await mount(reducedMotion, true, 'beginner', true);
  try {
    const reader = screen.getByText('first retained content');
    const path = view.overlayRef.current!.querySelector('path')!;
    const contact = view.overlayRef.current!.querySelector('circle')!;
    const tube = view.scene.children[0].children.find(object => object instanceof THREE.Mesh && object.renderOrder === 6) as THREE.Mesh;
    expect(tube.geometry).toBeInstanceOf(THREE.TubeGeometry);
    const exposed = () => 1 - Number(path.getAttribute('stroke-dashoffset'));
    // A live DOM reader yields the original slab immediately, not its birth
    // owner. Compare the visible filament to the actual hidden 3D consumer.
    expect.soft(path.getAttribute('pathLength')).toBe('1');
    expect.soft(path.getAttribute('stroke-dasharray')).toBe('1');
    expect.soft(exposed()).toBeCloseTo(reducedMotion ? 1 : 0.03, 5);
    expect.soft(contact.style.visibility).toBe(reducedMotion ? 'visible' : 'hidden');
    for (const elapsed of [90, 450, 899, 900, 1100]) {
      now = 10_000 + elapsed;
      await view.sync();
      const count = tube.geometry.getIndex()!.count;
      expect.soft(Math.abs(exposed() - tube.geometry.drawRange.count / count)).toBeLessThanOrEqual(1 / count);
      expect.soft(contact.style.visibility).toBe(reducedMotion || elapsed >= 900 ? 'visible' : 'hidden');
      expect(reader).toBeVisible();
      expect(screen.getByRole('button', { name: 'Close workspace' })).toBeEnabled();
      expect(view.scene.children[0].visible).toBe(false);
    }
    expect(getTabStoreSnapshot().tabs[0].lifecycle).toBe(reducedMotion ? 'live' : 'unfurling');
  } finally { await view.close(); }
});

it('preserves the real painted nerve when the same result updates then closes between frames', async () => {
  let now=10_000;vi.spyOn(performance,'now').mockImplementation(()=>now);
  const view=await mount(false,true,'beginner',true);
  try {
    now+=250;await view.sync();
    const nerve=view.scene.getObjectByName('workspace-nerve') as THREE.Mesh<THREE.BufferGeometry,THREE.ShaderMaterial>;
    const fibers=view.scene.getObjectByName('workspace-nerve-fibers') as THREE.Points<THREE.BufferGeometry,THREE.ShaderMaterial>;
    const before=nerve.material.uniforms.reach.value as number;
    const tab=getTabStoreSnapshot().tabs.find(value=>value.id===view.first.id)!;
    act(()=>updateMaterializedTab(tab.id,{content:{...tab.content!,code:'first retained content and a new chunk',streaming:true}}));
    await view.commit();
    act(()=>closeWorkspace(tab.id));await view.commit();
    act(()=>advance(1,false,view.store.getState()));
    expect(nerve.visible).toBe(true);expect(fibers.visible).toBe(true);
    expect(nerve.material.uniforms.reach.value).toBeCloseTo(before,6);
    expect(fibers.material.uniforms.reach.value).toBeCloseTo(before,6);
    expect(getTabStoreSnapshot().recoverableTabs?.find(value=>value.id===tab.id)?.content?.code).toBe('first retained content and a new chunk');
  } finally { await view.close(); }
});

it('retargets the real nerve contact after the body moves during return', async () => {
  let now=10_000;vi.spyOn(performance,'now').mockImplementation(()=>now);
  const view=await mount(false,true);
  try {
    const nerve=view.scene.getObjectByName('workspace-nerve') as THREE.Mesh<THREE.BufferGeometry,THREE.ShaderMaterial>;
    const fibers=view.scene.getObjectByName('workspace-nerve-fibers') as THREE.Points<THREE.BufferGeometry,THREE.ShaderMaterial>;
    act(()=>closeWorkspace(view.first.id));await view.sync();now+=650;await view.sync();
    const before=(nerve.material.uniforms.p3.value as THREE.Vector3).clone();
    setBodyGroupWorldMatrix(new THREE.Matrix4().makeTranslation(0,1,0));
    act(()=>expect(reopenMaterializedTab(view.first.id)).toBe(true));await view.sync();
    expect((nerve.material.uniforms.p3.value as THREE.Vector3).distanceTo(before)).toBeLessThan(.00001);
    expect((fibers.material.uniforms.p3.value as THREE.Vector3).distanceTo(before)).toBeLessThan(.00001);
    now+=130;await view.sync();const midpoint=(nerve.material.uniforms.p3.value as THREE.Vector3).clone();
    now+=130;await view.sync();const end=nerve.material.uniforms.p3.value as THREE.Vector3;
    expect(end.distanceTo(before)).toBeGreaterThan(.01);
    expect(midpoint.distanceTo(before)).toBeGreaterThan(0);
    expect(midpoint.distanceTo(before)).toBeLessThan(end.distanceTo(before));
    expect(screen.getByText('first retained content')).toBeVisible();
  } finally { await view.close(); }
});

it('reopens from the real painted nerve and rim buffers without delaying the reader', async () => {
  let now=10_000;vi.spyOn(performance,'now').mockImplementation(()=>now);
  const view=await mount(false,true);
  try {
    const nerve=view.scene.getObjectByName('workspace-nerve') as THREE.Mesh<THREE.BufferGeometry,THREE.ShaderMaterial>;
    const fibers=view.scene.getObjectByName('workspace-nerve-fibers') as THREE.Points<THREE.BufferGeometry,THREE.ShaderMaterial>;
    const rim=view.scene.getObjectByName('workspace-contact-rim') as THREE.Points<THREE.BufferGeometry,THREE.ShaderMaterial>;
    act(()=>closeWorkspace(view.first.id));await view.sync();
    now+=650;await view.sync();
    const before=nerve.material.uniforms.reach.value as number;
    const positions=(rim.geometry.getAttribute('position').array as Float32Array).slice();
    const alpha=(rim.geometry.getAttribute('aReturnAlpha').array as Float32Array).slice();
    expect(rim.material.uniforms.uReturning.value).toBe(1);
    act(()=>expect(reopenMaterializedTab(view.first.id)).toBe(true));await view.sync();
    expect(screen.getByText('first retained content')).toBeVisible();
    expect(nerve.material.uniforms.reach.value).toBeCloseTo(before,6);
    expect(fibers.material.uniforms.reach.value).toBeCloseTo(before,6);
    expect(rim.material.uniforms.uReturning.value).toBe(1);
    expect(Array.from(rim.geometry.getAttribute('position').array)).toEqual(Array.from(positions));
    expect(Array.from(rim.geometry.getAttribute('aReturnAlpha').array)).toEqual(Array.from(alpha));
    now+=260;await view.sync();
    expect(nerve.material.uniforms.reach.value).toBe(1);
    expect(rim.material.uniforms.uReturning.value).toBe(0);
    expect(rim.material.uniforms.uVisible.value).toBe(1);
    expect(screen.getByText('first retained content')).toBeVisible();
  } finally { await view.close(); }
});

it('a replacement and same-result Reopen use their own reach without replaying on streamed reader updates', async () => {
  let now = 10_000;
  vi.spyOn(performance, 'now').mockImplementation(() => now);
  const view = await mount(false, true, 'beginner', true);
  try {
    const path = view.overlayRef.current!.querySelector('path')!;
    const contact = view.overlayRef.current!.querySelector('circle')!;
    const exposed = () => 1 - Number(path.getAttribute('stroke-dashoffset'));
    now += 450; await view.sync();
    const grown = exposed();
    let second = '';
    act(() => { second = showContentSurface({ filepath: 'second.txt', language: 'text', code: 'second result' }, getContentSurfacePlacement(3)).id; focusWorkspace(second); });
    await view.sync();
    expect.soft(exposed()).toBeCloseTo(0.03, 5);
    expect.soft(contact.style.visibility).toBe('hidden');
    expect(screen.getByText('second result')).toBeVisible();
    act(() => focusWorkspace(view.first.id)); await view.sync();
    expect.soft(exposed()).toBeCloseTo(grown, 5); // focus is not another birth
    const reader = screen.getByText('first retained content');
    act(() => updateMaterializedTab(view.first.id, { content: { filepath: 'first.txt', language: 'text', code: 'first retained content\nmore incoming work' } }));
    await view.sync();
    expect.soft(exposed()).toBeCloseTo(grown, 5);
    expect(screen.getByText(/^first retained content/)).toBe(reader);
    const nerve = view.scene.getObjectByName('workspace-nerve') as THREE.Mesh<THREE.BufferGeometry, THREE.ShaderMaterial>;
    const fibers = view.scene.getObjectByName('workspace-nerve-fibers') as THREE.Points<THREE.BufferGeometry, THREE.ShaderMaterial>;
    expect(nerve.material.uniforms.reach.value).toBeCloseTo(grown, 5);
    act(() => closeWorkspace(view.first.id)); await view.sync();
    expect(path.getAttribute('d')).not.toBe('');
    expect(exposed()).toBeCloseTo(grown, 5); // return begins from the last painted nerve
    expect(nerve.visible).toBe(true); expect(fibers.visible).toBe(true);
    expect(nerve.material.uniforms.reach.value).toBeCloseTo(grown, 5);
    expect(fibers.material.uniforms.reach.value).toBeCloseTo(grown, 5);
    now += 50;
    act(() => { expect(reopenMaterializedTab(view.first.id)).toBe(true); }); await view.sync();
    expect.soft(exposed()).toBeCloseTo(grown, 5); // retarget from the last painted return
    expect.soft(contact.style.visibility).toBe('hidden');
    expect(screen.getByText(/^first retained content/)).toBe(reader);
    expect(getTabStoreSnapshot().tabs.find(tab => tab.id === second)).toBeDefined();
    act(() => setAmbientMotionPaused(true));
    await view.sync();
    expect.soft(exposed()).toBe(1); // actual sovereign motion policy is reactive
    expect.soft(contact.style.visibility).toBe('visible');
    expect.soft(getTabStoreSnapshot().tabs.find(tab => tab.id === view.first.id)?.lifecycle).toBe('live');
    now += 50;
    act(() => setAmbientMotionPaused(false)); await view.sync();
    expect.soft(exposed()).toBe(1); // unpause cannot replay a settled birth
    expect.soft(contact.style.visibility).toBe('visible');
    expect(screen.getByText(/^first retained content/)).toBe(reader);
  } finally { await view.close(); }
});

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
    const svg = view.overlayRef.current!;
    const path = svg.querySelector('path')!, contact = svg.querySelector('circle')!;
    const readNodes = vi.spyOn(svg, 'querySelector');
    const readAttributes = vi.spyOn(path, 'getAttribute');
    const readVisibility = vi.spyOn(contact.style, 'visibility', 'get');
    const writeAttributes = vi.spyOn(path, 'setAttribute');
    // Read-only frame advancement with a steady reader; no layout or observer event.
    // The actual connection and surface callbacks run, not a mocked render hook.
    const canvas = view.dom.container.querySelector('canvas')!;
    for (let time = 2; time <= 100; time++) act(() => advance(time, false, _roots.get(canvas)!.store.getState()));
    expect(measure.mock.calls.length).toBe(before);
    expect.soft(readNodes).not.toHaveBeenCalled();
    expect.soft(readAttributes).not.toHaveBeenCalled();
    expect.soft(readVisibility).not.toHaveBeenCalled();
    expect.soft(writeAttributes).not.toHaveBeenCalled();
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

async function mountDecision(mode: 'beginner' | 'expert', reducedMotion: boolean, requestRef = 'conversation-approval', initiallyStopped = false) {
  const pending: PendingApproval = { token: 'fixture-only-capability', prompt: 'Create a fixture',
    summary: 'Create fixture.py', explanation: 'Synthetic proposal', kind: 'create', filepath: 'fixture.py',
    content: 'print("fixture")', diff: '', command: '', url: '' };
  const tab = showApprovalSurface({ requestRef, kindLabel: 'create', filepath: pending.filepath,
    summary: pending.summary, explanation: pending.explanation, content: pending.content, diff: '', command: '' },
  getApprovalSurfacePlacement(3));
  setMaterializedTabLifecycle(tab.id, 'live');
  const app = (present = !initiallyStopped, active = true) => <div className="lm-app" data-being-phase={initiallyStopped ? 'stopped' : undefined}><canvas />
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

it.each(['conversation-approval', 'dev-approval'])(
  'cold Stop observation preserves the product boundary without suppressing an unrelated lab owner (%s)', async requestRef => {
    const view = await mountDecision('beginner', true, requestRef, true);
    try {
      const slab = view.scene.children[0];
      expect(slab.visible).toBe(requestRef !== 'conversation-approval');
      const host = view.dom.container.querySelector('.lm-app')!;
      await act(async () => { host.setAttribute('data-being-phase', 'resting'); });
      expect(slab.visible).toBe(true);
      await act(async () => { host.setAttribute('data-being-phase', 'stopped'); });
      expect(slab.visible).toBe(requestRef !== 'conversation-approval');
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

it.each([['beginner', false], ['beginner', true], ['expert', false], ['expert', true]] as const)(
  'observed Stop cannot resurrect a pickable approval slab when the DOM decision is held (%s, reduced=%s)', async (mode, reduced) => {
    const view = await mountDecision(mode, reduced);
    try {
      const slab = view.scene.children[0];
      const host = view.dom.container.querySelector('.lm-app')!;
      // The actual product publishes stopped and removes its actionable
      // permission panel. Missing-panel fallback must not resurrect it in 3D.
      await act(async () => { host.setAttribute('data-being-phase', 'stopped'); });
      await view.dialog(false, false);
      expect.soft(slab.visible, 'Stop holds the same request, not a second approval route').toBe(false);
      let body: THREE.Mesh | undefined;
      slab.traverse(object => { if (object instanceof THREE.Mesh && object.geometry.type === 'ExtrudeGeometry') body = object; });
      view.scene.updateMatrixWorld(true);
      const target = body!.getWorldPosition(new THREE.Vector3());
      expect.soft(new THREE.Raycaster(target.clone().add(new THREE.Vector3(0, 0, 10)), new THREE.Vector3(0, 0, -1))
        .intersectObject(slab, true), 'a held slab must not retain 3D pointer targets').toHaveLength(0);
      expect(getTabStoreSnapshot().tabs.find(record => record.id === view.tab.id)).toMatchObject({
        lifecycle: 'live', approval: { requestRef: 'conversation-approval', content: 'print("fixture")' },
      });
      await act(async () => { host.setAttribute('data-being-phase', 'resting'); });
      expect(slab.visible, 'without Stop or a readable owner, standalone fallback remains available').toBe(true);
      await act(async () => { host.setAttribute('data-being-phase', 'stopped'); });
      expect(slab.visible, 'Stop publication alone must work even when no dialog is mounted').toBe(false);
      await view.dialog(true);
      await act(async () => { host.setAttribute('data-being-phase', 'awaiting-human'); });
      expect(slab.visible).toBe(false);
      expect(screen.getByRole('button', { name: mode === 'beginner' ? 'Allow once' : 'AUTHORIZE' })).toBeEnabled();
    } finally { await view.close(); }
  },
);

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
it('keeps the edge study on waiting surfaces and follows workspace identity when focus changes',async()=>{
  const view=await mount(false);
  let other='';
  act(()=>{
    other=showContentSurface({filepath:'waiting.txt',language:'text',code:'waiting result'},getContentSurfacePlacement(4)).id;
    setMaterializedTabLifecycle(other,'live');focusWorkspace(view.first.id);
  });
  await view.sync();
  const findDust=()=>view.scene.getObjectsByProperty('name','waiting-workspace-edge') as THREE.Points[];
  let dust=findDust();expect(dust).toHaveLength(1);
  expect(dust[0].geometry.getAttribute('position').count).toBe(144);
  const material=dust[0].material as THREE.ShaderMaterial;
  expect(material.uniforms.uGain.value).toBe(1);
  let now=10000;vi.spyOn(performance,'now').mockImplementation(()=>now);
  act(()=>setMaterializedTabLifecycle(other,'unfurling',now));await view.sync();
  expect(material.uniforms.uGain.value).toBe(0);
  now+=260;await view.sync();expect(material.uniforms.uGain.value).toBeCloseTo(.5,4);
  act(()=>setMaterializedTabLifecycle(other,'live',now));await view.sync();expect(material.uniforms.uGain.value).toBe(1);
  let owner:THREE.Object3D|null=dust[0];while(owner&&owner.name!==`gagos-workspace-${other}`)owner=owner.parent;
  expect(owner).not.toBeNull();
  act(()=>focusWorkspace(other));await view.sync();
  dust=findDust();expect(dust).toHaveLength(1);
  owner=dust[0];while(owner&&owner.name!==`gagos-workspace-${view.first.id}`)owner=owner.parent;
  expect(owner).not.toBeNull();
  await view.close();
});
it('fades waiting edge particles on the existing return timeline',async()=>{
  let now=10000;vi.spyOn(performance,'now').mockImplementation(()=>now);
  const view=await mount(false);
  try {
    let other='';act(()=>{
      other=showContentSurface({filepath:'returning.txt',language:'text',code:'retained'},getContentSurfacePlacement(4)).id;
      setMaterializedTabLifecycle(other,'live',now);focusWorkspace(view.first.id);
    });
    await view.sync();const dust=view.scene.getObjectByName('waiting-workspace-edge') as THREE.Points;
    expect(dust).toBeTruthy();const material=dust.material as THREE.ShaderMaterial;expect(material.uniforms.uGain.value).toBe(1);
    act(()=>closeWorkspace(other));await view.sync();expect(material.uniforms.uGain.value).toBe(1);
    now+=POINTS_SLAB_RETRACT_MS/2;await view.sync();expect(material.uniforms.uGain.value).toBeCloseTo(.5,4);
    now+=POINTS_SLAB_RETRACT_MS/2;await view.sync();expect(material.uniforms.uGain.value).toBe(0);
  } finally {await view.close();}
});


it('waiting edge breath follows the real shared body uniform and holds still for reduced motion', async () => {
  const breathRef = { value: 0.2 };
  const view = await mount(false, true, 'beginner', false, true, undefined, breathRef);
  try {
    act(() => {
      const waiting = showContentSurface({ filepath: 'breathing.txt', language: 'text', code: 'waiting' }, getContentSurfacePlacement(4));
      setMaterializedTabLifecycle(waiting.id, 'live');
      focusWorkspace(view.first.id);
    });
    await view.sync();
    const dust = view.scene.getObjectByName('waiting-workspace-edge') as THREE.Points;
    expect(dust).toBeTruthy();
    let material = dust.material as THREE.ShaderMaterial;
    expect(material.uniforms.uBreath.value).toBe(0.2);
    expect(material.fragmentShader).toMatch(/uBreath/);
    breathRef.value = 0.8;
    await view.sync();
    expect(material.uniforms.uBreath.value).toBe(0.8);
    act(() => setAmbientMotionPaused(true));
    await view.sync();
    material = (view.scene.getObjectByName('waiting-workspace-edge') as THREE.Points).material as THREE.ShaderMaterial;
    expect(material.uniforms.uBreath.value).toBe(0.5);
    breathRef.value = 0.1;
    await view.sync();
    expect(material.uniforms.uBreath.value).toBe(0.5);
  } finally { await view.close(); }
});

it('starts a newly created waiting nerve at its current reach instead of showing the full tube', async () => {
  const now = 10000;
  vi.spyOn(performance, 'now').mockReturnValue(now);
  const view = await mount(false, true, 'beginner', false, true);
  try {
    act(() => {
      showContentSurface({ filepath: 'new-waiting.txt', language: 'text', code: 'waiting' }, getContentSurfacePlacement(8));
      focusWorkspace(view.first.id);
    });
    await view.sync();
    const owner = view.scene.children.find(node => node.getObjectByName('text:new-waiting.txt'))!;
    const tube = owner.children.find(node => node instanceof THREE.Mesh && node.renderOrder === 6) as THREE.Mesh<THREE.TubeGeometry>;
    expect(tube.geometry.drawRange.count).toBe(Math.max(2, Math.floor(tube.geometry.getIndex()!.count * 0.03)));
    expect(tube.geometry.drawRange.count).toBeLessThan(tube.geometry.getIndex()!.count);
  } finally { await view.close(); }
});

it('stages a crowded compact pair at distinct heights without changing workspace identities', async () => {
  const view=await mount(true,true,'beginner',false,true);
  const ids:string[]=[];
  try {
    act(()=>{
      for(const seat of [0,1,3,4,5,6,7,8,9,10,11]){
        const tab=showContentSurface({filepath:`organic-${seat}.txt`,language:'text',code:'waiting'},getContentSurfacePlacement(seat));
        ids.push(tab.id);setMaterializedTabLifecycle(tab.id,'live');
      }
      focusWorkspace(view.first.id);
      view.store.getState().setSize(390,844);
    });
    await view.sync();view.scene.updateMatrixWorld(true);
    const left=view.scene.getObjectByName(`gagos-workspace-${ids[2]}`)!;
    const right=view.scene.getObjectByName(`gagos-workspace-${ids[3]}`)!;
    expect(left).toBeTruthy();expect(right).toBeTruthy();
    const a=left.getWorldPosition(new THREE.Vector3()),b=right.getWorldPosition(new THREE.Vector3());
    expect(Math.abs(a.y-b.y)).toBeGreaterThan(0.005);
    const fartherLeft=view.scene.getObjectByName(`gagos-workspace-${ids[4]}`)!;
    expect(Math.abs(a.x-fartherLeft.getWorldPosition(new THREE.Vector3()).x)).toBeGreaterThan(0.01);
    expect(getTabStoreSnapshot().tabs.map(tab=>tab.id)).toEqual([view.first.id,...ids]);
    expect(getTabStoreSnapshot().focusId).toBe(view.first.id);
    expect(screen.getByRole('region',{name:'Selected workspace'})).toBeVisible();
  } finally {await view.close();}
});

it.each([false,true])('keeps staggered compact workspace geometry inside a phone-sized pane (reduced=%s)', async reducedMotion=>{
  const view=await mount(reducedMotion,true,'beginner',false,true);
  try {
    act(()=>{
      for(const seat of [0,1,3,4,5,6,7,8,9,10,11]){
        const tab=showContentSurface({filepath:`phone-pane-${seat}.txt`,language:'text',code:'waiting'},getContentSurfacePlacement(seat));
        setMaterializedTabLifecycle(tab.id,'live');
      }
      focusWorkspace(view.first.id);view.store.getState().setSize(390,844);
    });
    const camera=view.store.getState().camera as THREE.PerspectiveCamera;
    camera.setViewOffset(390,280,0,-150,390,844);
    await view.sync();view.scene.updateMatrixWorld(true);
    const point=new THREE.Vector3(),pixel=new THREE.Vector2(),boxes:THREE.Box2[]=[];
    for(const root of view.scene.children){
      if(!root.visible)continue;
      root.traverse(node=>{
        if(!(node instanceof THREE.Mesh)||node.geometry.type!=='ExtrudeGeometry')return;
        const positions=node.geometry.getAttribute('position'),box=new THREE.Box2();
        for(let vertex=0;vertex<positions.count;vertex++){
          point.fromBufferAttribute(positions,vertex).applyMatrix4(node.matrixWorld).project(camera);
          box.expandByPoint(pixel.set((point.x+1)*195,(1-point.y)*422));
        }
        expect.soft(box.min.x).toBeGreaterThanOrEqual(0);expect.soft(box.max.x).toBeLessThanOrEqual(390);
        expect.soft(box.min.y).toBeGreaterThanOrEqual(150);expect.soft(box.max.y).toBeLessThanOrEqual(430);
        boxes.push(box);
      });
    }
    expect(boxes).toHaveLength(11);
    for(let i=0;i<boxes.length;i++)for(const other of boxes.slice(i+1))expect.soft(boxes[i].intersectsBox(other)).toBe(false);
    expect(screen.getByRole('region',{name:'Selected workspace'})).toBeVisible();
  } finally {await view.close();}
});
