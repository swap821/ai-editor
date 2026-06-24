/**
 * spineFlashBridge — product-only bridge for the first-cloud-route spine flash.
 *
 * A one-shot travelling pulse down the visible spine. GagosChrome triggers it
 * when the operator's first subtask routes to the cloud factory; the
 * product-only SuperbrainReactiveEffects renders it without touching ported lab
 * files.
 */

export interface SpineFlashState {
  /** 0..1 current brightness of the flash. */
  intensity: number;
  /** 0..1 progress of the bead down the spine. */
  progress: number;
}

type Listener = (state: SpineFlashState) => void;

const DURATION_S = 1.6;

let intensity = 0;
let progress = 0;
let elapsed = 0;
const listeners = new Set<Listener>();

function getState(): SpineFlashState {
  return { intensity, progress };
}

function notify(): void {
  const state = getState();
  for (const listener of listeners) listener(state);
}

/** Fire a new spine flash from the brainstem down to the conus. */
export function triggerSpineFlash(): void {
  intensity = 1;
  progress = 0;
  elapsed = 0;
  notify();
}

/** Advance the flash animation; call from a useFrame loop. */
export function advanceSpineFlash(delta: number): void {
  if (intensity <= 0 && progress >= 1) return;
  elapsed += delta;
  progress = Math.min(1, elapsed / DURATION_S);
  intensity = Math.max(0, 1 - elapsed / (DURATION_S * 0.85));
  if (intensity <= 0 && progress >= 1) {
    intensity = 0;
    progress = 1;
  }
  notify();
}

export function subscribeSpineFlash(listener: Listener): () => void {
  listeners.add(listener);
  listener(getState());
  return () => listeners.delete(listener);
}

export function getSpineFlashState(): SpineFlashState {
  return getState();
}

/** Test seam: reset the bridge between cases. */
export function __resetSpineFlashBridgeForTests(): void {
  intensity = 0;
  progress = 0;
  elapsed = 0;
  listeners.clear();
}
