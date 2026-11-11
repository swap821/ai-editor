import type { Camera, Matrix4, Vector3 } from 'three';

export interface ConnectionRect { left: number; top: number; width: number; height: number }
export interface ConnectionPoint { x: number; y: number }
export interface WorkspaceConnectionGeometry {
  source: ConnectionPoint;
  target: ConnectionPoint;
  path: string;
  horizontal: boolean;
  middle: number;
  straight?: boolean;
}
export interface WorkspaceConnectionInput {
  origin: Vector3;
  bodyWorld: Matrix4;
  dockScale: number;
  camera: Camera;
  canvas: ConnectionRect;
  plane: ConnectionRect;
  overlay: ConnectionRect;
  occluders?: readonly ConnectionRect[];
  straight?: boolean;
}

/** The reader and its returning points must travel the same curve. A small,
 * bounded lift gives long horizontal connections a natural arc; the vertical
 * phone connection keeps its existing compact path. */
export function workspaceConnectionControls(connection: Pick<WorkspaceConnectionGeometry, 'source' | 'target' | 'horizontal' | 'middle' | 'straight'>,
  out = { x1:0, y1:0, x2:0, y2:0 }) {
  const { source, target, horizontal, middle } = connection;
  const lift = horizontal && !connection.straight ? Math.min(20, Math.abs(target.x - source.x) * 0.12) : 0;
  out.x1=horizontal?middle:source.x;out.y1=horizontal?source.y-lift:middle;
  out.x2=horizontal?middle:target.x;out.y2=horizontal?target.y-lift:middle;
  return out;
}

function connectionPath(source: ConnectionPoint, target: ConnectionPoint, horizontal: boolean, middle: number, straight=false) {
  const { x1, y1, x2, y2 } = workspaceConnectionControls({ source, target, horizontal, middle, straight });
  return `M ${source.x} ${source.y} C ${x1} ${y1}, ${x2} ${y2}, ${target.x} ${target.y}`;
}

/** Move the returning contact along the same exposed edge as the body moves.
 * A different edge requires a fresh projection rather than crossing the reader. */
export function retargetWorkspaceConnection(current:WorkspaceConnectionGeometry, previous:ConnectionPoint,
  previousHorizontal:boolean, progress:number):WorkspaceConnectionGeometry|null {
  if(current.horizontal!==previousHorizontal||!Number.isFinite(previous.x+previous.y+progress))return null;
  // Opposite edges share orientation but cannot be joined through the reader.
  if(current.horizontal?current.target.x!==previous.x:current.target.y!==previous.y)return null;
  const t=Math.min(1,Math.max(0,progress));
  const round=(value:number)=>Math.round(value*2)/2;
  const target={x:round(previous.x+(current.target.x-previous.x)*t),y:round(previous.y+(current.target.y-previous.y)*t)};
  const middle=round(current.horizontal?(current.source.x+target.x)/2:(current.source.y+target.y)/2);
  return {...current,target,middle,path:connectionPath(current.source,target,current.horizontal,middle,current.straight)};
}

/** Geometry only: a focused workspace is not evidence of backend activity. */
export function projectWorkspaceConnection(input: WorkspaceConnectionInput, scratch = input.origin.clone()): WorkspaceConnectionGeometry | null {
  const { origin, bodyWorld, dockScale, camera, canvas, plane, overlay, occluders = [], straight=false } = input;
  if (![canvas, plane, overlay].every((rect) =>
    [rect.left, rect.top, rect.width, rect.height].every(Number.isFinite) && rect.width > 0 && rect.height > 0)
    || !Number.isFinite(dockScale) || dockScale <= 0
    || !bodyWorld.elements.every(Number.isFinite)) return null;

  scratch.copy(origin).multiplyScalar(dockScale).applyMatrix4(bodyWorld).project(camera);
  if (![scratch.x, scratch.y, scratch.z].every(Number.isFinite)
    || Math.abs(scratch.x) > 1 || Math.abs(scratch.y) > 1 || Math.abs(scratch.z) > 1) return null;
  const x = canvas.left + (scratch.x + 1) * canvas.width / 2;
  const y = canvas.top + (1 - scratch.y) * canvas.height / 2;
  const right = plane.left + plane.width;
  const bottom = plane.top + plane.height;
  const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value));
  const inset = Math.min(24, plane.width / 2, plane.height / 2);
  let endX: number;
  let endY: number;
  let horizontal = false;
  if (x < plane.left) {
    endX = plane.left - 2;
    endY = clamp(y, plane.top + inset, bottom - inset);
    horizontal = true;
  } else if (x > right) {
    endX = right + 2;
    endY = clamp(y, plane.top + inset, bottom - inset);
    horizontal = true;
  } else if (y < plane.top) {
    endX = clamp(x, plane.left + inset, right - inset);
    endY = plane.top - 2;
  } else if (y > bottom) {
    endX = clamp(x, plane.left + inset, right - inset);
    endY = bottom + 2;
  } else {
    // Never invent an exposed socket when the body is behind the reading plane.
    return null;
  }
  // The contact bead reaches 3px around its endpoint, 2px outside the reader.
  // A decision painted on that rim must not appear fed by an older reader's
  // seat. Leave exposed reader edges intact; never infer a new decision seat.
  if (occluders.some(rect => endX + 3 >= rect.left && endX - 3 <= rect.left + rect.width
    && endY + 3 >= rect.top && endY - 3 <= rect.top + rect.height)) return null;
  if (x < overlay.left || x > overlay.left + overlay.width || y < overlay.top || y > overlay.top + overlay.height) return null;
  const round = (value: number) => Math.round(value * 2) / 2;
  const source = { x: round(x - overlay.left), y: round(y - overlay.top) };
  const target = { x: round(endX - overlay.left), y: round(endY - overlay.top) };
  const middle = horizontal ? round((source.x + target.x) / 2) : round((source.y + target.y) / 2);
  const path = connectionPath(source, target, horizontal, middle, straight);
  return { source, target, path, horizontal, middle, straight };
}

/** A dismissed reader has no hit/reading plane. Its last real contact can
 * receive retiring matter while the same seat follows the moving body. This
 * never relaxes exposed-edge ownership for a live reader or a decision. */
export function projectWorkspaceReturnConnection(input: Omit<WorkspaceConnectionInput,'plane'> & {
  target: ConnectionPoint; horizontal: boolean;
}, scratch=input.origin.clone()): WorkspaceConnectionGeometry|null {
  const {origin,bodyWorld,dockScale,camera,canvas,overlay,target,horizontal}=input;
  if(![canvas,overlay].every(rect=>Number.isFinite(rect.left+rect.top+rect.width+rect.height)&&rect.width>0&&rect.height>0)
    ||!Number.isFinite(dockScale)||dockScale<=0||!bodyWorld.elements.every(Number.isFinite)
    ||!Number.isFinite(target.x+target.y)) return null;
  scratch.copy(origin).multiplyScalar(dockScale).applyMatrix4(bodyWorld).project(camera);
  if(!Number.isFinite(scratch.x+scratch.y+scratch.z)||Math.abs(scratch.x)>1||Math.abs(scratch.y)>1||Math.abs(scratch.z)>1)return null;
  const x=canvas.left+(scratch.x+1)*canvas.width/2,y=canvas.top+(1-scratch.y)*canvas.height/2;
  if(x<overlay.left||x>overlay.left+overlay.width||y<overlay.top||y>overlay.top+overlay.height
    ||target.x<0||target.x>overlay.width||target.y<0||target.y>overlay.height)return null;
  const round=(value:number)=>Math.round(value*2)/2;
  const source={x:round(x-overlay.left),y:round(y-overlay.top)};
  const middle=round(horizontal?(source.x+target.x)/2:(source.y+target.y)/2);
  const path=connectionPath(source,target,horizontal,middle);
  return {source,target,path,horizontal,middle};
}
