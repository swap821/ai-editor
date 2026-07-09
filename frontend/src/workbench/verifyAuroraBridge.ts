/**
 * verifyAuroraBridge — product-only bridge for the verify-pass aurora effect.
 *
 * The 3D scene lives under frontend/src/superbrain/ and is overwritten by the
 * lab port, so this product-only store lets a product-side effect component
 * publish transient aurora intensity without touching ported files.
 */

type AuroraState = { intensity: number; verdict: 'pass' | 'fail' | 'caution' | null };
type Listener = (state: AuroraState) => void;

let state: AuroraState = { intensity: 0, verdict: null };
const listeners = new Set<Listener>();

function notify(): void {
  for (const listener of listeners) listener(state);
}

export function setAuroraIntensity(value: number, verdict?: 'pass' | 'fail' | 'caution' | null): void {
  state = { intensity: value, verdict: verdict !== undefined ? verdict : state.verdict };
  notify();
}

export function getAuroraState(): AuroraState {
  return state;
}

export function subscribeAurora(listener: Listener): () => void {
  listeners.add(listener);
  listener(state);
  return () => listeners.delete(listener);
}

/** Test seam: reset the bridge between cases. */
export function __resetAuroraBridgeForTests(): void {
  state = { intensity: 0, verdict: null };
  listeners.clear();
}
