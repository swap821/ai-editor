import { useCallback, useLayoutEffect, useMemo, useRef, type RefObject } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { Color, Matrix4, Vector3 } from 'three';
import type { TabSnapshot } from '../../superbrain/lib/tabStore';
import { SEGMENT_ANCHORS } from '../../superbrain/lib/spineAnatomy';
import { readBeingMode } from '../../superbrain/lib/beingMode';
import { copyBodyGroupWorldMatrix, getBrainDockScale, getCortexAnchor, getSpineFusion } from '../../superbrain/lib/spineFusionBus';
import type { WorkPlaneAttentionTarget } from '../../superbrain/lib/brainAttentionPosture';
import { MATERIALIZATION_REACH_MS } from '../../superbrain/lib/materializationTiming';
import { POINTS_SLAB_RETRACT_MS } from '../../superbrain/lib/reabsorptionTiming';
import { useReducedMotion } from '../../superbrain/lib/reducedMotion';
import { deriveOrganMaterialState } from '../../superbrain/lib/organMaterialState';
import { projectWorkspaceConnection, projectWorkspaceReturnConnection, retargetWorkspaceConnection, type ConnectionRect, type ConnectionPoint } from './workspaceConnection';
import { WorkspaceRimPoints } from './WorkspaceRimPoints';
import { WorkspaceNerve } from './WorkspaceNerve';
import { createWorkspaceNerve } from './workspaceNerveState';
import { createNerveProjection, projectNerveWorld, nerveVisibleReach } from './workspaceNerveProjection';
import { commitWorkspaceRimPaint, createWorkspaceRimState, observeWorkspaceRimGesture, writeWorkspaceRimState, writeWorkspaceRimReturn, resumeWorkspaceRimBirth, type WorkspaceRimLayout } from './workspaceRim';

type ProjectionLayout=WorkspaceRimLayout & {seat:number};
const WORKSPACE_SIGNAL_MS=400;
const REOPEN_REVERSAL_MS=260;
const WORK_NERVE_COLOR = new Color(deriveOrganMaterialState({ kind: 'content', focused: true }).palette.reach);
const DECISION_NERVE_COLOR = new Color(deriveOrganMaterialState({ kind: 'approval', focused: true }).palette.reach);
function sameRect(a:ConnectionRect,b:ConnectionRect) {
  return a.left===b.left&&a.top===b.top&&a.width===b.width&&a.height===b.height;
}

/** One spatial connection, not a stream, work status, verification or authority. */
export function WorkspaceConnectionProjection({ overlayRef, snapshot, attentionTargetRef, motionHeld=false, breathRef }: {
  overlayRef: RefObject<SVGSVGElement | null>;
  snapshot: TabSnapshot;
  attentionTargetRef?: RefObject<WorkPlaneAttentionTarget | null>;
  motionHeld?:boolean;
  breathRef?: { value: number };
}) {
  const reducedMotion = useReducedMotion();
  const canvas=useThree(state=>state.gl.domElement);
  const rim=useMemo(createWorkspaceRimState,[]);
  const nerve=useMemo(createWorkspaceNerve,[]);
  const nerveProjection=useMemo(createNerveProjection,[]);
  const lastBreath=useRef(.5);
  const visualRetirement=useRef({id:'',kind:'content' as const,lifecycle:'retracting' as const,phaseStartedAt:0});
  const panel = snapshot.panels?.find((candidate) => candidate.open && candidate.id === snapshot.focusId);
  const artifact = snapshot.tabs.find((candidate) => candidate.id === snapshot.focusId && candidate.kind === 'content' && candidate.lifecycle !== 'retracting');
  // Same ownership contract as useDomWorkPlane: only the current adapter's
  // conversation approval delegates its slab to this readable dialog. A lab
  // proposal or missing seat must never borrow the selected reader's address.
  const approval = snapshot.tabs.find((candidate) => candidate.kind === 'approval'
    && candidate.lifecycle !== 'retracting' && candidate.approval?.requestRef === 'conversation-approval');
  const readerSeat = (panel ?? artifact)?.seatIndex;
  const criticalOccluded=useRef(false);
  // A short, coalesced cue for admitted visible content changes. It carries no
  // inferred progress or completion, and never replays after a held interval.
  const signal=useRef<{id:string|null;code:string;startedAt:number|null;pending:boolean;lastChange:number}>(
    {id:null,code:'',startedAt:null,pending:false,lastChange:0});
  useLayoutEffect(()=>{
    const state=signal.current,id=artifact?.id??null,code=artifact?.content?.code??'';
    const allowed=!!id&&!!artifact?.content?.streaming&&!approval?.id&&!criticalOccluded.current&&!motionHeld&&!reducedMotion;
    if(!allowed||state.id!==id){
      state.id=id;state.code=code;state.startedAt=null;state.pending=false;return;
    }
    if(state.code!==code){
      const now=performance.now();
      if(Number.isFinite(now)){
        if(state.startedAt===null||now-state.startedAt>=WORKSPACE_SIGNAL_MS){state.startedAt=now;state.pending=false;}
        else state.pending=true;
        state.lastChange=now;
      }
    }
    state.code=code;
  },[artifact?.id,artifact?.content?.code,artifact?.content?.streaming,approval?.id,motionHeld,reducedMotion]);
  const scratch = useRef({ origin: new Vector3(), projected: new Vector3(), cortex: new Vector3(), world: new Matrix4(),
    target: { targetId: '', lateral: 0, vertical: 0 } });
  const bounds = useRef<{ canvas: ConnectionRect; plane: ConnectionRect; overlay: ConnectionRect;
    occluders: ConnectionRect[]; radius:number; seat: number; decision: boolean; targetId: string } | null>(null);
  // One bounded decorative retirement of the last actually painted reader.
  // It never retains DOM focus or creates/advances a tab lifecycle.
  const captured=useRef<{id:string;layout:ProjectionLayout;target:ConnectionPoint;horizontal:boolean;cancelled:boolean;nerveReach:number;rimPainted:boolean;retirementObserved:boolean;lastReturnProgress:number|null;returnBaseProgress:number;lastVisibleReach:number}|null>(null);
  const reversal=useRef<{id:string;startAt:number;startReach:number;startProgress:number;startUnfurl:number;hasRim:boolean;seat:number;layout:ProjectionLayout;target:ConnectionPoint;horizontal:boolean;startOrigin:number}|null>(null);
  useLayoutEffect(()=>{
    // Distinct commits can occur without a renderer frame between them.
    // Observe interruption now; only a real current-reader paint can rearm.
    const current=captured.current;
    const retiring=!!current&&snapshot.tabs.some(tab=>tab.id===current.id&&tab.lifecycle==='retracting');
    const reopened=!!current&&current.retirementObserved&&snapshot.focusId===current.id;
    const reopenedTab=reopened?snapshot.tabs.find(tab=>tab.id===current?.id):undefined;
    if(reopened&&current&&!current.cancelled&&reopenedTab?.kind==='content'
      &&reopenedTab.seatIndex===current.layout.seat&&!approval?.id&&!motionHeld&&!reducedMotion) {
      reversal.current={id:current.id,startAt:reopenedTab.phaseStartedAt,startReach:current.lastVisibleReach,
        startProgress:current.lastReturnProgress??0,startUnfurl:rim.uniforms.uUnfurl.value,
        hasRim:current.rimPainted,seat:current.layout.seat,layout:current.layout,
        target:{...current.target},horizontal:current.horizontal,startOrigin:rim.uniforms.uOrigin.value};
    }
    if(reversal.current&&(snapshot.focusId!==reversal.current.id||approval?.id||motionHeld||reducedMotion))reversal.current=null;
    // Motion preference/hold can start and end between renderer frames.
    if((motionHeld||reducedMotion)&&artifact)observeWorkspaceRimGesture(rim,artifact,true);
    // A committed switch to Conversation has a null focus just like Close.
    // Distinguish it by the owner's lifecycle, not by focus alone.
    const changedAttention=!!current&&snapshot.focusId!==current.id&&(!retiring||snapshot.focusId!==null);
    const interruption=changedAttention||reopened||!!approval?.id||motionHeld||reducedMotion;
    if(current&&retiring&&!current.retirementObserved){current.returnBaseProgress=current.lastReturnProgress??0;current.retirementObserved=true;}
    if(current&&interruption)current.cancelled=true;
    if((retiring&&interruption)||approval?.id){if(nerve.mesh)nerve.mesh.visible=false;if(nerve.points)nerve.points.visible=false;}
  },[snapshot.focusId,snapshot.tabs,approval?.id,artifact,motionHeld,reducedMotion,nerve,rim]);
  const retireAttention = useCallback(() => {
    if (attentionTargetRef?.current === scratch.current.target) attentionTargetRef.current = null;
  }, [attentionTargetRef]);
  const paint = useRef({ svg: null as SVGSVGElement | null, path: null as SVGPathElement | null,
    contact: null as SVGCircleElement | null, pathData: '', offset: '', contactVisibility: 'hidden', visible: false });
  const clear = useCallback(() => {
    if (nerve.mesh) nerve.mesh.visible=false;
    if (nerve.points) nerve.points.visible=false;
    rim.uniforms.uVisible.value=0;
    commitWorkspaceRimPaint(rim);
    const current = paint.current;
    if (current.pathData !== '') { current.path?.setAttribute('d', ''); current.pathData = ''; }
    // A child's explicit visible value overrides its parent's hidden value.
    // Retire both paints on Close, unavailable geometry and renderer teardown.
    if (current.contactVisibility !== 'hidden') {
      if (current.contact) current.contact.style.visibility = 'hidden';
      current.contactVisibility = 'hidden';
    }
    if (current.visible) { if (current.svg) current.svg.style.visibility = 'hidden'; current.visible = false; }
  }, [rim,nerve]);
  useLayoutEffect(() => {
    const svg = overlayRef.current;
    const boundPaint = paint.current;
    // The overlay owns these nodes and paint values. Cache them at binding,
    // not by querying/reading attributes or styles during every render frame.
    boundPaint.svg = svg;
    boundPaint.path = svg?.querySelector('path') ?? null;
    boundPaint.contact = svg?.querySelector('circle') ?? null;
    const root = svg?.closest('.lm-app');
    bounds.current = null;
    retireAttention();
    clear();
    if (!svg || !root || !canvas || !root.contains(canvas)) return;
    let plane: HTMLElement | null = null;
    let observedOccluders: Element[] = [];
    const watchMutations = () => {
      attributes.disconnect();
      attributes.observe(root, { attributes: true, attributeFilter: ['data-working', 'data-being-focus', 'data-experience-mode', 'style'] });
      if (plane) attributes.observe(plane, { attributes: true, attributeFilter: ['hidden', 'data-workspace-id', 'data-workspace-collapsed', 'style', 'class'] });
      // Direct owner changes only, not every streaming text mutation.
      for (const owner of root.querySelectorAll('.gagos-chrome, .lm-stop')) attributes.observe(owner,
        { childList: true, attributes: true, attributeFilter: ['data-approval-pending'] });
    };
    const measure = () => {
      const pendingOwner = root.querySelector('.gagos-chrome[data-approval-pending="true"]');
      const decision = pendingOwner !== null;
      const currentCanvas=canvas.getBoundingClientRect(),currentOverlay=svg.getBoundingClientRect();
      const criticalRects=Array.from(root.querySelectorAll('.approval-panel, .lm-stop__detail'))
        .map(element=>element.getBoundingClientRect()).filter(rect=>rect.width>0&&rect.height>0);
      criticalOccluded.current=decision||criticalRects.length>0;
      if(criticalOccluded.current){
        signal.current.startedAt=null;signal.current.pending=false;
        // A critical overlay can appear and disappear without a renderer frame.
        if(reversal.current){reversal.current=null;clear();}
      }
      if(captured.current) {
        const prior=captured.current.layout;
        // A resized/repositioned viewport has new controls. Drop the old
        // decorative envelope rather than stretching it across those controls.
        if(criticalOccluded.current||(['left','top','width','height'] as const).some(key=>
          prior.canvas[key]!==currentCanvas[key]||prior.overlay[key]!==currentOverlay[key]))captured.current.cancelled=true;
      }
      const nextPlane = decision
        ? pendingOwner.querySelector<HTMLElement>('.approval-panel[role="alertdialog"]')
        : root.querySelector<HTMLElement>('.lm-surface');
      if (nextPlane !== plane) {
        if (plane) observer?.unobserve(plane);
        plane = nextPlane;
        if (plane) observer?.observe(plane);
        watchMutations();
      }
      const seat = decision ? approval?.seatIndex : readerSeat;
      const targetId = decision ? approval?.id : panel?.id ?? artifact?.id;
      const style = plane ? getComputedStyle(plane) : null;
      if (!plane || plane.closest('[hidden]') || style?.display === 'none' || style?.visibility === 'hidden'
        || !targetId || (!decision && plane.dataset.workspaceId !== targetId)
        || typeof seat !== 'number' || !Number.isInteger(seat) || !SEGMENT_ANCHORS[seat]) {
        bounds.current = null; retireAttention(); clear(); return;
      }
      const overlay = svg.getBoundingClientRect();
      const nextOccluders = Array.from(root.querySelectorAll('.approval-panel, .lm-stop__detail')).filter(element => element !== plane);
      for (const element of observedOccluders) if (!nextOccluders.includes(element)) observer?.unobserve(element);
      for (const element of nextOccluders) if (!observedOccluders.includes(element)) observer?.observe(element);
      observedOccluders = nextOccluders;
      bounds.current = { canvas: canvas.getBoundingClientRect(), plane: plane.getBoundingClientRect(), overlay,
        radius: Number.parseFloat(style?.borderTopLeftRadius??'')||0,
        seat, decision, targetId, occluders: nextOccluders.map(element => element.getBoundingClientRect()).filter(rect => rect.width > 0 && rect.height > 0) };
      svg.setAttribute('viewBox', `0 0 ${overlay.width} ${overlay.height}`);
      svg.setAttribute('data-connection-kind', decision ? 'approval' : 'workspace');
    };
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(measure) : null;
    const attributes = new MutationObserver(measure);
    watchMutations();
    measure();
    [svg, canvas].forEach((element) => observer?.observe(element));
    window.addEventListener('resize', measure);
    window.visualViewport?.addEventListener('resize', measure);
    window.visualViewport?.addEventListener('scroll', measure);
    return () => {
      observer?.disconnect(); attributes.disconnect();
      window.removeEventListener('resize', measure);
      window.visualViewport?.removeEventListener('resize', measure);
      window.visualViewport?.removeEventListener('scroll', measure);
      bounds.current = null; retireAttention(); clear();
      boundPaint.svg = null; boundPaint.path = null; boundPaint.contact = null;
    };
  }, [approval?.id, approval?.seatIndex, artifact?.id, canvas, clear, overlayRef, panel?.id, readerSeat, retireAttention, snapshot.focusId]);

  useFrame(({ camera,gl }) => {
    // Phase facts remain observable while the cable/reader is occluded or
    // unmeasurable. This does not grant permission or paint through a boundary.
    observeWorkspaceRimGesture(rim,artifact,reducedMotion||motionHeld);
    const retained=captured.current;
    const former=retained?snapshot.tabs.find(tab=>tab.id===retained.id):undefined;
    if(retained&&former?.lifecycle==='retracting'&&(snapshot.focusId!==null||approval||criticalOccluded.current||reducedMotion||motionHeld))retained.cancelled=true;
    const retiring=retained&&!retained.cancelled&&former?.lifecycle==='retracting'&&snapshot.focusId===null?former:undefined;
    const layout=retiring?retained!.layout:bounds.current;
    if(!retiring&&(!artifact||!layout))captured.current=null;
    const current = paint.current;
    const { svg, path, contact } = current;
    const raw = layout ? SEGMENT_ANCHORS[layout.seat] : undefined;
    const fusion = getSpineFusion();
    const points = readBeingMode() === 'points';
    if (!svg || !raw || !layout || (points && !fusion.ready)
      || !copyBodyGroupWorldMatrix(scratch.current.world)) {
      if(retiring)retained!.cancelled=true;
      reversal.current=null;retireAttention(); clear(); return;
    }
    // The readable plane and cable share ownership, not a fabricated work
    // signal. Project the actual cortex (not its lower feeding vertebra).
    // Cached layout plus existing live matrices only; no frame-loop DOM read,
    // React update, allocation or independently advancing attention clock.
    if(retiring)retireAttention();
    else if (attentionTargetRef) {
      const { canvas, plane, targetId } = layout;
      const head = scratch.current.cortex.set(...getCortexAnchor()).multiplyScalar(getBrainDockScale())
        .applyMatrix4(scratch.current.world).project(camera);
      const canvasValid = Number.isFinite(canvas.left + canvas.top + canvas.width + canvas.height) && canvas.width > 0 && canvas.height > 0;
      const planeValid = Number.isFinite(plane.left + plane.top + plane.width + plane.height) && plane.width > 0 && plane.height > 0;
      if (!canvasValid || !planeValid || !Number.isFinite(head.x + head.y + head.z)
        || Math.abs(head.x) > 1 || Math.abs(head.y) > 1 || Math.abs(head.z) > 1) retireAttention();
      else {
        const target = scratch.current.target;
        const x = canvas.left + (head.x + 1) * canvas.width / 2;
        const y = canvas.top + (1 - head.y) * canvas.height / 2;
        target.targetId = targetId;
        target.lateral = Math.max(-1, Math.min(1, (plane.left + plane.width / 2 - x) / (canvas.width / 2)));
        target.vertical = Math.max(-1, Math.min(1, (plane.top + plane.height / 2 - y) / (canvas.height / 2)));
        attentionTargetRef.current = target;
      }
    }
    const origin = scratch.current.origin.copy(raw);
    if (points) origin.multiplyScalar(fusion.spineScale).add(scratch.current.projected.set(...fusion.weld));
    let connection = retiring?projectWorkspaceReturnConnection({
      origin,bodyWorld:scratch.current.world,dockScale:getBrainDockScale(),camera,...layout,target:retained!.target,horizontal:retained!.horizontal,
    },scratch.current.projected):projectWorkspaceConnection({
      origin, bodyWorld: scratch.current.world, dockScale: getBrainDockScale(), camera, ...layout, straight:layout.decision,
    }, scratch.current.projected);
    if (!connection) { if(retiring)retained!.cancelled=true;else captured.current=null;reversal.current=null;clear(); return; }
    const candidate=reversal.current;
    const compatible=!!candidate&&candidate.seat===layout.seat&&sameRect(candidate.layout.canvas,layout.canvas)
      &&sameRect(candidate.layout.overlay,layout.overlay)&&sameRect(candidate.layout.plane,layout.plane);
    if(candidate&&(!compatible||criticalOccluded.current))reversal.current=null;
    let reversing=!retiring&&compatible&&!criticalOccluded.current&&candidate?.id===artifact?.id
      &&!layout.decision&&!reducedMotion&&!motionHeld?candidate:null;
    const reversalProgress=reversing?Math.min(1,Math.max(0,(performance.now()-reversing.startAt)/REOPEN_REVERSAL_MS)):0;
    const reversalEase=reversalProgress*reversalProgress*(3-2*reversalProgress);
    if(reversing) {
      const retargeted=retargetWorkspaceConnection(connection,reversing.target,reversing.horizontal,reversalEase);
      if(retargeted)connection=retargeted;
      else {reversal.current=null;reversing=null;}
    }
    if(retiring) {
      reversal.current=null;
      const dpr=gl.getPixelRatio();
      if(!Number.isFinite(dpr)||dpr<=0){retained!.cancelled=true;clear();return;}
      rim.uniforms.uDpr.value=dpr;
      const elapsed=(performance.now()-retiring.phaseStartedAt)/POINTS_SLAB_RETRACT_MS;
      if(!Number.isFinite(elapsed)||elapsed<0||elapsed>=1){retained!.cancelled=true;clear();return;}
      const initial=retained!.returnBaseProgress;
      const progress=initial+(1-initial)*elapsed;
      if(retained!.rimPainted){
        const visualOwner=visualRetirement.current;visualOwner.id=retiring.id;
        visualOwner.phaseStartedAt=performance.now()-progress*POINTS_SLAB_RETRACT_MS;
        if(!writeWorkspaceRimReturn(rim,visualOwner,performance.now(),layout,connection)){retained!.cancelled=true;clear();return;}
      } else {
        // A partial nerve can exist before any rim points are born. Never
        // manufacture rim tissue just to animate the connection returning.
        rim.uniforms.uVisible.value=0;rim.uniforms.uReturning.value=0;rim.uniforms.uReturnTime.value=progress;
      }
    } else if(reversing?.hasRim&&reversalProgress<.7) {
      const reverseTime=reversing.startProgress*(1-Math.min(1,reversalEase/.784));
      const visualOwner=visualRetirement.current;visualOwner.id=reversing.id;
      visualOwner.phaseStartedAt=performance.now()-reverseTime*POINTS_SLAB_RETRACT_MS;
      if(!writeWorkspaceRimReturn(rim,visualOwner,performance.now(),layout,connection)){reversal.current=null;clear();return;}
    } else {
      const rimReady=writeWorkspaceRimState(rim,artifact,performance.now(),reducedMotion||motionHeld,layout,connection.target,gl.getPixelRatio());
      if(reversing&&!rimReady){reversal.current=null;reversing=null;}
      if(reversing?.hasRim&&rimReady) {
        // The returned rim keeps its original birth origin while it regrows;
        // the moving contact can then retarget without changing point coverage.
        rim.uniforms.uOrigin.value=reversing.startOrigin;
        const growth=Math.min(1,Math.max(0,(reversalProgress-.7)/.3));
        resumeWorkspaceRimBirth(rim,reversing.startUnfurl+(1-reversing.startUnfurl)*growth);
        if(reversalProgress===1)rim.gestureSettled=true;
      }
    }
    commitWorkspaceRimPaint(rim);
    // Avoid DOM writes while a still/reduced-motion body remains at the same pixel.
    if (current.pathData !== connection.path) {
      path?.setAttribute('d', connection.path);
      current.pathData = connection.path;
      contact?.setAttribute('cx', String(connection.target.x));
      contact?.setAttribute('cy', String(connection.target.y));
    }
    // The same birth owner keeps running when its slab yields to the DOM.
    // Restore that existing nerve reach, not a second animation/timer or an
    // entrance delay on readable work. Focus/stream updates do not reset it.
    const reach = !layout.decision && artifact?.lifecycle === 'reaching' && !reducedMotion && !motionHeld && !rim.gestureSettled
      ? Math.min(1, Math.max(0, (performance.now() - artifact.phaseStartedAt) / MATERIALIZATION_REACH_MS)) : 1;
    const normalReach=nerveVisibleReach(reach,false,0);
    const visualReach=retiring
      ?nerveVisibleReach(reach,true,(performance.now()-retiring.phaseStartedAt)/POINTS_SLAB_RETRACT_MS,retained?.nerveReach)
      :reversing?reversing.startReach+(1-reversing.startReach)*reversalEase:normalReach;
    // Capture the last actually projected nerve independently of rim birth.
    // Close may arrive before the rim exists or between animation frames.
    if(!retiring&&artifact&&!layout.decision) {
      const nerveReach=visualReach;
      const rimPainted=rim.uniforms.uVisible.value===1&&rim.paintedCount>0;
      const lastReturnProgress=reversing?.hasRim&&reversalProgress<.7?rim.uniforms.uReturnTime.value:null;
      if(!captured.current||captured.current.id!==artifact.id||captured.current.layout!==layout)captured.current={
        id:artifact.id,layout,target:{...connection.target},horizontal:connection.horizontal,cancelled:false,nerveReach,rimPainted,retirementObserved:false,lastReturnProgress,returnBaseProgress:0,lastVisibleReach:visualReach,
      };
      else {captured.current.target.x=connection.target.x;captured.current.target.y=connection.target.y;
        captured.current.horizontal=connection.horizontal;captured.current.cancelled=false;captured.current.nerveReach=nerveReach;captured.current.rimPainted=rimPainted;captured.current.retirementObserved=false;captured.current.lastReturnProgress=lastReturnProgress;captured.current.lastVisibleReach=visualReach;}
    } else if(retiring&&retained){retained.lastReturnProgress=rim.uniforms.uReturnTime.value;retained.lastVisibleReach=visualReach;}
    else if(!retiring) captured.current=null;
    if(reversing&&reversalProgress===1)reversal.current=null;
    // A spatial connection only: it follows the admitted seat and reader path,
    // without independently signalling backend work or authority.
    if (nerve.mesh && nerve.material && nerve.points && nerve.dustMaterial) {
      nerve.mesh.visible = projectNerveWorld(nerveProjection,connection,layout.canvas,layout.overlay,
        camera,scratch.current.projected.z,gl.getPixelRatio());
      nerve.points.visible = nerve.mesh.visible;
      if (nerve.mesh.visible) {
        const u=nerve.material.uniforms;
        u.p0.value.copy(nerveProjection.p0);u.p1.value.copy(nerveProjection.p1);
        u.p2.value.copy(nerveProjection.p2);u.p3.value.copy(nerveProjection.p3);
        u.radius.value=nerveProjection.radius;
        u.color.value.copy(layout.decision ? DECISION_NERVE_COLOR : WORK_NERVE_COLOR);
        u.reach.value=visualReach;
        const cue=signal.current,now=performance.now();
        let progress=-1;
        if(!retiring&&!layout.decision&&artifact?.id===cue.id&&cue.startedAt!==null&&!reducedMotion&&!motionHeld){
          const elapsed=now-cue.startedAt;
          if(Number.isFinite(elapsed)&&elapsed>=0&&elapsed<WORKSPACE_SIGNAL_MS)progress=elapsed/WORKSPACE_SIGNAL_MS;
          else if(Number.isFinite(elapsed)&&cue.pending&&now-cue.lastChange<=WORKSPACE_SIGNAL_MS){
            cue.startedAt=now;cue.pending=false;progress=0;
          } else {cue.startedAt=null;cue.pending=false;}
        }
        u.signal.value=progress;
        // The connection shares the body's motion; a hold never generates a new pulse.
        if(reducedMotion||layout.decision)lastBreath.current=.5;
        else if(!motionHeld&&Number.isFinite(breathRef?.value))lastBreath.current=Math.max(0,Math.min(1.35,breathRef!.value));
        u.breath.value=lastBreath.current;
        const dust=nerve.dustMaterial.uniforms;
        dust.p0.value.copy(u.p0.value);dust.p1.value.copy(u.p1.value);dust.p2.value.copy(u.p2.value);dust.p3.value.copy(u.p3.value);
        dust.radius.value=u.radius.value;dust.reach.value=u.reach.value;dust.dpr.value=gl.getPixelRatio();dust.breath.value=u.breath.value;
        dust.signal.value=u.signal.value;dust.color.value.copy(u.color.value);
      }
    }
    const offset = String(1-visualReach);
    if (current.offset !== offset) { path?.setAttribute('stroke-dashoffset', offset); current.offset = offset; }
    const contactVisibility = !retiring&&reach >= 1 ? 'visible' : 'hidden';
    if (current.contactVisibility !== contactVisibility) {
      if (contact) contact.style.visibility = contactVisibility;
      current.contactVisibility = contactVisibility;
    }
    if (!current.visible) { svg.style.visibility = 'visible'; current.visible = true; }
  });
  return <><WorkspaceRimPoints state={rim} /><WorkspaceNerve state={nerve} /></>;
}
