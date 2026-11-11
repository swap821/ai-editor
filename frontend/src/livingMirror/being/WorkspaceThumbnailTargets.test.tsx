import { act, createRef } from 'react';
import { cleanup, fireEvent, render } from '@testing-library/react';
import { advance, createRoot, extend, useFrame, _roots, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, expect, it, vi } from 'vitest';
import { WorkspaceThumbnailTargets } from './WorkspaceThumbnailTargets';
import { LivingWorkspaceShell } from '../LivingWorkspaceShell';
import { __resetTabStoreForTests, focusWorkspace, getTabStoreSnapshot, setMaterializedTabLifecycle, showContentSurface } from '../../superbrain/lib/tabStore';
import { getContentSurfacePlacement } from '../../superbrain/lib/materializedSurfaceAnchors';

extend({ Group: THREE.Group });
afterEach(() => { cleanup(); __resetTabStoreForTests(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('tracks a real scene object, hides at a permission boundary, and reacquires a replaced object', async () => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  const rect = {x:0,y:0,left:0,top:0,right:800,bottom:800,width:800,height:800,toJSON:()=>({})};
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function(this: Element) { return this.matches('.lm-surface') ? {...rect,right:0,bottom:0,width:0,height:0} : rect; });
  vi.spyOn(Element.prototype, 'getClientRects').mockReturnValue([rect] as unknown as DOMRectList);
  const selected=showContentSurface({filepath:'first.txt',language:'text',code:'first'},getContentSurfacePlacement(2));
  setMaterializedTabLifecycle(selected.id,'live');
  const other=showContentSurface({filepath:'other.txt',language:'text',code:'other'},getContentSurfacePlacement(4));
  setMaterializedTabLifecycle(other.id,'live');
  // The store may attend the newly created tab; use its actual snapshot with the first as focus.
  const snapshot={...getTabStoreSnapshot(),focusId:selected.id};
  const overlayRef=createRef<SVGSVGElement>(),select=vi.fn();
  const dom=render(<div className="lm-app"><div className="lm-scene"/><canvas data-decoy="true"/><canvas/><svg ref={overlayRef}/><section className="lm-surface"><h2 tabIndex={-1}>Current workspace</h2></section><button data-secondary-id={other.id} onClick={select} style={{visibility:'hidden'}}/></div>);
  const canvas=dom.container.querySelectorAll('canvas')[1];
  const button=dom.container.querySelector('button')!;
  const scene=new THREE.Scene();
  const camera=new THREE.PerspectiveCamera(55,1,.1,100);camera.position.set(0,0,10);camera.updateMatrixWorld();
  const root=createRoot(canvas),store=_roots.get(canvas)!.store;
  const gl={domElement:canvas,render(){},setSize(){},setPixelRatio(){},getPixelRatio:()=>1} as unknown as RootState['gl'];
  await root.configure({gl,scene,camera,frameloop:'never',size:{width:800,height:800,left:0,top:0}});
  const invalidate=vi.fn();store.setState({invalidate});
  await act(async()=>{root.render(<WorkspaceThumbnailTargets snapshot={snapshot} overlayRef={overlayRef}/>)});
  const first=new THREE.Group(),container=new THREE.Group();first.name=`gagos-workspace-${other.id}`;first.position.x=-2;container.add(first);scene.add(container);
  const frame=()=>act(()=>advance(1,false,store.getState()));
  frame();expect(button.style.visibility).toBe('visible');const initial=button.style.transform;
  invalidate.mockClear();window.dispatchEvent(new Event('resize'));expect(invalidate).toHaveBeenCalled();
  first.position.x=-1;frame();expect(button.style.transform).not.toBe(initial);
  fireEvent.click(button);expect(select).toHaveBeenCalledTimes(1); // keyboard-style activation
  const previousPoint=first.getWorldPosition(new THREE.Vector3()).project(camera);
  first.position.x=2; // move after paint, before pointer activation
  fireEvent.click(button,{detail:1,clientX:(previousPoint.x+1)*400,clientY:400});
  expect(select).toHaveBeenCalledTimes(1);
  fireEvent.click(button);expect(select).toHaveBeenCalledTimes(2);
  const duplicate=new THREE.Group();duplicate.name=first.name;duplicate.position.x=2;scene.add(duplicate);
  fireEvent.click(button);expect(select).toHaveBeenCalledTimes(2);
  scene.remove(duplicate);frame();expect(button.style.visibility).toBe('visible');
  const correctName=first.name;first.name='unrelated-surface';
  fireEvent.click(button);expect(select).toHaveBeenCalledTimes(2);
  first.name=correctName;frame();expect(button.style.visibility).toBe('visible');
  const oldView=first.getWorldPosition(new THREE.Vector3()).project(camera);
  camera.position.x=3; // camera can also change after the last painted frame
  fireEvent.click(button,{detail:1,clientX:(oldView.x+1)*400,clientY:400});
  expect(select).toHaveBeenCalledTimes(2);
  camera.position.x=0;camera.updateMatrixWorld();first.position.x=-1;frame();
  button.focus();scene.remove(container);const before=button.style.transform;frame();
  expect(button.style.visibility).toBe('hidden');expect(document.activeElement).toBe(dom.container.querySelector('h2'));
  const replacement=new THREE.Group();replacement.name=first.name;replacement.position.x=2;scene.add(replacement);
  frame();expect(button.style.transform).not.toBe(before);
  const guard=document.createElement('div');guard.className='gagos-chrome';guard.dataset.approvalPending='true';dom.container.querySelector('.lm-app')!.appendChild(guard);
  fireEvent.click(button);expect(select).toHaveBeenCalledTimes(2); // before mutation-observer delivery
  await act(async()=>{});frame();expect(button.style.visibility).toBe('hidden');
  guard.remove();await act(async()=>{});frame();expect(button.style.visibility).toBe('visible');
  button.focus();expect(document.activeElement).toBe(button);
  dom.container.querySelector('[data-decoy]')!.dispatchEvent(new Event('webglcontextlost', {cancelable:true}));
  expect(button.style.visibility).toBe('visible');
  canvas.dispatchEvent(new Event('webglcontextlost', {cancelable:true}));
  // A lost renderer may never deliver another animation frame.
  expect(button.style.visibility).toBe('hidden');
  expect(document.activeElement).toBe(dom.container.querySelector('h2'));
  canvas.dispatchEvent(new Event('webglcontextrestored'));frame();expect(button.style.visibility).toBe('visible');
  await act(async()=>root.unmount());expect(button.style.visibility).toBe('hidden');dom.unmount();
});
it('does not leave ambiguous targets when two moving workspace surfaces overlap', async () => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  const rect = {x:0,y:0,left:0,top:0,right:800,bottom:800,width:800,height:800,toJSON:()=>({})};
  vi.spyOn(Element.prototype,'getBoundingClientRect').mockImplementation(function(this: Element) { return this.matches('.lm-surface') ? {...rect,right:0,bottom:0,width:0,height:0} : rect; });
  vi.spyOn(Element.prototype,'getClientRects').mockReturnValue([rect] as unknown as DOMRectList);
  const first=showContentSurface({filepath:'first.txt',language:'text',code:'first'},getContentSurfacePlacement(2));setMaterializedTabLifecycle(first.id,'live');
  const left=showContentSurface({filepath:'left.txt',language:'text',code:'left'},getContentSurfacePlacement(4));setMaterializedTabLifecycle(left.id,'live');
  const right=showContentSurface({filepath:'right.txt',language:'text',code:'right'},getContentSurfacePlacement(6));setMaterializedTabLifecycle(right.id,'live');
  const snapshot={...getTabStoreSnapshot(),focusId:first.id},overlayRef=createRef<SVGSVGElement>(),select=vi.fn();
  const dom=render(<div className="lm-app"><div className="lm-scene"/><canvas/><svg ref={overlayRef}/><section className="lm-surface"><h2 tabIndex={-1}>Current workspace</h2></section><button data-secondary-id={left.id} onClick={select} style={{visibility:'hidden'}}/><button data-secondary-id={right.id} style={{visibility:'hidden'}}/></div>);
  const canvas=dom.container.querySelector('canvas')!,buttons=dom.container.querySelectorAll('button'),scene=new THREE.Scene();
  const camera=new THREE.PerspectiveCamera(55,1,.1,100);camera.position.set(0,0,10);camera.updateMatrixWorld();
  const root=createRoot(canvas),store=_roots.get(canvas)!.store;
  const gl={domElement:canvas,render(){},setSize(){},setPixelRatio(){},getPixelRatio:()=>1} as unknown as RootState['gl'];
  await root.configure({gl,scene,camera,frameloop:'never',size:{width:800,height:800,left:0,top:0}});
  await act(async()=>{root.render(<WorkspaceThumbnailTargets snapshot={snapshot} overlayRef={overlayRef}/>)});
  const a=new THREE.Group(),b=new THREE.Group(),peerContainer=new THREE.Group();a.name=`gagos-workspace-${left.id}`;b.name=`gagos-workspace-${right.id}`;a.position.x=-2;b.position.x=2;peerContainer.add(b);scene.add(a,peerContainer);
  const frame=()=>act(()=>advance(1,false,store.getState()));frame();
  expect(buttons[0].style.visibility).toBe('visible');expect(buttons[1].style.visibility).toBe('visible');
  buttons[0].focus();b.position.x=-2;frame();
  expect(buttons[0].style.visibility).toBe('hidden');expect(buttons[1].style.visibility).toBe('hidden');
  expect(document.activeElement).toBe(dom.container.querySelector('h2'));
  scene.remove(peerContainer);frame();expect(buttons[0].style.visibility).toBe('visible');expect(buttons[1].style.visibility).toBe('hidden');
  fireEvent.click(buttons[0]);expect(select).toHaveBeenCalledTimes(1);
  let now=0;vi.spyOn(performance,'now').mockImplementation(()=>now);const lookup=vi.spyOn(scene,'getObjectByName');
  store.setState({frameloop:'always'});
  for(let tick=0;tick<60;tick++){now=tick*16;frame();}
  expect(lookup.mock.calls.filter(([name])=>name===b.name).length).toBeLessThanOrEqual(18);
  const replacement=new THREE.Group();replacement.name=b.name;replacement.position.x=-2;scene.add(replacement);
  // The replacement can mount between throttled lookups while animation runs.
  // Activation must inspect it before any frame or React selection handler runs.
  now+=1;fireEvent.click(buttons[0]);expect(select).toHaveBeenCalledTimes(1);
  frame();expect(buttons[0].style.visibility).toBe('hidden');expect(buttons[1].style.visibility).toBe('hidden');
  store.setState({frameloop:'demand'});frame();expect(buttons[0].style.visibility).toBe('hidden');expect(buttons[1].style.visibility).toBe('hidden');
  replacement.position.x=2;frame();expect(buttons[0].style.visibility).toBe('visible');expect(buttons[1].style.visibility).toBe('visible');
  await act(async()=>root.unmount());dom.unmount();
});
it('bounds missing-surface searches during motion but finds a late surface on a demand frame', async () => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  let now=0;vi.spyOn(performance,'now').mockImplementation(()=>now);
  const rect={x:0,y:0,left:0,top:0,right:800,bottom:800,width:800,height:800,toJSON:()=>({})};
  vi.spyOn(Element.prototype,'getBoundingClientRect').mockReturnValue(rect);
  vi.spyOn(Element.prototype,'getClientRects').mockReturnValue([rect] as unknown as DOMRectList);
  const focused=showContentSurface({filepath:'first.txt',language:'text',code:'first'},getContentSurfacePlacement(2));setMaterializedTabLifecycle(focused.id,'live');
  const other=showContentSurface({filepath:'second.txt',language:'text',code:'second'},getContentSurfacePlacement(4));setMaterializedTabLifecycle(other.id,'live');
  const snapshot={...getTabStoreSnapshot(),focusId:focused.id},overlayRef=createRef<SVGSVGElement>();
  const dom=render(<div className="lm-app"><div className="lm-scene"/><canvas/><svg ref={overlayRef}/><button data-secondary-id={other.id} style={{visibility:'hidden'}}/></div>);
  const canvas=dom.container.querySelector('canvas')!,button=dom.container.querySelector('button')!,scene=new THREE.Scene();
  const camera=new THREE.PerspectiveCamera(55,1,.1,100);camera.position.set(0,0,10);camera.updateMatrixWorld();
  const root=createRoot(canvas),store=_roots.get(canvas)!.store;
  const gl={domElement:canvas,render(){},setSize(){},setPixelRatio(){},getPixelRatio:()=>1} as unknown as RootState['gl'];
  await root.configure({gl,scene,camera,frameloop:'never',size:{width:800,height:800,left:0,top:0}});
  await act(async()=>{root.render(<WorkspaceThumbnailTargets snapshot={snapshot} overlayRef={overlayRef}/>)});
  const lookup=vi.spyOn(scene,'getObjectByName');
  store.setState({frameloop:'always'});
  for(let frame=0;frame<60;frame++){now=frame*16;act(()=>advance(now,false,store.getState()));}
  expect(button.style.visibility).toBe('hidden');
  expect(lookup.mock.calls.filter(([name])=>name===`gagos-workspace-${other.id}`).length).toBeLessThanOrEqual(9);
  const late=new THREE.Group();late.name=`gagos-workspace-${other.id}`;scene.add(late);
  store.setState({frameloop:'demand'});act(()=>advance(now,false,store.getState()));
  expect(button.style.visibility).toBe('visible');
  await act(async()=>root.unmount());dom.unmount();
});

it('remeasures a growing reader before allowing its projected workspace target to overlap', async () => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  const observers: Array<{ targets: Set<Element>; callback: ResizeObserverCallback }> = [];
  class ControlledResizeObserver {
    targets = new Set<Element>();
    constructor(callback: ResizeObserverCallback) { observers.push({ targets: this.targets, callback }); }
    observe(target: Element) { this.targets.add(target); }
    unobserve(target: Element) { this.targets.delete(target); }
    disconnect() { this.targets.clear(); }
  }
  vi.stubGlobal('ResizeObserver', ControlledResizeObserver);
  const rect = { x: 0, y: 0, left: 0, top: 0, right: 800, bottom: 800, width: 800, height: 800, toJSON: () => ({}) };
  let readerCoversTarget = false;
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function(this: Element) {
    if (this.matches('.lm-surface')) return readerCoversTarget
      ? { ...rect, x: 340, y: 340, left: 340, top: 340, right: 460, bottom: 460, width: 120, height: 120 }
      : { ...rect, right: 0, bottom: 0, width: 0, height: 0 };
    return rect;
  });
  vi.spyOn(Element.prototype, 'getClientRects').mockReturnValue([rect] as unknown as DOMRectList);
  const first = showContentSurface({ filepath: 'first.txt', language: 'text', code: 'first' }, getContentSurfacePlacement(2));
  setMaterializedTabLifecycle(first.id, 'live');
  const other = showContentSurface({ filepath: 'other.txt', language: 'text', code: 'other' }, getContentSurfacePlacement(4));
  setMaterializedTabLifecycle(other.id, 'live');
  const snapshot = { ...getTabStoreSnapshot(), focusId: first.id }, overlayRef = createRef<SVGSVGElement>();
  const dom = render(<div className="lm-app"><div className="lm-scene"/><canvas/><svg ref={overlayRef}/><section className="lm-surface"><h2 tabIndex={-1}>Current workspace</h2></section><button data-secondary-id={other.id} style={{ visibility: 'hidden' }}/></div>);
  const canvas = dom.container.querySelector('canvas')!, reader = dom.container.querySelector('.lm-surface')!, button = dom.container.querySelector('button')!;
  const scene = new THREE.Scene(), object = new THREE.Group(); object.name = `gagos-workspace-${other.id}`; scene.add(object);
  const camera = new THREE.PerspectiveCamera(55, 1, .1, 100); camera.position.set(0, 0, 10); camera.updateMatrixWorld();
  const root = createRoot(canvas), store = _roots.get(canvas)!.store;
  const gl = { domElement: canvas, render() {}, setSize() {}, setPixelRatio() {}, getPixelRatio: () => 1 } as unknown as RootState['gl'];
  await root.configure({ gl, scene, camera, frameloop: 'never', size: { width: 800, height: 800, left: 0, top: 0 } });
  const invalidate = vi.fn(); store.setState({ invalidate });
  await act(async () => { root.render(<WorkspaceThumbnailTargets snapshot={snapshot} overlayRef={overlayRef}/>); });
  const frame = () => act(() => advance(1, false, store.getState()));
  const resizeReader = () => {
    for (const entry of observers) if (entry.targets.has(reader)) entry.callback([{ target: reader } as ResizeObserverEntry], {} as ResizeObserver);
  };
  frame(); expect(button.style.visibility).toBe('visible');
  button.focus(); readerCoversTarget = true; invalidate.mockClear();
  act(resizeReader); frame();
  expect(invalidate).toHaveBeenCalled();
  expect(button.style.visibility).toBe('hidden');
  expect(document.activeElement).toBe(dom.container.querySelector('h2'));
  readerCoversTarget = false; act(resizeReader); frame();
  expect(button.style.visibility).toBe('visible');
  await act(async () => root.unmount()); dom.unmount();
});

it('tracks all eleven waiting seats with bounded shared lookup and safe overlap recovery', async () => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  const observers: Array<{targets:Set<Element>;disconnected:boolean}> = [];
  class CountingResizeObserver {
    record={targets:new Set<Element>(),disconnected:false};
    constructor(){observers.push(this.record);}
    observe(element:Element){this.record.targets.add(element);}
    unobserve(element:Element){this.record.targets.delete(element);}
    disconnect(){this.record.disconnected=true;this.record.targets.clear();}
  }
  vi.stubGlobal('ResizeObserver',CountingResizeObserver);
  let now = 0; vi.spyOn(performance, 'now').mockImplementation(() => now);
  const rect = { x: 0, y: 0, left: 0, top: 0, right: 1200, bottom: 1200, width: 1200, height: 1200, toJSON: () => ({}) };
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function(this: Element) {
    return this.matches('.lm-surface') ? { ...rect, right: 0, bottom: 0, width: 0, height: 0 } : rect;
  });
  vi.spyOn(Element.prototype, 'getClientRects').mockReturnValue([rect] as unknown as DOMRectList);
  const focused = showContentSurface({ filepath: 'focused.txt', language: 'text', code: 'focused' }, getContentSurfacePlacement(0));
  setMaterializedTabLifecycle(focused.id, 'live');
  const waiting = Array.from({ length: 11 }, (_, i) => {
    const tab = showContentSurface({ filepath: `waiting-${i}.txt`, language: 'text', code: 'waiting' }, getContentSurfacePlacement(i + 1));
    setMaterializedTabLifecycle(tab.id, 'live'); return tab;
  });
  const snapshot = { ...getTabStoreSnapshot(), focusId: focused.id }, overlayRef = createRef<SVGSVGElement>();
  const dom = render(<div className="lm-app"><div className="lm-scene"/><canvas/><svg ref={overlayRef}/><section className="lm-surface"><h2 tabIndex={-1}>Current workspace</h2></section>{waiting.map(tab => <button key={tab.id} data-secondary-id={tab.id} style={{visibility:'hidden'}}/>)}</div>);
  const canvas = dom.container.querySelector('canvas')!, buttons = dom.container.querySelectorAll('button'), scene = new THREE.Scene();
  const objects = waiting.map((tab, i) => { const obj = new THREE.Group(); obj.name = `gagos-workspace-${tab.id}`; obj.position.set(-3 + (i % 4) * 2, 3 - Math.floor(i / 4) * 3, 0); scene.add(obj); return obj; });
  const camera = new THREE.PerspectiveCamera(55, 1, .1, 100); camera.position.set(0, 0, 10); camera.updateMatrixWorld();
  const root = createRoot(canvas), store = _roots.get(canvas)!.store;
  const gl = { domElement: canvas, render() {}, setSize() {}, setPixelRatio() {}, getPixelRatio: () => 1 } as unknown as RootState['gl'];
  await root.configure({ gl, scene, camera, frameloop: 'never', size: { width: 1200, height: 1200, left: 0, top: 0 } });
  await act(async () => { root.render(<WorkspaceThumbnailTargets snapshot={snapshot} overlayRef={overlayRef}/>); });
  const lookup = vi.spyOn(scene, 'getObjectByName');
  const project = vi.spyOn(THREE.Vector3.prototype, 'project');
  const frame = () => act(() => advance(now, false, store.getState()));
  frame();
  expect(Array.from(buttons).filter(button => button.style.visibility === 'visible')).toHaveLength(11);
  expect(observers).toHaveLength(1);
  expect(Array.from(buttons).every(button=>observers[0].targets.has(button))).toBe(true);
  await act(async()=>{root.render(<WorkspaceThumbnailTargets snapshot={{...snapshot,tabs:[...snapshot.tabs]}} overlayRef={overlayRef}/>);});
  expect(observers).toHaveLength(1); // Same selection must not replace the shared observer.
  expect(observers[0].disconnected).toBe(false);
  expect(lookup.mock.calls).toHaveLength(11);
  expect(project).toHaveBeenCalledTimes(11);
  store.setState({frameloop:'always'});
  for (let tick = 0; tick < 60; tick++) { now = tick * 16; frame(); }
  expect(lookup.mock.calls).toHaveLength(11);
  expect(project).toHaveBeenCalledTimes(11 * 61);
  buttons[0].focus(); objects[1].position.copy(objects[0].position); frame();
  expect(buttons[0].style.visibility).toBe('hidden'); expect(buttons[1].style.visibility).toBe('hidden');
  expect(Array.from(buttons).slice(2).every(button => button.style.visibility === 'visible')).toBe(true);
  expect(document.activeElement).toBe(dom.container.querySelector('h2'));
  objects[1].position.x += 2; frame();
  buttons[10].focus(); scene.remove(objects[10]); lookup.mockClear(); frame();
  expect(document.activeElement).toBe(dom.container.querySelector('h2'));
  for (let tick = 0; tick < 60; tick++) { now += 16; frame(); }
  expect(Array.from(buttons).slice(0,10).every(button => button.style.visibility === 'visible')).toBe(true);
  expect(buttons[10].style.visibility).toBe('hidden');
  expect(lookup.mock.calls.filter(([name]) => name === objects[10].name).length).toBeLessThanOrEqual(9);
  scene.add(objects[10]); store.setState({frameloop:'demand'}); frame();
  expect(Array.from(buttons).filter(button => button.style.visibility === 'visible')).toHaveLength(11);
  await act(async () => root.unmount());
  expect(observers[0].disconnected).toBe(true);
  dom.unmount();
});

it('keeps an edge workspace selectable by shifting its hit area inside the pane', async () => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  const rect = { x: 0, y: 0, left: 0, top: 0, right: 800, bottom: 800, width: 800, height: 800, toJSON: () => ({}) };
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue(rect);
  vi.spyOn(Element.prototype, 'getClientRects').mockReturnValue([rect] as unknown as DOMRectList);
  const focused = showContentSurface({ filepath: 'focused.txt', language: 'text', code: 'focused' }, getContentSurfacePlacement(0));
  setMaterializedTabLifecycle(focused.id, 'live');
  const waiting = showContentSurface({ filepath: 'edge.txt', language: 'text', code: 'edge' }, getContentSurfacePlacement(1));
  setMaterializedTabLifecycle(waiting.id, 'live');
  const snapshot = { ...getTabStoreSnapshot(), focusId: focused.id }, overlayRef = createRef<SVGSVGElement>();
  const dom = render(<div className="lm-app"><div className="lm-scene"/><canvas/><svg ref={overlayRef}/><button data-secondary-id={waiting.id} style={{visibility:'hidden'}}/></div>);
  const canvas = dom.container.querySelector('canvas')!, button = dom.container.querySelector('button')!, scene = new THREE.Scene();
  const object = new THREE.Group(); object.name = `gagos-workspace-${waiting.id}`; object.position.x = -4.7; scene.add(object);
  const camera = new THREE.PerspectiveCamera(55, 1, .1, 100); camera.position.set(0, 0, 10); camera.updateMatrixWorld();
  const root = createRoot(canvas), store = _roots.get(canvas)!.store;
  const gl = { domElement: canvas, render() {}, setSize() {}, setPixelRatio() {}, getPixelRatio: () => 1 } as unknown as RootState['gl'];
  await root.configure({gl, scene, camera, frameloop:'never', size:{width:800,height:800,left:0,top:0}});
  await act(async () => { root.render(<WorkspaceThumbnailTargets snapshot={snapshot} overlayRef={overlayRef}/>); });
  act(() => advance(1, false, store.getState()));
  expect(button.style.visibility).toBe('visible');
  expect(button.style.transform).toMatch(/^translate3d\(0px, /);
  await act(async () => root.unmount()); dom.unmount();
});


it('projects the current scene pose on the same frame as workspace motion', async () => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  const rect={x:0,y:0,left:0,top:0,right:800,bottom:800,width:800,height:800,toJSON:()=>({})};
  vi.spyOn(Element.prototype,'getBoundingClientRect').mockReturnValue(rect);
  vi.spyOn(Element.prototype,'getClientRects').mockReturnValue([rect] as unknown as DOMRectList);
  const focused=showContentSurface({filepath:'focused.txt',language:'text',code:'focused'},getContentSurfacePlacement(0));setMaterializedTabLifecycle(focused.id,'live');
  const other=showContentSurface({filepath:'moving.txt',language:'text',code:'moving'},getContentSurfacePlacement(1));setMaterializedTabLifecycle(other.id,'live');
  const snapshot={...getTabStoreSnapshot(),focusId:focused.id},overlayRef=createRef<SVGSVGElement>();
  const dom=render(<div className="lm-app"><div className="lm-scene"/><canvas/><svg ref={overlayRef}/><button data-secondary-id={other.id} style={{visibility:'hidden'}}/></div>);
  const canvas=dom.container.querySelector('canvas')!,button=dom.container.querySelector('button')!,scene=new THREE.Scene();
  const object=new THREE.Group();object.name=`gagos-workspace-${other.id}`;scene.add(object);
  const camera=new THREE.PerspectiveCamera(55,1,.1,100);camera.position.set(0,0,10);camera.updateMatrixWorld();
  const root=createRoot(canvas),store=_roots.get(canvas)!.store;
  const gl={domElement:canvas,render(){},setSize(){},setPixelRatio(){},getPixelRatio:()=>1} as unknown as RootState['gl'];
  await root.configure({gl,scene,camera,frameloop:'never',size:{width:800,height:800,left:0,top:0}});
  let nextX=-2;
  function MovingSurface(){useFrame(()=>{object.position.x=nextX;});return null;}
  await act(async()=>{root.render(<><MovingSurface/><WorkspaceThumbnailTargets snapshot={snapshot} overlayRef={overlayRef}/></>)});
  const frame=()=>act(()=>advance(1,false,store.getState()));
  for(const x of [-2,0,2]){
    nextX=x;frame();
    const projected=object.getWorldPosition(new THREE.Vector3()).project(camera);
    const left=Math.round((projected.x+1)*400-48);
    expect(button.style.visibility).toBe('visible');
    expect(button.style.transform).toBe(`translate3d(${left}px, 376px, 0px)`);
  }
  await act(async()=>root.unmount());dom.unmount();
});


it('guards the real workspace owner when a missing surface reappears before activation', async () => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('fetch', vi.fn(async () => ({ok:false,status:503,json:async()=>({})})));
  const rect={x:0,y:0,left:0,top:0,right:800,bottom:800,width:800,height:800,toJSON:()=>({})};
  const empty={...rect,right:0,bottom:0,width:0,height:0};
  vi.spyOn(Element.prototype,'getBoundingClientRect').mockImplementation(function(this:Element){
    return this.matches('.lm-app, .lm-scene, canvas')?rect:empty;
  });
  vi.spyOn(Element.prototype,'getClientRects').mockReturnValue([rect] as unknown as DOMRectList);
  const selected=showContentSurface({filepath:'focused.txt',language:'text',code:'focused'},getContentSurfacePlacement(0));
  const target=showContentSurface({filepath:'target.txt',language:'text',code:'target'},getContentSurfacePlacement(1));
  const missing=showContentSurface({filepath:'missing.txt',language:'text',code:'missing'},getContentSurfacePlacement(2));
  for(const tab of [selected,target,missing])setMaterializedTabLifecycle(tab.id,'live');
  focusWorkspace(selected.id);
  const snapshot=getTabStoreSnapshot(),overlayRef=createRef<SVGSVGElement>();
  const dom=render(<div className="lm-app"><div className="lm-scene"/><canvas/><svg ref={overlayRef}/><LivingWorkspaceShell experienceMode="beginner"/></div>);
  const canvas=dom.container.querySelector('canvas')!,scene=new THREE.Scene();
  const camera=new THREE.PerspectiveCamera(55,1,.1,100);camera.position.set(0,0,10);camera.updateMatrixWorld();
  const root=createRoot(canvas),store=_roots.get(canvas)!.store;
  const gl={domElement:canvas,render(){},setSize(){},setPixelRatio(){},getPixelRatio:()=>1} as unknown as RootState['gl'];
  await root.configure({gl,scene,camera,frameloop:'never',size:{width:800,height:800,left:0,top:0}});
  try {
    await act(async()=>{root.render(<WorkspaceThumbnailTargets snapshot={snapshot} overlayRef={overlayRef}/>)});
    const present=new THREE.Group();present.name=`gagos-workspace-${target.id}`;scene.add(present);
    act(()=>advance(1,false,store.getState()));
    const button=dom.container.querySelector<HTMLButtonElement>(`[data-secondary-id="${target.id}"]`)!;
    expect(button.style.visibility).toBe('visible');
    const returned=new THREE.Group();returned.name=`gagos-workspace-${missing.id}`;scene.add(returned);
    fireEvent.click(button); // No animation frame has admitted the returned object.
    expect(getTabStoreSnapshot().focusId).toBe(selected.id);
    expect(button.style.visibility).toBe('hidden');
    scene.remove(returned);act(()=>advance(2,false,store.getState()));
    expect(button.style.visibility).toBe('visible');
    fireEvent.click(button);
    expect(getTabStoreSnapshot().focusId).toBe(target.id);
  } finally {await act(async()=>root.unmount());dom.unmount();}
});


it('remeasures moving reader occlusion on visual viewport scroll and resize', async () => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  const viewport=new EventTarget();vi.stubGlobal('visualViewport',viewport);
  const tasks=new Map<number,FrameRequestCallback>();let sequence=0;
  const schedule=vi.spyOn(window,'requestAnimationFrame').mockImplementation(callback=>{tasks.set(++sequence,callback);return sequence;});
  vi.spyOn(window,'cancelAnimationFrame').mockImplementation(id=>{tasks.delete(id);});
  const flushViewport=()=>{const pending=[...tasks.values()];tasks.clear();for(const callback of pending)callback(0);};
  const rect={x:0,y:0,left:0,top:0,right:800,bottom:800,width:800,height:800,toJSON:()=>({})};
  let covers=false;
  vi.spyOn(Element.prototype,'getBoundingClientRect').mockImplementation(function(this:Element){
    if(this.matches('.lm-surface')){const x=covers?340:620;return {...rect,x,left:x,right:x+120,y:340,top:340,bottom:460,width:120,height:120};}
    return rect;
  });
  vi.spyOn(Element.prototype,'getClientRects').mockReturnValue([rect] as unknown as DOMRectList);
  const first=showContentSurface({filepath:'first.txt',language:'text',code:'first'},getContentSurfacePlacement(2));setMaterializedTabLifecycle(first.id,'live');
  const other=showContentSurface({filepath:'other.txt',language:'text',code:'other'},getContentSurfacePlacement(4));setMaterializedTabLifecycle(other.id,'live');
  const snapshot={...getTabStoreSnapshot(),focusId:first.id},overlayRef=createRef<SVGSVGElement>(),select=vi.fn();
  const dom=render(<div className="lm-app"><div className="lm-scene"/><canvas/><svg ref={overlayRef}/><section className="lm-surface"><h2 tabIndex={-1}>Current workspace</h2></section><button data-secondary-id={other.id} onClick={select} style={{visibility:'hidden'}}/></div>);
  const canvas=dom.container.querySelector('canvas')!,button=dom.container.querySelector('button')!,scene=new THREE.Scene();
  const object=new THREE.Group();object.name=`gagos-workspace-${other.id}`;scene.add(object);
  const camera=new THREE.PerspectiveCamera(55,1,.1,100);camera.position.set(0,0,10);camera.updateMatrixWorld();
  const root=createRoot(canvas),store=_roots.get(canvas)!.store;
  const gl={domElement:canvas,render(){},setSize(){},setPixelRatio(){},getPixelRatio:()=>1} as unknown as RootState['gl'];
  await root.configure({gl,scene,camera,frameloop:'never',size:{width:800,height:800,left:0,top:0}});
  const invalidate=vi.fn();store.setState({invalidate});
  await act(async()=>{root.render(<WorkspaceThumbnailTargets snapshot={snapshot} overlayRef={overlayRef}/>);});
  const frame=()=>act(()=>advance(1,false,store.getState()));frame();
  expect(button.style.visibility).toBe('visible');button.focus();
  covers=true;invalidate.mockClear();schedule.mockClear();
  act(()=>{viewport.dispatchEvent(new Event('scroll'));viewport.dispatchEvent(new Event('resize'));});
  expect(schedule).toHaveBeenCalledTimes(1);
  fireEvent.click(button);expect(select).not.toHaveBeenCalled(); // guard remeasures before the scheduled frame
  invalidate.mockClear();act(flushViewport);frame();
  expect(invalidate).toHaveBeenCalled();expect(button.style.visibility).toBe('hidden');
  expect(document.activeElement).toBe(dom.container.querySelector('h2'));
  covers=false;invalidate.mockClear();act(()=>viewport.dispatchEvent(new Event('resize')));act(flushViewport);frame();
  expect(invalidate).toHaveBeenCalled();expect(button.style.visibility).toBe('visible');
  act(()=>viewport.dispatchEvent(new Event('scroll')));expect(tasks.size).toBe(1);
  await act(async()=>root.unmount());expect(tasks.size).toBe(0);invalidate.mockClear();
  act(()=>{viewport.dispatchEvent(new Event('scroll'));viewport.dispatchEvent(new Event('resize'));});
  expect(tasks.size).toBe(0);expect(invalidate).not.toHaveBeenCalled();dom.unmount();
});
