import { describe, it, expect, vi } from 'vitest';
import { subscribeReducedMotion, getReducedMotionSnapshot } from './reducedMotion';

/** A fake matchMedia returning a controllable MediaQueryList with listener spies. */
function fakeWin(matches: boolean) {
  const listeners = new Set<() => void>();
  const mql = {
    matches,
    addEventListener: (_t: string, cb: () => void) => listeners.add(cb),
    removeEventListener: (_t: string, cb: () => void) => listeners.delete(cb),
  };
  return {
    win: { matchMedia: () => mql } as unknown as Window,
    fire: () => listeners.forEach((cb) => cb()),
    listenerCount: () => listeners.size,
  };
}

describe('reducedMotion store', () => {
  it('snapshot reflects the media query', () => {
    expect(getReducedMotionSnapshot(fakeWin(true).win)).toBe(true);
    expect(getReducedMotionSnapshot(fakeWin(false).win)).toBe(false);
  });

  it('subscribe wires a change listener and notifies on change', () => {
    const { win, fire, listenerCount } = fakeWin(false);
    const onChange = vi.fn();
    const unsub = subscribeReducedMotion(onChange, win);
    expect(listenerCount()).toBe(1);
    fire();
    expect(onChange).toHaveBeenCalledTimes(1);
    unsub();
    expect(listenerCount()).toBe(0); // unsubscribe removes the listener
  });

  it('is SSR-safe: no window/matchMedia → false + no-op unsubscribe', () => {
    expect(getReducedMotionSnapshot(undefined)).toBe(false);
    const unsub = subscribeReducedMotion(() => {}, undefined);
    expect(typeof unsub).toBe('function');
    expect(() => unsub()).not.toThrow();
  });
});
