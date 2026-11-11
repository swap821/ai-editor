import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createRef, useState, type RefObject } from 'react';
import { Color, Matrix4, Mesh, PerspectiveCamera, Points, ShaderMaterial, Vector3 } from 'three';
import { WorkspaceConnectionOverlay } from './WorkspaceConnectionOverlay';
import { WorkspaceConnectionProjection } from './WorkspaceConnectionProjection';
import { __resetSpineFusionForTests, setBodyGroupWorldMatrix, setCortexAnchor, setSpineFusion } from '../../superbrain/lib/spineFusionBus';
import { __resetTabStoreForTests, closeWorkspace, focusWorkspace, getTabStoreSnapshot, openWorkspacePanel,
  showContentSurface, showApprovalSurface, updateMaterializedTab, setMaterializedTabLifecycle,
  beginRetractingMaterializedTab, reopenMaterializedTab } from '../../superbrain/lib/tabStore';
import ApprovalPanel from '../../superbrain/components/ui/ApprovalPanel';
import GuidedApprovalPanel from '../GuidedApprovalPanel';
import type { WorkspaceRimState } from './workspaceRim';

let frame: (state: { camera: PerspectiveCamera; gl: { domElement: HTMLCanvasElement; getPixelRatio:()=>number } }) => void;
let rimPaint: WorkspaceRimState | undefined;
let nervePaint: {mesh:Mesh;points:Points;material:ShaderMaterial;dustMaterial:ShaderMaterial}|undefined;
// The GPU is external here; retain its real projection/phase writer and inspect
// the same reusable uniforms/buffers that the installed Points consumes.
vi.mock('./WorkspaceRimPoints',()=>({WorkspaceRimPoints:({state}:{state:WorkspaceRimState})=>{rimPaint=state;return null;}}));
// Keep the production projection owner; replace only GPU objects with actual
// Three materials and geometry-free objects so visibility/uniforms are testable.
vi.mock('./workspaceNerveState',()=>({
  createWorkspaceNerve:()=>{
    const uniforms=()=>({p0:{value:new Vector3()},p1:{value:new Vector3()},p2:{value:new Vector3()},p3:{value:new Vector3()},
      radius:{value:0},reach:{value:0},dpr:{value:1},breath:{value:.5},signal:{value:-1},color:{value:new Color('#79ebff')}});
    return {mesh:new Mesh(),points:new Points(),material:new ShaderMaterial({uniforms:uniforms()}),
      dustMaterial:new ShaderMaterial({uniforms:uniforms()})};
  },
}));
vi.mock('./WorkspaceNerve',()=>({WorkspaceNerve:({state}:{state:typeof nervePaint})=>{nervePaint=state;return null;}}));
// WebGL is external to this DOM integration test. Keep the real seat store,
// fusion/matrix publication, camera projection and resulting SVG geometry.
vi.mock('@react-three/fiber', () => ({
  useFrame: (callback: typeof frame) => { frame = callback; },
  useThree: (selector: (state: { gl: { domElement: HTMLCanvasElement | null } }) => unknown) =>
    selector({ gl: { domElement: document.querySelector('canvas') } }),
}));
const camera = new PerspectiveCamera(90, 1, 0.1, 100);
camera.position.set(0, 0, 10);
camera.updateMatrixWorld();
const overlayRef = createRef<SVGSVGElement>();

function Surface({ renderer = true, decision = false, guided = false, motionHeld=false, attentionTargetRef, breathRef }: { renderer?: boolean; decision?: boolean; guided?: boolean; motionHeld?:boolean; breathRef?: {value:number};
  attentionTargetRef?: RefObject<{ targetId: string; lateral: number; vertical: number } | null> }) {
  const pending = { token: 'fixture-decision', prompt: 'Create a fixture', url: '', kind: 'create' as const, filepath: 'same.py',
    content: 'new proposal', diff: '+new proposal', command: '', summary: 'New proposal', explanation: '' };
  const [canvas, setCanvas] = useState<HTMLCanvasElement | null>(null);
  return <div className="lm-app">
    <canvas ref={setCanvas} /><section className="lm-surface" data-workspace-id={getTabStoreSnapshot().focusId ?? undefined} />
    <div className="gagos-chrome" data-approval-pending={decision ? 'true' : 'false'}>
      {decision && (guided ? <GuidedApprovalPanel pending={pending} onSettled={() => {}} />
        : <ApprovalPanel pending={pending} onSettled={() => {}} />)}
    </div>
    <WorkspaceConnectionOverlay overlayRef={overlayRef} />
    {renderer && canvas && <WorkspaceConnectionProjection {...{ overlayRef, snapshot: getTabStoreSnapshot(), attentionTargetRef, motionHeld, breathRef }} />}
  </div>;
}
function step(dpr=1) {
  act(() => frame({ camera, gl: { domElement: document.querySelector('canvas')!,getPixelRatio:()=>dpr } }));
}
function path() { return overlayRef.current!.querySelector('path')!.getAttribute('d'); }

beforeEach(() => {
  rimPaint=undefined;nervePaint=undefined;
  __resetTabStoreForTests();
  __resetSpineFusionForTests();
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
    const value = this.matches('canvas') ? { x: 100, y: 50, width: 400, height: 400 }
      : this.matches('.lm-surface') ? { x: 600, y: 100, width: 600, height: 600 }
        : { x: 20, y: 10, width: 1200, height: 800 };
    return { ...value, left: value.x, top: value.y, right: value.x + value.width, bottom: value.y + value.height, toJSON: () => value };
  });
  setSpineFusion(1, [0, 0, 0]);
  setBodyGroupWorldMatrix(new Matrix4());
  openWorkspacePanel('history', 'Recent observations');
});
afterEach(() => {
  cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); __resetTabStoreForTests(); __resetSpineFusionForTests();
});

describe('body-to-workplane connection', () => {
  it('coalesces real content changes and never replays a cue after a hold or completion', () => {
    let now=10000;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();
    const artifact=showContentSurface({filepath:'signal.py',code:'',language:'python',streaming:true},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'live',now);
    const view=render(<Surface/>);step();
    const value=()=>nervePaint!.material.uniforms.signal.value as number;
    expect(value()).toBe(-1);
    act(()=>updateMaterializedTab(artifact.id,{content:{...artifact.content!,code:'first',streaming:true}}));
    view.rerender(<Surface/>);step();expect(value()).toBe(0);
    now+=200;
    act(()=>updateMaterializedTab(artifact.id,{content:{...artifact.content!,code:'second',streaming:true}}));
    view.rerender(<Surface/>);step();expect(value()).toBeCloseTo(.5,4);
    now+=200;step();expect(value()).toBe(0);
    now+=401;step();expect(value()).toBe(-1);
    view.rerender(<Surface motionHeld/>);
    act(()=>updateMaterializedTab(artifact.id,{content:{...artifact.content!,code:'held',streaming:true}}));
    view.rerender(<Surface motionHeld/>);step();expect(value()).toBe(-1);
    view.rerender(<Surface/>);step();expect(value()).toBe(-1);
    act(()=>updateMaterializedTab(artifact.id,{content:{...artifact.content!,code:'resumed',streaming:true}}));
    view.rerender(<Surface/>);step();expect(value()).toBe(0);
    act(()=>updateMaterializedTab(artifact.id,{content:{...artifact.content!,code:'finished',streaming:false}}));
    view.rerender(<Surface/>);step();expect(value()).toBe(-1);
  });
  it('drops stale queued cues and does not replay them when work is refocused', () => {
    let now=10000;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();
    const artifact=showContentSurface({filepath:'stale.py',code:'',language:'python',streaming:true},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'live',now);
    const view=render(<Surface/>);step();
    act(()=>updateMaterializedTab(artifact.id,{content:{...artifact.content!,code:'first',streaming:true}}));
    view.rerender(<Surface/>);step();expect(nervePaint!.material.uniforms.signal.value).toBe(0);
    now+=100;act(()=>updateMaterializedTab(artifact.id,{content:{...artifact.content!,code:'second',streaming:true}}));
    view.rerender(<Surface/>);step();expect(nervePaint!.material.uniforms.signal.value).toBeCloseTo(.25,4);
    now+=1000;step();expect(nervePaint!.material.uniforms.signal.value).toBe(-1);
    act(()=>updateMaterializedTab(artifact.id,{content:{...artifact.content!,code:'third',streaming:true}}));
    view.rerender(<Surface/>);step();expect(nervePaint!.material.uniforms.signal.value).toBe(0);
    act(()=>focusWorkspace(null));view.rerender(<Surface/>);step();
    act(()=>focusWorkspace(artifact.id));view.rerender(<Surface/>);step();
    expect(nervePaint!.material.uniforms.signal.value).toBe(-1);
  });
  it('cancels the cue at an occluding decision even without a matching scene approval', async () => {
    let now=10000;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();
    const artifact=showContentSurface({filepath:'decision.py',code:'',language:'python',streaming:true},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'live',now);
    const view=render(<Surface/>);step();
    act(()=>updateMaterializedTab(artifact.id,{content:{...artifact.content!,code:'first',streaming:true}}));
    view.rerender(<Surface/>);step();expect(nervePaint!.material.uniforms.signal.value).toBe(0);
    now+=100;view.rerender(<Surface decision/>);await act(async()=>{});step();
    view.rerender(<Surface/>);await act(async()=>{});step();expect(nervePaint!.material.uniforms.signal.value).toBe(-1);
  });
  it('shares the body breath, freezes on a hold, and ignores nonfinite values',()=>{
    __resetTabStoreForTests();const artifact=showContentSurface({filepath:'breath.py',code:'partial',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'live',1000);
    const breathRef={value:.2},view=render(<Surface breathRef={breathRef}/>);step();
    expect(nervePaint!.material.uniforms.breath.value).toBe(.2);expect(nervePaint!.dustMaterial.uniforms.breath.value).toBe(.2);
    breathRef.value=.8;step();expect(nervePaint!.material.uniforms.breath.value).toBe(.8);
    view.rerender(<Surface breathRef={breathRef} motionHeld/>);breathRef.value=.1;step();
    expect(nervePaint!.material.uniforms.breath.value).toBe(.8);expect(nervePaint!.dustMaterial.uniforms.breath.value).toBe(.8);
    view.rerender(<Surface breathRef={breathRef}/>);breathRef.value=NaN;step();
    expect(nervePaint!.material.uniforms.breath.value).toBe(.8);
    breathRef.value=9;step();expect(nervePaint!.material.uniforms.breath.value).toBe(1.35);
  });
  it('uses a still midpoint when reduced motion is requested',()=>{
    vi.stubGlobal('matchMedia',(query:string):MediaQueryList=>({matches:query.includes('reduced-motion'),media:query,onchange:null,
      addEventListener(){},removeEventListener(){},addListener(){},removeListener(){},dispatchEvent:()=>true}));
    __resetTabStoreForTests();const artifact=showContentSurface({filepath:'still.py',code:'partial',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'live',1000);const breathRef={value:.9};render(<Surface breathRef={breathRef}/>);step();
    expect(nervePaint!.material.uniforms.breath.value).toBe(.5);expect(nervePaint!.dustMaterial.uniforms.breath.value).toBe(.5);
    breathRef.value=.1;step();expect(nervePaint!.material.uniforms.breath.value).toBe(.5);
  });
  it('matches the SVG birth front, settles under a hold, and hides for invalid DPR',()=>{
    let now=2500;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();const artifact=showContentSurface({filepath:'nerve.py',code:'partial',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'reaching',2400);const view=render(<Surface/>);step();
    const svg=overlayRef.current!.querySelector('path')!;
    expect(nervePaint!.mesh.visible).toBe(true);expect(nervePaint!.points.visible).toBe(true);
    expect(nervePaint!.material.uniforms.reach.value).toBeCloseTo(1-Number(svg.getAttribute('stroke-dashoffset')),6);
    expect(nervePaint!.dustMaterial.uniforms.reach.value).toBe(nervePaint!.material.uniforms.reach.value);
    view.rerender(<Surface motionHeld/>);step();expect(nervePaint!.material.uniforms.reach.value).toBe(1);
    view.rerender(<Surface/>);step();expect(nervePaint!.material.uniforms.reach.value).toBe(1);
    step(0);expect(nervePaint!.mesh.visible).toBe(false);expect(nervePaint!.points.visible).toBe(false);
  });
  it('clears the old return at a committed hold even when no animation frame runs',()=>{
    let now=1000;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();const artifact=showContentSurface({filepath:'return-nerve.py',code:'keep',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'live',1000);const view=render(<Surface/>);step();
    now=3000;act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);step();
    expect(nervePaint!.mesh.visible).toBe(true);expect(nervePaint!.points.visible).toBe(true);
    view.rerender(<Surface motionHeld/>);
    expect(nervePaint!.mesh.visible).toBe(false);expect(nervePaint!.points.visible).toBe(false);
    view.rerender(<Surface/>);now=3100;step();
    expect(nervePaint!.mesh.visible).toBe(false);expect(nervePaint!.points.visible).toBe(false);
  });
  it('returns only the already painted nerve without inventing an unborn rim',()=>{
    let now=2410;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();const artifact=showContentSurface({filepath:'early-close.py',code:'partial',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'reaching',2400);const view=render(<Surface/>);step();
    expect(nervePaint!.mesh.visible).toBe(true);expect(rimPaint!.paintedCount).toBe(0);
    const before=nervePaint!.material.uniforms.reach.value as number;
    now=2420;act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);step();
    expect(nervePaint!.mesh.visible).toBe(true);expect(nervePaint!.points.visible).toBe(true);
    expect(nervePaint!.material.uniforms.reach.value).toBeCloseTo(before,6);
    expect(rimPaint!.uniforms.uVisible.value).toBe(0);expect(path()).not.toBe('');
    expect(getTabStoreSnapshot().recoverableTabs?.find(tab=>tab.id===artifact.id)?.content?.code).toBe('partial');
  });
  it.each(['focus round-trip','hold pulse','Reopen round-trip'] as const)('latches committed %s cancellation even without an intervening renderer frame',interruption=>{
    let now=1000;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();const artifact=showContentSurface({filepath:'committed-return.py',code:'keep this',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'live',1000);const view=render(<Surface/>);step();
    now=3000;act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);step();
    expect(rimPaint!.uniforms.uVisible.value).toBe(1);
    if(interruption==='focus round-trip') {
      act(()=>openWorkspacePanel('next-commit','Next work'));view.rerender(<Surface/>);
      act(()=>focusWorkspace(null));view.rerender(<Surface/>);
    } else if(interruption==='hold pulse'){view.rerender(<Surface motionHeld/>);view.rerender(<Surface/>);}
    else {
      act(()=>reopenMaterializedTab(artifact.id));view.rerender(<Surface/>);
      act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);
    }
    // Both changes above committed; no useFrame callback saw the middle state.
    now=3100;step();expect(rimPaint!.uniforms.uVisible.value).toBe(0);expect(path()).toBe('');
    expect(getTabStoreSnapshot().recoverableTabs?.find(tab=>tab.id===artifact.id)?.content?.code).toBe('keep this');
  });
  it.each(['new focus','permission','resize'] as const)('drops only the decorative return on %s and never resurrects its old envelope',async interruption=>{
    let now=1000;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();const artifact=showContentSurface({filepath:'interrupt.py',code:'keep this',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'live',1000);
    const view=render(<Surface/>);step();now=3000;act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);step();
    expect(rimPaint!.uniforms.uVisible.value).toBe(1);
    if(interruption==='new focus')act(()=>openWorkspacePanel('next-panel','Next work'));
    if(interruption==='resize')Object.defineProperty(view.container.querySelector('canvas')!,'getBoundingClientRect',{
      configurable:true,value:()=>new DOMRect(100,50,440,400),
    });
    now=3100;view.rerender(<Surface decision={interruption==='permission'}/>);
    await act(async()=>{});act(()=>window.dispatchEvent(new Event('resize')));step();
    expect(rimPaint!.uniforms.uVisible.value).toBe(0);
    if(interruption==='permission')expect(view.container.querySelector('.approval-panel')).toBeTruthy();
    act(()=>focusWorkspace(null));now=3200;view.rerender(<Surface/>);await act(async()=>{});step();
    expect(rimPaint!.uniforms.uVisible.value).toBe(0);expect(path()).toBe('');
    expect(getTabStoreSnapshot().recoverableTabs?.find(tab=>tab.id===artifact.id)?.content?.code).toBe('keep this');
  });
  it.each([0,250,650])('reopens from the last painted return at %sms with the same identity', elapsed=>{
    let now=1000;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();
    const artifact=showContentSurface({filepath:'reversal.py',code:'keep this',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'live',now);
    const view=render(<Surface/>);step();
    now=3000;act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);now+=elapsed;step();
    const nerveBefore=nervePaint!.material.uniforms.reach.value as number;
    const beforePositions=rimPaint!.positions.slice();
    const beforeAlpha=rimPaint!.returnAlpha.slice();
    expect(rimPaint!.uniforms.uReturning.value).toBe(1);
    act(()=>expect(reopenMaterializedTab(artifact.id)).toBe(true));view.rerender(<Surface/>);step();
    expect(getTabStoreSnapshot().focusId).toBe(artifact.id);
    expect(nervePaint!.material.uniforms.reach.value).toBeCloseTo(nerveBefore,6);
    expect(nervePaint!.dustMaterial.uniforms.reach.value).toBeCloseTo(nerveBefore,6);
    expect(rimPaint!.uniforms.uVisible.value).toBe(1);
    expect(rimPaint!.uniforms.uReturning.value).toBe(1);
    expect(Array.from(rimPaint!.positions)).toEqual(Array.from(beforePositions));
    expect(Array.from(rimPaint!.returnAlpha)).toEqual(Array.from(beforeAlpha));
    expect(getTabStoreSnapshot().tabs.find(tab=>tab.id===artifact.id)?.content?.code).toBe('keep this');
  });
  it('retargets the contact from its last return when the being moves before Reopen',()=>{
    let now=1000;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();const artifact=showContentSurface({filepath:'moving-reopen.py',code:'keep this',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'live',now);const view=render(<Surface/>);step();
    now=3000;act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);now=3650;step();
    const endpoint=()=>{const d=path()!;const match=d.match(/,\s*(-?[\d.]+)\s+(-?[\d.]+)$/);if(!match)throw new Error(`Unexpected path: ${d}`);return {x:Number(match[1]),y:Number(match[2])};};
    const before=endpoint();
    setBodyGroupWorldMatrix(new Matrix4().makeTranslation(0,2,0));
    act(()=>expect(reopenMaterializedTab(artifact.id)).toBe(true));view.rerender(<Surface/>);step();
    const first=endpoint();expect(first.x).toBe(before.x);expect(first.y).toBe(before.y);
    now+=130;step();const middle=endpoint();
    now+=130;step();const end=endpoint();
    expect(end.y).not.toBe(before.y);
    expect(middle.y).toBeGreaterThanOrEqual(Math.min(before.y,end.y));
    expect(middle.y).toBeLessThanOrEqual(Math.max(before.y,end.y));
    expect(getTabStoreSnapshot().tabs.find(tab=>tab.id===artifact.id)?.content?.code).toBe('keep this');
  });
  it('reverses toward the work and can close again from the exact intermediate paint',()=>{
    let now=1000;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();const artifact=showContentSurface({filepath:'twice.py',code:'keep this',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'live',now);const view=render(<Surface/>);step();
    now=3000;act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);now=3650;step();
    const start=nervePaint!.material.uniforms.reach.value as number;
    act(()=>expect(reopenMaterializedTab(artifact.id)).toBe(true));view.rerender(<Surface/>);step();
    now+=100;step();
    const intermediate=nervePaint!.material.uniforms.reach.value as number;
    expect(intermediate).toBeGreaterThan(start);expect(intermediate).toBeLessThan(1);
    const positions=rimPaint!.positions.slice(),alpha=rimPaint!.returnAlpha.slice();
    act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);step();
    expect(nervePaint!.material.uniforms.reach.value).toBeCloseTo(intermediate,6);
    expect(Array.from(rimPaint!.positions)).toEqual(Array.from(positions));
    expect(Array.from(rimPaint!.returnAlpha)).toEqual(Array.from(alpha));
    now+=100;step();expect(nervePaint!.material.uniforms.reach.value).toBeLessThan(intermediate);
    expect(getTabStoreSnapshot().recoverableTabs?.find(tab=>tab.id===artifact.id)?.content?.code).toBe('keep this');
  });
  it('preserves partially born rim paint through the return-to-birth handoff',()=>{
    let now=2530;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();const artifact=showContentSurface({filepath:'partial-rim.py',code:'keep this',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'unfurling',2400);const view=render(<Surface/>);step();
    expect(rimPaint!.paintedCount).toBeGreaterThan(0);expect(rimPaint!.paintedCount).toBeLessThan(2400);
    now=3000;act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);now=3650;step();
    setBodyGroupWorldMatrix(new Matrix4().makeTranslation(0,2,0));
    act(()=>expect(reopenMaterializedTab(artifact.id)).toBe(true));view.rerender(<Surface/>);step();
    const rendered=()=>{
      const rim=rimPaint!,u=rim.uniforms,positions=new Float32Array(rim.positions.length),alpha=new Float32Array(rim.offset.length);
      const smooth=(lo:number,hi:number,x:number)=>{const t=Math.min(1,Math.max(0,(x-lo)/(hi-lo)));return t*t*(3-2*t);};
      for(let i=0;i<alpha.length;i++){
        const sep=Math.abs(rim.data[i*2]-u.uOrigin.value),travel=Math.min(sep,1-sep)*2;
        const spread=1-Math.pow(1-u.uUnfurl.value,3),settle=smooth(0,.2,spread-travel*.82);
        const loft=u.uReturning.value>.5?0:(1-settle)*10;
        positions[i*3]=rim.positions[i*3]+rim.normals[i*2]*loft;
        positions[i*3+1]=rim.positions[i*3+1]+rim.normals[i*2+1]*loft;
        positions[i*3+2]=rim.positions[i*3+2];
        alpha[i]=u.uReturning.value>.5?rim.returnAlpha[i]:smooth(travel*.82,travel*.82+.18,spread)*(.38+.46*rim.data[i*2+1]+.32*(1-settle));
      }
      return {positions,alpha};
    };
    now+=181;step();const before=rendered();
    now+=1;step();const after=rendered();
    let largestDistance=0,largestAlpha=0;
    for(let i=0;i<before.alpha.length;i++){
      if(Math.max(before.alpha[i],after.alpha[i])>.002)largestDistance=Math.max(largestDistance,Math.hypot(before.positions[i*3]-after.positions[i*3],before.positions[i*3+1]-after.positions[i*3+1]));
      largestAlpha=Math.max(largestAlpha,Math.abs(before.alpha[i]-after.alpha[i]));
    }
    expect(largestDistance).toBeLessThan(1);expect(largestAlpha).toBeLessThan(.02);
    now+=78;step();expect(rimPaint!.uniforms.uUnfurl.value).toBe(1);
    const settled=rendered();now+=1;step();const live=rendered();
    let liveDistance=0,liveAlpha=0;
    for(let i=0;i<settled.alpha.length;i++){
      if(Math.max(settled.alpha[i],live.alpha[i])>.002)liveDistance=Math.max(liveDistance,Math.hypot(settled.positions[i*3]-live.positions[i*3],settled.positions[i*3+1]-live.positions[i*3+1]));
      liveAlpha=Math.max(liveAlpha,Math.abs(settled.alpha[i]-live.alpha[i]));
    }
    expect(liveDistance).toBeLessThan(1);expect(liveAlpha).toBeLessThan(.02);
    expect(getTabStoreSnapshot().tabs.find(tab=>tab.id===artifact.id)?.content?.code).toBe('keep this');
  });
  it('reopens a partial nerve without manufacturing a rim that was never born',()=>{
    let now=2500;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();const artifact=showContentSurface({filepath:'partial-nerve.py',code:'keep this',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'reaching',2400);const view=render(<Surface/>);step();
    act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);now+=300;step();
    const before=nervePaint!.material.uniforms.reach.value as number;
    expect(rimPaint!.uniforms.uVisible.value).toBe(0);
    act(()=>expect(reopenMaterializedTab(artifact.id)).toBe(true));view.rerender(<Surface/>);step();
    expect(nervePaint!.material.uniforms.reach.value).toBeCloseTo(before,6);
    expect(rimPaint!.uniforms.uVisible.value).toBe(0);
    now+=100;step();expect(nervePaint!.material.uniforms.reach.value).toBeGreaterThan(before);
    expect(rimPaint!.uniforms.uVisible.value).toBe(0);
  });
  it('does not replay a reversal after Stop detail appears between frames',()=>{
    let now=1000;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();const artifact=showContentSurface({filepath:'stop-reopen.py',code:'keep this',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'live',now);const view=render(<Surface/>);step();
    now=3000;act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);now=3500;step();
    act(()=>expect(reopenMaterializedTab(artifact.id)).toBe(true));view.rerender(<Surface/>);step();
    const detail=document.createElement('div');detail.className='lm-stop__detail';
    view.container.querySelector('.lm-app')!.appendChild(detail);act(()=>window.dispatchEvent(new Event('resize')));
    detail.remove();act(()=>window.dispatchEvent(new Event('resize')));
    now+=20;step();
    expect(rimPaint!.uniforms.uReturning.value).toBe(0);
    expect(getTabStoreSnapshot().focusId).toBe(artifact.id);
    expect(getTabStoreSnapshot().tabs.find(tab=>tab.id===artifact.id)?.content?.code).toBe('keep this');
  });
  it('drops the old reversal envelope when the canvas changes size',()=>{
    let now=1000;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();const artifact=showContentSurface({filepath:'resize-reopen.py',code:'keep this',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'live',now);const view=render(<Surface/>);step();
    now=3000;act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);now=3500;step();
    act(()=>expect(reopenMaterializedTab(artifact.id)).toBe(true));view.rerender(<Surface/>);step();
    Object.defineProperty(view.container.querySelector('canvas')!,'getBoundingClientRect',{
      configurable:true,value:()=>new DOMRect(100,50,440,400),
    });
    act(()=>window.dispatchEvent(new Event('resize')));now+=10;step();
    expect(rimPaint!.uniforms.uReturning.value).toBe(0);
    expect(getTabStoreSnapshot().focusId).toBe(artifact.id);
    expect(getTabStoreSnapshot().tabs.find(tab=>tab.id===artifact.id)?.content?.code).toBe('keep this');
  });
  it('latches a hold during Reopen even if no animation frame occurs during the hold',()=>{
    let now=1000;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();const artifact=showContentSurface({filepath:'hold-no-frame.py',code:'keep this',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'live',now);const view=render(<Surface/>);step();
    now=3000;act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);now=3500;step();
    act(()=>expect(reopenMaterializedTab(artifact.id)).toBe(true));view.rerender(<Surface/>);step();
    view.rerender(<Surface motionHeld/>);view.rerender(<Surface/>);now+=20;step();
    expect(nervePaint!.material.uniforms.reach.value).toBe(1);
    expect(rimPaint!.uniforms.uUnfurl.value).toBe(1);expect(rimPaint!.uniforms.uVisible.value).toBe(1);
    expect(getTabStoreSnapshot().tabs.find(tab=>tab.id===artifact.id)?.content?.code).toBe('keep this');
  });
  it('settles a reopen immediately on hold and does not replay the reversal after release',()=>{
    let now=1000;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();const artifact=showContentSurface({filepath:'held-reopen.py',code:'keep this',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'live',now);const view=render(<Surface/>);step();
    now=3000;act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);now=3500;step();
    act(()=>expect(reopenMaterializedTab(artifact.id)).toBe(true));view.rerender(<Surface/>);step();
    now+=50;view.rerender(<Surface motionHeld/>);step();
    expect(nervePaint!.material.uniforms.reach.value).toBe(1);expect(rimPaint!.uniforms.uUnfurl.value).toBe(1);
    view.rerender(<Surface/>);now+=20;step();
    expect(nervePaint!.material.uniforms.reach.value).toBe(1);expect(rimPaint!.uniforms.uUnfurl.value).toBe(1);
  });
  it('completes a reopened reverse and keeps its rim settled without replay',()=>{
    let now=1000;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();const artifact=showContentSurface({filepath:'settle.py',code:'keep this',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'live',now);const view=render(<Surface/>);step();
    now=3000;act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);now=3500;step();
    act(()=>expect(reopenMaterializedTab(artifact.id)).toBe(true));view.rerender(<Surface/>);step();
    now+=260;step();
    expect(nervePaint!.material.uniforms.reach.value).toBe(1);
    expect(rimPaint!.uniforms.uVisible.value).toBe(1);expect(rimPaint!.uniforms.uReturning.value).toBe(0);
    expect(rimPaint!.uniforms.uUnfurl.value).toBe(1);
    now+=100;step();expect(rimPaint!.uniforms.uVisible.value).toBe(1);expect(rimPaint!.uniforms.uUnfurl.value).toBe(1);
  });
  it('Reopen reverses the old return and restores the same retained identity',()=>{
    let now=1000;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();const artifact=showContentSurface({filepath:'reopen.py',code:'keep this',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'live',1000);
    const view=render(<Surface/>);step();
    now=3000;act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);now=3650;step();
    expect(rimPaint!.uniforms.uReturning.value).toBe(1);
    const lastPositions=rimPaint!.positions.slice(),lastAlpha=rimPaint!.returnAlpha.slice();
    now=3700;act(()=>{expect(reopenMaterializedTab(artifact.id)).toBe(true);});view.rerender(<Surface/>);step();
    expect(getTabStoreSnapshot().focusId).toBe(artifact.id);expect(rimPaint!.uniforms.uReturning.value).toBe(1);
    expect(Array.from(rimPaint!.positions)).toEqual(Array.from(lastPositions));
    expect(Array.from(rimPaint!.returnAlpha)).toEqual(Array.from(lastAlpha));
    now=4000;act(()=>setMaterializedTabLifecycle(artifact.id,'unfurling',3900));view.rerender(<Surface/>);step();
    expect(rimPaint!.uniforms.uUnfurl.value).toBe(1);
    expect(getTabStoreSnapshot().tabs.find(tab=>tab.id===artifact.id)?.content?.code).toBe('keep this');
  });
  it('does not revive an old nerve after switching to Conversation before Close without a frame', () => {
    let now=2500;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();
    const artifact=showContentSurface({filepath:'conversation.py',code:'keep this',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'reaching',2400);
    const view=render(<Surface/>);step();
    act(()=>focusWorkspace(null));view.rerender(<Surface/>);
    act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);step();
    expect(nervePaint!.mesh.visible).toBe(false);expect(path()).toBe('');
    expect(getTabStoreSnapshot().recoverableTabs?.find(tab=>tab.id===artifact.id)?.content?.code).toBe('keep this');
  });
  it('preserves the painted nerve across a streamed update and Close before the next frame', () => {
    let now=2500;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();
    const artifact=showContentSurface({filepath:'same-owner.py',code:'first',language:'python',streaming:true},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'reaching',2400);
    const view=render(<Surface/>);step();
    const before=nervePaint!.material.uniforms.reach.value as number;
    act(()=>updateMaterializedTab(artifact.id,{content:{...artifact.content!,code:'first plus next chunk',streaming:true}}));
    view.rerender(<Surface/>); // a committed same-owner update, but no renderer frame
    act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);step();
    expect(nervePaint!.mesh.visible).toBe(true);
    expect(nervePaint!.material.uniforms.reach.value).toBeCloseTo(before,6);
    expect(rimPaint!.uniforms.uVisible.value).toBe(0);
    expect(getTabStoreSnapshot().recoverableTabs?.find(tab=>tab.id===artifact.id)?.content?.code).toBe('first plus next chunk');
  });
  it('returns only the already painted nerve when Close interrupts its growth', () => {
    let now=2500;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();
    const artifact=showContentSurface({filepath:'early.py',code:'keep this',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'reaching',2400);
    const view=render(<Surface/>);step();
    const before=nervePaint!.material.uniforms.reach.value as number;
    const paintedPath=path();
    expect(before).toBeGreaterThan(.03);expect(before).toBeLessThan(1);
    expect(rimPaint!.uniforms.uVisible.value).toBe(0);
    act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);step();
    expect(getTabStoreSnapshot().focusId).toBeNull();
    expect(path()).toBe(paintedPath);
    expect(nervePaint!.mesh.visible).toBe(true);
    expect(nervePaint!.material.uniforms.reach.value).toBeCloseTo(before,6);
    expect(nervePaint!.dustMaterial.uniforms.reach.value).toBeCloseTo(before,6);
    expect(rimPaint!.uniforms.uVisible.value).toBe(0);
    now+=650;step();
    expect(nervePaint!.material.uniforms.reach.value).toBeCloseTo(before/2,6);
    expect(1-Number(overlayRef.current!.querySelector('path')!.getAttribute('stroke-dashoffset'))).toBeCloseTo(before/2,6);
    now+=650;step();
    expect(nervePaint!.mesh.visible).toBe(false);expect(path()).toBe('');
    expect(getTabStoreSnapshot().recoverableTabs?.find(tab=>tab.id===artifact.id)?.content?.code).toBe('keep this');
  });
  it.each(['new focus','hold'] as const)('cancels a partially grown return on %s without reviving it later', interruption => {
    let now=2500;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();
    const artifact=showContentSurface({filepath:'early-interrupt.py',code:'keep this',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'reaching',2400);
    const view=render(<Surface/>);step();
    act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);step();
    expect(nervePaint!.mesh.visible).toBe(true);
    if(interruption==='new focus')act(()=>openWorkspacePanel('next-panel','Next work'));
    view.rerender(<Surface motionHeld={interruption==='hold'}/>);step();
    if(interruption==='new focus')act(()=>focusWorkspace(null));
    view.rerender(<Surface/>);step();
    expect(nervePaint!.mesh.visible).toBe(false);expect(path()).toBe('');
    expect(getTabStoreSnapshot().recoverableTabs?.find(tab=>tab.id===artifact.id)?.content?.code).toBe('keep this');
  });
  it('latches an intervening hold even if no return frame is drawn', () => {
    let now=2500;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();
    const artifact=showContentSurface({filepath:'early-hold.py',code:'keep this',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'reaching',2400);
    const view=render(<Surface/>);step();
    act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);
    view.rerender(<Surface motionHeld/>);view.rerender(<Surface/>);
    now+=100;step();
    expect(nervePaint!.mesh.visible).toBe(false);expect(path()).toBe('');
    expect(rimPaint!.uniforms.uVisible.value).toBe(0);
  });
  it('does not create a return when Close occurs before any nerve frame was painted', () => {
    vi.spyOn(performance,'now').mockReturnValue(2500);
    __resetTabStoreForTests();
    const artifact=showContentSurface({filepath:'unpainted.py',code:'keep this',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'reaching',2400);
    const view=render(<Surface/>);
    act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);step();
    expect(nervePaint!.mesh.visible).toBe(false);expect(path()).toBe('');
    expect(rimPaint!.uniforms.uVisible.value).toBe(0);
  });
  it('reduced motion keeps explicit Close immediate and retains the result without drawing a return',()=>{
    vi.stubGlobal('matchMedia',(query:string):MediaQueryList=>({matches:query.includes('reduced-motion'),media:query,onchange:null,
      addEventListener(){},removeEventListener(){},addListener(){},removeListener(){},dispatchEvent:()=>true}));
    __resetTabStoreForTests();const artifact=showContentSurface({filepath:'reduced-return.py',code:'keep this',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'live');const view=render(<Surface/>);step();
    expect(nervePaint!.mesh.visible).toBe(true);expect(nervePaint!.material.uniforms.reach.value).toBe(1);
    act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);step();
    expect(getTabStoreSnapshot().focusId).toBeNull();expect(rimPaint!.uniforms.uVisible.value).toBe(0);expect(path()).toBe('');
    expect(nervePaint!.mesh.visible).toBe(false);expect(nervePaint!.points.visible).toBe(false);
    expect(getTabStoreSnapshot().recoverableTabs?.find(tab=>tab.id===artifact.id)?.content?.code).toBe('keep this');
  });
  it('returns the last painted reader into its moving seat after Close without retaining focus or changing the owner clock',()=>{
    let now=1000;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();
    const artifact=showContentSurface({filepath:'return.py',code:'retained partial',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'live',1000);
    const attentionTargetRef=createRef<{targetId:string;lateral:number;vertical:number}|null>();
    const view=render(<Surface attentionTargetRef={attentionTargetRef}/>);step();
    const before=path();expect(rimPaint!.uniforms.uVisible.value).toBe(1);
    now=3000;act(()=>closeWorkspace(artifact.id));view.rerender(<Surface attentionTargetRef={attentionTargetRef}/>);step();
    const retired=getTabStoreSnapshot().tabs.find(tab=>tab.id===artifact.id)!;
    expect(getTabStoreSnapshot().focusId).toBeNull();expect(attentionTargetRef.current).toBeNull();
    expect(retired.lifecycle).toBe('retracting');expect(retired.phaseStartedAt).toBe(3000);
    expect(rimPaint!.uniforms.uVisible.value,'the DOM owner closed; only decorative matter returns').toBe(1);
    expect(path()).toBe(before);
    now=3650;setBodyGroupWorldMatrix(new Matrix4().makeTranslation(2,0,0));step(1.5);
    expect(rimPaint!.uniforms.uDpr.value).toBe(1.5);
    expect(path()).not.toBe(before);
    expect(path()!.split(',').pop()).toBe(before!.split(',').pop());
    expect(getTabStoreSnapshot().tabs.find(tab=>tab.id===artifact.id)).toBe(retired);
    expect(getTabStoreSnapshot().recoverableTabs?.find(tab=>tab.id===artifact.id)?.content?.code).toBe('retained partial');
    now=4300;step();expect(rimPaint!.uniforms.uVisible.value).toBe(0);expect(path()).toBe('');
    expect(getTabStoreSnapshot().tabs.find(tab=>tab.id===artifact.id)).toBe(retired);
  });
  it('does not replay an interrupted return when the canonical hold is released',()=>{
    let now=1000;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();const artifact=showContentSurface({filepath:'held-return.py',code:'partial',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'live',1000);
    const view=render(<Surface/>);step();now=3000;act(()=>closeWorkspace(artifact.id));view.rerender(<Surface/>);step();
    expect(rimPaint!.uniforms.uVisible.value).toBe(1);
    now=3100;view.rerender(<Surface motionHeld/>);step();expect(rimPaint!.uniforms.uVisible.value).toBe(0);expect(path()).toBe('');
    now=3200;view.rerender(<Surface/>);step();expect(rimPaint!.uniforms.uVisible.value).toBe(0);expect(path()).toBe('');
  });
  it('observes a new birth while the actual reader is hidden and the cable projection cannot paint',()=>{
    let now=2410;vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();
    const artifact=showContentSurface({filepath:'fixture.py',code:'partial',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'reaching',2400);
    const view=render(<Surface motionHeld />);step();
    expect(rimPaint!.uniforms.uUnfurl.value).toBe(1);
    const reader=view.container.querySelector<HTMLElement>('.lm-surface')!;
    reader.hidden=true;now=3010;setMaterializedTabLifecycle(artifact.id,'reaching',3000);
    view.rerender(<Surface />);act(()=>window.dispatchEvent(new Event('resize')));step();
    expect(rimPaint!.uniforms.uVisible.value).toBe(0);expect(path()).toBe('');
    reader.hidden=false;now=4030;setMaterializedTabLifecycle(artifact.id,'unfurling',3900);
    view.rerender(<Surface />);act(()=>window.dispatchEvent(new Event('resize')));step();
    expect(rimPaint!.uniforms.uUnfurl.value).toBe(.25);
  });
  it('settles new decorative growth under the existing canonical Stop hold without advancing the tab owner',()=>{
    vi.spyOn(performance,'now').mockReturnValue(2530);
    __resetTabStoreForTests();
    const artifact=showContentSurface({filepath:'fixture.py',code:'partial',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'unfurling',2400);
    const view=render(<Surface motionHeld />);step();
    expect(rimPaint!.uniforms.uUnfurl.value).toBe(1);
    expect(getTabStoreSnapshot().tabs[0].lifecycle).toBe('unfurling');
    view.rerender(<Surface motionHeld={false} />);step();
    expect(rimPaint!.uniforms.uUnfurl.value,'a short Stop release cannot replay the same birth').toBe(1);
    view.unmount();
  });
  it('feeds the rim from the selected owner epoch and retires it across decision, Conversation and renderer loss',async()=>{
    let now=2530;
    vi.spyOn(performance,'now').mockImplementation(()=>now);
    __resetTabStoreForTests();
    const artifact=showContentSurface({filepath:'fixture.py',code:'readable partial',language:'python'},{seatIndex:2});
    setMaterializedTabLifecycle(artifact.id,'unfurling',2400);
    const view=render(<Surface />);step();
    expect(rimPaint,'one rim in the existing render owner').toBeDefined();
    expect(rimPaint!.uniforms.uVisible.value).toBe(1);
    expect(rimPaint!.uniforms.uUnfurl.value).toBe(.25);
    const originalPaint=rimPaint;
    // Streams do not reset the tab's epoch or replace its render buffers.
    updateMaterializedTab(artifact.id,{content:{...artifact.content!,code:'readable partial plus next chunk'}});
    now=2660;view.rerender(<Surface />);step();
    expect(rimPaint).toBe(originalPaint);expect(rimPaint!.uniforms.uUnfurl.value).toBe(.5);
    view.rerender(<Surface decision />);await act(async()=>{});step();
    expect(rimPaint!.uniforms.uVisible.value).toBe(0);
    view.rerender(<Surface />);await act(async()=>{});step();
    expect(rimPaint!.uniforms.uVisible.value).toBe(1);
    act(()=>focusWorkspace(null));view.rerender(<Surface />);step();
    expect(rimPaint!.uniforms.uVisible.value).toBe(0);
    act(()=>focusWorkspace(artifact.id));view.rerender(<Surface />);step();
    expect(rimPaint!.uniforms.uVisible.value).toBe(1);
    view.rerender(<Surface renderer={false} />);
    expect(originalPaint!.uniforms.uVisible.value).toBe(0);
    expect(getTabStoreSnapshot().tabs[0].content?.code).toBe('readable partial plus next chunk');
  });
  it('publishes the actual cortex-to-plane direction and retires only its own target on Conversation or renderer loss', () => {
    setCortexAnchor([0, 0, 0]); // declared external geometry, not the pre-publish fallback at y=.1
    const attentionTargetRef = createRef<{ targetId: string; lateral: number; vertical: number } | null>();
    const view = render(<Surface attentionTargetRef={attentionTargetRef} />); step();
    // Actual camera projects the cortex at (300,250), independently of the
    // lower vertebra feeding the cable. Measured plane centre is (900,400).
    expect.soft(attentionTargetRef.current).toEqual({ targetId: 'history', lateral: 1, vertical: 0.75 });
    const plane = view.container.querySelector('.lm-surface')!;
    let rect = new DOMRect(20, 100, 100, 300);
    // The inherited prototype method is already a shared mock. Spying on it
    // again changes the canvas/overlay too; supply only this plane's boundary.
    Object.defineProperty(plane, 'getBoundingClientRect', { configurable: true, value: () => rect });
    act(() => window.dispatchEvent(new Event('resize'))); step();
    expect.soft(attentionTargetRef.current).toEqual({ targetId: 'history', lateral: -1, vertical: 0 });
    rect = new DOMRect(100, 500, 400, 200);
    act(() => window.dispatchEvent(new Event('resize'))); step();
    expect.soft(attentionTargetRef.current).toEqual({ targetId: 'history', lateral: 0, vertical: 1 });
    const measurementCount = vi.mocked(Element.prototype.getBoundingClientRect).mock.calls.length;
    for (let n = 0; n < 30; n++) step();
    expect(vi.mocked(Element.prototype.getBoundingClientRect).mock.calls.length, 'frames reuse measured layout').toBe(measurementCount);
    act(() => focusWorkspace(null)); view.rerender(<Surface attentionTargetRef={attentionTargetRef} />); step();
    expect(attentionTargetRef.current).toBeNull();
    act(() => focusWorkspace('history')); view.rerender(<Surface attentionTargetRef={attentionTargetRef} />); step();
    expect.soft(attentionTargetRef.current?.targetId).toBe('history');
    view.rerender(<Surface renderer={false} attentionTargetRef={attentionTargetRef} />);
    expect(attentionTargetRef.current).toBeNull();
  });
  // Missing the pending-dialog target draws no connection (or the older
  // reader's seat). The independent oracle is seat 6's projected pixel and
  // the actual dialog edge, not the projection helper under test.
  it.each([[false, false], [false, true], [true, false], [true, true]])(
    'connects the owned decision, preserving same-path reading and immediate reduced motion (guided=%s, reduced=%s)',
    async (guided, reduced) => {
      vi.stubGlobal('matchMedia', (query: string): MediaQueryList => ({ matches: reduced && query.includes('reduced-motion'),
        media: query, onchange: null, addEventListener: () => {}, removeEventListener: () => {},
        addListener: () => {}, removeListener: () => {}, dispatchEvent: () => true }));
      __resetTabStoreForTests();
      const older = showContentSurface({ filepath: 'same.py', code: 'older result', language: 'python' }, { seatIndex: 2 });
      setMaterializedTabLifecycle(older.id, 'live');
      const newer = showContentSurface({ filepath: 'writing', code: '', language: 'python' }, { seatIndex: 5 });
      updateMaterializedTab(newer.id, { content: { filepath: 'same.py', code: 'new proposal', language: 'python', completion: 'awaiting-approval' } });
      const attentionTargetRef = createRef<{ targetId: string; lateral: number; vertical: number } | null>();
      const view = render(<Surface guided={guided} attentionTargetRef={attentionTargetRef} />); step();
      const readerPath = path();
      let decisionRect = new DOMRect(650, 160, 500, 300);
      vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
        return this.matches('canvas') ? new DOMRect(100, 50, 400, 400)
          : this.matches('.approval-panel') ? decisionRect
            : this.matches('.lm-surface') ? new DOMRect(600, 100, 600, 600)
              : new DOMRect(20, 10, 1200, 800);
      });
      const approval = showApprovalSurface({ requestRef: 'conversation-approval', kindLabel: 'create',
        filepath: 'same.py', summary: 'New proposal', explanation: '', content: 'new proposal', diff: '+new proposal', command: '' }, { seatIndex: 6 });
      // A critical decision connects on the next frame, not after its old
      // materialization timer. The reader remains selected and selectable.
      view.rerender(<Surface guided={guided} decision attentionTargetRef={attentionTargetRef} />);
      await act(async () => {}); step();
      expect(nervePaint!.mesh.visible).toBe(true);expect(nervePaint!.points.visible).toBe(true);
      expect(nervePaint!.material.uniforms.color.value.getHexString()).toBe('ffc36e');
      expect(nervePaint!.dustMaterial.uniforms.color.value.getHexString()).toBe('ffc36e');
      expect(nervePaint!.material.uniforms.signal.value).toBe(-1);
      expect(nervePaint!.material.uniforms.breath.value).toBe(.5);
      expect(nervePaint!.material.uniforms.reach.value).toBe(1);
      expect.soft(path()).toBe('M 280 278 C 454 278, 454 278, 628 278');
      expect.soft(attentionTargetRef.current?.targetId, 'body aim and cable own the same decision').toBe(approval.id);
      expect.soft(overlayRef.current!.querySelector('circle')).toHaveStyle({ visibility: 'visible' });
      expect.soft(overlayRef.current!.querySelector('path')).toHaveAttribute('stroke-dashoffset', '0');
      decisionRect = new DOMRect(100, 500, 400, 200);
      act(() => window.dispatchEvent(new Event('resize'))); step();
      expect.soft(path()).toBe('M 280 278 C 280 383, 280 383, 280 488');
      expect(getTabStoreSnapshot().focusId).toBe(older.id);
      expect(getTabStoreSnapshot().tabs.filter(tab => tab.kind === 'content').map(tab => [tab.id, tab.seatIndex, tab.content?.code]))
        .toEqual([[older.id, 2, 'older result'], [newer.id, 5, 'new proposal']]);
      expect(view.container.innerHTML).not.toContain('fixture-decision');
      act(() => focusWorkspace(null));
      view.rerender(<Surface guided={guided} decision />); await act(async () => {}); step();
      expect(path(), 'the owned decision also connects from explicit Conversation').toBe('M 280 278 C 280 383, 280 383, 280 488');
      expect(getTabStoreSnapshot().focusId).toBeNull();
      for (const seat of [null, 12, -1, 2.5]) {
        act(() => updateMaterializedTab(approval.id, { seatIndex: seat }));
        view.rerender(<Surface guided={guided} decision />); await act(async () => {}); step();
        expect(path(), 'no fabricated decision seat or older reader fallback').toBe('');
        expect(nervePaint!.mesh.visible).toBe(false);expect(nervePaint!.points.visible).toBe(false);
      }
      act(() => updateMaterializedTab(approval.id, { seatIndex: 6,
        approval: { ...approval.approval!, requestRef: 'dev-approval' } }));
      view.rerender(<Surface guided={guided} decision />); await act(async () => {}); step();
      expect(path(), 'a lab proposal does not own the operational dialog').toBe('');
      expect(nervePaint!.mesh.visible).toBe(false);expect(nervePaint!.points.visible).toBe(false);
      act(() => updateMaterializedTab(approval.id, { approval: approval.approval }));
      view.rerender(<Surface guided={guided} decision />); await act(async () => {}); step();
      expect(path()).toBe('M 280 278 C 280 383, 280 383, 280 488');
      act(() => beginRetractingMaterializedTab(approval.id));
      view.rerender(<Surface guided={guided} decision />); await act(async () => {}); step();
      expect(path(), 'a retiring record cannot attach to a lingering decision').toBe('');
      expect(nervePaint!.mesh.visible).toBe(false);expect(nervePaint!.points.visible).toBe(false);
      act(() => focusWorkspace(older.id));
      view.rerender(<Surface guided={guided} />); await act(async () => {}); step();
      expect(path()).toBe(readerPath);
      expect(nervePaint!.material.uniforms.color.value.getHexString()).toBe('79ebff');
    },
  );
  it('follows actual workspace focus and removes the connection on Conversation', () => {
    const view = render(<Surface />);
    step();
    const first = path();
    expect(first).toMatch(/^M 280 /);
    act(() => openWorkspacePanel('terminal', 'Terminal'));
    view.rerender(<Surface />); step();
    expect(path()).not.toBe(first);
    act(() => focusWorkspace('history'));
    view.rerender(<Surface />); step();
    expect(path()).toBe(first);
    act(() => focusWorkspace(null));
    view.rerender(<Surface />); step();
    expect(path()).toBe('');
    expect(overlayRef.current!.querySelector('circle')).toHaveStyle({ visibility: 'hidden' });
    expect(overlayRef.current).toHaveAttribute('aria-hidden', 'true');
  });
  it('does not draw from a fabricated pre-load body matrix or after explicit close', () => {
    __resetSpineFusionForTests();
    const view = render(<Surface />); step();
    expect(path()).toBe('');
    setSpineFusion(1, [0, 0, 0]); setBodyGroupWorldMatrix(new Matrix4()); step();
    expect(path()).not.toBe('');
    act(() => closeWorkspace('history'));
    view.rerender(<Surface />); step();
    expect(path()).toBe('');
  });
  it('clears the old geometry when the renderer unmounts, without touching workspace records', () => {
    const view = render(<Surface />); step();
    expect(path()).not.toBe('');
    view.rerender(<Surface renderer={false} />);
    expect(path()).toBe('');
    expect(overlayRef.current!.querySelector('circle')).toHaveStyle({ visibility: 'hidden' });
    expect(overlayRef.current).toHaveStyle({ visibility: 'hidden' });
    expect(getTabStoreSnapshot().focusId).toBe('history');
    expect(getTabStoreSnapshot().panels?.[0].open).toBe(true);
    view.rerender(<Surface />); step();
    expect(path()).not.toBe('');
  });
  it('refreshes the measured edge on resize, without changing the selected seat', () => {
    const view = render(<Surface />); step();
    const plane = view.container.querySelector('.lm-surface')!;
    Object.defineProperty(plane, 'getBoundingClientRect', { configurable: true,
      value: () => ({ left: 700, top: 100, width: 500, height: 600 }),
    });
    act(() => window.dispatchEvent(new Event('resize'))); step();
    expect(path()).toMatch(/, 678 [\d.]+$/);
    expect(getTabStoreSnapshot().panels?.[0].seatIndex).toBe(2);
  });
  it('draws no phantom connection for readable-only History and connects after a real seat is freed', () => {
    __resetTabStoreForTests();
    for (let n = 0; n < 12; n++) openWorkspacePanel(`panel-${n}`, `Panel ${n}`);
    openWorkspacePanel('history', 'Recent observations');
    const view = render(<Surface />); step();
    expect(getTabStoreSnapshot().panels?.find((panel) => panel.id === 'history')?.seatIndex).toBeNull();
    expect(path()).toBe('');
    act(() => { closeWorkspace('panel-0'); focusWorkspace('history'); });
    view.rerender(<Surface />); step();
    expect(path()).not.toBe('');
  });
  it.each([false, true])('retires an occluded older reader socket without attaching a same-path decision to that seat; reduced=%s', async reduced => {
    vi.stubGlobal('matchMedia', (query: string): MediaQueryList => ({ matches: reduced && query.includes('reduced-motion'),
      media: query, onchange: null, addEventListener: () => {}, removeEventListener: () => {},
      addListener: () => {}, removeListener: () => {}, dispatchEvent: () => true }));
    __resetTabStoreForTests();
    const older = showContentSurface({ filepath: 'same.py', code: 'older result', language: 'python' }, { seatIndex: 2 });
    setMaterializedTabLifecycle(older.id, 'live');
    const newer = showContentSurface({ filepath: 'writing', code: '', language: 'python' }, { seatIndex: 5 });
    updateMaterializedTab(newer.id, { content: { filepath: 'same.py', code: 'new proposal', language: 'python', completion: 'awaiting-approval' } });
    const view = render(<Surface />); step();
    const readerPath = path();
    expect(readerPath).not.toBe('');
    // The decision covers the reader's contact rim, as on the compact phone.
    // Real panel/store/projection; only external layout and WebGL are supplied.
    vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
      const value = this.matches('canvas') ? { x: 100, y: 50, width: 400, height: 400 }
        : this.matches('.lm-surface, .approval-panel') ? { x: 600, y: 100, width: 600, height: 600 }
          : { x: 20, y: 10, width: 1200, height: 800 };
      return { ...value, left: value.x, top: value.y, right: value.x + value.width, bottom: value.y + value.height, toJSON: () => value };
    });
    view.rerender(<Surface decision />);
    await act(async () => {}); step();
    expect(path()).toBe('');
    expect(overlayRef.current!.querySelector('circle')).toHaveStyle({ visibility: 'hidden' });
    expect(getTabStoreSnapshot().focusId).toBe(older.id);
    expect(getTabStoreSnapshot().tabs.filter(tab => tab.kind === 'content').map(tab => [tab.id, tab.seatIndex, tab.content?.code]))
      .toEqual([[older.id, 2, 'older result'], [newer.id, 5, 'new proposal']]);
    view.rerender(<Surface />);
    await act(async () => {}); step();
    expect(path()).toBe(readerPath);
    expect(overlayRef.current!.querySelector('circle')).toHaveStyle({ visibility: 'visible' });
  });
});
