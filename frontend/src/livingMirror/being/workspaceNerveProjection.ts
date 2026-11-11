import { Vector3, type Camera } from 'three';
import { easeOutExpo } from '../../superbrain/lib/motionEasing';
import { workspaceConnectionControls, type ConnectionRect, type WorkspaceConnectionGeometry } from './workspaceConnection';

/** Reused slots for the scene bridge. All points lie at the anatomical
 * anchor's camera depth so perspective projects them onto the same SVG cubic. */
export function createNerveProjection() {
  return {p0:new Vector3(),p1:new Vector3(),p2:new Vector3(),p3:new Vector3(),sample:new Vector3(),
    controls:{x1:0,y1:0,x2:0,y2:0},radius:0};
}
type NerveProjection=ReturnType<typeof createNerveProjection>;
function toWorld(out:Vector3,x:number,y:number,z:number,canvas:ConnectionRect,overlay:ConnectionRect,camera:Camera) {
  return out.set((overlay.left+x-canvas.left)/canvas.width*2-1,
    1-(overlay.top+y-canvas.top)/canvas.height*2,z).unproject(camera);
}
function finite(v:Vector3){return Number.isFinite(v.x)&&Number.isFinite(v.y)&&Number.isFinite(v.z);}

export function projectNerveWorld(out:NerveProjection, connection:WorkspaceConnectionGeometry,
  canvas:ConnectionRect,overlay:ConnectionRect,camera:Camera,z:number,dpr:number) {
  const {source,target}=connection;
  if(!Number.isFinite(z)||Math.abs(z)>1||!Number.isFinite(dpr)||dpr<=0
    ||!Number.isFinite(canvas.left+canvas.top+canvas.width+canvas.height+overlay.left+overlay.top)
    ||canvas.width<=0||canvas.height<=0||!Number.isFinite(source.x+source.y+target.x+target.y+connection.middle)
    ||Math.hypot(target.x-source.x,target.y-source.y)<.5)return false;
  const c=workspaceConnectionControls(connection,out.controls);
  toWorld(out.p0,source.x,source.y,z,canvas,overlay,camera);
  toWorld(out.p1,c.x1,c.y1,z,canvas,overlay,camera);
  toWorld(out.p2,c.x2,c.y2,z,canvas,overlay,camera);
  toWorld(out.p3,target.x,target.y,z,canvas,overlay,camera);
  toWorld(out.sample,source.x+1.5,source.y,z,canvas,overlay,camera);
  out.radius=out.p0.distanceTo(out.sample);
  return finite(out.p0)&&finite(out.p1)&&finite(out.p2)&&finite(out.p3)&&Number.isFinite(out.radius)&&out.radius>0;
}

/** Matches the SVG dash's actual revealed interval, including its small
 * initial visible segment and its linear retirement. */
export function nerveVisibleReach(birth:number,retiring:boolean,retirement:number,startingReach=1) {
  return retiring?Math.min(1,Math.max(0,startingReach))*Math.min(1,Math.max(0,1-retirement)):Math.max(.03,easeOutExpo(birth));
}
