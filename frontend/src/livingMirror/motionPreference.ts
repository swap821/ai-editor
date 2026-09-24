/**
 * Read the platform motion preference without assuming a browser exists.
 *
 * The Living Mirror shell is also rendered by SSR-like and test environments
 * where `window` or `matchMedia` may be absent. Missing capability is an
 * unavailable preference, not permission to invent a reduced-motion state.
 */
export function detectSystemReducedMotion(
  source: Pick<Window, 'matchMedia'> | undefined = typeof window === 'undefined' ? undefined : window,
): boolean {
  return typeof source?.matchMedia === 'function'
    && source.matchMedia('(prefers-reduced-motion: reduce)').matches;
}
