import { PerspectiveCamera } from 'three';

export type PresenceFrame = Readonly<{
  width: number; height: number; x: number; y: number; stageWidth: number; stageHeight: number;
}>;

// Paint-only ownership, scoped to the installed camera. Not a second body,
// render owner, domain store, device detector or public debugging API.
const destinations = new WeakMap<PerspectiveCamera, PresenceFrame>();
export const setPresenceDestination = (camera: PerspectiveCamera, frame: PresenceFrame): void => { destinations.set(camera, frame); };
export const clearPresenceDestination = (camera: PerspectiveCamera): void => { destinations.delete(camera); };
export const getPresenceDestination = (camera: PerspectiveCamera): PresenceFrame | undefined => destinations.get(camera);

/** A matrix calculator only; never installed in R3F or passed to a renderer.
 * Three owns the perspective math (including zoom/film/depth conventions). */
export function createSettledPresenceProjection() {
  const calculator = new PerspectiveCamera();
  return (camera: PerspectiveCamera) => {
    const frame = destinations.get(camera);
    if (!frame) return camera.projectionMatrix;
    calculator.fov = camera.fov; calculator.zoom = camera.zoom;
    calculator.near = camera.near; calculator.far = camera.far;
    calculator.filmGauge = camera.filmGauge; calculator.filmOffset = camera.filmOffset;
    calculator.coordinateSystem = camera.coordinateSystem;
    calculator.setViewOffset(frame.width, frame.height, frame.x, frame.y, frame.stageWidth, frame.stageHeight);
    // Framing changes x/y only. Preserve the installed renderer's actual depth
    // row, including reversed depth (Three exposes it as a read-only getter).
    const source = camera.projectionMatrix.elements, target = calculator.projectionMatrix.elements;
    target[2] = source[2]; target[6] = source[6]; target[10] = source[10]; target[14] = source[14];
    return calculator.projectionMatrix;
  };
}
