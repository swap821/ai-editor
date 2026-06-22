// reducedMotion — a REACTIVE prefers-reduced-motion store (poster-gap audit P2.6:
// "convert reduced-motion to a useSyncExternalStore"). The 3D scene used to read
// the setting ONCE at mount (useMemo([]) / useRef), so toggling the OS setting
// mid-session did nothing — a real vestibular/a11y defect. This mirrors the
// matchMedia-as-external-store pattern already used by CyberCursor, so the whole
// being responds the instant the operator flips reduced-motion.
//
// The snapshot delegates to shouldReduceMotion() so there is ONE source of truth.
// SSR-safe (server snapshot = false). `win` is injectable for tests only.

import { useSyncExternalStore } from 'react';
import { shouldReduceMotion } from './openingMotion';

/** Subscribe to OS reduced-motion changes; returns an unsubscribe. SSR/no-mediaquery → no-op. */
export function subscribeReducedMotion(
  onChange: () => void,
  win: Window | undefined = typeof window !== 'undefined' ? window : undefined,
): () => void {
  if (!win || typeof win.matchMedia !== 'function') return () => {};
  const mql = win.matchMedia('(prefers-reduced-motion: reduce)');
  mql.addEventListener('change', onChange);
  return () => mql.removeEventListener('change', onChange);
}

/** Current reduced-motion state (one source of truth: shouldReduceMotion). */
export const getReducedMotionSnapshot = (win?: Window): boolean => shouldReduceMotion(win);

/** SSR snapshot: never reduce on the server (avoids a hydration flash). */
const getServerSnapshot = (): boolean => false;

/** Reactive hook — re-renders the consumer when the OS reduced-motion setting flips. */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(subscribeReducedMotion, () => getReducedMotionSnapshot(), getServerSnapshot);
}
