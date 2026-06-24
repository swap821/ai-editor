/**
 * verifyAuroraBridge — product-only bridge for the verify-pass aurora effect.
 *
 * The 3D scene lives under frontend/src/superbrain/ and is overwritten by the
 * lab port, so this product-only store lets a product-side effect component
 * publish transient aurora intensity without touching ported files.
 */

type Listener = (intensity: number) => void;

let intensity = 0;
const listeners = new Set<Listener>();

function notify(): void {
  for (const listener of listeners) listener(intensity);
}

export function setAuroraIntensity(value: number): void {
  intensity = value;
  notify();
}

export function getAuroraIntensity(): number {
  return intensity;
}

export function subscribeAurora(listener: Listener): () => void {
  listeners.add(listener);
  listener(intensity);
  return () => listeners.delete(listener);
}

/** Test seam: reset the bridge between cases. */
export function __resetAuroraBridgeForTests(): void {
  intensity = 0;
  listeners.clear();
}
