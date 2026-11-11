import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { publishCognition } from '../../superbrain/lib/cognitionBus';
import { useCognitionBus } from './useCognitionBus';

// 2026-11-11: the verify toast's timers were returned from inside the bus
// callback, a cleanup the bus never calls, so they outlived an unmount. In CI
// one fired after the test environment was gone ("window is not defined").

const verify = () =>
  publishCognition({ type: 'verify', detail: 'ran', data: { verdict: 'pass', output: '' } });

describe('useCognitionBus verify toast', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows the toast, then lets it leave and go', () => {
    const { result, unmount } = renderHook(() => useCognitionBus(false));
    act(() => verify());
    expect(result.current.verifyToast?.verdict).toBe('unknown');
    act(() => vi.advanceTimersByTime(2600));
    expect(result.current.verifyToast?.leaving).toBe(true);
    act(() => vi.advanceTimersByTime(250));
    expect(result.current.verifyToast).toBeNull();
    unmount();
  });

  it('leaves no timer behind when it unmounts mid-toast', () => {
    const { unmount } = renderHook(() => useCognitionBus(false));
    act(() => verify());
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('leaves no timer behind under reduced motion either', () => {
    const { unmount } = renderHook(() => useCognitionBus(true));
    act(() => verify());
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
