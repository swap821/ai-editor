import { useCallback, useLayoutEffect, useMemo, useRef, type RefObject } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { Object3D, Vector3 } from 'three';
import type { TabSnapshot } from '../../superbrain/lib/tabStore';

type Rect={left:number;top:number;right:number;bottom:number;width:number;height:number};
type Layout={root:Rect;canvas:Rect;pane:Rect;obstacles:Rect[]};
type SceneCache=Map<string,{object:Object3D|null;missingAt:number}>;
const MISSING_LOOKUP_INTERVAL_MS=125;
const intersects=(a:Rect,b:Rect)=>a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top;
function hitArea(x:number,y:number,pane:Rect):Rect|null {
  if(pane.width<96||pane.height<48||x<pane.left||x>pane.right||y<pane.top||y>pane.bottom)return null;
  const cx=Math.max(pane.left+48,Math.min(pane.right-48,x));
  const cy=Math.max(pane.top+24,Math.min(pane.bottom-24,y));
  return {left:cx-48,right:cx+48,top:cy-24,bottom:cy+24,width:96,height:48};
}
function belongsToScene(object:Object3D,scene:Object3D):boolean {
  for(let parent:Object3D|null=object;parent;parent=parent.parent)if(parent===scene)return true;
  return false;
}
function resolveWorkspace(id:string,scene:Object3D,frameloop:string,cache:SceneCache):Object3D|null {
  const previous=cache.get(id),now=performance.now();
  if(previous?.object && previous.object.name===`gagos-workspace-${id}` && belongsToScene(previous.object,scene))return previous.object;
  const missingAt=previous?.object ? -Infinity : previous?.missingAt ?? -Infinity;
  if(frameloop==='always' && now-missingAt<MISSING_LOOKUP_INTERVAL_MS)return null;
  const object=scene.getObjectByName(`gagos-workspace-${id}`)??null;
  cache.set(id,{object,missingAt:object ? -Infinity : now});
  return object;
}

/** One measurement and projection owner for the existing background 3D surfaces. */
export function WorkspaceThumbnailTargets({snapshot,overlayRef}:{snapshot:TabSnapshot;overlayRef:RefObject<SVGSVGElement|null>}) {
  const canvas=useThree(state=>state.gl.domElement),invalidate=useThree(state=>state.invalidate),getState=useThree(state=>state.get);
  const idsKey=JSON.stringify(snapshot.tabs.filter(tab=>tab.kind==='content'&&tab.id!==snapshot.focusId
    &&tab.lifecycle==='live'&&typeof tab.seatIndex==='number').map(tab=>tab.id));
  const ids=useMemo(()=>JSON.parse(idsKey) as string[],[idsKey]),idsRef=useRef(ids);
  const layout=useRef<Layout|null>(null),buttons=useRef(new Map<string,HTMLElement>()),ready=useRef(new Set<string>());
  const sceneCache=useRef<SceneCache>(new Map()),scratch=useRef(new Vector3()),lost=useRef(false);
  const projectRef=useRef<(force:boolean)=>Map<string,Rect|null>>(()=>new Map());
  const hide=useCallback((id:string,restoreFocus=false)=>{
    const el=buttons.current.get(id);
    if(!el)return;
    if(el.style.visibility!=='hidden')el.style.visibility='hidden';
    if(document.activeElement===el){
      const root=overlayRef.current?.closest('.lm-app');
      const fallback=restoreFocus ? root?.querySelector<HTMLElement>('.lm-surface:not([hidden]) h2') : null;
      if(fallback)fallback.focus({preventScroll:true});else el.blur();
    }
  },[overlayRef]);
  const hideAll=useCallback((restoreFocus=false)=>{
    for(const id of buttons.current.keys())hide(id,restoreFocus);
  },[hide]);
  useLayoutEffect(()=>{
    idsRef.current=ids;
    const root=overlayRef.current?.closest('.lm-app'),pane=root?.querySelector('.lm-scene');
    if(!root||!canvas||!pane)return;
    const obstacleSelector='.lm-surface:not([hidden]), .lm-stop, .gagos-bar, .gagos-status, .lm-navigation';
    const relevant='.gagos-chrome, .lm-stop__detail, .gagos-account-panel, .bond-panel, [data-secondary-id], .lm-surface, .lm-scene, .gagos-bar, .gagos-status, .lm-navigation';
    const observed=new Set<Element>();let observer:ResizeObserver|null=null;
    const measure=()=>{
      const obstacles=Array.from(root.querySelectorAll(obstacleSelector));
      const found=new Map<string,HTMLElement>();
      for(const element of root.querySelectorAll<HTMLElement>('[data-secondary-id]')){
        const id=element.dataset.secondaryId;if(id&&idsRef.current.includes(id))found.set(id,element);
      }
      for(const [id,element] of buttons.current)if(found.get(id)!==element)hide(id,true);
      buttons.current=found;
      const nextObserved=new Set<Element>([canvas,pane,...obstacles,...found.values()]);
      for(const old of observed)if(!nextObserved.has(old)){observer?.unobserve(old);observed.delete(old);}
      for(const element of nextObserved)if(!observed.has(element)){observed.add(element);observer?.observe(element);}
      ready.current=new Set([...found].filter(([,element])=>element.getClientRects().length>0).map(([id])=>id));
      if(root.querySelector('.gagos-chrome[data-approval-pending="true"], .lm-stop__detail, .gagos-account-panel, .bond-panel')){
        layout.current=null;hideAll();return;
      }
      layout.current={root:root.getBoundingClientRect(),canvas:canvas.getBoundingClientRect(),pane:pane.getBoundingClientRect(),
        obstacles:obstacles.map(element=>element.getBoundingClientRect()).filter(rect=>rect.width>0&&rect.height>0)};
      invalidate();
    };
    observer=typeof ResizeObserver==='function'?new ResizeObserver(measure):null;
    const touchesLayout=(node:Node)=>node instanceof Element&&(node.matches(relevant)||node.querySelector(relevant)!==null);
    const mutation=new MutationObserver(records=>{
      if(records.some(record=>record.type==='attributes'||[...record.addedNodes,...record.removedNodes].some(touchesLayout)))measure();
    });
    mutation.observe(root,{subtree:true,childList:true,attributes:true,attributeFilter:['data-working','data-being-focus','data-approval-pending','hidden']});
    // React's selection handler runs in bubble phase. Re-measure and project
    // synchronously in capture so a surface mounted since the last frame cannot
    // turn a stale target into an ambiguous selection.
    const guardActivation=(event:Event)=>{
      const target=event.target instanceof Element?event.target.closest<HTMLElement>('[data-secondary-id]'):null;
      if(!target||!root.contains(target))return;
      const id=target.dataset.secondaryId,wasVisible=target.style.visibility==='visible';
      measure();
      const hits=projectRef.current(true),hit=id?hits.get(id):null;
      const pointer=event instanceof MouseEvent&&event.detail>0;
      const outside=pointer&&(!hit||event.clientX<hit.left||event.clientX>hit.right||event.clientY<hit.top||event.clientY>hit.bottom);
      if(!id||!wasVisible||buttons.current.get(id)!==target||target.style.visibility!=='visible'||outside){
        event.preventDefault();event.stopPropagation();
      }
    };
    root.addEventListener('click',guardActivation,true);
    const onLost=()=>{lost.current=true;hideAll(true);};
    const onRestored=()=>{lost.current=false;invalidate();};
    canvas.addEventListener('webglcontextlost',onLost);canvas.addEventListener('webglcontextrestored',onRestored);
    // Visual viewport motion can translate the reader without resizing it.
    // Coalesce mobile viewport events; activation still remeasures synchronously.
    const viewport=window.visualViewport;let viewportFrame:number|null=null;
    const scheduleViewportMeasure=()=>{
      if(viewportFrame!==null)return;
      if(typeof window.requestAnimationFrame!=='function'){measure();return;}
      viewportFrame=window.requestAnimationFrame(()=>{viewportFrame=null;measure();});
    };
    measure();window.addEventListener('resize',measure);
    viewport?.addEventListener('resize',scheduleViewportMeasure);viewport?.addEventListener('scroll',scheduleViewportMeasure);
    const currentCache=sceneCache.current;
    return ()=>{root.removeEventListener('click',guardActivation,true);hideAll(true);canvas.removeEventListener('webglcontextlost',onLost);canvas.removeEventListener('webglcontextrestored',onRestored);observer?.disconnect();mutation.disconnect();window.removeEventListener('resize',measure);viewport?.removeEventListener('resize',scheduleViewportMeasure);viewport?.removeEventListener('scroll',scheduleViewportMeasure);if(viewportFrame!==null)window.cancelAnimationFrame(viewportFrame);layout.current=null;buttons.current.clear();ready.current.clear();currentCache.clear();};
  },[ids,overlayRef,hide,hideAll,canvas,invalidate]);
  projectRef.current=(force)=>{
    const {camera,scene,frameloop}=getState(),b=layout.current,selected=idsRef.current;
    if(force)camera.updateWorldMatrix(true,false);
    const hits=new Map<string,Rect|null>();
    if(!b||lost.current||ready.current.size===0){hideAll();return hits;}
    const fresh=new Map<string,Object3D>();
    if(force){
      // One scene walk per activation, not per frame, also rejects duplicate
      // identities rather than trusting whichever duplicate the cache saw first.
      const names=new Map(selected.map(id=>[`gagos-workspace-${id}`,id]));
      let duplicate=false;
      scene.traverse(object=>{
        const id=names.get(object.name);
        if(id===undefined)return;
        if(fresh.has(id))duplicate=true;else fresh.set(id,object);
      });
      if(duplicate){hideAll(true);return hits;}
    }
    for(const id of selected){
      const target=force?(fresh.get(id)??null):resolveWorkspace(id,scene,frameloop,sceneCache.current);
      if(force)sceneCache.current.set(id,{object:target,missingAt:target?-Infinity:performance.now()});
      if(!target){hits.set(id,null);continue;}
      let visible=true;
      for(let parent:Object3D|null=target;parent;parent=parent.parent)if(!parent.visible){visible=false;break;}
      if(!visible){hits.set(id,null);continue;}
      target.updateWorldMatrix(true,false);target.getWorldPosition(scratch.current);scratch.current.project(camera);
      const p=scratch.current;
      if(!Number.isFinite(p.x+p.y+p.z)||Math.abs(p.z)>1){hits.set(id,null);continue;}
      const x=b.canvas.left+(p.x+1)*b.canvas.width/2,y=b.canvas.top+(1-p.y)*b.canvas.height/2;
      hits.set(id,hitArea(x,y,b.pane));
    }
    for(const id of selected){
      const el=buttons.current.get(id),hit=hits.get(id);
      if(!el||!ready.current.has(id)||!hit||b.obstacles.some(rect=>intersects(hit,rect))){hide(id,true);continue;}
      let overlap=false;
      for(const [otherId,other] of hits)if(otherId!==id&&other&&intersects(hit,other)){overlap=true;break;}
      if(overlap){hide(id,true);continue;}
      const transform=`translate3d(${Math.round(hit.left-b.root.left)}px, ${Math.round(hit.top-b.root.top)}px, 0px)`;
      if(el.style.transform!==transform)el.style.transform=transform;
      if(el.style.visibility!=='visible')el.style.visibility='visible';
    }
    return hits;
  };
  useFrame(()=>{projectRef.current(false);});
  return null;
}
