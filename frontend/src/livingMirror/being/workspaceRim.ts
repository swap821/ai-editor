import { Color, Vector2, Vector4, type BufferAttribute, type Points, type ShaderMaterial } from 'three';
import type { MaterializedTabRecord } from '../../superbrain/lib/tabStore';
import { MATERIALIZATION_UNFURL_MS } from '../../superbrain/lib/materializationTiming';
import { POINTS_SLAB_RETRACT_MS } from '../../superbrain/lib/reabsorptionTiming';
import { deriveOrganMaterialState } from '../../superbrain/lib/organMaterialState';
import { workspaceConnectionControls, type ConnectionPoint, type ConnectionRect, type WorkspaceConnectionGeometry } from './workspaceConnection';

export interface WorkspaceRimLayout {
  canvas: ConnectionRect; plane: ConnectionRect; overlay: ConnectionRect;
  radius: number; occluders: readonly ConnectionRect[]; decision: boolean; targetId: string;
}
export function createWorkspaceRimState() {
  const count=2400, data=new Float32Array(count*2), offset=new Float32Array(count);
  let seed=8917;
  const random=()=>{seed=Math.imul(1664525,seed)+1013904223|0;return(seed>>>0)/4294967296;};
  for(let i=0;i<count;i++) {
    data[i*2]=i/count; data[i*2+1]=random();
    offset[i]=i%4===0?random()*18:(i%3)*2.7+random()*1.5;
  }
  const palette=deriveOrganMaterialState({kind:'content',focused:true}).palette;
  return { uniforms: { uVisible:{value:0},uUnfurl:{value:0},uOrigin:{value:0},uReturning:{value:0},uReturnTime:{value:0},
    uViewport:{value:new Vector2(1,1)},uDpr:{value:1},
    uReachColor:{value:new Color(palette.reach)},uLiveColor:{value:new Color(palette.live)} },
    rect:new Vector4(),radius:0,length:0,revision:0,
    positions:new Float32Array(count*3),basePositions:new Float32Array(count*3),normals:new Float32Array(count*2),data,offset,
    returnAlpha:new Float32Array(count).fill(1),returning:false,
    birthAlpha:new Float32Array(count),birthLift:new Float32Array(count),paintedCount:0,
    coverageUnfurl:-1,coverageOrigin:-1,coverageRevision:-1,
    point:new Vector2(),normal:new Vector2(),
    gestureOwnerId:null as string|null,gesturePhase:null as MaterializedTabRecord['lifecycle']|null,
    gesturePhaseAt:0,gestureSettled:false,
    points:null as Points|null,material:null as ShaderMaterial|null,
    positionAttribute:null as BufferAttribute|null,normalAttribute:null as BufferAttribute|null,returnAlphaAttribute:null as BufferAttribute|null };
}
export type WorkspaceRimState = ReturnType<typeof createWorkspaceRimState>;
type WorkspaceRimOwner=Pick<MaterializedTabRecord,'id'|'kind'|'lifecycle'|'phaseStartedAt'>;

/** Observe the current focused owner even while geometry cannot paint. A
 * hidden new birth must not inherit a previous settled gesture. */
export function observeWorkspaceRimGesture(out:WorkspaceRimState,owner:WorkspaceRimOwner|undefined,reduced:boolean) {
  if(!owner||owner.kind!=='content'||!Number.isFinite(owner.phaseStartedAt)
    ||(owner.lifecycle!=='reaching'&&owner.lifecycle!=='unfurling'&&owner.lifecycle!=='live')) {
    out.gestureOwnerId=null;out.gesturePhase=null;out.gestureSettled=false;return false;
  }
  const phaseChanged=out.gesturePhase!==owner.lifecycle||out.gesturePhaseAt!==owner.phaseStartedAt;
  const continuesBirth=out.gesturePhase==='reaching'&&owner.lifecycle==='unfurling';
  if(out.gestureOwnerId!==owner.id||(phaseChanged&&owner.lifecycle!=='live'&&!continuesBirth)) out.gestureSettled=false;
  out.gestureOwnerId=owner.id;out.gesturePhase=owner.lifecycle;out.gesturePhaseAt=owner.phaseStartedAt;
  if(reduced||owner.lifecycle==='live') out.gestureSettled=true;
  return true;
}

/** One clockwise perimeter, starting at left-middle. CPU positions are the
 * actual GPU buffers; no second shader approximation of the rounded corners. */
export function sampleWorkspaceRim(state: WorkspaceRimState, fraction: number, out: Vector2, normal: Vector2) {
  const {x,y,z:w,w:h}=state.rect,r=state.radius,arc=Math.PI*r/2;
  let d=((fraction%1+1)%1)*state.length;
  if(d<=h/2-r) {out.set(x,y+h/2-d);normal.set(-1,0);return;}
  d-=h/2-r;
  let angle:number,cx:number,cy:number;
  if(d<=arc) {angle=Math.PI+d/r;cx=x+r;cy=y+r;}
  else if((d-=arc)<=w-2*r) {out.set(x+r+d,y);normal.set(0,-1);return;}
  else if((d-=w-2*r)<=arc) {angle=1.5*Math.PI+d/r;cx=x+w-r;cy=y+r;}
  else if((d-=arc)<=h-2*r) {out.set(x+w,y+r+d);normal.set(1,0);return;}
  else if((d-=h-2*r)<=arc) {angle=d/r;cx=x+w-r;cy=y+h-r;}
  else if((d-=arc)<=w-2*r) {out.set(x+w-r-d,y+h);normal.set(0,1);return;}
  else if((d-=w-2*r)<=arc) {angle=Math.PI/2+d/r;cx=x+r;cy=y+h-r;}
  else {d-=arc;out.set(x,y+h-r-d);normal.set(-1,0);return;}
  normal.set(Math.cos(angle),Math.sin(angle)); out.set(cx+normal.x*r,cy+normal.y*r);
}

function smoothRimStep(lo:number,hi:number,value:number) {
  const t=Math.min(1,Math.max(0,(value-lo)/(hi-lo)));return t*t*(3-2*t);
}

/** Snapshot the birth shader's actual coverage/loft, not merely the Points
 * visibility flag. Keep it immutable during retirement; no unborn tissue. */
function captureBirthPaint(out:WorkspaceRimState) {
  const {uUnfurl,uOrigin}=out.uniforms;
  if(out.coverageUnfurl===uUnfurl.value&&out.coverageOrigin===uOrigin.value&&out.coverageRevision===out.revision)return;
  const spread=1-Math.pow(1-uUnfurl.value,3);out.paintedCount=0;
  for(let i=0;i<out.offset.length;i++) {
    const separation=Math.abs(out.data[i*2]-uOrigin.value),travel=Math.min(separation,1-separation)*2;
    const born=smoothRimStep(travel*.82,travel*.82+.18,spread),settle=smoothRimStep(0,.20,spread-travel*.82);
    out.birthAlpha[i]=born*(.38+.46*out.data[i*2+1]+.32*(1-settle));out.birthLift[i]=(1-settle)*10;
    if(out.birthAlpha[i]>.002)out.paintedCount++;
  }
  out.coverageUnfurl=uUnfurl.value;out.coverageOrigin=uOrigin.value;out.coverageRevision=out.revision;
}

/** Pure presentation write into reused slots/buffers. The tab owner advances
 * its own phase; this observer never creates timers, state or work claims. */
export function writeWorkspaceRimState(out: WorkspaceRimState,
  owner: WorkspaceRimOwner|undefined,
  now:number,reduced:boolean,layout:WorkspaceRimLayout,contact:ConnectionPoint,dpr:number) {
  const u=out.uniforms; u.uVisible.value=0;u.uUnfurl.value=0;u.uReturning.value=0;u.uReturnTime.value=0;
  if(out.returning) {
    out.positions.set(out.basePositions);out.returning=false;
    if(out.positionAttribute)out.positionAttribute.needsUpdate=true;
  }
  const validOwner=observeWorkspaceRimGesture(out,owner,reduced);
  if(!validOwner||!owner||owner.id!==layout.targetId||layout.decision
    ||!Number.isFinite(now+contact.x+contact.y+dpr)
    ||dpr<=0||!Number.isFinite(layout.radius)) return false;
  const {canvas,plane,overlay}=layout;
  if(!validRect(canvas)||!validRect(plane)||!validRect(overlay)) return false;
  // A permission/Stop overlay may occlude a different part of the rim than
  // the nerve bead. Retire decoration across that boundary, not its controls.
  for(const rect of layout.occluders) if(rect.width>0&&rect.height>0
    &&rect.left<plane.left+plane.width+24&&rect.left+rect.width>plane.left-24
    &&rect.top<plane.top+plane.height+24&&rect.top+rect.height>plane.top-24) return false;
  const x=plane.left-canvas.left-2,y=plane.top-canvas.top-2,w=plane.width+4,h=plane.height+4;
  const r=Math.max(.1,Math.min(Math.max(0,layout.radius)+2,w/4,h/4));
  if(out.rect.x!==x||out.rect.y!==y||out.rect.z!==w||out.rect.w!==h||out.radius!==r) {
    out.rect.set(x,y,w,h);out.radius=r;out.length=2*(w+h-4*r)+Math.PI*2*r;
    for(let i=0;i<out.offset.length;i++) {
      sampleWorkspaceRim(out,out.data[i*2],out.point,out.normal);
      out.positions[i*3]=out.point.x+out.normal.x*out.offset[i];
      out.positions[i*3+1]=out.point.y+out.normal.y*out.offset[i];
      out.positions[i*3+2]=(out.data[i*2+1]-.5)*9;
      out.normals[i*2]=out.normal.x;out.normals[i*2+1]=out.normal.y;
    }
    out.basePositions.set(out.positions);out.revision++;
    if(out.positionAttribute) out.positionAttribute.needsUpdate=true;
    if(out.normalAttribute) out.normalAttribute.needsUpdate=true;
  }
  const tx=contact.x+overlay.left-canvas.left,ty=contact.y+overlay.top-canvas.top;
  const dl=Math.abs(tx-x),dr=Math.abs(tx-x-w),dt=Math.abs(ty-y),db=Math.abs(ty-y-h);
  const edge=Math.min(dl,dr,dt,db),arc=Math.PI*r/2;
  // The existing projection rounds to half pixels. No invented socket if the
  // observed target is not on this reader's exposed edge.
  if(edge>1) return false;
  let distance:number;
  if(edge===dl) distance=ty<=y+h/2?y+h/2-ty:out.length-(ty-y-h/2);
  else if(edge===dt) distance=h/2-r+arc+(tx-x-r);
  else if(edge===dr) distance=h/2-r+2*arc+w-2*r+(ty-y-r);
  else distance=h/2-r+3*arc+w-2*r+h-2*r+(x+w-r-tx);
  u.uOrigin.value=((distance/out.length)%1+1)%1;
  u.uViewport.value.set(canvas.width,canvas.height);u.uDpr.value=dpr;
  u.uUnfurl.value=out.gestureSettled?1:owner.lifecycle==='unfurling'
    ?Math.min(1,Math.max(0,(now-owner.phaseStartedAt)/MATERIALIZATION_UNFURL_MS)):0;
  u.uVisible.value=out.gestureSettled||owner.lifecycle==='unfurling'?1:0;
  if(u.uVisible.value===1)captureBirthPaint(out);
  return true;
}

/** Continue the already-painted birth after a reversed return. This changes
 * presentation only; the real tab lifecycle and its timestamp remain intact. */
export function resumeWorkspaceRimBirth(out:WorkspaceRimState,unfurl:number) {
  out.uniforms.uVisible.value=1;
  out.uniforms.uUnfurl.value=Math.min(1,Math.max(0,unfurl));
  captureBirthPaint(out);
}

function validRect(rect:ConnectionRect) {
  return Number.isFinite(rect.left+rect.top+rect.width+rect.height)&&rect.width>0&&rect.height>0;
}

/** Reuse the exact born perimeter and point buffers. Only presentation matter
 * survives Close; the existing record/epoch owns its finite retirement. */
export function writeWorkspaceRimReturn(out:WorkspaceRimState,owner:WorkspaceRimOwner,now:number,
  layout:WorkspaceRimLayout,connection:WorkspaceConnectionGeometry) {
  const u=out.uniforms;u.uVisible.value=0;
  const progress=(now-owner.phaseStartedAt)/POINTS_SLAB_RETRACT_MS;
  if(owner.kind!=='content'||owner.lifecycle!=='retracting'||owner.id!==layout.targetId
    ||!Number.isFinite(progress)||progress<0||progress>=1||out.length<=0||out.paintedCount===0)return false;
  const dx=layout.overlay.left-layout.canvas.left,dy=layout.overlay.top-layout.canvas.top;
  const sx=connection.source.x+dx,sy=connection.source.y+dy,tx=connection.target.x+dx,ty=connection.target.y+dy;
  const controls=workspaceConnectionControls(connection);
  const cx1=controls.x1+dx,cy1=controls.y1+dy,cx2=controls.x2+dx,cy2=controls.y2+dy;
  // Convergence changes coverage, not the number of points. Keep the nerve
  // from becoming an overexposed beam as an entire envelope enters it.
  const densityGain=Math.min(1,Math.hypot(tx-sx,ty-sy)/out.length*1.5);
  for(let i=0;i<out.offset.length;i++) {
    const relative=((out.data[i*2]-u.uOrigin.value)%1+1)%1;
    const lane=relative>.5?relative-1:relative;
    const arrival=.34+Math.abs(lane)*.50+(out.data[i*2+1]-.5)*.06;
    const raw=Math.min(1,progress/arrival),gather=raw*raw*(3-2*raw);
    if(progress<=arrival) {
      if(gather===0) {
        // Start from the actual Float32 attributes consumed by the birth
        // shader, including its small remaining far-edge loft at live.
        out.positions[i*3]=out.basePositions[i*3]+out.normals[i*2]*out.birthLift[i];
        out.positions[i*3+1]=out.basePositions[i*3+1]+out.normals[i*2+1]*out.birthLift[i];
      } else {
        sampleWorkspaceRim(out,u.uOrigin.value+lane*(1-gather),out.point,out.normal);
        const offset=out.offset[i]+out.birthLift[i];
        out.positions[i*3]=out.point.x+out.normal.x*offset*(1-gather);
        out.positions[i*3+1]=out.point.y+out.normal.y*offset*(1-gather);
      }
      out.positions[i*3+2]=out.basePositions[i*3+2]*(1-gather);out.returnAlpha[i]=out.birthAlpha[i]*Math.max(densityGain,1-gather);
    } else {
      const q=Math.min(1,(progress-arrival)/.32),t=1-q;
      out.positions[i*3]=q*q*q*sx+3*q*q*t*cx1+3*q*t*t*cx2+t*t*t*tx;
      out.positions[i*3+1]=q*q*q*sy+3*q*q*t*cy1+3*q*t*t*cy2+t*t*t*ty;
      out.positions[i*3+2]=0;
      const fade=Math.min(1,Math.max(0,(q-.75)/.25));out.returnAlpha[i]=out.birthAlpha[i]*(1-fade*fade*(3-2*fade))*densityGain;
    }
  }
  out.returning=true;u.uVisible.value=1;u.uReturning.value=1;u.uReturnTime.value=progress;
  if(out.positionAttribute)out.positionAttribute.needsUpdate=true;
  if(out.returnAlphaAttribute)out.returnAlphaAttribute.needsUpdate=true;
  return true;
}

/** Declarative uniform props can be copied by the renderer. Write the actual
 * mounted GPU material, including retirement, rather than relying on aliasing. */
export function commitWorkspaceRimPaint(state:WorkspaceRimState) {
  const u=state.uniforms,gpu=state.material?.uniforms;
  if(state.points) state.points.visible=u.uVisible.value===1;
  if(!gpu) return;
  gpu.uVisible.value=u.uVisible.value;gpu.uUnfurl.value=u.uUnfurl.value;
  gpu.uOrigin.value=u.uOrigin.value;gpu.uDpr.value=u.uDpr.value;
  gpu.uReturning.value=u.uReturning.value;gpu.uReturnTime.value=u.uReturnTime.value;
  gpu.uViewport.value.copy(u.uViewport.value);
}
