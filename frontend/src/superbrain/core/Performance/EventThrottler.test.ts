import { afterEach, describe, expect, it, vi } from 'vitest';
import { EventThrottler } from './EventThrottler';

describe('EventThrottler', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('fires immediately when the limit has elapsed', () => {
    vi.spyOn(performance, 'now').mockReturnValue(100);
    const callback = vi.fn();
    const throttled = new EventThrottler(30).throttle(callback);

    throttled('first');

    expect(callback).toHaveBeenCalledExactlyOnceWith('first');
  });

  it('coalesces a burst and fires the final call at the trailing edge', () => {
    vi.useFakeTimers();
    vi.spyOn(performance, 'now').mockReturnValue(100);

    const callback = vi.fn();
    const throttled = new EventThrottler(30).throttle(callback);

    throttled('first');
    throttled('middle');
    throttled('final');

    expect(callback).toHaveBeenCalledExactlyOnceWith('first');

    vi.advanceTimersByTime(30);

    expect(callback).toHaveBeenCalledTimes(2);
    expect(callback).toHaveBeenLastCalledWith('final');
  });

  it('leaves no pending calls after the trailing edge', () => {
    vi.useFakeTimers();
    vi.spyOn(performance, 'now').mockReturnValue(100);

    const callback = vi.fn();
    const throttled = new EventThrottler(30).throttle(callback);

    throttled('first');
    throttled('middle');
    throttled('final');

    vi.advanceTimersByTime(30);
    vi.runOnlyPendingTimers();

    expect(callback).toHaveBeenCalledTimes(2);
  });

  it('fires a new call immediately after the limit and cancels a pending trailing call', () => {
    vi.useFakeTimers();
    const now = vi.spyOn(performance, 'now').mockReturnValue(100);

    const callback = vi.fn();
    const throttled = new EventThrottler(30).throttle(callback);

    throttled('first');
    now.mockReturnValue(110);
    throttled('pending');
    now.mockReturnValue(130);
    throttled('later');

    expect(callback).toHaveBeenCalledTimes(2);
    expect(callback).toHaveBeenLastCalledWith('later');

    vi.runOnlyPendingTimers();

    expect(callback).toHaveBeenCalledTimes(2);
  });
});
