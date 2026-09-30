import type { Camera, Matrix4, Vector3 } from 'three';

export interface ConnectionRect { left: number; top: number; width: number; height: number }
export interface ConnectionPoint { x: number; y: number }
export interface WorkspaceConnectionGeometry {
  source: ConnectionPoint;
  target: ConnectionPoint;
  path: string;
}
export interface WorkspaceConnectionInput {
  origin: Vector3;
  bodyWorld: Matrix4;
  dockScale: number;
  camera: Camera;
  canvas: ConnectionRect;
  plane: ConnectionRect;
  overlay: ConnectionRect;
}

/** Geometry only: a focused workspace is not evidence of backend activity. */
export function projectWorkspaceConnection(input: WorkspaceConnectionInput, scratch = input.origin.clone()): WorkspaceConnectionGeometry | null {
  const { origin, bodyWorld, dockScale, camera, canvas, plane, overlay } = input;
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
  if (x < overlay.left || x > overlay.left + overlay.width || y < overlay.top || y > overlay.top + overlay.height) return null;
  const round = (value: number) => Math.round(value * 2) / 2;
  const source = { x: round(x - overlay.left), y: round(y - overlay.top) };
  const target = { x: round(endX - overlay.left), y: round(endY - overlay.top) };
  const middle = horizontal ? round((source.x + target.x) / 2) : round((source.y + target.y) / 2);
  const path = horizontal
    ? `M ${source.x} ${source.y} C ${middle} ${source.y}, ${middle} ${target.y}, ${target.x} ${target.y}`
    : `M ${source.x} ${source.y} C ${source.x} ${middle}, ${target.x} ${middle}, ${target.x} ${target.y}`;
  return { source, target, path };
}
